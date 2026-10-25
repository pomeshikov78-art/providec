// 06 — Снимки БД: экспорт, валидный импорт через tcDialog, негатив (повреждённый снимок).
const { test, expect } = require('@playwright/test');
const { login, lastToast } = require('./helpers');
const fs = require('fs');
const os = require('os');
const path = require('path');

function tmpFile(name, data) {
  const p = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'tc-e2e-')), name);
  fs.writeFileSync(p, data);
  return p;
}

test('6.1 экспорт снимка: JSON с program=v101.0.0, schemaVersion и CRC32', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('db', true));
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    page.evaluate(() => exportDB()),
  ]);
  expect(download.suggestedFilename()).toMatch(/^technocontour_demo_snapshot_.*\.json$/);
  const p = await download.path();
  const snap = JSON.parse(fs.readFileSync(p, 'utf8'));
  expect(snap.program).toBe('v101.0.0');
  expect(snap.schemaVersion).toBe(1);
  expect(snap.integrity.algorithm).toBe('CRC32');
  expect(snap.data.ORGS.length).toBe(100);
});

test('6.2 валидный импорт: подтверждение через tcDialog (не нативный confirm), данные восстановлены', async ({ page }) => {
  test.setTimeout(90 * 1000);
  await login(page, 'L7');
  await page.evaluate(() => showPage('db', true));
  // экспортируем валидный снимок
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    page.evaluate(() => exportDB()),
  ]);
  const snapPath = await download.path();
  const snapText = fs.readFileSync(snapPath, 'utf8');
  const keep = tmpFile('snapshot_ok.json', snapText);
  // нативный confirm/prompt не должны вызываться — перехватываем и роняем тест при вызове
  await page.evaluate(() => {
    window.confirm = () => { throw new Error('window.confirm вызван!'); };
    window.prompt = () => { throw new Error('window.prompt вызван!'); };
  });
  await page.setInputFiles('#dbRestoreFile', keep);
  // появится диалог tcDialog с кнопкой «Заменить данные»
  await page.waitForSelector('#tcDialog', { timeout: 15000 });
  await expect(page.locator('#tcDialogTitle')).toContainText('Восстановление демонстрационных данных');
  await expect(page.locator('#tcDialog')).toContainText('Контрольная сумма CRC32 совпала');
  await page.click('#tcDlgOk');
  await page.waitForFunction(() => !document.getElementById('tcDialog'), null, { timeout: 20000 });
  await expect.poll(async () => (await lastToast(page)).includes('восстановлены'), { timeout: 10000 }).toBe(true);
});

test('6.3 негатив: снимок с битой CRC32 отклоняется до диалога, данные не меняются', async ({ page }) => {
  test.setTimeout(90 * 1000);
  await login(page, 'L7');
  await page.evaluate(() => showPage('db', true));
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    page.evaluate(() => exportDB()),
  ]);
  const snap = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
  const orgsBefore = await page.evaluate(() => JSON.stringify(ORGS));
  // повреждаем контрольную сумму
  snap.integrity.checksum = 'deadbeef';
  const bad = tmpFile('snapshot_bad_crc.json', JSON.stringify(snap));
  await page.setInputFiles('#dbRestoreFile', bad);
  await expect.poll(async () => (await lastToast(page)).includes('отклонён'), { timeout: 10000 }).toBe(true);
  await expect(page.locator('#tcDialog')).toHaveCount(0);
  const orgsAfter = await page.evaluate(() => JSON.stringify(ORGS));
  expect(orgsAfter).toBe(orgsBefore);
});

test('6.4 негатив: повреждённый JSON отклоняется безопасно', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('db', true));
  const bad = tmpFile('broken.json', '{"system":"АИС «Техноконтур»", <<<не json');
  await page.setInputFiles('#dbRestoreFile', bad);
  await expect.poll(async () => (await lastToast(page)).includes('отклонён'), { timeout: 10000 }).toBe(true);
  await expect(page.locator('#tcDialog')).toHaveCount(0);
});

test('6.5 самодиагностика снимков: диалог role=dialog, все проверки пройдены', async ({ page }) => {
  test.setTimeout(90 * 1000);
  await login(page, 'L7');
  await page.evaluate(() => showPage('db', true));
  await page.evaluate(() => dbRunSelfTests());
  await page.waitForSelector('#dbSelfTestDialog', { timeout: 30000 });
  const dlg = page.locator('#dbSelfTestDialog');
  await expect(dlg).toHaveAttribute('role', 'dialog');
  await expect(dlg).toHaveAttribute('aria-modal', 'true');
  const rep = await page.evaluate(() => DB_LAST_SELF_TEST_REPORT);
  expect(rep.summary.failed).toBe(0);
  expect(rep.program).toBe('v101.0.0');
  expect(rep.summary.total).toBeGreaterThanOrEqual(20);
  await page.click('#dbSelfTestDone');
  await expect(dlg).toHaveCount(0);
});
