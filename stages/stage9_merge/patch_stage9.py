#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЭТАП 9 — объединение веток разработки клиента.
Вход : src9/base.html (загруженная ветка v99 = клиент v82+патчи, P0.1–P0.59)
Выход: /home/user/ais_providets.html (объединённая программа v100.0.0)

Операции:
 1. РЕКОНСТРУКЦИЯ истории версий в RENDERERS.about: в base.html блок записей истории
    (строки вида ["vN.0.0","дата","текст"], между '<tbody>'+ и '.map(([v,d,c])') из-за
    ошибки запятых образует цепочку comma-операторов — страница «О системе» фактически
    возвращала только «хвост». Блок заменяется единым корректным массивом, записи
    сортируются по убыванию номера (устойчиво), добавляется запись v100.0.0.
 2. УНИФИКАЦИЯ версионных метаданных: v82.0.0 (кроме записей истории), v49.0.0 (футер),
    74.0.0 (примечание входа), v12.0.0 (тур), v37.0.0 (план фаз), _v81 (имена экспортов)
    → v100.0.0 / _v100.
 3. ДОБАВЛЕНИЕ серверного моста Этапа 8 (src9/bridge_stage9.js) отдельным <script> перед
    </body> — по образцу патч-IIFE закалённой ветки.
 4. Контрольные утверждения (assertions) после каждой операции.
"""
import re, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.html")
BRIDGE = os.path.join(HERE, "bridge_stage9.js")
OUT = os.path.join(os.path.dirname(HERE), "ais_providets.html")

V100_ENTRY = ("v100.0.0", "18.10.2026",
 "Этап 9 — объединение двух веток разработки и устранение критического дефекта: "
 "(1) к закалённой клиентской ветке (v13–v82, работы P0.1–P0.59: XSS/URL-валидация, лимиты ответов API, эпохи сессии, "
 "атомарный bootstrap, снимки данных с CRC32 и самодиагностикой, Air-Gap-политика, SBOM-реестр, контрольные ворота выпуска) "
 "подключён серверный мост Этапа 8 — MOD-KPI (регламентный пересчёт из СУБД, телеметрия KPI-2/4/5/8, kpi.threshold_breached → "
 "авто-санкция MOD-STIM по Прил. 1.6), MOD-EXPERT (детерминированное назначение экспертов, заключения с серверной цепочкой "
 "ИВП-1→ИВП-2: арбитраж → паспорт верифицирован → стимул → цифровой двойник, SLA ≤ 8 ч), MOD-DOC (неизменяемый поток "
 "Проект → На подписании → Подписан (ЭЦП) → Утверждён, серверная карточка и аудит), MOD-AI (детерминированная модель v4.0-srv: "
 "tech-gap к порогу суверенитета 75 %, риск срыва контрольных точек, 6 правил рекомендаций, публикация при confidence ≥ 0.7), "
 "MOD-STIM (каталог мер, автоприменение по событиям шины); мост активен только в серверном режиме, демо-режим не изменён, "
 "все запросы проходят через закалённый srvApi (валидация адреса, лимит размера ответа, эпоха сессии, таймаут 30 с); "
 "(2) исправлен критический дефект страницы «О системе»: malformed-структура массива истории версий приводила к тому, что "
 "comma-оператор отбрасывал всё содержимое страницы до истории, а записи v49–v82 не отображались — история реконструирована "
 "единым массивом с сортировкой от новых к старым; "
 "(2b) исправлены пять дефектов встроенной самодиагностики закалённой ветки: очистка диагностического текста не срабатывала "
 "для JSON-ключей в кавычках (api_key, session_id — секрет попадал в отчёты); регекс негативного теста самоссылки организации "
 "не совпадал с фактическим сообщением валидатора; проверка сводного P0-пакета вызывала асинхронный сборщик синхронно "
 "(выделен синхронный buildP0EvidenceBundleCore); цифровой двойник для негативных тестов снимков отсутствовал до первого "
 "открытия MOD-PASS/MOD-PROF — добавлена стартовая сборка двойника E03 (организации, не затрагиваемой негативными тестами); "
 "негативные тесты ID организаций не учитывали двойники — копия снимка в тесте теперь исключает двойник переименованной организации (изоляция проверяемого валидатора); "
 "(3) унифицированы версионные метаданные (экран входа, примечание прототипа, «О системе», футер, тур оператора, план Фаз 0–6, "
 "SBOM, диагностические отчёты и имена JSON-экспортов _v100) — устранён разнобой v82/74/49/37/12; "
 "(4) проверки: бэкенд — 80 серверных тестов (pytest, Этапы 1–8), клиент — встроенные smoke-тесты 20 + объединённый набор "
 "DOM-тестов Этапа 9, live-сценарий 12 проверок (uvicorn + HTTP-цепочки Этапа 8)")

def main():
    src = open(BASE, encoding="utf-8").read()
    lines = src.split("\n")

    # ---------- 1. реконструкция истории версий ----------
    i_title = next(i for i, l in enumerate(lines) if "История версий программы</div>" in l)
    i_thead = i_title + 1
    assert "<tbody>'+" in lines[i_thead], "ожидалась строка <tbody>'+ после заголовка истории"
    i_map = next(i for i in range(i_thead + 1, len(lines)) if lines[i].lstrip().startswith(".map(([v,d,c])"))
    region = "\n".join(lines[i_thead + 1:i_map])

    entry_re = re.compile(r'\[\s*"(v\d+\.\d+\.\d+)"\s*,\s*"(\d{2}\.\d{2}\.\d{4})"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]')
    found = entry_re.findall(region)
    # контроль полноты разбора: весь текст региона должен состоять из записей, запятых и скобок
    residue = entry_re.sub("", region)
    residue_clean = re.sub(r'[\s,\[\]]+', "", residue)
    assert residue_clean == "", "в регионе истории остался неразобранный текст: %r" % residue_clean[:200]
    print("· записей истории разобрано:", len(found))
    versions = [v for v, _, _ in found]
    assert "v82.0.0" in versions and "v49.0.0" in versions and "v1.0.0" in versions, "потеряны ключевые записи"

    entries = [(int(v[1:].split(".")[0]), v, d, t) for v, d, t in found]
    # дедупликация точных дублей (версия+текст), порядок сохранения — исходный
    seen, uniq = set(), []
    for e in entries:
        key = (e[1], e[3])
        if key in seen:
            print("  · дубль пропущен:", e[1], e[3][:40]); continue
        seen.add(key); uniq.append(e)
    uniq.sort(key=lambda e: -e[0])  # устойчивая сортировка по убыванию мажорной версии
    v100 = (100, V100_ENTRY[0], V100_ENTRY[1], V100_ENTRY[2])
    assert '"' not in v100[3] and "\\" not in v100[3], "текст записи v100 не должен содержать кавычек/бэкслешей"
    all_entries = [v100] + uniq

    body_lines = []
    for idx, (_, v, d, t) in enumerate(all_entries):
        comma = "," if idx < len(all_entries) - 1 else ""
        body_lines.append('    ["%s","%s","%s"]%s' % (v, d, t, comma))
    new_region = "   [\n" + "\n".join(body_lines) + "\n   ]"
    lines[i_thead + 1:i_map] = new_region.split("\n")
    src = "\n".join(lines)
    print("· история реконструирована: %d записей (v100 → v1), регион строк %d–%d заменён" % (len(all_entries), i_thead + 2, i_map))

    # контроль: массив истории теперь один и корректен — между '<tbody>'+ и '.map(([v,d,c])' ровно '[ ... ]'
    m = re.search(r"<tbody>'\+\n(   \[\n.*?\n   \])\n(\s*\.map\(\(\[v,d,c\]\))", src, re.S)
    assert m, "реконструированный блок истории не найден/некорректен"
    assert m.group(1).count("[\"v") == len(all_entries), "число записей в блоке не совпало"

    # ---------- 2. унификация версионных метаданных ----------
    def sub_assert(pattern, repl, expect_min=1, flags=0, note=""):
        nonlocal src
        new, n = re.subn(pattern, repl, src, flags=flags)
        assert n >= expect_min, "замена не выполнена (%s): %r" % (note or pattern, n)
        src = new
        print("· замен %d: %s" % (n, note or pattern))

    # v82.0.0 везде, кроме записей истории (они имеют вид "v82.0.0","17.10.2026")
    sub_assert(r'v82\.0\.0(?!","17\.10\.2026")', "v100.0.0", 20, note="v82.0.0 → v100.0.0 (кроме истории)")
    sub_assert(r'программа v49\.0\.0', "программа v100.0.0", 1, note="футер v49 → v100")
    sub_assert(r'версии 74\.0\.0', "версии 100.0.0", 1, note="примечание входа 74 → 100")
    sub_assert(r"includes\('74\.0\.0'\)", "includes('100.0.0')", 1, note="REL-VER-01: нота")
    sub_assert(r'_v81\.json', "_v100.json", 10, note="имена экспортов _v81 → _v100")
    sub_assert(r'Программа v12\.0\.0 по ТЗ', "Программа v100.0.0 по ТЗ", 1, note="тур оператора")
    sub_assert(r'прототип v37\.0\.0', "прототип v100.0.0", 1, note="план Фаз 0–6 (hint)")
    sub_assert(r'([Пп])рототип v7\.0\.0', r"\1рототип v100.0.0", 2, note="план: mchip и footer v7 → v100")

    # финальный скан: вне блока истории не осталось старых «текущих» версий
    # (v52.0.0 — контрольное отрицание в REL-VER-01; v3.7.5 — версия демо-модели MOD-AI, не версия программы)
    hist_block = m.group(1)
    outside = src.replace(hist_block, "")
    stale = sorted(set(re.findall(r'v\d+\.\d+\.\d+', outside)) - {"v100.0.0", "v52.0.0", "v3.7.5"})
    assert not stale, "вне истории остались литералы версий: %s" % stale
    print("· скан чист: вне истории только v100.0.0 (+v52.0.0 в REL-VER-01, +v3.7.5 демо-модель AI)")

    # ---------- 3. исправление четырёх дефектов встроенной самодиагностики ветки P0 ----------
    # D-1: sanitizeDiagnosticText не скрывал секреты у JSON-ключей в кавычках ("api_key":"…")
    sub_assert(r'private\[_-\]\?key\)\\s\*\[:=\]\\s\*\)', r'private[_-]?key)"?\\s*[:=]\\s*)', 1,
               note="D-1: sanitizer — кавычка после JSON-ключа")
    src_check = re.search(r'private\[_-\]\?key\)"\?\\s\*', src)
    assert src_check, "D-1 не применён"

    # D-2: регекс негативного теста самоссылки не совпадал с сообщением валидатора
    sub_assert(r'rejected=/ссылку организации на саму себя/\.test',
               r'rejected=/ссылк[уа] организации на саму себя/.test', 1,
               note="D-2: тест самоссылки — регекс под сообщение валидатора")

    # D-3: синхронная проверка P0-пакета вызывала async-сборщик → выделен синхронный core
    old_head = 'async function buildP0EvidenceBundle(){\n  const report='
    assert src.count(old_head) == 1, "D-3: не найдена шапка buildP0EvidenceBundle"
    src = src.replace(old_head, 'function buildP0EvidenceBundleCore(){\n  const report=')
    i = src.index('function buildP0EvidenceBundleCore(){')
    j = src.index('\n  try{', i)
    src = (src[:j] + '\n  return report;\n}\n'
           'async function buildP0EvidenceBundle(){\n'
           '  const report=buildP0EvidenceBundleCore();' + src[j:])
    sub_assert(r'const b=buildP0EvidenceBundle\(\);', 'const b=buildP0EvidenceBundleCore();', 1,
               note="D-3: самопроверка вызывает синхронный core")
    # (в записи истории v100 функция тоже упомянута — контролируем именно кодовые вхождения)
    for pat in ('function buildP0EvidenceBundleCore(){',
                'const report=buildP0EvidenceBundleCore();',
                'const b=buildP0EvidenceBundleCore();'):
        assert src.count(pat) == 1, "D-3: шаблон не найден/дублируется: " + pat

    # D-5: негативные тесты ID организаций не учитывали цифровые двойники —
    # переименование организации оставляло «сиротский» двойник, и тест падал
    # на валидаторе двойников вместо проверяемого валидатора ID. Мутация
    # двойника следует за мутацией организации.
    sub_assert(r'x\.data\.ORGS\[0\]\.id="ORG_WITH_BAD_PREFIX";const y=reseal\(x\);',
               'const s9OldId=x.data.ORGS[0].id;x.data.ORGS[0].id="ORG_WITH_BAD_PREFIX";'
               'if(x.data.twin)delete x.data.twin[s9OldId];const y=reseal(x);', 1,
               note="D-5a: тест формата ID — двойник переименованной организации исключён из копии")
    sub_assert(r'x\.data\.ORGS\[1\]\.id=x\.data\.ORGS\[0\]\.id;const y=reseal\(x\);',
               'const s9OldId1=x.data.ORGS[1].id;x.data.ORGS[1].id=x.data.ORGS[0].id;'
               'if(x.data.twin)delete x.data.twin[s9OldId1];const y=reseal(x);', 1,
               note="D-5b: тест дубля ID — двойник переименованной организации исключён из копии")

    # ---------- 4. мост Этапа 8 ----------
    bridge = open(BRIDGE, encoding="utf-8").read()
    assert "</body>" in src
    twin_seed = ("<script>\n"
        "/* ===== ЭТАП 9 (D-4): стартовый цифровой двойник E03 — самодиагностика снимков (P0.46) требует\n"
        "   ≥ 1 двойника для негативных тестов валидации; ранее state.twin пустовал до первого открытия\n"
        "   страниц MOD-PASS/MOD-PROF, из-за чего два встроенных теста падали на «свежем» сеансе. ===== */\n"
        "(function seedDemoTwinStage9(){\n"
        "  try{if(typeof buildTwin===\"function\"&&typeof state===\"object\"&&state.twin&&Object.keys(state.twin).length===0&&typeof orgById===\"function\"&&orgById(\"E03\"))buildTwin(\"E03\",true);}catch(e){}\n"
        "})();\n"
        "</script>\n")
    block = (twin_seed +
        "<script>\n/* ===== ЭТАП 9: серверный мост модулей Этапа 8 (KPI/STIM/DOC/EXPERT/AI) — "
        "объединение веток, версия v100.0.0 ===== */\n" + bridge + "\n</script>\n</body>")
    src = src.replace("</body>", block, 1)
    assert src.count("__TC_STAGE9_BRIDGE") >= 2

    open(OUT, "w", encoding="utf-8").write(src)
    print("· итог записан:", OUT, len(src.encode("utf-8")), "байт")

if __name__ == "__main__":
    main()
