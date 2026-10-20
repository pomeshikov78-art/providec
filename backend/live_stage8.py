import httpx, json, os, sys
B = "http://127.0.0.1:8000/api/v1"
BACKEND = os.path.dirname(os.path.abspath(__file__))

def login(l, p, mfa=None):
    b = {"login": l, "password": p}
    if mfa: b["mfa_code"] = mfa
    r = httpx.post(B + "/auth/login", json=b).json()
    return {"Authorization": "Bearer " + r["access_token"]}, r

h5, _ = login("analyst", "tc-analyst-2026")
h2, _ = login("regulator", "tc-reg-2026")
h0, _ = login("guest", "tc-guest-2026")
import pyotp, sqlite3
con = sqlite3.connect(os.path.join(BACKEND, "technocontour.db"))
sec = con.execute("select totp_secret from users where login='admin'").fetchone()[0]
h7, _ = login("admin", "tc-admin-2026", pyotp.TOTP(sec).now())

print("1) KPI:", end=" ")
k = httpx.get(B + "/kpis", headers=h0).json()
print(k["period"], "·", len(k["items"]), "показателей · hist KPI-1:", len(k["items"][0]["hist"]), "· KPI-1 cur:", k["items"][0]["cur"])

print("2) Пересчёт KPI (L2):", end=" ")
r = httpx.post(B + "/kpis/recalculate", headers=h2).json()
print("отклонений:", [b["code"] for b in r["breached"]],
      "· KPI-1:", [i["cur"] for i in r["items"] if i["code"] == "KPI-1"][0],
      "· KPI-3:", [i["cur"] for i in r["items"] if i["code"] == "KPI-3"][0],
      "· KPI-7:", [i["cur"] for i in r["items"] if i["code"] == "KPI-7"][0])

print("3) Авто-санкция эскалации (MOD-STIM):", end=" ")
s = httpx.get(B + "/stims", headers=h0).json()
esc = [x for x in s["items"] if "kpi.threshold_breached" in (x["base"] or "")]
print(len(esc), "создано ·", esc[0]["t"] if esc else "—", "· всего мер:", s["total"])

print("4) RBAC guest:", end=" ")
codes = [httpx.post(B + "/kpis/recalculate", headers=h0).status_code,
         httpx.post(B + "/stims", headers=h0, json={"kind": "stim", "title": "X"}).status_code,
         httpx.post(B + "/ai/run", headers=h0).status_code,
         httpx.post(B + "/expert/V02/assign", headers=h0).status_code]
print(codes, "(ожидаем 403×4)")

print("5) Экспертиза V03 (E11, арбитраж):", end=" ")
a = httpx.post(B + "/expert/V03/assign", headers=h5).json()
c = httpx.post(B + "/expert/V03/conclude", headers=h5, json={"verdict": "Расхождение ЕГРЮЛ устранено"}).json()
org = httpx.get(B + "/orgs/E11", headers=h0).json()
print("эксперт:", a["expert"], "· org_verified:", c["org_verified"], "· E11 status:", org["status"])

print("6) Цепочка: заключение в MOD-DOC + стимул:", end=" ")
d = httpx.get(B + "/documents", headers=h0).json()
v03 = [x for x in d["items"] if "V03" in x["t"]]
st = httpx.get(B + "/stims", headers=h0).json()
e11s = [x for x in st["items"] if "passport.verified · E11" in (x["base"] or "")]
print("документ:", v03[0]["id"] if v03 else "НЕТ", v03[0]["sign"] if v03 else "",
      "· подпись:", (v03[0]["signature"] or "")[:22] if v03 else "",
      "· стимул:", e11s[0]["t"][:40] if e11s else "НЕТ")

print("7) Двойник E11 пересобран:", end=" ")
ev = httpx.get(B + "/core/events?type=twin.rebuilt&limit=30", headers=h7).json()
print("да" if any("E11" in e["payload"] for e in ev) else "НЕТ")

print("8) AI-цикл (L2):", end=" ")
run = httpx.post(B + "/ai/run", headers=h2).json()
print(run["run_id"], "· модель", run["model"], "· tech-gap:", len(run["tech_gaps"]["gaps"]),
      "· риски:", len(run["fail_risk"]), "· рек:", len(run["recommendations"]))
print("   топ-риск:", run["fail_risk"][0]["id"], run["fail_risk"][0]["risk"],
      "% · просрочка", run["fail_risk"][0]["factors"]["overdue_days"], "дн")
for x in run["recommendations"][:3]:
    print("   →", x["m"], int(x["conf"] * 100), "%:", x["t"][:80])
lat = httpx.get(B + "/ai/recommendations", headers=h0).json()
rid = lat["recommendations"][0]["rid"]
ac = httpx.post(B + f"/ai/recommendations/{rid}/accept", headers=h2)
print("   принятие rid", rid, "→", ac.json()["status"])

print("9) DOC: поток подписания:", end=" ")
doc = httpx.post(B + "/documents", headers=h2,
                 json={"title": "Справка (live-проверка этапа 8)", "org_id": "E14", "kind": "Справка"}).json()
s1 = httpx.post(B + f"/documents/{doc['id']}/sign", headers=h2).json()
s2 = httpx.post(B + f"/documents/{doc['id']}/sign", headers=h2).json()
s3 = httpx.post(B + f"/documents/{doc['id']}/sign", headers=h2).json()
s4 = httpx.post(B + f"/documents/{doc['id']}/sign", headers=h2)
print(doc["id"], "→", s1["sign"], "→", s2["sign"], "→", s3["sign"],
      "→ terminal:", s4.status_code, "· sig:", (s2["signature"] or "")[:18])

print("10) SLA ИВП-1:", end=" ")
sla = httpx.get(B + "/expert/sla", headers=h7).json()
print("нарушений:", len(sla["breached"]), sla["breached"])

print("11) Graceful degradation MOD-AI:", end=" ")
off = httpx.patch(B + "/core/modules/MOD-AI", headers=h7, json={"enabled": False})
g = httpx.get(B + "/ai/forecast", headers=h7)
on = httpx.patch(B + "/core/modules/MOD-AI", headers=h7, json={"enabled": True})
g2 = httpx.get(B + "/ai/forecast", headers=h7)
print("off:", off.status_code, "→ /ai/forecast:", g.status_code, "· on:", on.status_code, "→", g2.status_code)

print("12) Аудит-цепочка + метрики:", end=" ")
v = httpx.get(B + "/core/audit/verify", headers=h7).json()
m = httpx.get("http://127.0.0.1:8000/metrics").text
print("audit ok:", v["ok"], "· checked:", v.get("checked"),
      "· tc_events_total:", [l.split()[-1] for l in m.splitlines() if l.startswith("tc_events_total")])
