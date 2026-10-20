"""MOD-REPORT: генерация реальных файлов DOCX / XLSX / PDF на сервере.

Инструменты: python-docx (ООXML Word), openpyxl (ООXML Excel), reportlab (PDF,
шрифт Vera с кириллицей; в production варианта Б — сертифицированный генератор
из реестра российского ПО, точка замены изолирована в данном модуле).
Норматив ТЗ (Задача 8.5): время генерации отчёта ≤ 5 с — контролируется тестами.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Dict, List

# ---------------------------------------------------------------- XLSX
def build_orgs_xlsx(rows: List[dict], title: str = "Реестр организаций") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Реестр"
    head = ["Код", "Наименование", "Тип", "Город", "ФО", "ИНН", "TRL", "MRL", "IRL",
            "Индекс зрелости", "Полнота паспорта, %", "Статус", "Стадия ЖЦ", "Инвестиции, млрд ₽"]
    ws.append([f"АИС «Техноконтур» — {title}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · источник: БД системы (Postgres Pro/SQLite dev)"])
    ws.append([])
    ws.append(head)
    fill = PatternFill("solid", fgColor="1F4E79")
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for r in rows:
        ws.append([r.get("id"), r.get("name"), r.get("type"), r.get("city"), r.get("reg"),
                   r.get("inn"), r.get("trl"), r.get("mrl"), r.get("irl"), r.get("index_i"),
                   r.get("fill_total"), r.get("status"), r.get("stage"), r.get("rev")])
    widths = [8, 46, 8, 18, 16, 12, 6, 6, 6, 12, 12, 12, 8, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = w
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:N{4 + len(rows)}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_evm_xlsx(projects: List[dict], agg: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "EVM портфеля"
    ws.append(["АИС «Техноконтур» — Освоенный объем (EVM) портфеля НИОКР"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    ws.append([])
    ws.append(["Проект", "Организация", "Стадия", "Бюджет, млрд ₽", "PV", "EV", "AC", "SPI", "CPI",
               "Статус SPI", "PERT: te, дней", "σ", "P(уложиться), %"])
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79")
    for p in projects:
        e = p.get("evm") or {}
        pt = p.get("pert") or {}
        ws.append([p.get("id"), p.get("org"), p.get("stage_name"), p.get("budget"),
                   e.get("pv"), e.get("ev"), e.get("ac"), e.get("spi"), e.get("cpi"),
                   e.get("spi_status"), pt.get("te"), pt.get("sd"), pt.get("probability")])
    ws.append([])
    ws.append(["ИТОГО по портфелю", None, None, None, agg.get("totals", {}).get("pv"),
               agg.get("totals", {}).get("ev"), agg.get("totals", {}).get("ac"),
               agg.get("spi"), agg.get("cpi")])
    ws[f"A{ws.max_row}"].font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- DOCX
def build_passport_docx(org: dict, passport: dict) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    h = doc.add_heading(f'Цифровой паспорт организации', level=0)
    doc.add_paragraph(f'{org.get("name")} ({org.get("id")})')
    doc.add_paragraph(f'АИС «Техноконтур» (шифр «Провидец») · структура паспорта — Приложение 2 к ТЗ · '
                      f'сформирован {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    p = doc.add_paragraph()
    run = p.add_run(f'Статус: {passport.get("status")} · Полнота: {passport.get("fill_total")}% · '
                    f'Версия: {("ред. " + str(passport["version"]["n"]) + ", CRC32 " + passport["version"]["crc32"]) if passport.get("version") else "исходная"}')
    run.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    for s in passport.get("sections", []):
        doc.add_heading(f'Раздел {s["n"]}. {s["name"]} — полнота {s["fill"]} % (порог {s["threshold"]} %)', level=1)
        t = doc.add_table(rows=1, cols=4)
        t.style = "Light Grid Accent 1"
        hdr = t.rows[0].cells
        for i, name in enumerate(["#", "Поле", "Тип", "Значение"]):
            hdr[i].text = name
            hdr[i].paragraphs[0].runs[0].bold = True
        for i, f in enumerate(s.get("fields", []), start=1):
            row = t.add_row().cells
            row[0].text = str(i)
            row[1].text = f["name"] + (" *" if f["required"] else "")
            row[2].text = f["ftype"]
            row[3].text = f["value"] or "— не заполнено —"
    doc.add_paragraph("* — обязательное поле (Приложение 2 к ТЗ). Значения получены из БД системы; "
                      "источники раздела 1 — ЕГРЮЛ/ГИСП (MOD-INT).")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- PDF
_FONT_REG = None
_FONT_BD = None


def _pdf_fonts():
    global _FONT_REG, _FONT_BD
    if _FONT_REG:
        return _FONT_REG, _FONT_BD
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fp = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    pdfmetrics.registerFont(TTFont("Vera", os.path.join(fp, "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("VeraBd", os.path.join(fp, "VeraBd.ttf")))
    _FONT_REG, _FONT_BD = "Vera", "VeraBd"
    return _FONT_REG, _FONT_BD


def build_portfolio_pdf(agg: dict, projects: List[dict], risks: List[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)
    freg, fbd = _pdf_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=30, rightMargin=30,
                            topMargin=30, bottomMargin=30,
                            title="Портфель НИОКР — АИС «Техноконтур»")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName=fbd, fontSize=16)
    body = ParagraphStyle("body", parent=ss["Normal"], fontName=freg, fontSize=9)
    story = [Paragraph("АИС «Техноконтур» — Сводный отчёт по портфелю НИОКР (ИВП-6)", h1),
             Paragraph(f"Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
                       f"данные: БД системы · EVM/PERT рассчитаны сервером (MOD-NIOKR)", body),
             Spacer(1, 10),
             Paragraph(f"Портфель: проектов {agg.get('total_projects', len(projects))} · "
                       f"SPI {agg.get('spi')} · CPI {agg.get('cpi')} · "
                       f"антирейтинг: {agg.get('worst', {}).get('project', '—')} "
                       f"(SPI {agg.get('worst', {}).get('spi')})", body),
             Spacer(1, 6)]
    data = [["Проект", "Организация", "Стадия", "Бюджет", "PV", "EV", "AC", "SPI", "CPI", "P(срок), %"]]
    for p in projects:
        e = p.get("evm") or {}
        pt = p.get("pert") or {}
        data.append([p.get("id", ""), p.get("org", ""), str(p.get("stage", "")), str(p.get("budget", "")),
                     str(e.get("pv", "")), str(e.get("ev", "")), str(e.get("ac", "")),
                     str(e.get("spi", "")), str(e.get("cpi", "")), str(pt.get("probability", ""))])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), fbd), ("FONTNAME", (0, 1), (-1, -1), freg),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CB3C9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F7FB")]),
    ]))
    story += [t, Spacer(1, 12), Paragraph("Реестр рисков (MOD-RISK)", ParagraphStyle("h2", parent=ss["Heading2"], fontName=fbd))]
    rdata = [["ID", "Категория", "Риск", "P", "I", "Ранг", "Статус"]]
    for r in sorted(risks, key=lambda x: -(x.get("p", 0) * x.get("i", 0))):
        rdata.append([r.get("id", ""), r.get("cat", ""), (r.get("t", "") or "")[:60],
                      str(r.get("p", "")), str(r.get("i", "")),
                      str(r.get("p", 0) * r.get("i", 0)), r.get("st", "")])
    t2 = Table(rdata, repeatRows=1)
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), fbd), ("FONTNAME", (0, 1), (-1, -1), freg),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7B2D26")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9A79C")),
    ]))
    story.append(t2)
    doc.build(story)
    return buf.getvalue()
