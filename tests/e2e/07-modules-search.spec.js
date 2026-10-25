// 07 — Реестр модулей (graceful degradation) и поиск (Ctrl+K / gsearch).
const { test, expect } = require('@playwright/test');
const { login, watchErrors } = require('./helpers');

test('7.1 отключение модуля в реестре: nav-индикатор, страница-заглушка, остальные работают', async ({ page }) => {
  const errs = watchErrors(page);
  await login(page, 'L7');
  await page.evaluate(() => setModule('MOD-RISK', false));
  await expect(page.locator("#nav .nav-item[data-page='risk']")).toHaveClass(/offmod/);
  await page.click("#nav .nav-item[data-page='risk']");
  await expect(page.locator('.mod-off')).toBeVisible();
  await expect(page.locator('.mod-off')).toContainText('MOD-RISK отключен');
  // ядро и другие модули работают
  await page.click("#nav .nav-item[data-page='dashboard']");
  await page.waitForFunction(() => state.page === 'dashboard');
  await expect(page.locator('#main h2').first()).toBeVisible();
  expect(errs, errs.join('|')).toEqual([]);
  await page.evaluate(() => setModule('MOD-RISK', true));
});

test('7.2 включение модуля кнопкой со страницы-заглушки', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => setModule('MOD-RISK', false));
  await page.evaluate(() => showPage('risk', true));
  await expect(page.locator('.mod-off')).toBeVisible();
  await page.click('.mod-off button');
  await page.waitForFunction(() => modOn('MOD-RISK') && !document.querySelector('.mod-off'), null, { timeout: 10000 });
  expect(await page.evaluate(() => state.page)).toBe('risk');
  await expect(page.locator('#main h2').first()).toBeVisible();
});

test('7.3 Ctrl+K фокусирует глобальный поиск', async ({ page }) => {
  await login(page);
  await page.keyboard.press('Control+k');
  const id = await page.evaluate(() => document.activeElement && document.activeElement.id);
  expect(id).toBe('gsearch');
});

test('7.4 глобальный поиск: находит предприятие, переход открывает паспорт E01', async ({ page }) => {
  await login(page, 'L7');
  await page.click('#gsearch');
  await page.fill('#gsearch', 'E01');
  await page.waitForSelector('#gres.open .gres-i');
  const first = page.locator('#gres .gres-i').first();
  await expect(first).toContainText('E01');
  await first.click();
  await page.waitForFunction(() => state.page === 'pass' && state.selEnt === 'E01', null, { timeout: 10000 });
  await expect(page.locator('#main h2').first()).toBeVisible();
});

test('7.5 глобальный поиск: пустой результат показывает честную заглушку', async ({ page }) => {
  await login(page);
  await page.click('#gsearch');
  await page.fill('#gsearch', 'zzz-нет-такого-999');
  await expect(page.locator('#gres .empty-note')).toBeVisible();
  await page.keyboard.press('Escape');
});

test('7.6 реестр модулей: 15 модулей, переключатель влияет на modOn', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('registry', true));
  expect(await page.evaluate(() => MODULES.length)).toBe(15);
  expect(await page.evaluate(() => MODULES.filter(m => m.req).length)).toBe(6);
  const before = await page.evaluate(() => modOn('MOD-STIM'));
  await page.evaluate(v => setModule('MOD-STIM', !v), before);
  expect(await page.evaluate(() => modOn('MOD-STIM'))).toBe(!before);
  await page.evaluate(v => setModule('MOD-STIM', v), before);
});
