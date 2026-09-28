// Chrome -> synthetic mic -> SmallWebRTC -> real voice pipeline -> backend.
// Negative clips must never create a user message or backend dispatch.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const fixture = fs.readFileSync(path.join(root, 'tests/e2e/fixtures/voice-resilience/input-1-1.wav')).toString('base64');
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
await context.addInitScript(() => {
  const qa = window.__noiseQA = { messages: [], audio: null, dest: null, source: null };
  const NativePeer = window.RTCPeerConnection;
  window.RTCPeerConnection = class extends NativePeer {
    createDataChannel(...args) {
      const channel = super.createDataChannel(...args);
      channel.addEventListener('message', event => { try { qa.messages.push(JSON.parse(event.data)); } catch {} });
      return channel;
    }
  };
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async constraints => {
    if (!constraints.audio) return original(constraints);
    qa.audio ||= new AudioContext();
    if (!qa.dest) {
      qa.dest = qa.audio.createMediaStreamDestination();
      qa.source = qa.audio.createConstantSource(); qa.source.offset.value = 0; qa.source.connect(qa.dest); qa.source.start();
    }
    await qa.audio.resume(); return qa.dest.stream;
  };
  qa.play = async (kind, base64) => {
    const audio = qa.audio; const rate = audio.sampleRate;
    let buffer;
    if (base64) {
      buffer = await audio.decodeAudioData(Uint8Array.from(atob(base64), c => c.charCodeAt(0)).buffer);
    } else {
      buffer = audio.createBuffer(1, Math.round(rate * 1.5), rate);
      const data = buffer.getChannelData(0); let seed = 2026;
      const noise = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 2147483648 - 1; };
      for (let i = 0; i < data.length; i++) {
        const t = i / rate;
        if (kind === 'white_low') data[i] = .0002 * noise();
        if (kind === 'pink_low') data[i] = .0001 * Math.sin(2*Math.PI*17*t) + .0001*noise();
        if (kind === 'hum_50') data[i] = .002*Math.sin(2*Math.PI*50*t);
        if (kind === 'hum_60') data[i] = .002*Math.sin(2*Math.PI*60*t);
        if (kind === 'fan') data[i] = .002*Math.sin(2*Math.PI*110*t) + .001*noise();
        if (kind === 'click' && i === Math.floor(rate*.5)) data[i] = .9;
        if (kind === 'knock' && i >= rate*.5 && i < rate*.51) data[i] = .6*Math.exp(-(i-rate*.5)/(rate*.002))*noise();
        if (kind === 'clicks' && [0.3, 0.6, 0.9, 1.2].some(x => i === Math.floor(rate*x))) data[i] = .9;
        if (kind === 'keyboard' && [0.2,0.35,0.6,0.85,1.1].some(x => i >= Math.floor(rate*x) && i < Math.floor(rate*x)+30)) data[i] = .15*noise();
        if (kind === 'rub' && i >= rate*.6 && i < rate*.75) data[i] = .015*noise();
      }
    }
    const source = audio.createBufferSource(); source.buffer = buffer; source.connect(qa.dest);
    await audio.resume(); await new Promise(resolve => { source.onended = resolve; source.start(); });
  };
});
const page = await context.newPage();
const errors = []; page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto('http://localhost:5173/?debug=1');
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.waitForFunction(() => window.__noiseQA.messages.some(x => x.type === 'bot-stopped-speaking'), null, { timeout: 60000 });
  const kinds = ['silence','white_low','pink_low','hum_50','hum_60','click','knock','clicks','keyboard','fan','rub'];
  const baseline = await page.evaluate(() => window.__noiseQA.messages.length);
  for (const kind of kinds) await page.evaluate(kind => window.__noiseQA.play(kind), kind);
  await page.waitForTimeout(4000);
  const noiseEvents = await page.evaluate(index => window.__noiseQA.messages.slice(index), baseline);
  const backendDispatches = noiseEvents.filter(x => x.type === 'server-message' && x.data?.event === 'backend_dispatch_started');
  const userTurns = noiseEvents.filter(x => x.type === 'server-message' && x.data?.event === 'user_turn_finalized');
  expect(backendDispatches, 'noise must not call backend').toHaveLength(0);
  expect(userTurns, 'noise must not produce a user turn').toHaveLength(0);
  await expect(page.locator('.user-row')).toHaveCount(0);
  console.log(`NEGATIVE PASS ${kinds.length}/${kinds.length}: ${kinds.join(', ')}`);
  const offset = await page.evaluate(() => window.__noiseQA.messages.length);
  await page.evaluate(base64 => window.__noiseQA.play('voice', base64), fixture);
  await page.waitForFunction(offset => window.__noiseQA.messages.slice(offset).some(x => x.type === 'server-message' && x.data?.event === 'assistant_response_finalized'), offset, { timeout: 90000 });
  const valid = await page.evaluate(offset => window.__noiseQA.messages.slice(offset), offset);
  const validUsers = valid.filter(x => x.type === 'server-message' && x.data?.event === 'user_turn_finalized');
  const validDispatches = valid.filter(x => x.type === 'server-message' && x.data?.event === 'backend_dispatch_started');
  expect(validUsers).toHaveLength(1); expect(validDispatches).toHaveLength(1);
  await expect(page.locator('.user-row')).toHaveCount(1);
  console.log(`POSITIVE PASS: ${validUsers[0].data.text}`);
  expect(errors).toHaveLength(0);
} finally { await context.close(); await browser.close(); }
