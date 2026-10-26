// srv-B: шина событий и серверные модули (KPI/AI/EXPERT) против живой СУБД.
const { test, expect } = require('@playwright/test');
const { api, serverLogin, waitConnected } = require('./srv-helpers');

test.beforeEach(async () => {
  test.skip(process.env.TC_WITH_BACKEND !== '1', 'стенд бэкенда не поднят (нужен TC_WITH_BACKEND=1)');
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
  await page.waitForFunction(() => state.events.some(e => e.type === 'passport.verified'), null, { timeout: 25000 });
  const stimsAfter = await page.evaluate(() => STIMS.length);
  expect(stimsAfter).toBeGreaterThan(stimsBefore);
  const token = await page.evaluate(() => SRV.token);
  const audit = await api('GET', '/api/v1/core/audit?limit=50', { token });
  expect(audit.status).toBe(200);
  const rows = Array.isArray(audit.json) ? audit.json : (audit.json.items || []);
  expect(rows.some(r => String(r.action || '').includes('Выдача экспертного заключения'))).toBe(true);
});
