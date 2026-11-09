import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const session = fs.readFileSync(path.join(root, 'logs/test/CURRENT_SESSION.txt'), 'utf8').trim();
const out = path.join(root, 'logs/test/web-research-repair', `text-${Date.now()}`);
fs.mkdirSync(out, { recursive: true });
const cases = [
  ['Hola Giana, ¿podés decirme el día de hoy cuál es?', 'CLOCK'],
  ['¿Podés buscar por mí en la web qué eventos culturales hay en Minas?', 'WEB_SEARCH'],
  ['Te di una orden bien clara, necesito que busques por mí en la web qué eventos culturales hay en estas fechas en la ciudad de Minas.', 'WEB_SEARCH'],
  ['¿Qué eventos culturales hay esta semana en Minas?', 'WEB_SEARCH'],
  ['¿Qué podés contarme del Cerro Arequita?', 'RAG'],
  ['¿Qué día y hora es?', 'CLOCK'],
];
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const results = [];
try {
  await page.goto('http://localhost:5173/');
  for (let index = 0; index < cases.length; index++) {
    await page.getByRole('textbox', { name: 'Mensaje para Gianna' }).fill(cases[index][0]);
    const pending = page.waitForResponse(r => r.url().endsWith('/api/ask-text'), { timeout: 90000 });
    await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click();
    const response = await pending;
    const data = await response.json();
    fs.writeFileSync(path.join(out, `response-${index + 1}.json`), JSON.stringify(data, null, 2));
    expect(response.ok()).toBe(true);
    if (cases[index][1] === 'RAG') expect(data.rag_invoked).toBe(true);
    else expect(data.route).toBe(cases[index][1]);
    await expect(page.locator('.assistant-row .message-content').last()).toHaveText(data.answer);
    if (data.route === 'CLOCK') {
      expect(data.time_context.timezone).toBe('America/Montevideo');
      expect(data.answer).toContain(data.time_context.time);
      expect(data.answer).toContain(data.time_context.weekday);
      expect(data.web_invoked).toBe(false);
      const current = await (await fetch('http://localhost:5000/api/time')).json();
      expect(Math.abs(Date.parse(current.now) - Date.parse(data.time_context.now))).toBeLessThan(5000);
    } else if (data.route === 'WEB_SEARCH') {
      expect(data.web_invoked).toBe(true);
      expect(data.rag_invoked).toBe(false);
      expect(data.state).toBe('ANSWERABLE');
      expect(data.llm_invoked).toBe(true);
      expect(data.sources_read).toBeGreaterThan(0);
      expect(data.search_queries.length).toBe(3);
      expect(data.answer).not.toContain('No te voy a recomendar');
      expect(data.answer).not.toMatch(/\[\d/);
      if (index === 1 || index === 2) {
        // Dated positive acceptance: live sources announce this event for this period.
        expect(data.time_context.date).toBe('2026-09-19');
        expect(data.answer).toMatch(/Semana de Lavalleja/i);
        expect(data.answer).toMatch(/7.{0,10}11/);
        expect(data.answer).toMatch(/octubre/i);
        expect(data.evidence.some(x => /7.{0,15}11/.test(x.text) && /2026/.test(x.text))).toBe(true);
        if (index === 2) expect(data.requested_window).toEqual(results[1].requested_window);
      } else {
        expect(data.requested_window).toEqual({ start: data.time_context.date, end: data.time_context.week_end });
        // A real published option today; absence is not a passing result.
        expect(data.answer).toMatch(/Entre Sierras/i);
        expect(data.answer).toMatch(/20[:.]30/);
      }
      const sourcePanel = page.locator('.assistant-row').last().locator('.sources-panel');
      if ((data.evidence?.length || data.searched_sources?.length) > 0) {
        await sourcePanel.locator('button').click();
        expect(await sourcePanel.locator('a[href^="https://"]').count()).toBeGreaterThan(0);
      }
    } else {
      expect(data.rag_invoked).toBe(true);
      expect(data.answer).toMatch(/Arequita/i);
    }
    await page.screenshot({ path: path.join(out, `turn-${index + 1}.png`) });
    results.push({ status: 'PASS', query: cases[index][0], ...data });
    console.log(`PASS ${data.route} ${data.state}: ${data.answer}`);
  }
  const history = await page.locator('.message-content').allTextContents();
  await page.reload();
  expect(await page.locator('.message-content').allTextContents()).toEqual(history);
} catch (error) {
  results.push({ status: 'FAIL', error: error.message });
  await page.screenshot({ path: path.join(out, 'failure.png') });
  process.exitCode = 1;
  console.error(error);
} finally {
  fs.writeFileSync(path.join(out, 'RESULTS.json'), JSON.stringify(results, null, 2));
  await browser.close();
  console.log(`ARTIFACTS ${out}`);
}
