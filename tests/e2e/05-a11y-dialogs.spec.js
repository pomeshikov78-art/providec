// 05 — Доступность: тосты, диалоги tcDialog, справка F1 (пункты 0.3/0.4 плана).
const { test, expect } = require('@playwright/test');
const { login, lastToast } = require('./helpers');
const fs = require('fs');
const path = require('path');

test('5.1 P3.3: контейнер тостов — role=status aria-live=polite', async ({ page }) => {
  await page.goto('ais_providets_v103.html');
  const t = page.locator('#toasts');
  await expect(t).toHaveAttribute('role', 'status');
  await expect(t).toHaveAttribute('aria-live', 'polite');
});

test('5.2 P3.3: обычный тост без role=alert; ошибочный — role=alert + assertive', async ({ page }) => {
  await login(page);
  await page.evaluate(() => toast('обычное сообщение', 'ok', 'TEST'));
  let last = page.locator('#toasts').locator('div.toast').last();
  await expect(last).toContainText('обычное сообщение');
  expect(await last.getAttribute('role')).toBeFalsy();

  await page.evaluate(() => toast('сообщение об ошибке', 'err', 'TEST'));
  last = page.locator('#toasts').locator('div.toast').last();
  await expect(last).toHaveAttribute('role', 'alert');
  await expect(last).toHaveAttribute('aria-live', 'assertive');
});

test('5.3 P3.4: в исходном артефакте нет window.confirm(/window.prompt(', async ({}) => {
  const html = fs.readFileSync(path.resolve(__dirname, '../../ais_providets_v103.html'), 'utf8');
  expect(html).not.toMatch(/window\.confirm\s*\(/);
  expect(html).not.toMatch(/window\.prompt\s*\(/);
});

test('5.4 P3.4: tcConfirm — диалог с фокусом внутри, Esc отменяет (resolve false)', async ({ page }) => {
  await login(page);
  await page.evaluate(() => { window.__dlg = 'pending'; tcConfirm('E2E-подтверждение', 'Тело сообщения').then(v => { window.__dlg = v; }); });
  const dlg = page.locator('#tcDialog');
  await expect(dlg).toBeVisible();
  await expect(dlg).toHaveAttribute('role', 'dialog');
  await expect(dlg).toHaveAttribute('aria-modal', 'true');
  await expect(dlg).toContainText('E2E-подтверждение');
  // фокус внутри диалога
  await page.waitForFunction(() => document.activeElement && document.activeElement.closest('#tcDialog'), null, { timeout: 5000 });
  // фокус-ловушка: несколько Tab не выводят фокус наружу
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => !!(document.activeElement && document.activeElement.closest('#tcDialog')))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => window.__dlg === false, null, { timeout: 5000 });
  await expect(dlg).toHaveCount(0);
});

test('5.5 P3.4: tcConfirm — Enter подтверждает (resolve true)', async ({ page }) => {
  await login(page);
  await page.evaluate(() => { window.__dlg = 'pending'; tcConfirm('E2E-OK', 'M').then(v => { window.__dlg = v; }); });
  await page.waitForSelector('#tcDialog');
  await page.waitForFunction(() => document.activeElement && document.activeElement.closest('#tcDialog'), null, { timeout: 5000 });
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => window.__dlg === true, null, { timeout: 5000 });
});

test('5.6 P3.4: tcPrompt — поле ввода, Enter возвращает значение; Esc → null', async ({ page }) => {
  await login(page);
  await page.evaluate(() => { window.__dlg = 'pending'; tcPrompt('MFA-тест', 'Введите код', 'Код', { inputNumeric: true }).then(v => { window.__dlg = v; }); });
  await page.waitForSelector('#tcDlgInp');
  await expect(page.locator('#tcDlgInp')).toHaveAttribute('inputmode', 'numeric');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'tcDlgInp', null, { timeout: 5000 });
  await page.keyboard.type('654321');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => window.__dlg === '654321', null, { timeout: 5000 });

  await page.evaluate(() => { window.__dlg2 = 'pending'; tcPrompt('MFA-тест2', 'M', 'Код').then(v => { window.__dlg2 = v; }); });
  await page.waitForSelector('#tcDialog');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => window.__dlg2 === null, null, { timeout: 5000 });
});

test('5.7 P3.4: Enter в открытом диалоге на экране входа НЕ запускает doLogin повторно', async ({ page }) => {
  // диалог поверх экрана входа: глобальный Enter-логин обязан блокироваться capture-обработчиком
  await page.goto('ais_providets_v103.html');
  await page.waitForSelector('#loginBtn');
  await page.evaluate(() => { window.__dlg = 'pending'; tcPrompt('Код', 'M', 'Код').then(v => { window.__dlg = v; }); });
  await page.waitForSelector('#tcDlgInp');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'tcDlgInp', null, { timeout: 5000 });
  await page.keyboard.type('123456');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => window.__dlg === '123456', null, { timeout: 5000 });
  await page.waitForTimeout(600);
  // boot-последовательность не запускалась: экран входа ещё видим
  await expect(page.locator('#login')).toBeVisible();
  expect(await page.evaluate(() => document.getElementById('boot').style.display)).not.toBe('block');
});

test('5.8 справка F1: открывается, поиск работает, переход закрывает окно', async ({ page }) => {
  await login(page);
  await page.keyboard.press('F1');
  await expect(page.locator('#helpWin')).toHaveClass(/on/);
  await page.fill('#helpQ', 'TRL');
  await page.waitForSelector('#helpRes .hr-i');
  const hits = await page.locator('#helpRes .hr-i').count();
  expect(hits).toBeGreaterThan(3);
  // клик по первому переходу — окно закрывается
  const goItem = page.locator('#helpRes .hr-i', { hasText: 'перейти' }).first();
  if (await goItem.count()) {
    await goItem.click();
    await page.waitForTimeout(400);
    const cls = (await page.getAttribute('#helpWin', 'class')) || '';
    expect(cls).not.toContain('on');
  }
});

test('5.9 «Что нового · v101» присутствует в индексе справочного центра', async ({ page }) => {
  await login(page);
  const found = await page.evaluate(() => buildHelpIndex().some(x => String(x.c).indexOf('Что нового') === 0));
  expect(found).toBe(true);
});
