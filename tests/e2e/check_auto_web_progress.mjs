import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
let progress = 'RETRIEVING';
let complete;
const answerReady = new Promise(resolve => { complete = resolve; });

try {
  await page.route('**/api/turn-progress?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ state: progress }) });
  });
  await page.route('**/api/ask-text', async route => {
    await answerReady;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      answer: 'Encontré una opción en Minas.', state: 'ANSWERABLE', route: 'WEB_SEARCH',
      web_invoked: true, rag_invoked: true, evidence: [],
    }) });
  });
  await page.goto('http://localhost:5173');
  await page.getByRole('textbox', { name: 'Mensaje para Gianna' }).fill('¿Hay un restaurante de comida etíope en Minas?');
  await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click();
  await expect(page.locator('.status-retrieving')).toBeVisible();
  await expect(page.locator('.web-search-card')).toHaveCount(0);
  progress = 'WEB_SEARCHING';
  await expect(page.locator('.web-search-card')).toBeVisible({ timeout: 5000 });
  await expect(page.locator('.web-search-card strong')).toHaveText('Gianna está buscando en la web');
  complete();
  await expect(page.locator('.assistant-row .message-content').last()).toHaveText('Encontré una opción en Minas.');
  await expect(page.locator('.web-search-card')).toHaveCount(0);
  console.log('AUTO_WEB_PROGRESS_PASS');
} finally {
  complete();
  await browser.close();
}
