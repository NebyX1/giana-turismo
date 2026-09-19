import { chromium, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const page = await browser.newPage();
try {
  await page.goto('http://localhost:5173');
  await page.getByRole('textbox', { name: 'Mensaje para Giana' }).fill('Buscar en la web horarios del Hotel Minas Uruguay');
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/ask-text'), { timeout: 90000 });
  await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click();
  await expect(page.locator('.status-web_searching')).toBeVisible();
  await page.screenshot({ path: fileURLToPath(new URL('../../logs/test/web-search-pending.png', import.meta.url)) });
  const response = await responsePromise;
  const result = await response.json();
  expect(response.ok()).toBeTruthy();
  expect(result.route).toBe('WEB_SEARCH');
  expect(result.web_invoked).toBe(true);
  expect(result.state).toBe('ANSWERABLE');
  expect(result.evidence.length).toBeGreaterThan(0);
  await expect(page.locator('.assistant-row .message-content').last()).toHaveText(result.answer);
  await expect(page.locator('.status-web_searching')).toHaveCount(0);
  console.log(JSON.stringify({ status: 'PASS', route: result.route, sources: result.evidence.length, answer: result.answer }));
} finally {
  await browser.close();
}