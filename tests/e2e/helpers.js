// Общие хелперы E2E-сценариев (план 3.1).
const APP = 'ais_providets_v101.html';

// Сетевой шум, допустимый в изолированной среде: тайлы (локальный сервер варианта Б
// или OSM варианта А), CDN Leaflet, favicon. Ошибки ресурсов этих хостов не считаются
// провалом сценария; pageerror (исключения JS) не фильтруются никогда.
const IGNORE_CONSOLE = /(favicon|tile\.openstreetmap\.org|127\.0\.0\.1:8080|unpkg\.com|net::ERR_)/;

/** Сборщик ошибок страницы: JS-исключения + console.error (кроме допустимого сетевого шума). */
function watchErrors(page) {
  const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + String(e && e.message || e).slice(0, 200)));
  page.on('console', m => {
    if (m.type() === 'error' && !IGNORE_CONSOLE.test(m.text())) errs.push('console: ' + m.text().slice(0, 200));
  });
  return errs;
}

/**
 * Полный цикл демо-входа через реальный UI (роль → «ВОЙТИ» → boot-анимация → enterApp).
 * @param {string} role — L0..L7 (null — не выбирать роль, использовать текущую)
 * @param {object} opts — { hash: 'risk' } откроет URL с хэшем (deep-link-сценарии)
 */
async function login(page, role = 'L7', opts = {}) {
  await page.goto(opts.hash ? APP + '#' + opts.hash : APP);
  await page.waitForSelector('#loginBtn', { state: 'visible' });
  if (role) await page.locator('#roleRow .role-btn', { hasText: role + ' ·' }).click();
  await page.click('#loginBtn');
  await page.waitForFunction(
    () => document.getElementById('app') && document.getElementById('app').style.display === 'grid',
    null, { timeout: 25000 });
  await page.waitForSelector('#nav .nav-item');
}

/** Текст последнего тоста (тосты живут ~5 с — вызывать сразу после события). */
async function lastToast(page) {
  return page.evaluate(() => {
    const w = document.getElementById('toasts');
    const d = w && w.lastElementChild;
    return d ? d.textContent : '';
  });
}

/** Все идентификаторы страниц из реестра RENDERERS. */
async function allPages(page) {
  return page.evaluate(() => Object.keys(RENDERERS).filter(k => typeof RENDERERS[k] === 'function'));
}

module.exports = { APP, IGNORE_CONSOLE, watchErrors, login, lastToast, allPages };
