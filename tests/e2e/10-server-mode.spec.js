// 10 — РАБОЧАЯ ПЛАТФОРМА: клиент v101 против ЖИВОГО бэкенда FastAPI (план, п. 3.3;
// ворота G-03: реальный IAM/JWT+MFA, bootstrap из СУБД, событийные цепочки, WORM-аудит).
// Стенд поднимает Playwright webServer (tests/run_backend.sh): свежая SQLite + детерминированный seed.
// Запуск: TC_WITH_BACKEND=1 npx playwright test --config tests/playwright.config.js --project=srv
const { test, expect } = require('@playwright/test');
const crypto = require('crypto');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '../..');
const API = process.env.TC_API || 'http://127.0.0.1:8000';
const DB = process.env.TC_DB || path.join(ROOT, 'backend', 'technocontour.db');
const PY = process.env.TC_PYTHON || 'python3';
const ADMIN = { login: 'admin', pass: 'tc-admin-2026' };
const APP = 'ais_providets_v102.html';

/* ---- TOTP (RFC 6238) на node:crypto; секрет читаем из СУБД стенда (dev-процедура) ---- */
function b32decode(s) {
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = 0, val = 0; const out = [];
  for (const c of String(s).replace(/=+$/, '').toUpperCase()) {
    const i = A.indexOf(c); if (i < 0) continue;
    val = (val << 5) | i; bits += 5;
    if (bits >= 8) { out.push((val >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  return Buffer.from(out);
}
function totp(secret) {
  const key = b32decode(secret);
  const ctr = Math.floor(Date.now() / 1000 / 30);
  const b = Buffer.alloc(8); b.writeBigUInt64BE(BigInt(ctr));
  const h = crypto.createHmac('sha1', key).update(b).digest();
  const o = h[h.length - 1] & 0xf;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, '0');
}
function adminSecret() {
  const code = 'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("select totp_secret from users where login=?",(sys.argv[2],)).fetchone()[0])';
  let lastErr = null;
  for (let i = 0; i < 60; i++) {
    try {
      return execFileSync(PY, ['-c', code, DB, ADMIN.login], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    } catch (e) {
      lastErr = e;
      const t = Date.now(); while (Date.now() - t < 1000) { /* sync sleep: стенд ещё сеет БД */ }
    }
  }
  throw lastErr;
}
async function api(method, p, { token, body } = {}) {
  const r = await fetch(API + p, {
    method,
    headers: {
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let j = null; try { j = await r.json(); } catch (e) { /* не-json ответ */ }
  return { status: r.status, json: j };
}

/* ---- Полный серверный вход через реальный UI (тумблер → URL → учётка → MFA tcPrompt) ---- */
async function serverLogin(page, { pass = ADMIN.pass, mfa } = {}) {
  await page.goto(APP);
  await page.waitForSelector('#loginBtn');
  await page.check('#srvEnabled');
  await page.fill('#srvUrl', API);
  await page.fill('#srvLogin', ADMIN.login);
  await page.fill('#srvPass', pass);
  await page.click('#loginBtn');
  if (mfa !== 'none' && mfa !== 'skip') {
    await page.waitForSelector('#tcDlgInp', { timeout: 25000 });
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'tcDlgInp', null, { timeout: 6000 });
    await page.keyboard.type(mfa || totp(adminSecret()));
    await page.keyboard.press('Enter');
  }
}
async function waitConnected(page, timeout = 30000) {
  await page.waitForFunction(() => SRV.connected === true && document.getElementById('app').style.display === 'grid', null, { timeout });
}

test.beforeEach(async () => {
  test.skip(process.env.TC_WITH_BACKEND !== '1', 'стенд бэкенда не поднят (нужен TC_WITH_BACKEND=1)');
});

test('s.1 серверный вход через UI: JWT + MFA/TOTP → роль L7 из IAM, данные из СУБД', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  expect(await page.evaluate(() => SRV.role)).toBe('L7');
  expect(await page.evaluate(() => SRV.fio)).toContain('Крылов');
  expect(await page.evaluate(() => SRV.boot && SRV.boot.modules.length)).toBe(15);
  // витрины клиента заменены реальными данными СУБД (seed: 100 организаций, 12 проектов)
  expect(await page.evaluate(() => ORGS.length)).toBe(100);
  expect(await page.evaluate(() => PROJECTS.length)).toBe(12);
  expect(await page.evaluate(() => SRV.geo && !!SRV.geo.tile_url)).toBe(true);
  await expect(page.locator('#userRoleTop')).toContainText('L7');
});

test('s.2 шина событий: клиентский опрос /core/events доставляет серверные события (SRV:)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  await page.waitForFunction(
    () => state.events.some(e => String(e.source).startsWith('SRV:')),
    null, { timeout: 25000 }); // интервал опроса 6 с
  const types = await page.evaluate(() => state.events.filter(e => String(e.source).startsWith('SRV:')).map(e => e.type));
  expect(types.length).toBeGreaterThan(0);
});

test('s.3 MOD-KPI: серверная витрина + регламентный пересчёт из СУБД через UI', async ({ page }) => {
  const posts = [];
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/api/v1/kpis/recalculate')) posts.push(r.url()); });
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('kpi', true));
  await page.waitForFunction(() => SRV.kpis && SRV.kpis.period, null, { timeout: 20000 });
  await expect(page.locator('#main')).toContainText('СЕРВЕРНЫЙ РЕЖИМ');
  const period = await page.evaluate(() => SRV.kpis.period);
  expect(String(period).length).toBeGreaterThan(3);
  await page.evaluate(() => srvKpiRecalc());
  await page.waitForFunction(() => state.audit.some(a => a.action === 'Пересчет KPI (сервер)'), null, { timeout: 20000 });
  expect(posts.length).toBeGreaterThan(0);
});

test('s.4 MOD-AI: прогнозный цикл на сервере + принятие рекомендации (rid из СУБД)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('ai', true));
  await page.evaluate(() => runAI());
  await page.waitForFunction(() => SRV.ai && SRV.ai.run_id, null, { timeout: 30000 });
  await expect(page.locator('#main')).toContainText('СЕРВЕРНАЯ модель');
  const rid = await page.evaluate(() => (SRV.ai.recommendations || []).find(r => r.status !== 'accepted')?.rid ?? SRV.ai.recommendations[0].rid);
  expect(rid).toBeTruthy();
  await page.evaluate(id => {
    const b = document.querySelector('[data-rid="' + id + '"] button');
    if (b) acceptRec(b);
  }, rid);
  // acceptRec-обёртка обновляет DOM-кнопку и аудит (SRV.ai не мутирует) — проверяем DOM+аудит
  await page.waitForFunction(
    id => {
      const box = document.querySelector('[data-rid="' + id + '"]');
      if (!box) return false;
      const btn = box.querySelector('button');
      return box.textContent.includes('Принято') || (btn && btn.disabled);
    },
    rid, { timeout: 20000 });
  await page.waitForFunction(() => state.audit.some(a => a.action === 'Принятие ИИ-рекомендации (сервер)'), null, { timeout: 10000 });
});

test('s.5 MOD-EXPERT: цепочка ИВП-1→ИВП-2 через клиент (assign → conclude → стимул + WORM-запись)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  const itemId = await page.evaluate(() => {
    const q = EXPERT_QUEUE.find(x => x.status === 'queued') || EXPERT_QUEUE[0];
    return q ? q.id : null;
  });
  expect(itemId, 'очередь экспертизы пуста').toBeTruthy();
  await page.evaluate(id => assignExpert(id), itemId);
  await page.waitForFunction(
    id => (EXPERT_QUEUE.find(x => x.id === id) || {}).status === 'in_review', itemId, { timeout: 20000 });
  const stimsBefore = await page.evaluate(() => STIMS.length);
  await page.evaluate(id => conclude(id), itemId);
  await page.waitForFunction(
    id => (EXPERT_QUEUE.find(x => x.id === id) || {}).status === 'done', itemId, { timeout: 25000 });
  // событийная цепочка: паспорт верифицирован → стимул MOD-STIM (ИВП-2, Прил. 1.6)
  await page.waitForFunction(() => state.events.some(e => e.type === 'passport.verified'), null, { timeout: 25000 });
  const stimsAfter = await page.evaluate(() => STIMS.length);
  expect(stimsAfter).toBeGreaterThan(stimsBefore);
  // WORM-аудит сервера содержит запись операции (проверяем независимым HTTP-запросом)
  const token = await page.evaluate(() => SRV.token);
  const audit = await api('GET', '/api/v1/core/audit?limit=50', { token });
  expect(audit.status).toBe(200);
  const rows = Array.isArray(audit.json) ? audit.json : (audit.json.items || []);
  expect(rows.some(r => String(r.action || '').includes('Выдача экспертного заключения'))).toBe(true);
});

test('s.6 негатив: неверный пароль → 401, MFA-диалог не открывается, вход не выполнен', async ({ page }) => {
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await serverLogin(page, { pass: 'неверный-пароль', mfa: 'none' });
  await page.waitForTimeout(3500);
  expect(await page.evaluate(() => SRV.connected)).toBe(false);
  expect(await page.evaluate(() => SRV.token === null)).toBe(true);
  await expect(page.locator('#tcDialog')).toHaveCount(0);
  await expect(page.locator('#login')).toBeVisible();
  // пароль очищен (защита сессии), сообщение об ошибке не содержит секрет
  expect(await page.inputValue('#srvPass')).toBe('');
  const bodyText = await page.evaluate(() => document.body.innerText);
  expect(bodyText).not.toContain('неверный-пароль');
  expect(errs, errs.join('|')).toEqual([]);
});

test('s.7 негатив: неверный код MFA → вход отклонён, демо-сеанс НЕ открывается автоматически', async ({ page }) => {
  await serverLogin(page, { mfa: '000000' });
  await page.waitForTimeout(4000);
  expect(await page.evaluate(() => SRV.connected)).toBe(false);
  expect(await page.evaluate(() => document.getElementById('app').style.display === 'grid')).toBe(false);
  await expect(page.locator('#login')).toBeVisible();
});

test('s.8 graceful degradation полного стека: MOD-AI off (API) → фолбэк-витрина, on → восстановление', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  // дожидаемся завершения ленивой загрузки витрин (хук enterApp), иначе in-flight
  // ответ, полученный ДО отключения модуля, перезапишет SRV.ai (гонка сценария)
  await page.waitForFunction(() => SRV._s9Stage8Loaded === true && !SRV._s9LoadInFlight, null, { timeout: 25000 });
  const token = await page.evaluate(() => SRV.token);
  expect((await api('PATCH', '/api/v1/core/modules/MOD-AI', { token, body: { enabled: false } })).status).toBe(200);
  // контроль на уровне API: модуль действительно отключён
  expect((await api('GET', '/api/v1/ai/recommendations', { token })).status).toBe(503);
  await page.evaluate(() => { SRV.ai = null; SRV._s9Stage8Loaded = false; showPage('ai', true); });
  await expect(page.locator('#main')).toContainText('Повторить загрузку', { timeout: 15000 });
  await expect(page.locator('#main')).not.toContainText('СЕРВЕРНАЯ модель');
  expect((await api('PATCH', '/api/v1/core/modules/MOD-AI', { token, body: { enabled: true } })).status).toBe(200);
  await page.evaluate(() => srvLoadStage8(true));
  await page.waitForFunction(() => SRV.ai && SRV.ai.model, null, { timeout: 25000 });
  await page.evaluate(() => showPage('ai', true));
  await expect(page.locator('#main')).toContainText('СЕРВЕРНАЯ модель');
});

test('s.9 выход: logout() → серверный POST /auth/logout + демо-режим, токен отозван (401)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  const token = await page.evaluate(() => SRV.token);
  expect(token).toBeTruthy();
  // мост Этапа 9 оборачивает logout(): POST /api/v1/auth/logout (keepalive) + srvDisconnect
  await page.evaluate(() => logout());
  await page.waitForTimeout(2500);
  expect(await page.evaluate(() => SRV.connected)).toBe(false);
  expect(await page.evaluate(() => SRV.token === null)).toBe(true);
  const after = await api('GET', '/api/v1/bootstrap', { token });
  expect(after.status, 'токен должен быть отозван на сервере (jti blacklist)').toBe(401);
});

test('s.10 RBAC сервера: админ-операция доступна L7 и отклоняется 403 для L0 (серверный контроль)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  const token = await page.evaluate(() => SRV.token);
  // L7 (admin) — пересчёт KPI разрешён
  expect((await api('POST', '/api/v1/kpis/recalculate', { token })).status).toBe(200);
  // L0 (guest) — та же операция отклоняется СЕРВЕРОМ (клиентский can() не считается контролем)
  const l0 = await api('POST', '/api/v1/auth/login', { body: { login: 'guest', password: 'tc-guest-2026' } });
  expect(l0.status, 'гостевой вход L0').toBe(200);
  const r = await api('POST', '/api/v1/kpis/recalculate', { token: l0.json.access_token });
  expect(r.status).toBe(403);
  // негатив: чужой/поддельный токен
  const bad = await api('GET', '/api/v1/bootstrap', { token: 'not-a-jwt' });
  expect(bad.status).toBe(401);
});
