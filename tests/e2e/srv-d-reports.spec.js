// srv-D: реальные отчётные файлы бэкенда + серверные контроль качества/двойник (Этап 12).
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const { api, serverLogin, waitConnected, waitPassSynced } = require('./srv-helpers');

test.beforeEach(async () => {
  test.skip(process.env.TC_WITH_BACKEND !== '1', 'стенд бэкенда не поднят (нужен TC_WITH_BACKEND=1)');
});

test('s.12 MOD-REPORT: DOCX в серверном режиме — реальный файл сервера (PK-магия ZIP)', async ({ page }) => {
  test.setTimeout(120000);
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('report', true));
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 40000 }),
    page.evaluate(() => exportReportDocx()),
  ]);
  expect(download.suggestedFilename()).toMatch(/^passport_.*\.docx$/);
  const buf = fs.readFileSync(await download.path());
  expect(buf.length).toBeGreaterThan(5000);
  expect(buf[0]).toBe(0x50); // 'P'
  expect(buf[1]).toBe(0x4b); // 'K' — ZIP/DOCX (python-docx), не клиентская текстовая подделка
  expect(await page.evaluate(() => state.audit.some(a => a.action === 'Формирование отчета (сервер)'))).toBe(true);
});

test('s.13 MOD-REPORT: XLSX реестра в серверном режиме — реальный файл (openpyxl)', async ({ page }) => {
  test.setTimeout(120000);
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('report', true));
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 40000 }),
    page.evaluate(() => exportReportXlsx()),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  const buf = fs.readFileSync(await download.path());
  expect(buf.length).toBeGreaterThan(3000);
  expect(buf[0]).toBe(0x50); expect(buf[1]).toBe(0x4b);
});

test('s.14 MOD-PASS/PROF: серверный контроль качества + пересборка двойника (WORM-аудит)', async ({ page }) => {
  test.setTimeout(120000);
  await serverLogin(page);
  await waitConnected(page);
  await page.evaluate(() => showPage('pass', true));
  await waitPassSynced(page);
  await page.evaluate(() => passportQuality(state.selEnt));
  await page.waitForFunction(
    () => Array.from(document.getElementById('toasts').children).some(t => /Качество паспорта|Контроль качества/.test(t.textContent)),
    null, { timeout: 20000 });
  await page.evaluate(() => recalcProfile(state.selEnt));
  await page.waitForFunction(
    () => Array.from(document.getElementById('toasts').children).some(t => t.textContent.includes('пересобран')),
    null, { timeout: 25000 });
  const token = await page.evaluate(() => SRV.token);
  const audit = await api('GET', '/api/v1/core/audit?limit=60', { token });
  expect(audit.status).toBe(200);
  const rows = Array.isArray(audit.json) ? audit.json : ((audit.json && audit.json.items) || []);
  expect(rows.some(r => String(r.action || '').includes('Пересборка цифрового двойника'))).toBe(true);
  expect(rows.some(r => String(r.action || '').includes('Контроль качества'))).toBe(true);
});
