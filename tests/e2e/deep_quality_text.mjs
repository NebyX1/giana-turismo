import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('../..',import.meta.url));
const out=path.join(root,'logs/test/deep-quality-repair',`text-${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
const norm=s=>s.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
const cases=[
  ['Hola Giana, ¿estás ahí?',r=>{expect(r.route).toBe('CONVERSATION');expect(r.rag_invoked).toBe(false);expect(norm(r.answer)).toContain('escucho');}],
  ['Hola Giana, necesito que me digas si hay algún lugar donde comer un asado en la ciudad de Minas',r=>{expect(norm(r.answer)).toContain('don jorgito');expect(norm(r.answer)).toContain('pololo');expect(r.web_invoked).toBe(false);}],
  ['Salud',r=>expect(r.route).toBe('CONVERSATION')],
  ['No, no, te pedí que me recomendaras un lugar donde comer un asado en la ciudad de Minas',r=>{expect(norm(r.answer)).toContain('don jorgito');expect(norm(r.answer)).toContain('pololo');}],
  ['¿Cuál es la dirección de Don Jorgito?',r=>expect(r.answer).toContain('947')],
  ['¿Y su teléfono?',r=>expect(r.answer).toMatch(/94\D*710\D*608/)],
  ['¿Qué eventos culturales hay esta semana en la ciudad de Minas?',checkWeek],
  ['Che, pero hay una cosa que no estás haciendo bien. Cá en la web, información sobre eventos culturales.',checkWeek],
  ['¿Y mañana?',r=>{expect(r.route).toBe('WEB_SEARCH');expect(r.requested_window).toEqual({start:'2026-09-20',end:'2026-09-20'});}],
  ['¿Y en Mariscala?',r=>{expect(r.route).toBe('WEB_SEARCH');expect(r.requested_window).toEqual({start:'2026-09-20',end:'2026-09-20'});expect(r.search_queries.every(q=>q.toLowerCase().includes('mariscala'))).toBe(true);}],
  ['¿Qué podés contarme del Cerro Arequita?',r=>{expect(r.rag_invoked).toBe(true);expect(norm(r.answer)).toContain('arequita');}],
  ['¿Qué día y hora es?',r=>{expect(r.route).toBe('CLOCK');expect(r.answer).toContain(r.time_context.time);}],
  ['¿Cuál es el menú y precio del día de hoy en Don Jorgito?',r=>{expect(r.web_invoked).toBe(true);expect(r.rag_invoked).toBe(true);expect(r.search_attempts.length).toBeGreaterThan(0);}],
  ['¿Qué eventos culturales hay en octubre de 2026 en Minas?',r=>{expect(r.route).toBe('WEB_SEARCH');expect(r.state).toBe('ANSWERABLE');expect(norm(r.answer)).toContain('semana de lavalleja');expect(r.requested_window).toEqual({start:'2026-10-01',end:'2026-10-31'});}],
  ['Hola de nuevo, ¿me recibís bien?',r=>expect(r.route).toBe('CONVERSATION')],
];
function checkWeek(r){
  expect(r.route).toBe('WEB_SEARCH');
  if(new Date(r.time_context.now)<new Date('2026-09-19T20:30:00-03:00')){
    expect(r.state).toBe('ANSWERABLE');
    expect(norm(r.answer)).toContain('entre sierras');
    expect(r.answer).toMatch(/20[:.]30/);
  }else{
    expect(['ANSWERABLE','NO_CONFIRMED_RESULT']).toContain(r.state);
    expect(norm(r.answer)).not.toMatch(/entre sierras.{0,100}(sera|podes ir|se hace)/);
  }
  expect((r.evidence_assessment?.events||[]).some(e=>norm(e.name).includes('milonga'))).toBe(false);
  expect(r.requested_window).toEqual({start:'2026-09-19',end:'2026-09-20'});
}
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const results=[];
try{
  await page.goto('http://localhost:5173/');
  for(let i=0;i<cases.length;i++){
    await page.getByRole('textbox',{name:'Mensaje para Gianna'}).fill(cases[i][0]);
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/ask-text'),{timeout:85000});
    await page.getByRole('button',{name:'Enviar mensaje',exact:true}).click();
    const http=await pending,r=await http.json();
    fs.writeFileSync(path.join(out,`response-${i+1}.json`),JSON.stringify(r,null,2));
    expect(http.ok()).toBe(true);
    cases[i][1](r);
    expect(r.answer).not.toContain('**');
    await expect(page.locator('.assistant-row .message-content').last()).toHaveText(r.answer);
    await expect(page.locator('.user-row')).toHaveCount(i+1);
    await expect(page.locator('.inline-error')).toHaveCount(0);
    await page.screenshot({path:path.join(out,`turn-${i+1}.png`)});
    results.push({turn:i+1,status:'PASS',question:cases[i][0],response:r});
    console.log(`TURN ${i+1} PASS ${r.route}`);
  }
  const history=await page.locator('.message-content').allTextContents();
  await page.reload();
  expect(await page.locator('.message-content').allTextContents()).toEqual(history);
  await page.getByRole('button',{name:'Nueva conversación'}).click();
  await expect(page.locator('.user-row')).toHaveCount(0);
  results.push({test:'reload preserves history; new conversation clears it',status:'PASS'});
}catch(error){
  results.push({status:'FAIL',error:error.message});
  await page.screenshot({path:path.join(out,'failure.png')});
  process.exitCode=1;console.error(error);
}finally{
  fs.writeFileSync(path.join(out,'RESULTS.json'),JSON.stringify(results,null,2));
  await browser.close();console.log(`ARTIFACTS ${out}`);
}
