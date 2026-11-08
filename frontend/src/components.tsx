import { useEffect, useState } from 'react';
import { stateLabel, useAutoScroll } from './hooks';
import { useConversationStore } from './store';
import type { ConversationMessage } from './types';
import gianaAvatar from './img/Gianna Avatar.png';

function Arrow() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M12 20V4m-7 7 7-7 7 7" /></svg>;
}

export function TopBar({ onNew, ready }: { onNew: () => void; ready: boolean }) {
  return <header className="topbar"><div className="brand"><div className="brand-mark"><img src={gianaAvatar} alt="Avatar de Gianna" /></div><div><div className="brand-name">GIANNA</div><div className="brand-subtitle">Asistente turística de Lavalleja</div></div></div><div className="top-actions"><span className={`connection-dot ${ready ? 'connected' : 'connecting'}`} /><span className="connection-label">{ready ? 'Lista para ayudarte' : 'Conectando con Gianna…'}</span><button type="button" onClick={onNew}>Nueva conversación</button></div></header>;
}

export function StatusIndicator() {
  const status = useConversationStore(s => s.status);
  if (!stateLabel[status] || status === 'WEB_SEARCHING') return null;
  return <div className={`status-indicator status-${status.toLowerCase()}`} role="status" aria-live="polite"><span className="status-pulse" />{stateLabel[status]}</div>;
}

export function WebSearchOverlay() {
  const searching = useConversationStore(s => s.status === 'WEB_SEARCHING');
  if (!searching) return null;
  return <div className="web-search-overlay" role="status" aria-live="polite"><div className="web-search-card"><div className="web-search-visual" aria-hidden="true"><span className="web-search-halo" /><span className="web-search-orbit"><i /></span><span className="web-search-core"><img src={gianaAvatar} alt="" /></span></div><strong>Gianna está buscando en la web</strong><p>Estoy revisando fuentes actuales para responderte…</p><div className="web-search-progress"><span /></div><div className="web-search-wait">Aguardá un momento</div></div></div>;
}

function SourcesPanel({ sources }: { sources: NonNullable<ConversationMessage['sources']> }) {
  const [open, setOpen] = useState(false);
  return <div className="sources-panel"><button className="sources-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>Fuentes ({sources.length}) {open ? '⌃' : '⌄'}</button>{open && <div className="sources-list">{sources.map((source, index) => {
    const candidate = source.url || source.source_refs?.find(ref => typeof ref === 'string' && /^https?:\/\//i.test(ref));
    const url = typeof candidate === 'string' && /^https?:\/\//i.test(candidate) ? candidate : undefined;
    return <div className="source-item" key={`${source.title}-${index}`}>
      {url ? <a href={url} target="_blank" rel="noopener noreferrer">{source.title || 'Fuente web'}</a> : <strong>{source.title || 'Guía turística de Lavalleja'}</strong>}
      {url ? <span>{source.consulted_only ? 'Consultada; no confirma un evento vigente.' : 'Fuente web.'}{source.retrieved_at ? ` Consultada: ${new Date(source.retrieved_at).toLocaleString('es-UY', { timeZone: 'America/Montevideo' })}` : ''}</span> : <span>Líneas {source.start_line}–{source.end_line}</span>}
    </div>;
  })}</div>}</div>;
}

function MessageBubble({ message }: { message: ConversationMessage }) {
  const assistant = message.role === 'assistant';
  return <article className={`message-row ${assistant ? 'assistant-row' : 'user-row'}`}><div className={`avatar ${assistant ? 'avatar-giana' : 'avatar-user'}`}>{assistant ? <img src={gianaAvatar} alt="Avatar de Gianna" /> : 'Vos'}</div><div className={`message-bubble ${assistant ? 'assistant-bubble' : 'user-bubble'}`}><div className="message-meta">{assistant ? 'GIANNA' : 'VOS'} <time>{new Date(message.timestamp).toLocaleTimeString('es-UY', { hour: '2-digit', minute: '2-digit' })}</time></div><div className="message-content">{message.content}</div>{assistant && !!message.sources?.length && <SourcesPanel sources={message.sources} />}</div></article>;
}

export function ConversationView({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  const messages = useConversationStore(s => s.messages);
  const busy = useConversationStore(s => s.status === 'RETRIEVING' || s.status === 'WEB_SEARCHING');
  const ref = useAutoScroll<HTMLDivElement>([messages, busy]);
  const suggestions = ['¿Qué puedo hacer en Minas?', '¿Dónde puedo comer en Villa Serrana?', 'Quiero conocer el Geoparque', '¿Dónde puedo alojarme cerca del Penitente?'];
  return <section className="conversation-area" ref={ref} aria-label="Conversación con Gianna">{!messages.length ? <div className="welcome"><div className="welcome-icon"><img src={gianaAvatar} alt="Avatar de Gianna" /></div><h1>¿Qué querés conocer de Lavalleja?</h1><p>Preguntame por paseos, comida, alojamientos y experiencias del departamento.</p><div className="suggestions">{suggestions.map(suggestion => <button key={suggestion} onClick={() => onSuggestion(suggestion)}>{suggestion}<Arrow /></button>)}</div></div> : <div className="message-list" aria-live="polite">{messages.map(item => <MessageBubble key={item.id} message={item} />)}{busy && <div className="thinking-dots" aria-label="Preparando respuesta"><i /><i /><i /></div>}</div>}</section>;
}

export function WebConsentCard({ query, onAccept, onReject }: { query: string; onAccept: () => void; onReject: () => void }) {
  return <div className="consent-card"><div><strong>No tengo ese dato actualizado en mi base.</strong><p>¿Querés que lo busque en la web?</p><small>{query}</small></div><div className="consent-actions"><button onClick={onAccept}>Buscar en la web</button><button onClick={onReject}>No, gracias</button></div></div>;
}

export function Composer({ onSend }: { onSend: (text: string) => void }) {
  const [text, setText] = useState('');
  const busy = useConversationStore(s => s.status === 'RETRIEVING' || s.status === 'WEB_SEARCHING');
  const submit = () => { const value = text.trim(); if (!value || busy) return; onSend(value); setText(''); };
  return <><StatusIndicator /><div className="composer"><textarea value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} maxLength={4000} placeholder="Escribí tu consulta a Gianna" rows={1} aria-label="Mensaje para Gianna" /><button className="send-button" onClick={submit} disabled={!text.trim() || busy} aria-label="Enviar mensaje"><Arrow /></button></div><div className="composer-hint">Enter para enviar · Shift + Enter para una nueva línea</div></>;
}

export function DebugPanel() {
  const enabled = new URLSearchParams(window.location.search).get('debug') === '1';
  const [data, setData] = useState<Record<string, unknown>>({});
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void fetch('/api/diagnostics', { signal: controller.signal }).then(r => r.ok ? r.json() : {}).then(setData).catch(() => undefined);
    return () => controller.abort();
  }, [enabled]);
  return enabled ? <aside className="debug-panel"><strong>Diagnóstico del chat</strong><pre>{JSON.stringify(data, null, 2)}</pre></aside> : null;
}
