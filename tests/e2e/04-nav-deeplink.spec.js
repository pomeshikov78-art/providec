// 04 — Навигация, клавиатура и deep-linking (пункты 0.5/0.6 плана, P3.5/P3.6).
const { test, expect } = require('@playwright/test');
const { login, watchErrors } = require('./helpers');

test('4.1 клик по nav-item переключает страницу и обновляет location.hash', async ({ page }) => {
  await login(page);
  await page.click("#nav .nav-item[data-page='registry']");
  await page.waitForFunction(() => state.page === 'registry');
  expect(page.url()).toMatch(/#registry$/);
  await page.click("#nav .nav-item[data-page='bus']");
  await page.waitForFunction(() => state.page === 'bus');
  expect(page.url()).toMatch(/#bus$/);
});

test('4.2 кнопка «назад» браузера возвращает предыдущую страницу (popstate/hashchange)', async ({ page }) => {
  await login(page);
  await page.click("#nav .nav-item[data-page='registry']");
  await page.waitForFunction(() => state.page === 'registry');
  await page.click("#nav .nav-item[data-page='bus']");
  await page.waitForFunction(() => state.page === 'bus');
  await page.goBack();
  await page.waitForFunction(() => state.page === 'registry', null, { timeout: 10000 });
  expect(page.url()).toMatch(/#registry$/);
  await page.goForward();
  await page.waitForFunction(() => state.page === 'bus', null, { timeout: 10000 });
});

test('4.3 deep-link: URL #risk открывает MOD-RISK после входа', async ({ page }) => {
  const errs = watchErrors(page);
  await login(page, 'L7', { hash: 'risk' });
  await page.waitForFunction(() => state.page === 'risk');
  await expect(page.locator('#main h2').first()).toBeVisible();
  expect(await page.evaluate(() => state.page)).toBe('risk');
  expect(errs, errs.join('|')).toEqual([]);
});

test('4.4 deep-link: недопустимый хэш игнорируется → dashboard', async ({ page }) => {
  await login(page, 'L7', { hash: 'evil-page<script>' });
  await page.waitForFunction(() => state.page === 'dashboard');
  expect(await page.evaluate(() => state.page)).toBe('dashboard');
});

test('4.5 hashchange извне переключает страницу (прямая навигация по хэшу)', async ({ page }) => {
  await login(page);
  await page.evaluate(() => { location.hash = '#ivp'; });
  await page.waitForFunction(() => state.page === 'ivp', null, { timeout: 10000 });
  await expect(page.locator('#main h2').first()).toContainText(/информационно-вычислительных|ИВП/i);
});

test('4.6 P3.5: Enter на сфокусированном nav-item переключает страницу', async ({ page }) => {
  await login(page);
  await page.focus("#nav .nav-item[data-page='ivp']");
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => state.page === 'ivp');
  await expect(page.locator("#nav .nav-item[data-page='ivp']")).toHaveAttribute('aria-current', 'page');
});

test('4.7 P3.5: Space на nav-item переключает страницу', async ({ page }) => {
  await login(page);
  await page.focus("#nav .nav-item[data-page='audit']");
  await page.keyboard.press('Space');
  await page.waitForFunction(() => state.page === 'audit');
});

test('4.8 P3.5: полный обход сайдбара клавишей Tab (все пункты фокусируемы)', async ({ page }) => {
  await login(page);
  await page.focus("#nav .nav-item[data-page='dashboard']");
  const seen = [];
  for (let i = 0; i < 8; i++) {
    const dp = await page.evaluate(() => {
      const a = document.activeElement;
      return a && a.classList && a.classList.contains('nav-item') ? a.getAttribute('data-page') : null;
    });
    seen.push(dp);
    await page.keyboard.press('Tab');
  }
  expect(seen.filter(Boolean).length).toBeGreaterThanOrEqual(6);
  // активный пункт помечен aria-current
  const cur = await page.evaluate(() => {
    const a = document.querySelector('#nav .nav-item[aria-current="page"]');
    return a ? a.getAttribute('data-page') : null;
  });
  expect(cur).toBeTruthy();
});

test('4.9 P3.5: сайдбар — <nav aria-label>, все nav-item — role=button tabindex=0', async ({ page }) => {
  await login(page);
  const nav = page.locator('#sidebar');
  await expect(nav).toHaveAttribute('aria-label', /.+/);
  const items = page.locator('#nav .nav-item');
  const n = await items.count();
  expect(n).toBeGreaterThan(10);
  for (let i = 0; i < n; i++) {
    await expect(items.nth(i)).toHaveAttribute('role', 'button');
    await expect(items.nth(i)).toHaveAttribute('tabindex', '0');
  }
});
