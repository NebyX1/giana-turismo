import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(new URL('../..', import.meta.url).pathname);
const qa = process.env.QA_SESSION_ID || 'qa-local';
const qaDir = process.env.QA_DIR || path.join(root, 'logs', 'test', qa);
const base = process.env.GIANA_URL || 'http://localhost:5173';
fs.mkdirSync(path.join(qaDir, 'screenshots'), { recursive: true });
fs.mkdirSync(path.join(qaDir, 'turns'), { recursive: true });
const results = [];
const consoleLines = [];

function record(id, status, detail, extra = {}) { results.push({ id, status, detail, timestamp: new Date().toISOString(), ...extra }); }
async function runCase(id, fn) {
  const browser = await chromium.launch({ headless: false, executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const context = await browser.newContext({ recordHar: { path: path.join(qaDir, 'browser-network.har'), mode: 'minimal' } });
  const page = await context.newPage();
  page.on('console', m => consoleLines.push(`[${id}] ${m.type()} ${m.text()}`));
  page.on('pageerror', e => consoleLines.push(`[${id}] pageerror ${e.message}`));
  try { await fn(page); record(id, 'PASS', 'ok'); }
  catch (e) { await page.screenshot({ path: path.join(qaDir, 'screenshots', `${id}-FAIL.png`), fullPage: true }).catch(() => {}); record(id, 'FAIL', e.message); }
  await context.close(); await browser.close();
}

await runCase('E2E-001', async page => {
  await page.goto(`${base}/?debug=1&qa_session=${encodeURIComponent(qa)}`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.waitForTimeout(10000);
  const body = await page.locator('body').innerText();
  if (!body.includes('QA SESSION: ' + qa)) throw new Error('QA session is not visible in debug panel');
  const trace = await page.request.get(`${base}/api/debug/last-turn?qa_session=${encodeURIComponent(qa)}`).then(r => r.json());
  if (!trace.events.some(e => e.event === 'frontend_webrtc_connected')) throw new Error('WebRTC did not connect');
  await page.screenshot({ path: path.join(qaDir, 'screenshots', 'E2E-001-PASS.png'), fullPage: true });
});

await runCase('E2E-014', async page => {
  await page.goto(`${base}/?debug=1&e2e_test_mode=true&e2e_force_error=LLM_TIMEOUT&qa_session=${encodeURIComponent(qa)}`, { waitUntil: 'networkidle' });
  await page.getByText('El modelo tardó demasiado. Probá de nuevo.', { exact: true }).first().waitFor();
  await page.screenshot({ path: path.join(qaDir, 'screenshots', 'E2E-014-PASS.png'), fullPage: true });
  const response = await page.request.get(`${base}/api/debug/last-turn?qa_session=${encodeURIComponent(qa)}`);
  const data = await response.json();
  if (!data.events.some(e => e.event === 'frontend_error_displayed' && e.error_code === 'LLM_TIMEOUT')) throw new Error('frontend_error_displayed was not observed');
});

fs.writeFileSync(path.join(qaDir, 'browser-console.log'), consoleLines.join('\n') + '\n');
const mandatory = ['E2E-001', 'E2E-014'];
const output = { qa_session_id: qa, generated_at: new Date().toISOString(), results, mandatory, pass: mandatory.every(id => results.find(x => x.id === id)?.status === 'PASS') };
fs.writeFileSync(path.join(qaDir, 'E2E_RESULTS.json'), JSON.stringify(output, null, 2));
fs.writeFileSync(path.join(qaDir, 'E2E_RESULTS.md'), `# GIANA Voice E2E QA\n\nQA session: ${qa}\n\n${results.map(x => `- ${x.id}: ${x.status} — ${x.detail}`).join('\n')}\n\nQuality gate: ${output.pass ? 'PASS' : 'FAIL'}\n`);
process.exit(output.pass ? 0 : 1);
