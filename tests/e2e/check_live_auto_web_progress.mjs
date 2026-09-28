import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();

try {
  await page.goto('http://localhost:5173');
  await page.getByRole('textbox', { name: 'Mensaje para Gianna' }).fill('¿Cuál es el menú y precio del día de hoy en Don Jorgito?');
  const response = page.waitForResponse(item => item.url().endsWith('/api/ask-text'), { timeout: 90000 });
  await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click();
  await expect(page.locator('.status-retrieving')).toBeVisible();
  await expect(page.locator('.web-search-card')).toBeVisible({ timeout: 80000 });
  const result = await (await response).json();
  expect(result.web_invoked).toBe(true);
  expect(result.rag_invoked).toBe(true);
  await expect(page.locator('.web-search-card')).toHaveCount(0);
  await expect(page.locator('.assistant-row .message-content').last()).toHaveText(result.answer);
  console.log(JSON.stringify({ status: 'LIVE_AUTO_WEB_PROGRESS_PASS', route: result.route, state: result.state, web_invoked: result.web_invoked }));
} finally {
  await browser.close();
}
