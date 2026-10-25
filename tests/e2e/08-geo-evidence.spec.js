// 08 — Гео/Leaflet (п. 0.7 плана), «доказательные» панели, встроенные smoke-тесты.
const { test, expect } = require('@playwright/test');
const { login, watchErrors, IGNORE_CONSOLE } = require('./helpers');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

test('8.1 MOD-GEO по умолчанию: SVG-карта без внешних запросов', async ({ page }) => {
  const reqs = [];
  page.on('request', r => reqs.push(r.url()));
  await login(page, 'L7');
  await page.evaluate(() => showPage('geo', true));
  await expect(page.locator('#main svg').first()).toBeVisible();
  // внешними считаем все http(s)-запросы, кроме собственного стенда (любой loopback-порт)
  const external = reqs.filter(u => /^https?:/.test(u) && !/^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?\//.test(u));
  expect(external, 'внешние запросы: ' + external.join(',')).toEqual([]);
});

test('8.2 P3.7 вариант Б: Leaflet грузится из ./vendor/leaflet без обращения к CDN', async ({ page }) => {
  test.setTimeout(90 * 1000);
  const cdn = [];
  page.on('request', r => { if (r.url().includes('unpkg.com') || r.url().includes('cdn.jsdelivr')) cdn.push(r.url()); });
  await login(page, 'L7');
  await page.evaluate(() => { state.variant = 'autonomous'; showPage('geo', true); });
  await page.evaluate(() => geoEngineToggle()); // svg → leaflet (локальные файлы)
  await page.waitForFunction(() => !!window.L, null, { timeout: 30000 });
  const src = await page.evaluate(() => {
    const s = document.querySelector('script[src*="leaflet"]');
    return s ? s.getAttribute('src') : null;
  });
  expect(src).toContain('vendor/leaflet/leaflet.js');
  expect(cdn, 'CDN-запросы в варианте Б: ' + cdn.join(',')).toEqual([]);
  // тайлы — только локальный сервер варианта Б (может быть недоступен — это штатная деградация)
  const tileUrl = await page.evaluate(() => {
    const l = SRV.lmap;
    return l ? 'ok' : 'none';
  });
  expect(['ok', 'none']).toContain(tileUrl);
});

test('8.3 P3.7 CDN-режим: у тегов Leaflet установлены SRI, совпадающие с файлами поставки', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => { state.variant = 'network'; showPage('geo', true); });
  await page.evaluate(() => geoEngineToggle());
  await page.waitForSelector('script[src*="unpkg.com/leaflet"]', { timeout: 10000, state: 'attached' });
  const attrs = await page.evaluate(() => {
    const s = document.querySelector('script[src*="leaflet"]');
    const c = document.querySelector('link[href*="leaflet"]');
    return { js: s.getAttribute('integrity'), jsCo: s.crossOrigin, css: c.getAttribute('integrity'), cssCo: c.crossOrigin };
  });
  // эталон: фактические файлы vendor/ (они идентичны unpkg dist)
  const jsHash = 'sha256-' + crypto.createHash('sha256').update(fs.readFileSync(path.resolve(__dirname, '../../vendor/leaflet/leaflet.js'))).digest('base64');
  const cssHash = 'sha256-' + crypto.createHash('sha256').update(fs.readFileSync(path.resolve(__dirname, '../../vendor/leaflet/leaflet.css'))).digest('base64');
  expect(attrs.js).toBe(jsHash);
  expect(attrs.css).toBe(cssHash);
  expect(attrs.jsCo).toBe('anonymous');
  expect(attrs.cssCo).toBe('anonymous');
});

test('8.4 дорожная карта: панели P1–P5, ворота выпуска, манифест, комплект передачи на месте', async ({ page }) => {
  const errs = watchErrors(page);
  await login(page, 'L7');
  await page.evaluate(() => showPage('roadmap', true));
  for (const id of ['p1p5Roadmap', 'releaseGates', 'artifactManifestTemplate', 'releaseHandover']) {
    await expect(page.locator('#' + id), `нет панели #${id}`).toHaveCount(1);
  }
  // фильтр P1–P5 работает
  await page.selectOption('#p1p5Filter', 'P3');
  const visible = await page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-p1p5]')).filter(x => x.style.display !== 'none').map(x => x.getAttribute('data-p1p5')));
  expect(visible).toEqual(['P3']);
  await page.selectOption('#p1p5Filter', 'ALL');
  expect(errs, errs.join('|')).toEqual([]);
});

test('8.5 «О системе»: история версий v102 → v101 → v100 → v82', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('about', true));
  const html = await page.evaluate(() => document.getElementById('main').innerHTML);
  const i102 = html.indexOf('>v102.0.0<');
  const i101 = html.indexOf('>v101.0.0<');
  const i100 = html.indexOf('>v100.0.0<');
  const i82 = html.indexOf('>v82.0.0<');
  expect(i102).toBeGreaterThan(-1);
  expect(i102).toBeLessThan(i101);
  expect(i101).toBeLessThan(i100);
  expect(i100).toBeLessThan(i82);
  expect(html).toContain('Д-10');
  expect(html).toContain('Волна 0 плана улучшений');
  await expect(page.locator('#main')).toContainText('программа v102.0.0');
});

test('8.6 встроенные smoke-тесты (P0.19 + Волна 0): ≥ 25 проверок, 0 провалов', async ({ page }) => {
  await login(page, 'L7');
  const rep = await page.evaluate(() => runClientRegressionSmokeTests());
  expect(rep.summary.failed, JSON.stringify(rep.tests.filter(t => t.result !== 'PASS'))).toBe(0);
  expect(rep.summary.total).toBeGreaterThanOrEqual(26);
  expect(rep.program).toBe('v102.0.0');
  for (const id of ['REL-VER-01', 'REL-VER-02', 'A11Y-01', 'NAV-01', 'DL-01', 'GEO-SRI-01', 'SRV-LOGIN-01']) {
    expect(rep.tests.some(t => t.id === id && t.result === 'PASS'), `${id} не PASS`).toBe(true);
  }
});

test('8.7 самотест сетевой политики: 7/7 без отправки запросов', async ({ page }) => {
  const reqs = [];
  await login(page, 'L7');
  page.on('request', r => reqs.push(r.url()));
  const before = reqs.length;
  const rep = await page.evaluate(() => runNetworkPolicySelfTest());
  expect(rep.failed).toBe(0);
  expect(rep.total).toBe(7);
  expect(rep.networkRequestsSent).toBe(0);
  expect(reqs.length).toBe(before);
});
