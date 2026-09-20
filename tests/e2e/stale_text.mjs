// Isolated UI race contract, NOT proof of real model/backend behavior.
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage();
try{
  await page.goto('http://localhost:5173');
  for(const outcome of ['success','failure','consent']){
    let release;
    const blocked=new Promise(resolve=>{release=resolve;});
    await page.route('**/api/ask-text',async route=>{
      await blocked;
      await route.fulfill({status:outcome==='failure'?503:200,contentType:'application/json',body:JSON.stringify(outcome==='consent'?{state:'ASKING_WEB_PERMISSION'}:{answer:'OLD_RESPONSE_MUST_NOT_APPEAR',error_code:'OLD_FAILURE_MUST_NOT_APPEAR'})});
    });
    const request=page.waitForRequest(r=>r.url().endsWith('/api/ask-text'));
    await page.getByRole('textbox',{name:'Mensaje para Gianna'}).fill('Pregunta anterior');
    await page.getByRole('button',{name:'Enviar mensaje',exact:true}).click();
    await request;
    await page.getByRole('button',{name:'Nueva conversación'}).click();
    await expect(page.locator('.user-row')).toHaveCount(0);
    const response=page.waitForResponse(r=>r.url().endsWith('/api/ask-text'));
    release(); await response; await page.waitForTimeout(300);
    await expect(page.locator('.assistant-row')).toHaveCount(1);
    await expect(page.locator('.inline-error')).toHaveCount(0);
    await expect(page.locator('.consent-card')).toHaveCount(0);
    expect(await page.locator('body').innerText()).not.toContain('OLD_');
    await expect(page.getByText('Pregunta anterior',{exact:true})).toHaveCount(0);
    await page.unroute('**/api/ask-text');
    console.log(`PASS stale ${outcome} cannot contaminate new conversation`);
  }
}finally{await browser.close();}
