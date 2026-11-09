import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const root = process.cwd();
const fixture = path.join(root, 'logs', 'test', '20260919-030153-kokoro-migration', 'kokoro_input_query_16khz.wav');
const qa = 'kokoro-webrtc-real';
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required', `--use-file-for-fake-audio-capture=${fixture}%noloop`] });
const context = await browser.newContext(); const page = await context.newPage();
try {
  await page.goto(`http://localhost:5173/?debug=1&qa_session=${qa}`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.waitForTimeout(30000);
  const user = await page.locator('.user-row .message-content').allTextContents();
  const assistant = await page.locator('.assistant-row .message-content').allTextContents();
  const trace = await page.request.get(`http://localhost:5000/api/debug/last-turn?qa_session=${qa}`).then(r => r.json()).catch(() => ({}));
  const connected = (trace.events || []).some(e => e.event === 'frontend_webrtc_connected');
  const kokoro = (trace.events || []).filter(e => String(e.component).toLowerCase() === 'tts' && String(e.event).toLowerCase().includes('kokoro'));
  const result = { connected, user, assistant, kokoro_events: kokoro.length, trace_events: (trace.events || []).length, status: connected && assistant.some(x => x.trim()) && kokoro.length ? 'PASS' : 'PARTIAL' };
  fs.writeFileSync(path.join(root, 'logs', 'test', '20260919-030153-kokoro-migration', 'webrtc_kokoro_result.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  process.exitCode = result.status === 'PASS' ? 0 : 1;
} finally { await context.close(); await browser.close(); }
