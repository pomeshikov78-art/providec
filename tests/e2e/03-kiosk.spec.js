// 03 — Киоск-сценарий (инвариант: автономная демонстрация для варианта Б).
const { test, expect } = require('@playwright/test');
const { watchErrors, login } = require('./helpers');

test('3.1 киоск запускается и проходит ≥ 2 шага без JS-ошибок', async ({ page, browserName }) => {
  test.setTimeout(120 * 1000);
  const errs = watchErrors(page);
  await login(page);
  await page.evaluate(() => kioskStart());
  await expect(page.locator('#kioskBar')).toBeVisible();
  await expect(page.locator('#kioskStep')).toContainText('Шаг 1 /');
  // ждём перехода хотя бы на 3-й шаг (длительности шагов ~5–8 с)
  await page.waitForFunction(() => typeof kiosk !== 'undefined' && kiosk.i >= 2, null, { timeout: 60 * 1000 });
  const cap = await page.textContent('#kioskCap');
  expect(cap.trim().length).toBeGreaterThan(20);
  expect(errs, errs.join('|')).toEqual([]);
});

test('3.2 киоск: пауза/продолжение/остановка, P3.6 — хэш синхронизируется в replace-режиме', async ({ page }) => {
  test.setTimeout(90 * 1000);
  await login(page);
  const historyLenBefore = await page.evaluate(() => history.length);
  await page.evaluate(() => kioskStart());
  await expect(page.locator('#kioskBar')).toBeVisible();
  await page.evaluate(() => kioskPause());
  expect(await page.evaluate(() => kiosk.paused)).toBe(true);
  await page.evaluate(() => kioskPause()); // продолжить
  await page.waitForFunction(() => typeof kiosk !== 'undefined' && kiosk.i >= 1, null, { timeout: 45 * 1000 });
  await page.evaluate(() => kioskStop());
  await expect(page.locator('#kioskBar')).toBeHidden();
  expect(await page.evaluate(() => kiosk.on)).toBe(false);
  // история браузера не должна разрастаться: на http — replaceState (0 записей),
  // на file:// pushState/replaceState запрещён и используется fallback location.hash
  // (допустимо несколько записей — задокументированное ограничение file://-поставки)
  const historyLenAfter = await page.evaluate(() => history.length);
  expect(historyLenAfter - historyLenBefore).toBeLessThanOrEqual(3);
});
