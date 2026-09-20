import { useCallback, useEffect, useState } from 'react';
import { Dismiss16Regular } from '@fluentui/react-icons';
import { Button } from '@fluentui/react-components';
import { useVoiceSession } from './hooks';
import { useConversationStore } from './store';
import { Composer, ConversationView, DebugPanel, TopBar, WebConsentCard, WebSearchOverlay } from './components';
import { stripCitationMarkers } from './presentation';

const looksLikeWebRequest = (text: string) => {
  const q = text.toLocaleLowerCase('es-UY');
  return /\b(busca|buscá|buscar|consultá|consulta|averiguá|averigua|revisá|revisa)\b.*\b(web|internet|online|google)\b|\ben internet\b|\bweb\b/i.test(q)
    || /\b(eventos?|agenda|cartelera|actividades? culturales?|festival(?:es)?|conciertos?|funciones?)\b/i.test(q)
    || /\b(esta semana|mañana|manana|hoy|ahora|este mes|próxima semana|proxima semana|fin de semana)\b.*\b(evento|actividad|agenda|cartelera|cultural|abierto|horario|disponibilidad)\b/i.test(q)
    || /\b(está abierto|esta abierto|horario|disponibilidad|vigente|actualizado)\b/i.test(q);
};

export function AppShell() {
  const { toggle, disconnect } = useVoiceSession(); const consent = useConversationStore((s) => s.pendingWebConsent); const store = useConversationStore(); const [error, setError] = useState('');
  const reportError = (errorCode: string, message: string, turnId = '') => { const qaSessionId = new URLSearchParams(window.location.search).get('qa_session') || ''; void fetch('/api/debug/trace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ component: 'frontend', event: 'frontend_error_displayed', source: 'human', qa_session_id: qaSessionId, session_id: store.conversationId, turn_id: turnId, generation_id: store.currentGenerationId || '', status: 'error', error_code: errorCode, detail: JSON.stringify({ error_code: errorCode, source_component: 'AppShell', message }) }) }).catch(() => undefined); };
  useEffect(() => {
    if (!['RETRIEVING', 'WEB_SEARCHING', 'WAITING_TRANSCRIPT'].includes(store.voiceState)) return;
    const waitingTranscript = store.voiceState === 'WAITING_TRANSCRIPT';
    const timer = window.setTimeout(() => {
      const message = waitingTranscript ? 'No pude entender lo que dijiste. Probá nuevamente.' : 'La consulta está demorando más de lo previsto. Podés volver a intentarlo.';
      store.setVoiceState('ERROR'); setError(message);
      reportError(waitingTranscript ? 'STT_TRANSCRIPT_MISSING_AFTER_TURN_COMPLETE' : 'ANSWER_TIMEOUT', message);
    }, waitingTranscript ? 15000 : 65000);
    return () => window.clearTimeout(timer);
  }, [store.voiceState]);
  useEffect(() => {
    if (store.voiceState === 'IDLE' || store.voiceState === 'LISTENING' || store.voiceState === 'SPEAKING') setError('');
  }, [store.voiceState]);
  useEffect(() => { const params = new URLSearchParams(window.location.search); const code = params.get('e2e_force_error'); if (params.get('e2e_test_mode') !== 'true' || !code) return; const message = code === 'LLM_TIMEOUT' ? 'El modelo tardó demasiado. Probá de nuevo.' : 'Error controlado de prueba.'; store.setVoiceState('ERROR'); setError(message); reportError(code, message, `e2e-${Date.now()}`); }, []);
  const sendText = useCallback(async (text: string) => {
    const conversationId = store.conversationId;
    const generationId = crypto.randomUUID();
    const turnId = `text-${Date.now()}`;
    const isCurrent = () => {
      const current = useConversationStore.getState();
      return current.conversationId === conversationId && current.currentGenerationId === generationId;
    };
    store.addUserMessage(text);
    store.setVoiceState(looksLikeWebRequest(text) ? 'WEB_SEARCHING' : 'RETRIEVING');
    store.setGenerationId(generationId);
    try {
      const response = await fetch('/api/ask-text', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text, session_id: conversationId, turn_id: turnId, generation_id: generationId, source: 'human' }) });
      const data = await response.json();
      // A response from before New Conversation (or a superseded request)
      // cannot write content, consent or errors into the current conversation.
      if (!isCurrent()) return;
      if (data.state === 'ASKING_WEB_PERMISSION') { store.setWebConsent({ query: text }); return; }
      if (!response.ok) throw new Error(data.error_code || 'UNKNOWN_ERROR');
      store.setVoiceState('IDLE');
      const answer = stripCitationMarkers(data.answer || 'No encontré evidencia suficiente en la guía local.');
      const sources = data.evidence?.length ? data.evidence : data.searched_sources || [];
      const id = store.addAssistantMessage(answer, sources, false);
      store.finishAssistant(id, answer, sources);
    } catch (e) {
      if (!isCurrent()) return;
      const message = e instanceof Error ? e.message : 'UNKNOWN_ERROR';
      const code = message.includes('LLM') ? 'LLM_TIMEOUT' : message.includes('RAG') ? 'RAG_ERROR' : 'UNKNOWN_ERROR';
      reportError(code, message, turnId); setError(message); store.setVoiceState('ERROR');
    }
  }, [store]);
  return <div className="app-shell"><TopBar onNew={() => { void disconnect().then(() => { store.clearConversation(); store.setVoiceSessionId(null); setError(''); }); }} /><ConversationView onSuggestion={sendText} /><WebSearchOverlay /><footer className="composer-dock"><div className="composer-inner">{consent && <WebConsentCard query={consent.query} onAccept={() => { store.setWebConsent(null); void sendText(`${consent.query} buscá en la web`); }} onReject={() => store.setWebConsent(null)} />}{error && <div className="inline-error"><span>{error}</span><Button appearance="subtle" icon={<Dismiss16Regular />} onClick={() => setError('')} aria-label="Cerrar error" /></div>}<Composer onSend={sendText} onMic={async () => { try { await toggle(); } catch (e) { const message = e instanceof Error ? e.message : 'No pude acceder al micrófono.'; reportError(message.includes('WEBRTC') ? 'WEBRTC_ERROR' : 'UNKNOWN_ERROR', message); setError(message); } }} onSuggestion={sendText} /></div></footer><DebugPanel /></div>;
}
