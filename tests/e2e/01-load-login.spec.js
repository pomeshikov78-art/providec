// 01 — Загрузка, экран входа, версии, роли (инварианты демо-режима + P3.1/P3.2).
const { test, expect } = require('@playwright/test');
const { APP, watchErrors, login, IGNORE_CONSOLE } = require('./helpers');

test('1.1 загрузка без JS-ошибок (демо-экран входа)', async ({ page }) => {
  const errs = watchErrors(page);
  await page.goto(APP);
  await page.waitForSelector('#loginBtn', { state: 'visible' });
  await page.waitForTimeout(700);
  expect(errs, errs.join('|')).toEqual([]);
});

test('1.2 P3.2: ровно один meta providets-release-version = v102.0.0', async ({ page }) => {
  await page.goto(APP);
  const metas = page.locator('meta[name="providets-release-version"]');
  await expect(metas).toHaveCount(1);
  await expect(metas.first()).toHaveAttribute('content', 'v102.0.0');
});

test('1.3 P3.1: видимые версии на экране входа (loginVerLine + login-note)', async ({ page }) => {
  await page.goto(APP);
  await expect(page.locator('#loginVerLine')).toContainText('программа v102.0.0');
  await expect(page.locator('#loginVerLine')).toContainText('ТЗ 4.0');
  await expect(page.locator('.login-note')).toContainText('версии 102.0.0');
  // единая константа — источник
  expect(await page.evaluate(() => ver())).toBe('v102.0.0');
  expect(await page.evaluate(() => APP_VERSION.str)).toBe('v102.0.0');
  expect(await page.evaluate(() => Object.isFrozen(APP_VERSION))).toBe(true);
});

for (const role of ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7']) {
  test(`1.4 демо-вход ${role}: приложение запускается`, async ({ page }) => {
    const errs = watchErrors(page);
    await login(page, role);
    await expect(page.locator('#app')).toBeVisible();
    await expect(page.locator('#userRoleTop')).toContainText(role);
    await expect(page.locator('#main').locator('h2').first()).toBeVisible();
    expect(errs, errs.join('|')).toEqual([]);
  });
}

test('1.5 L0: ограниченный набор навигации (без registry/bus/ivp/audit)', async ({ page }) => {
  await login(page, 'L0');
  for (const p of ['registry', 'bus', 'ivp', 'audit']) {
    await expect(page.locator(`#nav .nav-item[data-page="${p}"]`)).toHaveCount(0);
  }
  await expect(page.locator('#nav .nav-item[data-page="dashboard"]')).toHaveCount(1);
});

test('1.6 выход из системы возвращает на экран входа', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => logout());
  await expect(page.locator('#login')).toBeVisible();
  await expect(page.locator('#app')).toBeHidden();
});

test('1.7 прототип-предупреждение на экране входа видимо и честно', async ({ page }) => {
  await page.goto(APP);
  const note = page.locator('.prototype-warning', { hasText: 'не является аутентификацией' });
  await expect(note).toBeVisible();
  await expect(note).toContainText('хранятся только в памяти страницы');
});
