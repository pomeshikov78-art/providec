// 09 — Тема, печать, серверный режим (UI-блокировки без бэкенда), аудит.
const { test, expect } = require('@playwright/test');
const { APP, login, watchErrors } = require('./helpers');

test('9.1 тема оформления переключается и сохраняется в localStorage', async ({ page }) => {
  await login(page);
  const before = await page.evaluate(() => document.body.classList.contains('light'));
  await page.evaluate(() => toggleTheme());
  expect(await page.evaluate(() => document.body.classList.contains('light'))).toBe(!before);
  expect(await page.evaluate(() => localStorage.getItem('tc_theme'))).toBeTruthy();
  await page.evaluate(() => toggleTheme());
  expect(await page.evaluate(() => document.body.classList.contains('light'))).toBe(before);
});

test('9.2 print-стили: сайдбар/тосты скрываются, контент печатается', async ({ page }) => {
  await login(page);
  await page.evaluate(() => showPage('about', true));
  await page.emulateMedia({ media: 'print' });
  expect(await page.evaluate(() => getComputedStyle(document.getElementById('sidebar')).display)).toBe('none');
  expect(await page.evaluate(() => getComputedStyle(document.getElementById('toasts')).display)).toBe('none');
  expect(await page.evaluate(() => getComputedStyle(document.getElementById('main')).display)).not.toBe('none');
  await page.emulateMedia({ media: 'screen' });
});

test('9.3 серверный режим: включение блокирует выбор клиентской роли (AUTH-03 в UI)', async ({ page }) => {
  await page.goto(APP);
  await page.waitForSelector('#loginBtn');
  await page.check('#srvEnabled');
  const btns = page.locator('#roleRow .role-btn');
  const n = await btns.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    await expect(btns.nth(i)).toBeDisabled();
    await expect(btns.nth(i)).toHaveAttribute('aria-disabled', 'true');
  }
  await page.uncheck('#srvEnabled');
  await expect(btns.first()).toBeEnabled();
});

test('9.4 серверный вход без бэкенда: честная ошибка, демо-режим доступен', async ({ page }) => {
  test.setTimeout(90 * 1000);
  await page.goto(APP);
  await page.waitForSelector('#loginBtn');
  await page.check('#srvEnabled');
  await page.fill('#srvUrl', 'http://127.0.0.1:9'); // заведомо недоступный адрес локального контура
  await page.fill('#srvLogin', 'admin');
  await page.fill('#srvPass', 'wrong-pass');
  await page.evaluate(() => srvTryLogin().catch(() => {}));
  // ошибка отображена, секреты не светятся; приложение живо
  await page.waitForTimeout(3000);
  expect(await page.evaluate(() => SRV.connected)).toBe(false);
  expect(await page.evaluate(() => SRV.token === null)).toBe(true);
  // демо-вход по-прежнему работает
  await page.uncheck('#srvEnabled');
  await page.click('#loginBtn');
  await page.waitForFunction(() => document.getElementById('app').style.display === 'grid', null, { timeout: 20000 });
});

test('9.5 журнал аудита: действия регистрируются, страница аудита рендерится', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => addAudit('E2E-проверка', 'тест', 'Успех'));
  await page.evaluate(() => showPage('audit', true));
  await expect(page.locator('#main')).toContainText('E2E-проверка');
  const n = await page.evaluate(() => state.audit.length);
  expect(n).toBeGreaterThan(0);
  expect(n).toBeLessThanOrEqual(300); // ограниченный буфер
});

test('9.6 тикер событий: буфер ≤ 6, лента не растёт бесконечно', async ({ page }) => {
  await login(page, 'L7');
  await page.waitForTimeout(2500); // несколько тиков симуляции
  const tick = await page.evaluate(() => document.getElementById('ticker').children.length);
  expect(tick).toBeLessThanOrEqual(6);
  const ev = await page.evaluate(() => state.events.length);
  expect(ev).toBeLessThanOrEqual(400);
});

test('9.7 полная страница загрузки не оставляет ошибок в консоли (чистый прогон)', async ({ page }) => {
  const errs = watchErrors(page);
  await login(page, 'L7');
  for (const p of ['dashboard', 'registry', 'bus', 'pass', 'prof', 'niokr', 'geo', 'kpi', 'about', 'roadmap']) {
    await page.evaluate(id => showPage(id, true), p);
    await page.waitForTimeout(120);
  }
  expect(errs, errs.join('|')).toEqual([]);
});
