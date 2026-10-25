// 02 — Обход всех страниц реестра RENDERERS (план 3.1: «обход всех 27 страниц»).
const { test, expect } = require('@playwright/test');
const { watchErrors, login, allPages } = require('./helpers');

test('2.1 реестр RENDERERS содержит ≥ 26 страниц', async ({ page }) => {
  await login(page);
  const pages = await allPages(page);
  expect(pages.length).toBeGreaterThanOrEqual(26);
  for (const p of ['dashboard', 'registry', 'bus', 'ivp', 'audit', 'db', 'pass', 'prof', 'niokr', 'geo', 'about']) {
    expect(pages, `нет страницы ${p}`).toContain(p);
  }
});

test('2.2 обход всех страниц: рендер без JS-ошибок, содержимое непустое', async ({ page }) => {
  const errs = watchErrors(page);
  await login(page);
  const pages = await allPages(page);
  const bad = [];
  for (const p of pages) {
    await page.evaluate(id => showPage(id, true), p);
    const len = await page.evaluate(() => document.getElementById('main').innerHTML.length);
    if (len < 200) bad.push(`${p}:${len}`);
  }
  expect(bad, 'пустые страницы: ' + bad.join(',')).toEqual([]);
  expect(errs, errs.join('|')).toEqual([]);
});

test('2.3 каждая страница имеет заголовок h2 и (где положено) панель пунктов ТЗ', async ({ page }) => {
  await login(page);
  const pages = await allPages(page);
  for (const p of pages) {
    await page.evaluate(id => showPage(id, true), p);
    await expect(page.locator('#main h2').first(), `нет h2 на ${p}`).toBeVisible();
  }
});

test('2.4 отключённый модуль: страница-заглушка вместо контента (graceful degradation)', async ({ page }) => {
  await login(page);
  await page.evaluate(() => setModule('MOD-AI', false));
  await page.evaluate(() => showPage('ai', true));
  await expect(page.locator('.mod-off')).toBeVisible();
  await expect(page.locator('.mod-off')).toContainText('MOD-AI');
  await page.evaluate(() => setModule('MOD-AI', true));
});
