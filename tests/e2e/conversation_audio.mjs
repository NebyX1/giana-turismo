// Real browser -> WebRTC -> STT -> backend -> Piper -> remote audio.
// Only the test browser's microphone source is controlled. No app responses
// or production modules are mocked. Each turn waits for complete playback.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const session = fs.readFileSync(path.join(root, 'logs/test/CURRENT_SESSION.txt'), 'utf8').trim();
const out = path.join(session, `browser-${Date.now()}`);
fs.mkdirSync(out, { recursive: true });
const mode = process.env.GIANA_E2E_MODE || 'conversation';
const cases = mode === 'voice-context' ? [
  ['¿Y su teléfono?', 'telefono'],
  ['¿Y su dirección?', 'direccion'],
  ['Quiero comer vegano en Minas.', 'vegano'],
  ['¿Y su dirección?', 'direccion'],
] : mode === 'voice-resilience' ? [
  ['Hola Giana, ¿estás ahí?', 'ahi'],
  ['Contame en detalle todo lo que se puede visitar en el Cerro Arequita y su entorno.', 'arequita'],
  ['Pará, decime qué día y hora es ahora.', 'hora'],
  ['Hola, ¿me recibís bien? Quiero comer asado en Minas.', 'asado'],
  ['Gracias, hasta después.', 'gracias'],
] : mode === 'deep-pause' ? [
  ['Quiero saber dónde podemos || comer algo vegano en la ciudad de Minas.', 'vegano', ['comer', 'minas']],
] : mode === 'deep-quality' ? [
  ['Hola Giana, necesito que me digas si hay algún lugar donde comer un asado en la ciudad de Minas.', 'asado'],
  ['Salud.', 'salud'],
  ['No, no, te pedí que me recomendaras un lugar donde comer un asado en la ciudad de Minas.', 'asado'],
  ['¿Cuál es el teléfono de Don Jorgito?', 'telefono'],
  ['¿Qué eventos culturales hay esta semana en la ciudad de Minas?', 'eventos'],
  ['Buscá en la web información sobre eventos culturales.', 'eventos'],
  ['¿Qué podés contarme del Cerro Arequita?', 'arequita'],
  ['Quiero saber dónde podemos || comer algo vegano en la ciudad de Minas.', 'vegano', ['comer', 'minas']],
  ['¿Puedo llevar un perro al Penitente?', 'penitente'],
  ['¿Qué día y hora es?', 'hora'],
  ['Hola Giana, ¿estás ahí?', 'ahi'],
  ['Hola, ¿me recibís bien? Quiero comer asado en Minas.', 'asado'],
  ['¿Qué eventos culturales hay en octubre de 2026 en Minas?', 'octubre'],
  ['Buenas noches Giana, ¿seguís ahí conmigo?', 'conmigo'],
] : mode === 'web-research' ? [
  ['¿Qué día y hora es?', 'hora'],
  ['¿Podés buscar por mí en la web qué eventos culturales hay en Minas?', 'minas'],
  ['Necesito que busques en la web qué eventos culturales hay en estas fechas en Minas.', 'minas'],
  ['¿Qué podés contarme del Cerro Arequita?', 'arequita'],
  ['¿Qué fecha es hoy?', 'fecha'],
] : mode === 'time-web' ? [
  ['Giana, ¿qué día y hora es?', 'hora'],
  ['¿Qué eventos culturales hay esta semana en Minas?', 'semana'],
  ['¿No podés buscar en la web algún evento cultural para recomendarme en Minas?', 'web'],
  ['Buscá en la web la página oficial del Teatro Lavalleja.', 'web'],
  ['¿Qué fecha es hoy?', 'fecha'],
] : mode === 'pauses' ? [
  ['Quiero visitar un lugar en Lavalleja y también || conocer otro paseo por Minas. ¿Qué me recomendás?', 'minas', ['lavalleja', 'minas']],
  ['¿Quién sos y cómo podés ayudarme?', 'ayudarme'],
  ['Gracias Giana, ¿seguís escuchándome?', 'giana'],
] : [
  ['Hola Giana, ¿me estás escuchando?', 'escuchando'],
  ['¿Qué podés contarme del Cerro Arequita?', 'arequita'],
  ['¿Y qué otro lugar puedo conocer cerca de Minas?', 'minas'],
  ['Quiero ir con mi familia el fin de semana. Nos gustan los paisajes y caminar. ¿Qué podemos conocer en Villa Serrana?', 'serrana'],
  ['¿Quién sos y cómo podés ayudarme?', 'ayudarme'],
  ['¿Qué puedo hacer en el Salto del Penitente?', 'penitente'],
  ['¿Me recomendás un paseo por Minas?', 'minas'],
  ['Gracias Giana, ¿seguís escuchándome?', 'giana'],
  ['Hola Giana, ¿me estás escuchando?', 'escuchando'],
  ['¿Qué puedo visitar en Villa Serrana?', 'serrana'],
];
const fixtures = [];
for (const [text] of cases) {
  const parts = [];
  for (const part of text.split(' || ')) {
  const cached = path.join(root, 'tests/e2e/fixtures', mode === 'deep-pause' ? 'deep-quality' : mode, `input-${mode === 'deep-pause' ? 8 : fixtures.length + 1}-${parts.length + 1}.wav`);
  let wav;
  if (fs.existsSync(cached)) wav = fs.readFileSync(cached);
  else {
    const response = await fetch('http://127.0.0.1:5001/synthesize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: part }) });
    if (!response.ok) throw new Error(`fixture TTS HTTP ${response.status}`);
    wav = Buffer.from(await response.arrayBuffer());
  }
  fs.writeFileSync(path.join(out, `input-${fixtures.length + 1}-${parts.length + 1}.wav`), wav);
  parts.push(wav.toString('base64'));
  }
  fixtures.push(parts);
}
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, recordHar: { path: path.join(out, 'network.har'), content: 'omit' } });
await context.addInitScript(() => {
  const qa = window.__qa = { peers: [], messages: [], recordings: [], audio: null, dest: null };
  const NativePeer = window.RTCPeerConnection;
  window.RTCPeerConnection = class extends NativePeer {
    constructor(...args) {
      super(...args); qa.peers.push(this);
      this.addEventListener('track', ({ track }) => {
        if (track.kind !== 'audio') return;
        const recording = { chunks: [], recorder: new MediaRecorder(new MediaStream([track])) };
        recording.recorder.ondataavailable = event => { if (event.data.size) recording.chunks.push(event.data); };
        recording.recorder.start(250); qa.recordings.push(recording);
      });
    }
    createDataChannel(...args) {
      const channel = super.createDataChannel(...args);
      channel.addEventListener('message', event => { try { qa.messages.push({ time: Date.now(), ...JSON.parse(event.data) }); } catch {} });
      return channel;
    }
  };
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async constraints => {
    if (!constraints.audio) return original(constraints);
    qa.audio ||= new AudioContext();
    if (!qa.dest || qa.dest.stream.getAudioTracks().every(track => track.readyState === 'ended')) {
      qa.dest = qa.audio.createMediaStreamDestination();
      qa.silence?.disconnect(); qa.silence?.stop(); qa.silence = null;
    }
    if (!qa.silence) { qa.silence = qa.audio.createConstantSource(); qa.silence.offset.value = 0; qa.silence.connect(qa.dest); qa.silence.start(); }
    await qa.audio.resume();
    return qa.dest.stream;
  };
  qa.play = async base64 => {
    const buffer = Uint8Array.from(atob(base64), c => c.charCodeAt(0)).buffer;
    const source = qa.audio.createBufferSource();
    source.buffer = await qa.audio.decodeAudioData(buffer); source.connect(qa.dest);
    await qa.audio.resume();
    await new Promise(resolve => { source.onended = resolve; source.start(); });
  };
  qa.stats = async () => {
    const stats = [];
    for (const peer of qa.peers) for (const report of (await peer.getStats()).values()) {
      if (report.type === 'inbound-rtp' && report.kind === 'audio') stats.push({ energy: report.totalAudioEnergy || 0, bytes: report.bytesReceived, samples: report.totalSamplesReceived });
    }
    return stats;
  };
});
const page = await context.newPage();
const logs = [];
page.on('console', m => logs.push(`${m.type()} ${m.text()}`));
page.on('pageerror', e => logs.push(`PAGE_ERROR ${e.message}`));
const results = [];
const startRequests = [];
page.on('request', r => { if(r.url().endsWith('/start') && r.method()==='POST') startRequests.push(r.postDataJSON()); });
const norm = s => s.normalize('NFD').replace(/\p{Diacritic}/gu, '').replace(/\s+/g, ' ').trim().toLowerCase();
async function saveRecordings(label) {
  const recordings = await page.evaluate(async () => {
    const output = [];
    for (const rec of window.__qa.recordings) {
      if (rec.recorder.state !== 'inactive') await new Promise(resolve => { rec.recorder.onstop = resolve; rec.recorder.stop(); });
      output.push(await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.readAsDataURL(new Blob(rec.chunks, { type: 'audio/webm' })); }));
    }
    return output;
  }).catch(() => []);
  recordings.forEach((data, i) => fs.writeFileSync(path.join(out, `received-${label}-${i}.webm`), Buffer.from(data, 'base64')));
}
try {
  await page.goto('http://localhost:5173/?debug=1');
  let countOffset = 0;
  if(mode==='voice-context'){
    await page.getByRole('textbox',{name:'Mensaje para Gianna'}).fill('¿Cuál es la dirección de Don Jorgito en Minas?');
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/ask-text'),{timeout:85000});
    await page.getByRole('button',{name:'Enviar mensaje',exact:true}).click();
    const response=await pending, data=await response.json();
    expect(response.ok()).toBe(true);expect(data.answer).toContain('947');
    await expect(page.locator('.assistant-row .message-content').last()).toHaveText(data.answer);
    countOffset=1;
    results.push({test:'text establishes entity before voice connection',status:'PASS',answer:data.answer});
  }
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.waitForFunction(() => window.__qa.messages.some(m => m.type === 'bot-stopped-speaking'), null, { timeout: 60000 });
  for (let index = 0; index < cases.length; index++) {
    if (index === 8 || (mode==='voice-context' && index===1)) {
      const history = await page.locator('.message-content').allTextContents();
      await saveRecordings('before-reconnect');
      await page.reload();
      expect(await page.locator('.message-content').allTextContents()).toEqual(history);
      await page.getByRole('button', { name: 'Activar micrófono' }).click();
      await page.waitForFunction(() => window.__qa.messages.some(m => m.type === 'bot-stopped-speaking'), null, { timeout: 60000 });
      results.push({ test: 'reconnect preserves history and plays welcome', status: 'PASS' });
    }
    if(mode==='voice-context' && index===2){
      await page.getByRole('button',{name:'Nueva conversación'}).click();
      await expect(page.locator('.user-row')).toHaveCount(0);
      countOffset=-2;
      const offset=await page.evaluate(()=>window.__qa.messages.length);
      await page.getByRole('button',{name:'Activar micrófono'}).click();
      await page.waitForFunction(offset=>window.__qa.messages.slice(offset).some(m=>m.type==='bot-stopped-speaking'),offset,{timeout:60000});
      expect(startRequests[1].body.conversation_id).toBe(startRequests[0].body.conversation_id);
      expect(startRequests[2].body.conversation_id).not.toBe(startRequests[0].body.conversation_id);
      results.push({test:'reconnect shares logical id; new conversation disconnects and changes id',status:'PASS'});
    }
    const offset = await page.evaluate(() => window.__qa.messages.length);
    const energyBefore = await page.evaluate(() => window.__qa.stats());
    for (let part = 0; part < fixtures[index].length; part++) {
      if (part) await page.waitForTimeout(900);
      await page.evaluate(wav => window.__qa.play(wav), fixtures[index][part]);
    }
    await page.waitForFunction(offset => window.__qa.messages.slice(offset).some(m => m.type === 'server-message' && m.data?.event === 'assistant_response_finalized'), offset, { timeout: 90000 });
    if(mode==='voice-resilience' && index===1){
      await page.waitForFunction(offset=>window.__qa.messages.slice(offset).some(m=>m.type==='bot-started-speaking'),offset,{timeout:30000});
      await page.waitForTimeout(400);
      const events=await page.evaluate(offset=>window.__qa.messages.slice(offset),offset);
      const answer=events.find(m=>m.type==='server-message'&&m.data?.event==='assistant_response_finalized').data;
      expect(answer.text.length).toBeGreaterThan(150);
      expect(events.some(m=>m.type==='bot-stopped-speaking')).toBe(false);
      results.push({turn:2,status:'PASS',test:'long answer is playing before deliberate interruption',generation_id:answer.generation_id,answer:answer.text});
      fs.writeFileSync(path.join(out,'interruption-target.json'),JSON.stringify({answer,events},null,2));
      continue;
    }
    // TTSTextFrames are emitted after transport playout, unlike synthesis stop.
    await page.waitForFunction(({offset,interrupted}) => {
      const events = window.__qa.messages.slice(offset);
      const answer = events.find(m => m.type === 'server-message' && m.data?.event === 'assistant_response_finalized')?.data.text;
      const spoken = events.filter(m => m.type === 'bot-tts-text').map(m => m.data.text).join(' ');
      const norm = s => s.replace(/\s+/g, ' ').trim();
      return answer && (interrupted ? norm(spoken).endsWith(norm(answer)) : norm(spoken) === norm(answer));
    }, {offset,interrupted:mode==='voice-resilience'&&index===2}, { timeout: 90000 });
    await page.waitForFunction(offset => window.__qa.messages.slice(offset).some(m => m.type === 'bot-stopped-speaking'), offset, { timeout: 90000 });
    const messages = await page.evaluate(offset => window.__qa.messages.slice(offset), offset);
    const users = messages.filter(m => m.type === 'server-message' && m.data?.event === 'user_turn_finalized');
    const answers = messages.filter(m => m.type === 'server-message' && m.data?.event === 'assistant_response_finalized');
    expect(users.length, 'one full user turn').toBe(1);
    expect(answers.length, 'one full answer').toBe(1);
    const user = users[0].data, answer = answers[0].data;
    if(mode==='voice-context'){
      if(index===0) expect(answer.text).toMatch(/94\D*710\D*608/);
      if(index===1) expect(answer.text).toContain('947');
      if(index===2){expect(norm(answer.text)).toContain('don tadeo');expect(norm(answer.text)).not.toContain('chivas');}
      if(index===3){expect(answer.text).toContain('748');expect(norm(answer.text)).not.toContain('jorgito');}
    }
    if(mode==='voice-resilience'){
      if(index===0 || index===4) expect(answer.route).toBe('CONVERSATION');
      if(index===2){expect(answer.route).toBe('CLOCK');expect(answer.text).toContain(answer.time_context.time);}
      if(index===3){expect(norm(answer.text)).toContain('jorgito');expect(norm(answer.text)).toContain('pololo');}
    }
    if (mode === 'deep-pause') expect(norm(answer.text)).toContain('don tadeo');
    if (mode === 'deep-quality') {
      if (index === 0 || index === 2) {
        expect(norm(answer.text)).toContain('don jorgito');
        expect(norm(answer.text)).toContain('pololo');
        expect(answer.web_invoked).not.toBe(true);
      } else if (index === 1) {
        expect(answer.route).toBe('CONVERSATION');
        expect(norm(answer.text)).not.toContain('servicios de salud');
      } else if (index === 3) {
        expect(answer.text).toMatch(/94\D*710\D*608/);
      } else if (index === 4 || index === 5) {
        expect(answer.web_invoked).toBe(true);
        if(new Date(answer.time_context.now)<new Date('2026-09-19T20:30:00-03:00')){
          expect(norm(answer.text)).toContain('entre sierras');
          expect(answer.text).toMatch(/20[:.]30/);
        } else {
          expect(['ANSWERABLE','NO_CONFIRMED_RESULT']).toContain(answer.state);
          expect(norm(answer.text)).not.toMatch(/entre sierras.{0,100}(sera|podes ir|se hace)/);
        }
        if(new Date(answer.time_context.now)>=new Date('2026-09-19T20:30:00-03:00'))
          expect(norm(answer.text)).not.toMatch(/(?:podes visitar|te recomiendo|tenes).{0,60}milonga/);
        expect(answer.requested_window).toEqual({start:'2026-09-19',end:'2026-09-20'});
      } else if (index === 6) expect(norm(answer.text)).toContain('arequita');
      else if (index === 7) expect(norm(answer.text)).toContain('don tadeo');
      else if (index === 8) expect(norm(answer.text)).toContain('correa');
      else if(index === 9) {
        expect(answer.route).toBe('CLOCK');
        expect(answer.text).toContain(answer.time_context.time);
      } else if(index===10 || index===13){
        expect(answer.route).toBe('CONVERSATION');expect(answer.rag_invoked).not.toBe(true);
      } else if(index===11){
        expect(norm(answer.text)).toContain('jorgito');expect(norm(answer.text)).toContain('pololo');
      } else if(index===12){
        expect(answer.web_invoked).toBe(true);expect(answer.state).toBe('ANSWERABLE');
        expect(norm(answer.text)).toContain('semana de lavalleja');
        expect(answer.requested_window).toEqual({start:'2026-10-01',end:'2026-10-31'});
      }
      expect(answer.text).not.toContain('**');
    }
    if (mode === 'time-web') {
      if (index === 0 || index === 4) {
        expect(answer.route).toBe('CLOCK');
        expect(answer.time_context.timezone).toBe('America/Montevideo');
        expect(answer.text).toContain(answer.time_context.date_label);
        expect(answer.text).toContain(answer.time_context.time);
      } else {
        expect(answer.route).toBe('WEB_SEARCH');
        expect(answer.web_invoked).toBe(true);
        expect(answer.state).toBe('ANSWERABLE');
        if (index === 1 || index === 2) {
          const clock = await (await fetch('http://localhost:5000/api/time')).json();
          expect(answer.requested_window.start).toBe(clock.date);
          expect(answer.requested_window.end).toBe(clock.week_end);
          expect(answer.text).not.toContain('2025');
          expect(answer.text).toMatch(/Entre Sierras/i);
          expect(answer.text).toMatch(/20[:.]30/);
        }
        if (index === 3) {
          expect(answer.state).toBe('ANSWERABLE');
          expect(answer.sources.some(source => /^https?:/.test(source.url))).toBe(true);
        }
      }
    }
    if (mode === 'web-research') {
      if (index === 0 || index === 4) {
        expect(answer.route).toBe('CLOCK');
        expect(answer.text).toContain(answer.time_context.date_label);
        expect(answer.text).toContain(answer.time_context.time);
      } else if (index === 1 || index === 2) {
        expect(answer.route).toBe('WEB_SEARCH');
        expect(answer.state).toBe('ANSWERABLE');
        expect(answer.text).toMatch(/Semana de Lavalleja/i);
        expect(answer.text).toMatch(/7.{0,10}11/);
        expect(answer.text).toMatch(/octubre/i);
        expect(answer.sources.some(source => /^https?:/.test(source.url))).toBe(true);
      } else {
        expect(answer.text).toMatch(/Arequita/i);
        expect(answer.web_invoked).not.toBe(true);
      }
    }
    const playedText = messages.filter(m => m.type === 'bot-tts-text').map(m => m.data.text).join(' ');
    if(mode==='voice-resilience'&&index===2) expect(norm(playedText)).toMatch(new RegExp(norm(answer.text).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$'));
    else expect(norm(playedText), 'entire answer completed transport playout').toBe(norm(answer.text));
    expect(norm(user.text)).toContain(cases[index][1]);
    for (const keyword of cases[index][2] || []) expect(norm(user.text), 'both sides of the pause preserved').toContain(keyword);
    await expect(page.locator('.user-row .message-content').last()).toHaveText(user.text);
    await expect(page.locator('.assistant-row .message-content').last()).toHaveText(answer.text);
    await expect(page.locator('.user-row')).toHaveCount(index + 1 + countOffset);
    await expect(page.locator('.assistant-row')).toHaveCount(index + 2 + countOffset);
    const energyAfter = await page.evaluate(() => window.__qa.stats());
    expect(energyAfter.reduce((n, x) => n + x.energy, 0)).toBeGreaterThan(energyBefore.reduce((n, x) => n + x.energy, 0));
    const trace = fs.readFileSync(path.join(session, 'trace.jsonl'), 'utf8').split('\n').filter(s => s.trim()).map(s => JSON.parse(s.replace(/^\uFEFF/, '')));
    const segments = trace.filter(e => e.event === 'tts_segment_completed' && e.generation_id === answer.generation_id);
    if(mode==='voice-resilience'&&index===2){
      const target=results.find(r=>r.turn===2);
      expect(trace.some(e=>e.event==='vad_speech_started'&&e.generation_id===target.generation_id),'speech started during old answer').toBe(true);
      expect(trace.some(e=>e.event==='interruption_received'&&e.session_id===answer.session_id&&e.turn_id===user.turn_id),'transport interruption received for replacement turn').toBe(true);
      const speechStart=messages.find(m=>m.type==='user-started-speaking')?.time;
      const oldStop=messages.find(m=>m.type==='bot-stopped-speaking')?.time;
      expect(speechStart).toBeTruthy();expect(oldStop).toBeTruthy();
      expect(oldStop-speechStart,'old playback stops promptly').toBeLessThan(1500);
      const newStart=messages.find(m=>m.type==='bot-started-speaking')?.time;
      expect(newStart).toBeGreaterThan(oldStop);
      expect(messages.filter(m=>m.type==='bot-tts-text'&&m.time>newStart).every(m=>norm(answer.text).includes(norm(m.data.text))),'no old text after replacement starts').toBe(true);
      results.push({test:'real barge-in stops playback and replacement answer completes',status:'PASS',stopLatencyMs:oldStop-speechStart});
    }
    expect(norm(segments.map(e => e.tts_text).join(' ')), 'all answer sentences synthesized').toBe(norm(answer.text));
    expect(segments.every(e => e.audio_bytes > 0)).toBe(true);
    results.push({ turn: index + 1, status: 'PASS', user: user.text, answer: answer.text, route: answer.route, state: answer.state, time_context: answer.time_context, requested_window: answer.requested_window, web_invoked: answer.web_invoked, playedText, generation_id: answer.generation_id, segments: segments.length, energyBefore, energyAfter });
    fs.writeFileSync(path.join(out, `turn-${index + 1}.json`), JSON.stringify({ ...results.at(-1), messages }, null, 2));
    await page.screenshot({ path: path.join(out, `turn-${index + 1}.png`) });
    console.log(`TURN ${index + 1} PASS ${user.text} (${segments.length} TTS segments)`);
  }
  const historyBefore = await page.locator('.message-content').allTextContents();
  await saveRecordings('after-reconnect');
  await page.reload();
  expect(await page.locator('.message-content').allTextContents()).toEqual(historyBefore);
  results.push({ test: 'history survives reload', status: 'PASS' });
} catch (error) {
  results.push({ status: 'FAIL', message: error.message }); process.exitCode = 1;
  console.error(error.message);
  await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {});
} finally {
  await saveRecordings('final');
  fs.writeFileSync(path.join(out,'final-observations.json'),JSON.stringify(await page.evaluate(()=>({messages:window.__qa.messages,microphoneTracks:window.__qa.dest?.stream.getAudioTracks().map(t=>({enabled:t.enabled,state:t.readyState})),audioState:window.__qa.audio?.state})).catch(()=>({})),null,2));
  fs.writeFileSync(path.join(out, 'console.log'), logs.join('\n'));
  fs.writeFileSync(path.join(out, 'RESULTS.json'), JSON.stringify({ level: 'E2E_BROWSER', mode, requiredTurns: cases.length, results, humanValidation: 'PENDING' }, null, 2));
  await context.close(); await browser.close();
  console.log(`ARTIFACTS ${out}`);
}
