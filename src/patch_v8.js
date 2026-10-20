// Патч v8: вставка страницы плана, NAV, TZREF, справка, about, версии
const fs = require('fs');
let s = fs.readFileSync(__dirname + '/app.js', 'utf8');
const block = fs.readFileSync(__dirname + '/plan_block.js', 'utf8');

function rep(from, to, tag) {
  if (!s.includes(from)) { console.error('NOT FOUND: ' + tag); process.exit(1); }
  s = s.replace(from, to);
}

// 1) страница плана — перед «О СИСТЕМЕ»
rep('/* ================= О СИСТЕМЕ ================= */', block + '\n/* ================= О СИСТЕМЕ ================= */', 'plan block');

// 2) NAV: пункт плана перед roadmap
rep('   {p:"roadmap",t:"Статус и дорожная карта",',
    '   {p:"plan",t:"План разработки (36 мес.)",ic:\'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18M7 14h5M7 17h8"/></svg>\'},\n   {p:"roadmap",t:"Статус и дорожная карта",', 'nav plan');

// 3) TZREF для plan
rep(' raci:[["Прил. 4 RACI","tz-app-4"],["Прил. 4.3 Этапы","tz-a4-4-3"]],',
    ' raci:[["Прил. 4 RACI","tz-app-4"],["Прил. 4.3 Этапы","tz-a4-4-3"]],\n plan:[["п.11 Состав работ","tz-11"],["п.12 Контроль и приемка","tz-12"],["п.1.6 Сроки","tz-1-6"]],', 'tzref plan');

// 4) справка F1: записи плана
rep('  idx.push({c:"Внедрение (ТЗ п.11)",t:"Дорожная карта промышленной разработки",',
    '  idx.push({c:"Внедрение (план ред. 1.0)",t:"Поэтапный план разработки: Фазы 0–6, 36 месяцев",x:"Бюджет 300 млн ₽: инфраструктура → ядро → MVP (6 модулей) → опциональные модули → ФСТЭК 1Б → промышленное внедрение → сопровождение",go:"showPage(\'plan\')"});\n  idx.push({c:"Внедрение (план ред. 1.0)",t:"Технологический стек промышленной разработки",x:"Python 3.11+/Go + FastAPI + Celery; Kafka/Redis Streams; React 18 + TS; Postgres Pro + PostGIS; Redis; MinIO; Docker/K8s; GitLab CI; Prometheus + Grafana; ELK",go:"showPage(\'plan\')"});\n  idx.push({c:"Внедрение (ТЗ п.11)",t:"Дорожная карта промышленной разработки",', 'help plan');

// 5) about: комплект документации + план
rep('руководство по эксплуатации — файл <span class="kbd">manual_providets_v2.html</span>. Открывайте файлы',
    'руководство по эксплуатации — файл <span class="kbd">manual_providets_v2.html</span>; поэтапный план разработки (ред. 1.0, 36 месяцев) — файл <span class="kbd">plan_providets_v1.html</span>. Открывайте файлы', 'about docs');

// 6) версии
rep('Программа v7.0.0 по ТЗ версии 4.0', 'Программа v8.0.0 по ТЗ версии 4.0', 'tour ver');
rep("'ТЗ версия 4.0 · программа v7.0.0 · 13 задач", "'ТЗ версия 4.0 · программа v8.0.0 · 13 задач", 'about mchip');
rep("программа v6.0.0 | '", "программа v8.0.0 | '", 'about footer');

// 7) история версий: строка v8
rep('   [["v7.0.0","14.10.2026",',
    '   [["v8.0.0","14.10.2026","Поэтапный план разработки (ред. 1.0) в программе и отдельным документом plan_providets_v1.html: интерактивная диаграмма Ганта (Фазы 0–6, 36 мес.), чек-листы задач с прогрессом и фиксацией в аудите, бюджет 300 млн ₽, риски плана; стартовые артефакты Фазы 0/1 — backend_scaffold_v1 (docker-compose, OpenAPI 3.0, AsyncAPI, SQL-схема Postgres Pro с 92 полями паспорта, каркас ядра FastAPI, ADR-001)"],\n    ["v7.0.0","14.10.2026",', 'history v8');

fs.writeFileSync(__dirname + '/app.js', s);
console.log('v8 patch applied');
