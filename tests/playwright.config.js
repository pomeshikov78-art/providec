// Playwright-конфигурация E2E-каркаса (план улучшений, п. 3.1 + 3.3).
// Три стенда:
//   file — поставка единым файлом (file://);
//   http — веб-стенд (http://127.0.0.1:8817);
//   srv  — РАБОЧАЯ ПЛАТФОРМА: клиент (8817) + живой бэкенд FastAPI (8000, SQLite, seed).
//          Включается TC_WITH_BACKEND=1 (поднимает uvicorn через tests/run_backend.sh).
const path = require('path');
const { defineConfig, devices } = require('@playwright/test');

const ROOT = path.resolve(__dirname, '..');
const PORT = process.env.TC_STATIC_PORT || 8817;
const API_PORT = process.env.TC_API_PORT || 8000;
const WITH_BACKEND = process.env.TC_WITH_BACKEND === '1';
const SRV_SPEC = '**/10-server-mode.spec.js';

const webServer = [
  {
    command: `python3 -m http.server ${PORT} --bind 127.0.0.1 --directory "${ROOT}"`,
    url: `http://127.0.0.1:${PORT}/ais_providets_v102.html`,
    reuseExistingServer: !process.env.CI,
    timeout: 30 * 1000,
  },
];
if (WITH_BACKEND) {
  webServer.push({
    command: `sh "${path.join(ROOT, 'tests', 'run_backend.sh')}"`,
    url: `http://127.0.0.1:${API_PORT}/api/v1/core/health`,
    // Всегда свежий стенд: «переиспользование» устаревшего uvicorn даёт пустую/удалённую
    // БД и недетерминированные TOTPs (дефект диагностики 25.10.2026).
    reuseExistingServer: false,
    timeout: 90 * 1000,
  });
}

module.exports = defineConfig({
  testDir: path.join(__dirname, 'e2e'),
  timeout: 90 * 1000,
  expect: { timeout: 8 * 1000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Ретрай: в тесных песочницах (1 ГБ RAM, строгий overcommit) первый запуск рендерера
  // может упасть «Target crashed» по ресурсам — это средовый шум, а не дефект артефакта.
  // Функциональные провалы воспроизводятся на ретрае и остаются провалами.
  retries: 1,
  // Песочница разработки ограничена 1 ГБ RAM — один worker; CI-раннеры — два.
  workers: process.env.CI ? 2 : (process.env.PW_WORKERS ? Number(process.env.PW_WORKERS) : 1),
  reporter: process.env.CI ? [['list'], ['html', { open: 'never', outputFolder: path.join(ROOT, 'playwright-report') }]] : [['list']],
  use: {
    // TC_NO_TRACE=1 — отключение трейсинга/скриншотов (диагностика падений рендерера
    // в малопаметных песочницах; в CI оставляем полный набор).
    trace: process.env.TC_NO_TRACE === '1' ? 'off' : 'retain-on-failure',
    screenshot: process.env.TC_NO_TRACE === '1' ? 'off' : 'only-on-failure',
    video: 'off',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'file',
      testIgnore: SRV_SPEC,
      use: { ...devices['Desktop Chrome'], baseURL: 'file://' + ROOT + '/' },
    },
    {
      name: 'http',
      testIgnore: SRV_SPEC,
      use: { ...devices['Desktop Chrome'], baseURL: `http://127.0.0.1:${PORT}/` },
    },
    {
      name: 'srv',
      testMatch: SRV_SPEC,
      // Песочница: честный ретрай — запуск браузера рядом с uvicorn ресурсоёмок.
      retries: 1,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${PORT}/`,
        // Песочница разработки (1 ГБ RAM, CommitLimit ~540 МБ): при живом uvicorn V8
        // рендерера не может зарезервировать CodeRange («Failed to reserve virtual
        // memory for CodeRange» → Target crashed). Браузер+рендерер в одном процессе
        // обходят ограничение; в CI (16 ГБ) флаг безвреден. Трейсинг в single-process
        // нестабилен — отключён для этого стенда.
        ...(process.env.CI ? {} : {
          launchOptions: { args: ['--single-process', '--no-zygote', '--disable-gpu'] },
          trace: 'off',
          screenshot: 'only-on-failure',
        }),
      },
    },
  ],
  webServer,
});
