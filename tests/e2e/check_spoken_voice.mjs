import { chromium } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';

const fixture = fileURLToPath(new URL('../../logs/test/spoken-arequita.wav', import.meta.url));
const synthesis = await fetch('http://127.0.0.1:5001/synthesize', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: 'Que podes contarme del Cerro Arequita?' }),
});
if (!synthesis.ok) throw new Error(`Piper HTTP ${synthesis.status}`);
await writeFile(fixture, Buffer.from(await synthesis.arrayBuffer()));
execFileSync(fileURLToPath(new URL('../../.venv/Scripts/python.exe', import.meta.url)), ['-c',
  'import wave,sys; reader=wave.open(sys.argv[1],"rb"); params=reader.getparams(); audio=reader.readframes(params.nframes); reader.close(); silence=bytes(params.framerate*params.nchannels*params.sampwidth); writer=wave.open(sys.argv[1],"wb"); writer.setparams(params); writer.writeframes(silence*10+audio+silence*8); writer.close()', fixture]);
const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${fixture}%noloop`, '--autoplay-policy=no-user-gesture-required'],
});
const page = await browser.newPage();
try {
  await page.goto('http://localhost:5173/?debug=1');
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.waitForFunction(() =>
    document.querySelectorAll('.user-row .message-content').length > 0 &&
    [...document.querySelectorAll('.assistant-row .message-content')].slice(1)
      .some(element => element.textContent.trim().length > 0), null, { timeout: 60000 });
  console.log('USER:', await page.locator('.user-row .message-content').allTextContents());
  console.log('ASSISTANT:', await page.locator('.assistant-row .message-content').allTextContents());
} catch (error) {
  console.error(error.message);
  console.log(await page.locator('body').innerText());
  process.exitCode = 1;
} finally {
  await page.screenshot({ path: fileURLToPath(new URL('../../logs/test/voice-spoken-check.png', import.meta.url)) });
  await browser.close();
}