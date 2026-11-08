import { useCallback, useEffect, useRef, useState } from 'react';
import { useBackendStatus, useWebSearchProgress } from './hooks';
import { useConversationStore } from './store';
import { Composer, ConversationView, DebugPanel, TopBar, WebConsentCard, WebSearchOverlay } from './components';
import { stripCitationMarkers } from './presentation';

const errorMessage = (code: string) => ({
  LLM_UNAVAILABLE: 'No pude conectar con Ollama. Revisá que esté abierto y tenga la sesión iniciada.',
  RAG_INDEX_UNAVAILABLE: 'La guía todavía no está lista. Revisá el estado del servidor.',
  ANSWER_TIMEOUT: 'La consulta está demorando más de lo previsto. Probá nuevamente.',
}[code] || 'No pude completar la consulta. Probá nuevamente.');

export function AppShell() {
  useWebSearchProgress();
  const ready = useBackendStatus();
  const store = useConversationStore();
  const [error, setError] = useState('');
  const activeRequest = useRef<AbortController | null>(null);
  const reset = useCallback(() => {
    activeRequest.current?.abort();
    useConversationStore.getState().clearConversation();
    setError('');
  }, []);

  useEffect(() => () => { activeRequest.current?.abort(); }, []);
  useEffect(() => {
    if (!store.messages.length || ['RETRIEVING', 'WEB_SEARCHING'].includes(store.status)) return;
    const timer = window.setTimeout(reset, 3 * 60 * 1000);
    return () => window.clearTimeout(timer);
  }, [store.messages, store.status, reset]);

  const sendText = useCallback(async (text: string) => {
    const current = useConversationStore.getState();
    if (['RETRIEVING', 'WEB_SEARCHING'].includes(current.status)) return;
    const conversationId = current.conversationId;
    const generationId = crypto.randomUUID();
    const isCurrent = () => {
      const latest = useConversationStore.getState();
      return latest.conversationId === conversationId && latest.currentGenerationId === generationId;
    };
    current.addUserMessage(text);
    current.setGenerationId(generationId);
    current.setStatus('RETRIEVING');
    setError('');
    const controller = new AbortController();
    activeRequest.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch('/api/ask-text', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ question: text, session_id: conversationId, turn_id: `text-${Date.now()}`, generation_id: generationId, source: 'human' }),
      });
      const data = await response.json();
      if (!isCurrent()) return;
      if (data.state === 'ASKING_WEB_PERMISSION') {
        current.setWebConsent({ query: text }); current.setStatus('IDLE'); return;
      }
      if (!response.ok) throw new Error(data.error_code || 'UNKNOWN_ERROR');
      current.addAssistantMessage(stripCitationMarkers(data.answer || 'No encontré evidencia suficiente en la guía local.'), data.evidence?.length ? data.evidence : data.searched_sources || []);
      current.setStatus('IDLE');
    } catch (reason) {
      if (!isCurrent()) return;
      const code = controller.signal.aborted ? 'ANSWER_TIMEOUT' : reason instanceof Error ? reason.message : 'UNKNOWN_ERROR';
      setError(errorMessage(code)); current.setStatus('ERROR');
    } finally {
      window.clearTimeout(timeout);
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }, []);

  const consent = store.pendingWebConsent;
  return <div className="app-shell"><TopBar onNew={reset} ready={ready} /><ConversationView onSuggestion={sendText} /><WebSearchOverlay /><footer className="composer-dock"><div className="composer-inner">{consent && <WebConsentCard query={consent.query} onAccept={() => { store.setWebConsent(null); void sendText(`${consent.query} buscá en la web`); }} onReject={() => store.setWebConsent(null)} />}{error && <div className="inline-error" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="Cerrar error">×</button></div>}<Composer onSend={sendText} /></div></footer><DebugPanel /></div>;
}
