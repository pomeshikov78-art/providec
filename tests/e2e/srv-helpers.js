// Общие хелперы стенда srv (клиент против живого FastAPI).
// TOTP (RFC 6238) на node:crypto; секрет читается из SQLite стенда (dev-процедура;
// в промышленном контуре — TC_FIRST_ADMIN_RUNBOOK + процедура регистрации администратора).
const crypto = require('crypto');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '../..');
const API = process.env.TC_API || 'http://127.0.0.1:8000';
const DB = process.env.TC_DB || path.join(ROOT, 'backend', 'technocontour.db');
const PY = process.env.TC_PYTHON || 'python3';
const ADMIN = { login: 'admin', pass: 'tc-admin-2026' };
const APP = 'ais_providets_v103.html';

function b32decode(s) {
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = 0, val = 0; const out = [];
  for (const c of String(s).replace(/=+$/, '').toUpperCase()) {
    const i = A.indexOf(c); if (i < 0) continue;
    val = (val << 5) | i; bits += 5;
    if (bits >= 8) { out.push((val >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  return Buffer.from(out);
}
function totp(secret) {
  const key = b32decode(secret);
  const ctr = Math.floor(Date.now() / 1000 / 30);
  const b = Buffer.alloc(8); b.writeBigUInt64BE(BigInt(ctr));
  const h = crypto.createHmac('sha1', key).update(b).digest();
  const o = h[h.length - 1] & 0xf;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, '0');
}
function adminSecret() {
  const code = 'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("select totp_secret from users where login=?",(sys.argv[2],)).fetchone()[0])';
  let lastErr = null;
  for (let i = 0; i < 60; i++) {
    try {
      return execFileSync(PY, ['-c', code, DB, ADMIN.login], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    } catch (e) {
      lastErr = e;
      const t = Date.now(); while (Date.now() - t < 1000) { /* sync sleep: стенд ещё сеет БД */ }
    }
  }
  throw lastErr;
}
async function api(method, p, { token, body } = {}) {
  const r = await fetch(API + p, {
    method,
    headers: {
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let j = null; try { j = await r.json(); } catch (e) { /* не-json ответ */ }
  return { status: r.status, json: j };
}

/* Полный серверный вход через реальный UI (тумблер → URL → учётка → MFA tcPrompt). */
async function serverLogin(page, { pass = ADMIN.pass, mfa } = {}) {
  await page.goto(APP);
  await page.waitForSelector('#loginBtn');
  await page.check('#srvEnabled');
  await page.fill('#srvUrl', API);
  await page.fill('#srvLogin', ADMIN.login);
  await page.fill('#srvPass', pass);
  await page.click('#loginBtn');
  if (mfa !== 'none' && mfa !== 'skip') {
    await page.waitForSelector('#tcDlgInp', { timeout: 25000 });
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'tcDlgInp', null, { timeout: 6000 });
    await page.keyboard.type(mfa || totp(adminSecret()));
    await page.keyboard.press('Enter');
  }
}
async function waitConnected(page, timeout = 30000) {
  await page.waitForFunction(() => SRV.connected === true && document.getElementById('app').style.display === 'grid', null, { timeout });
}
/* Ожидание серверной синхронизации значений полей паспорта (Этап 12). */
async function waitPassSynced(page, timeout = 25000) {
  await page.waitForFunction(() => { const ov = state.passOv[state.selEnt]; return ov && ov.__s12Synced; }, null, { timeout });
}

module.exports = { API, DB, PY, ADMIN, APP, totp, adminSecret, api, serverLogin, waitConnected, waitPassSynced };
