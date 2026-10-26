// srv-C: деградация полного стека, серверный RBAC, персистентность паспорта (Этап 12).
const { test, expect } = require('@playwright/test');
const { api, serverLogin, waitConnected, waitPassSynced } = require('./srv-helpers');

test.beforeEach(async () => {
  test.skip(process.env.TC_WITH_BACKEND !== '1', 'стенд бэкенда не поднят (нужен TC_WITH_BACKEND=1)');
});

test('s.8 graceful degradation полного стека: MOD-AI off (API) → фолбэк-витрина, on → восстановление', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  await page.waitForFunction(() => SRV._s9Stage8Loaded === true && !SRV._s9LoadInFlight, null, { timeout: 25000 });
  const token = await page.evaluate(() => SRV.token);
  expect((await api('PATCH', '/api/v1/core/modules/MOD-AI', { token, body: { enabled: false } })).status).toBe(200);
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

test('s.10 RBAC сервера: админ-операция доступна L7 и отклоняется 403 для L0 (серверный контроль)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  const token = await page.evaluate(() => SRV.token);
  expect((await api('POST', '/api/v1/kpis/recalculate', { token })).status).toBe(200);
  const l0 = await api('POST', '/api/v1/auth/login', { body: { login: 'guest', password: 'tc-guest-2026' } });
  expect(l0.status, 'гостевой вход L0').toBe(200);
  const r = await api('POST', '/api/v1/kpis/recalculate', { token: l0.json.access_token });
  expect(r.status).toBe(403);
  const bad = await api('GET', '/api/v1/bootstrap', { token: 'not-a-jwt' });
  expect(bad.status).toBe(401);
});

test('s.11 MOD-PASS: правка паспорта через UI → версия в СУБД → данные переживают повторный вход', async ({ page }) => {
  test.setTimeout(180000);
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('pass', true));
  await waitPassSynced(page);
  await page.evaluate(() => startPassEdit(state.selEnt));
  await page.waitForSelector('.pf-in');
  const marker = 'E2E-платформа-' + Date.now();
  const info = await page.evaluate(mk => {
    const inp = Array.from(document.querySelectorAll('.pf-in')).find(i => i.tagName === 'INPUT' && !i.disabled);
    if (!inp) return null;
    inp.value = mk;
    return { s: inp.dataset.s, f: inp.dataset.f };
  }, marker);
  expect(info, 'не найдено редактируемое поле').toBeTruthy();
  await page.evaluate(() => savePassVersion(state.selEnt));
  await page.waitForFunction(
    () => Array.from(document.getElementById('toasts').children).some(t => t.textContent.includes('сохранён на сервере')),
    null, { timeout: 25000 });
  const token = await page.evaluate(() => SRV.token);
  const orgId = await page.evaluate(() => state.selEnt);
  const vers = await api('GET', `/api/v1/orgs/${orgId}/passport/versions`, { token });
  expect(vers.status).toBe(200);
  expect(Array.isArray(vers.json) && vers.json.length).toBeGreaterThan(0);
  expect(vers.json[0].changes).toBeGreaterThan(0);
  expect(String(vers.json[0].crc32)).toMatch(/^0x[0-9a-f]{8}$/);
  const pas = await api('GET', `/api/v1/orgs/${orgId}/passport`, { token });
  const flat = [];
  (pas.json.sections || []).forEach(s => (s.fields || []).forEach(f => flat.push(f)));
  expect(flat.some(f => String(f.value || '').includes('E2E-платформа-')), 'значение не сохранено в СУБД').toBe(true);
  // персистентность между сеансами: выход → вход → серверное значение в оверлее
  await page.evaluate(() => logout());
  await page.waitForTimeout(1500);
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('pass', true));
  await waitPassSynced(page);
  const found = await page.evaluate(() => Object.values(state.passOv[state.selEnt]).some(v => String(v).includes('E2E-платформа-')));
  expect(found, 'значение не пережило повторный вход').toBe(true);
});
