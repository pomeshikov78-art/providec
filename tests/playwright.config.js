// Playwright-конфигурация E2E-каркаса (план улучшений, п. 3.1).
// Два стенда: file:// (поставка единым файлом) и http:// (веб-стенд) — план требует
// «≥ 40 сценариев зелёные на file:// и на http-стенде».
const path = require('path');
const { defineConfig, devices } = require('@playwright/test');

const ROOT = path.resolve(__dirname, '..');
const PORT = 8817;

module.exports = defineConfig({
  testDir: path.join(__dirname, 'e2e'),
  timeout: 60 * 1000,
  expect: { timeout: 6 * 1000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Песочница разработки ограничена 1 ГБ RAM — один worker; CI-раннеры — два.
  workers: process.env.CI ? 2 : (process.env.PW_WORKERS ? Number(process.env.PW_WORKERS) : 1),
  reporter: process.env.CI ? [['list'], ['html', { open: 'never', outputFolder: path.join(ROOT, 'playwright-report') }]] : [['list']],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'file',
      use: { ...devices['Desktop Chrome'], baseURL: 'file://' + ROOT + '/' },
    },
    {
      name: 'http',
      use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:' + PORT + '/' },
    },
  ],
  // HTTP-стенд: обычный статический сервер (как nginx из frontend/ в минимуме).
  // Для file-проекта поднимается впустую — издержки единого конфига.
  webServer: {
    command: `python3 -m http.server ${PORT} --bind 127.0.0.1 --directory "${ROOT}"`,
    url: `http://127.0.0.1:${PORT}/ais_providets_v101.html`,
    reuseExistingServer: !process.env.CI,
    timeout: 30 * 1000,
  },
});
