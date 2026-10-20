"""Этап 3: бизнес-логика модулей — EVM/PERT, Go/No-Go, кооперация, риски, реальные отчёты."""
import io
import time
import zipfile


def test_evm_formula(client, admin_headers):
    """Эталон по seed-данным прототипа v8: P01 (E03, стадия 4, review, бюджет 1.9, riskIdx 31):
    PV=1.9·5/9=1.06 · EV=1.9·4/9=0.84 · AC=EV·(0.92+31/400)=0.84 · SPI=0.79 · CPI=1.0."""
    r = client.get("/api/v1/niokr/projects/P01", headers=admin_headers)
    assert r.status_code == 200
    e = r.json()["evm"]
    assert (e["pv"], e["ev"], e["ac"], e["spi"], e["cpi"]) == (1.06, 0.84, 0.84, 0.79, 1.0)
    assert e["spi_status"] == "отставание"


def test_pert(client, admin_headers):
    p = client.get("/api/v1/niokr/projects/P01", headers=admin_headers).json()
    pt = p["pert"]
    assert pt["te"] == round((30 + 4 * 50 + 90) / 6, 1) == 53.3
    assert pt["sd"] == round((90 - 30) / 6, 1) == 10.0
    assert 0 <= pt["probability"] <= 100


def test_portfolio_summary(client, admin_headers):
    r = client.get("/api/v1/niokr/portfolio/summary", headers=admin_headers).json()
    assert r["total_projects"] == 12
    assert len(r["by_stage"]) == 9 and sum(r["by_stage"]) == 12
    assert r["worst"]["project"] == "P03"      # антирейтинг SPI (P03 = 0.67)


def test_gate_go_no_go_workflow(client, admin_headers):
    before = client.get("/api/v1/niokr/projects/P03", headers=admin_headers).json()
    st = before["stage"]
    # GO → стадия +1, событие niokr.gate_decision, EVM-снимок зафиксирован
    r = client.post("/api/v1/niokr/projects/P03/gates", json={"decision": "go", "comment": "тест этапа 3"},
                    headers=admin_headers)
    assert r.status_code == 200 and r.json()["stage"] == st + 1
    ev = client.get("/api/v1/core/events?type=niokr.gate_decision", headers=admin_headers).json()
    assert any("P03" in e["payload"] and "GO" in e["payload"] for e in ev)
    snap = client.get("/api/v1/niokr/projects/P03", headers=admin_headers).json()["evm_history"]
    assert len(snap) >= 1
    # NO-GO → откат стадии, alert-событие
    r = client.post("/api/v1/niokr/projects/P03/gates", json={"decision": "no-go"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["stage"] == st
    ev = client.get("/api/v1/core/events?type=niokr.gate_decision", headers=admin_headers).json()
    assert any("NO-GO" in e["payload"] for e in ev)
    assert ev[0]["sev"] == "alert"
    # append-only журнал решений
    gates = client.get("/api/v1/niokr/projects/P03", headers=admin_headers).json()["gates"]
    assert len(gates) >= 2 and gates[0]["decision"] == "no-go"


def test_gate_rbac(client, l0_headers, l4_headers):
    r = client.post("/api/v1/niokr/projects/P01/gates", json={"decision": "go"}, headers=l0_headers)
    assert r.status_code == 403
    r = client.post("/api/v1/niokr/projects/P01/gates", json={"decision": "go"}, headers=l4_headers)
    assert r.status_code == 403


def test_coop_scoring(client, admin_headers):
    r = client.get("/api/v1/coop/E14/partners?top=5", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["weights"] == {"comp": 0.45, "geo": 0.20, "stage": 0.20, "inv": 0.15}
    items = d["items"]
    assert len(items) == 5
    assert all(items[i]["total"] >= items[i + 1]["total"] for i in range(4))  # сортировка по убыванию
    assert all(0 <= it["total"] <= 100 for it in items)


def test_risks_matrix(client, admin_headers):
    d = client.get("/api/v1/risks", headers=admin_headers).json()
    assert d["total"] == 12
    assert len(d["matrix5x5"]) == 5
    assert sum(sum(row) for row in d["matrix5x5"]) == 12
    assert d["top3"][0]["score"] == 20          # R01: 4×5 (данные прототипа v8)


def test_report_xlsx_real_file(client, admin_headers):
    t0 = time.monotonic()
    r = client.get("/api/v1/reports/registry.xlsx", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))          # валидный OOXML-контейнер
    assert "[Content_Types].xml" in z.namelist() and "xl/workbook.xml" in z.namelist()
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    assert ws.max_row >= 104                             # заголовок + 100 организаций
    assert ws["A5"].value == "E01"
    assert time.monotonic() - t0 <= 5.0                  # норматив ТЗ ≤ 5 c


def test_report_docx_passport(client, admin_headers):
    r = client.get("/api/v1/reports/passport/E01.docx", headers=admin_headers)
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert "word/document.xml" in z.namelist()
    xml = z.read("word/document.xml").decode("utf-8")
    assert "Идентификационные сведения" in xml           # 12 разделов Прил. 2 внутри файла
    assert "Документальная доказательность" in xml   # раздел 12 Прил. 2


def test_report_pdf_portfolio(client, admin_headers):
    t0 = time.monotonic()
    r = client.get("/api/v1/reports/portfolio.pdf", headers=admin_headers)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000
    assert time.monotonic() - t0 <= 5.0


def test_report_events_and_audit(client, admin_headers):
    ev = client.get("/api/v1/core/events?type=report.generated", headers=admin_headers).json()
    assert len(ev) >= 3
    a = client.get("/api/v1/core/audit", headers=admin_headers).json()
    assert any("Формирование отчета" in x["action"] for x in a)
