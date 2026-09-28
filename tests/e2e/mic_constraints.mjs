// Verify constraints requested on a real Chrome-managed (fake hardware) track.
import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ permissions: ['microphone'] });
const page = await context.newPage();
const settings = [];
page.on('request', request => {
  if (!request.url().includes('/api/debug/trace') || request.method() !== 'POST') return;
  try { const body = request.postDataJSON(); if (body.event === 'frontend_mic_settings') settings.push(JSON.parse(body.detail)); } catch {}
});
try {
  await page.goto('http://localhost:5173/?debug=1');
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.waitForFunction(() => window.document.querySelector('.connection-dot.connected'), null, { timeout: 60000 });
  await expect.poll(() => settings.length, { timeout: 15000 }).toBeGreaterThan(0);
  const current = settings.at(-1);
  console.log('MIC SETTINGS', JSON.stringify(current));
  expect(current.echoCancellation).toBe(true);
  expect(current.noiseSuppression).toBe(true);
  // Chrome's synthetic hardware sometimes ignores AGC=false despite a
  // resolved applyConstraints promise. The app must report that mismatch.
  expect(current.autoGainControl === false || current.unsupported.includes('autoGainControl')).toBe(true);
  const direct = await page.evaluate(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false } });
    const applied = stream.getAudioTracks()[0].getSettings();
    stream.getTracks().forEach(track => track.stop());
    return { echoCancellation: applied.echoCancellation, noiseSuppression: applied.noiseSuppression, autoGainControl: applied.autoGainControl };
  });
  console.log('DIRECT CAPTURE CONTROL', JSON.stringify(direct));
} finally { await context.close(); await browser.close(); }
