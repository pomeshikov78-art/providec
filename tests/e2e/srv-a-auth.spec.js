// srv-A: аутентификация и сессия (живой бэкенд FastAPI). См. tests/README.md.
const { test, expect } = require('@playwright/test');
const { API, api, serverLogin, waitConnected } = require('./srv-helpers');

test.beforeEach(async () => {
  test.skip(process.env.TC_WITH_BACKEND !== '1', 'стенд бэкенда не поднят (нужен TC_WITH_BACKEND=1)');
});

test('s.1 серверный вход через UI: JWT + MFA/TOTP → роль L7 из IAM, данные из СУБД', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  expect(await page.evaluate(() => SRV.role)).toBe('L7');
  expect(await page.evaluate(() => SRV.fio)).toContain('Крылов');
  expect(await page.evaluate(() => SRV.boot && SRV.boot.modules.length)).toBe(15);
  expect(await page.evaluate(() => ORGS.length)).toBe(100);
  expect(await page.evaluate(() => PROJECTS.length)).toBe(12);
  expect(await page.evaluate(() => SRV.geo && !!SRV.geo.tile_url)).toBe(true);
  await expect(page.locator('#userRoleTop')).toContainText('L7');
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

test('s.9 выход: logout() → серверный POST /auth/logout + демо-режим, токен отозван (401)', async ({ page }) => {
  await serverLogin(page);
  await waitConnected(page);
  const token = await page.evaluate(() => SRV.token);
  expect(token).toBeTruthy();
  await page.evaluate(() => logout());
  await page.waitForTimeout(2500);
  expect(await page.evaluate(() => SRV.connected)).toBe(false);
  expect(await page.evaluate(() => SRV.token === null)).toBe(true);
  const after = await api('GET', '/api/v1/bootstrap', { token });
  expect(after.status, 'токен должен быть отозван на сервере (jti blacklist)').toBe(401);
});
