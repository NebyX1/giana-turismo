// Real browser, backend, CPU retrieval models and Ollama Cloud response.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(root, 'reports', 'browser');
fs.mkdirSync(output, { recursive: true });
const base = process.env.GIANA_BASE_URL || 'http://127.0.0.1:5000';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(base);
  await expect(page.getByRole('heading', { name: '¿Qué querés conocer de Lavalleja?' })).toBeVisible();
  await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
  await page.getByRole('textbox', { name: 'Mensaje para Gianna' }).fill('¿Qué es el Cerro Arequita en Lavalleja? Usá solo la guía local, sin buscar en internet.');
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/ask-text'), { timeout: 90000 });
  await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click();
  const response = await responsePromise;
  const result = await response.json();
  expect(response.ok()).toBe(true);
  expect(result.rag_invoked).toBe(true);
  expect(result.llm_invoked).toBe(true);
  expect(result.evidence.length).toBeGreaterThan(0);
  await expect(page.locator('.assistant-row .message-content').last()).toContainText('Arequita');
  await page.getByRole('button', { name: /^Fuentes / }).click();
  await expect(page.locator('.sources-list .source-item').first()).toBeVisible();
  await page.screenshot({ path: path.join(output, 'answer.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Nueva conversación' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
  await page.getByRole('button', { name: 'Nueva conversación' }).click();
  await expect(page.locator('.assistant-row')).toHaveCount(0);
  expect(errors).toEqual([]);
  fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({ status: 'PASS', errors, route: result.route, sources: result.evidence.length }, null, 2));
  console.log('CHAT_BROWSER_PASS desktop, sources, mobile, new conversation');
} finally {
  await browser.close();
}
