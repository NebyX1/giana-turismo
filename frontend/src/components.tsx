import { useEffect, useState } from 'react';
import { Add24Regular, ArrowUp24Filled, CheckmarkCircle16Filled, ChevronDown16Regular, Dismiss16Regular, Mic24Regular, MicOff24Regular, MoreHorizontal20Regular, Sparkle24Regular } from '@fluentui/react-icons';
import { Button, Card, Input, Spinner, Tooltip } from '@fluentui/react-components';
import { stateLabel, useAutoScroll } from './hooks';
import { useConversationStore } from './store';
import type { ConversationMessage, ConversationState } from './types';
import gianaAvatar from './img/Gianna Avatar.png';

export function TopBar({ onNew }: { onNew: () => void }) { const connection = useConversationStore((s) => s.connectionState); const qaSessionId = new URLSearchParams(window.location.search).get('qa_session'); return <header className="topbar"><div className="brand"><div className="brand-mark"><img src={gianaAvatar} alt="Avatar de Gianna" /></div><div><div className="brand-name">GIANNA</div><div className="brand-subtitle">Asistente turística de Lavalleja</div></div></div><div className="top-actions"><span className={`connection-dot ${connection}`} /> <span className="connection-label">{connection === 'connected' ? 'Conectada' : connection === 'connecting' ? 'Conectando…' : 'Lista para ayudarte'}</span>{qaSessionId && <span>QA SESSION: {qaSessionId}</span>}<Button appearance="subtle" icon={<Add24Regular />} onClick={onNew}>Nueva conversación</Button></div></header>; }

export function StatusIndicator() { const state = useConversationStore((s) => s.voiceState); const label = stateLabel[state]; if (!label || state === 'WEB_SEARCHING') return null; return <div className={`status-indicator status-${state.toLowerCase()}`} role="status" aria-live="polite"><span className="status-pulse" />{label}</div>; }

export function WebSearchOverlay() {
  const searching = useConversationStore((s) => s.voiceState === 'WEB_SEARCHING');
  if (!searching) return null;
  return <div className="web-search-overlay status-web_searching" role="status" aria-live="polite">
    <div className="web-search-card">
      <div className="web-search-visual" aria-hidden="true">
        <span className="web-search-halo" />
        <span className="web-search-orbit web-search-orbit-one"><i /></span>
        <span className="web-search-orbit web-search-orbit-two"><i /></span>
        <span className="web-search-core"><img src={gianaAvatar} alt="Avatar de Gianna" /></span>
      </div>
      <strong>Gianna está buscando en la web</strong>
      <p>Estoy revisando fuentes actuales para responderte…</p>
      <div className="web-search-progress" aria-hidden="true"><span /></div>
      <div className="web-search-wait"><span className="status-pulse" />Aguardá un momento<span className="search-dots"><i /><i /><i /></span></div>
    </div>
  </div>;
}

export function VoiceActivity() { const level = useConversationStore((s) => s.audioLevel); const state = useConversationStore((s) => s.voiceState); const active = state === 'LISTENING' || state === 'TRANSCRIBING'; return <div className={`voice-activity ${active ? 'active' : ''}`} aria-label="Actividad del micrófono">{Array.from({ length: 9 }, (_, i) => <i key={i} style={{ height: `${active ? Math.max(3, Math.min(28, 4 + level * 42 * (0.7 + ((i * 13) % 5) / 10))) : 3}px` }} />)}</div>; }

function SourcesPanel({ sources }: { sources: NonNullable<ConversationMessage['sources']> }) {
  const [open, setOpen] = useState(false);
  return <div className="sources-panel"><button className="sources-toggle" onClick={() => setOpen(!open)}><span>Fuentes ({sources.length})</span><ChevronDown16Regular className={open ? 'rotate' : ''} /></button>{open && <div className="sources-list">{sources.map((source, index) => {
    const candidate = source.url || source.source_refs?.find(ref => typeof ref === 'string' && /^https?:\/\//i.test(ref));
    const url = typeof candidate === 'string' && /^https?:\/\//i.test(candidate) ? candidate : undefined;
    return <div className="source-item" key={`${source.title}-${index}`}>
      {url ? <a href={url} target="_blank" rel="noopener noreferrer">{source.title || 'Fuente web'}</a> : <strong>{source.title || 'Guía turística de Lavalleja'}</strong>}
      {url ? <span>{source.consulted_only ? 'Consultada; no confirma un evento vigente.' : 'Fuente web.'}{source.retrieved_at ? ` Consultada: ${new Date(source.retrieved_at).toLocaleString('es-UY', { timeZone: 'America/Montevideo' })} (Uruguay)` : ''}</span> : <span>Líneas {source.start_line}–{source.end_line}</span>}
    </div>;
  })}</div>}</div>;
}

export function MessageBubble({ message }: { message: ConversationMessage }) { const assistant = message.role === 'assistant'; return <article className={`message-row ${assistant ? 'assistant-row' : 'user-row'}`}><div className={`avatar ${assistant ? 'avatar-giana' : 'avatar-user'}`}>{assistant ? <img src={gianaAvatar} alt="Avatar de Gianna" /> : 'Vos'}</div><div className={`message-bubble ${assistant ? 'assistant-bubble' : 'user-bubble'}`}><div className="message-meta">{assistant ? 'GIANNA' : 'VOS'} <time>{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div>{message.pending && !message.content ? <div className="thinking-dots"><i /><i /><i /></div> : <div className="message-content">{message.content}</div>}{assistant && message.sources?.length ? <SourcesPanel sources={message.sources} /> : null}</div></article>; }

export function ConversationView({ onSuggestion }: { onSuggestion?: (text: string) => void }) { const messages = useConversationStore((s) => s.messages); const liveTranscript = useConversationStore((s) => s.liveTranscript); const ref = useAutoScroll<HTMLDivElement>([messages, liveTranscript]); const greetingOnly = messages.length === 1 && messages[0].local; return <section className="conversation-area" ref={ref}>{messages.length === 0 ? <WelcomeScreen onSuggestion={onSuggestion} /> : <div className="message-list">{messages.map((message) => <MessageBubble key={message.id} message={message} />)}{greetingOnly && <WelcomeScreen onSuggestion={onSuggestion} />}{liveTranscript && <div className="live-transcript"><span>VOS</span>{liveTranscript}</div>}</div>}</section>; }

export function WelcomeScreen({ onSuggestion }: { onSuggestion?: (text: string) => void }) { const suggestions = ['¿Qué puedo hacer en Minas?', '¿Dónde puedo comer en Villa Serrana?', 'Quiero conocer el Geoparque', '¿Dónde puedo alojarme cerca del Penitente?']; return <div className="welcome"><div className="welcome-icon"><img src={gianaAvatar} alt="Avatar de Gianna" /></div><h1>¿Qué querés conocer de Lavalleja?</h1><p>Preguntame por paseos, comida, alojamientos y experiencias del departamento.</p><div className="suggestions">{suggestions.map((suggestion) => <button key={suggestion} onClick={() => onSuggestion?.(suggestion)}>{suggestion}<ArrowUp24Filled /></button>)}</div></div>; }

export function WebConsentCard({ query, onAccept, onReject }: { query: string; onAccept: () => void; onReject: () => void }) { return <Card className="consent-card"><div><strong>No tengo ese dato actualizado en mi base.</strong><p>¿Querés que lo busque en la web?</p><small>{query}</small></div><div className="consent-actions"><Button appearance="primary" onClick={onAccept}>Buscar en la web</Button><Button appearance="subtle" onClick={onReject}>No, gracias</Button></div></Card>; }

export function Composer({ onSend, onMic, onSuggestion }: { onSend: (text: string) => void; onMic: () => void; onSuggestion?: (text: string) => void }) { const [text, setText] = useState(''); const state = useConversationStore((s) => s.voiceState); const connected = useConversationStore((s) => s.connectionState); const submit = () => { const value = text.trim(); if (!value) return; onSend(value); setText(''); }; return <><StatusIndicator /><VoiceActivity /><div className="composer"><textarea value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} placeholder="Escribí o hablá con Gianna" rows={1} aria-label="Mensaje para Gianna" /><Tooltip content={state === 'LISTENING' ? 'Pausar micrófono' : 'Hablar con Gianna'} relationship="label"><button className={`mic-button ${state === 'LISTENING' || state === 'SPEAKING' ? 'mic-active' : ''}`} onClick={onMic} aria-label="Activar micrófono">{state === 'TRANSCRIBING' || state === 'CONNECTING' ? <Spinner size="tiny" /> : state === 'LISTENING' ? <MicOff24Regular /> : <Mic24Regular />}</button></Tooltip><button className="send-button" onClick={submit} disabled={!text.trim()} aria-label="Enviar mensaje"><ArrowUp24Filled /></button></div><div className="composer-hint">{connected === 'error' ? 'No pude acceder al micrófono. Revisá el permiso del navegador.' : 'Enter para enviar · Shift + Enter para una nueva línea'}</div></>; }

export function DebugPanel() {
  const enabled = new URLSearchParams(window.location.search).get('debug') === '1';
  const qaSessionId = new URLSearchParams(window.location.search).get('qa_session') || '';
  const debugSessionId = useConversationStore((s) => s.voiceSessionId || s.conversationId);
  const liveConnection = useConversationStore((s) => s.connectionState).toUpperCase();
  const [data, setData] = useState<{ turn_id?: string; events?: Array<Record<string, unknown>> }>({});
  useEffect(() => { if (!enabled) return; let active = true; const read = async () => { try { const response = await fetch(`/api/debug/last-turn?session_id=${encodeURIComponent(debugSessionId)}&qa_session=${encodeURIComponent(qaSessionId)}`, { cache: 'no-store' }); const next = await response.json(); if (active) setData(next); } catch { /* panel stays on last value */ } }; void read(); const timer = window.setInterval(read, 1000); return () => { active = false; window.clearInterval(timer); }; }, [enabled, debugSessionId, qaSessionId]);
  if (!enabled) return null;
  const events = data.events || []; const last = events[events.length - 1] || {};
  const latest = (names: string[]) => events.filter((item) => names.includes(String(item.event))).slice(-1)[0];
  const status = (names: string[], fallback = 'IDLE') => String(latest(names)?.status || fallback).toUpperCase();
  const detail = (names: string[]) => String(latest(names)?.detail || '—');
  const intent = latest(['intent_classified']);
  const latency = events.filter((item) => typeof item.elapsed_ms === 'number').slice(-1)[0]?.elapsed_ms;
  const timeline = events.filter((item) => ['speech_end', 'moonshine_transcript_final', 'intent_classified', 'rag_done', 'llm_first_chunk', 'llm_finished', 'tts_input_received', 'frontend_remote_track_started', 'frontend_audio_playing'].includes(String(item.event))).slice(-8);
  const smart = latest(['smart_turn_result']);
  const turnState = latest(['turn_finalized']) ? 'FINALIZED' : latest(['turn_waiting_transcript']) ? 'WAITING_TRANSCRIPT' : String(smart?.detail || '').includes('INCOMPLETE') ? 'WAITING_CONTINUATION' : latest(['smart_turn_analysis_started']) ? 'ANALYZING_END' : latest(['turn_started']) ? 'SPEECH' : 'LISTENING';
  const grace = latest(['grace_started']); const finalized = latest(['turn_finalized']); const responseBuffer = latest(['assistant_response_buffer_finalized']); const errorEvent = latest(['frontend_error_displayed', 'backend_request_failed', 'backend_request_timeout', 'TEXT_TTS_DIVERGENCE']);
  return <aside className="debug-panel"><strong>Voice debug</strong><span>SESSION: {String(last.session_id || '—')}</span><span>TURN: {String(data.turn_id || last.turn_id || '—')}</span><span>GENERATION: {String(last.generation_id || '—')}</span><span>TURN STATE: {turnState}</span><span>MIC: {liveConnection}</span><span>WEBRTC: {liveConnection}</span><span>REMOTE TRACK: {latest(['frontend_remote_track_started']) ? 'LIVE' : latest(['frontend_remote_track_stopped']) ? 'ENDED' : 'NOT_RECEIVED'}</span><span>AUDIO PLAYER: {latest(['frontend_audio_playing']) ? 'PLAYING' : latest(['frontend_audio_play_resolved']) ? 'READY' : latest(['frontend_audio_play_rejected']) ? 'ERROR' : 'IDLE'}</span><span>VAD: {latest(['vad_speech_started', 'vad_speech_stopped'])?.event === 'vad_speech_started' ? 'SPEECH' : 'SILENCE'}</span><span>SMART TURN: {smart ? String(smart.detail || 'IDLE') : latest(['smart_turn_analysis_started']) ? 'ANALYZING' : 'IDLE'}</span><span>GRACE WINDOW: {grace && !latest(['grace_finished', 'speech_resumed']) ? `ACTIVE ${String(grace.grace_ms || '—')} ms` : 'INACTIVE'}</span><span>TRANSCRIPT SEGMENTS: {String(latest(['transcript_buffer_updated'])?.transcript_segments || 0)}</span><span>FINAL USER TEXT: {String(finalized?.detail || '—')}</span><span>STT: {latest(['moonshine_transcript_final']) ? 'DONE' : 'IDLE'}</span><span>CONTEXT: {String(latest(['standalone_query_resolved'])?.context_turns || 0)} turns</span><span>STANDALONE QUERY: {String(latest(['standalone_query_resolved'])?.detail || '—')}</span><span>INTENT: {String(intent?.intent || detail(['intent_classified']).split(' ')[0] || '—')}</span><span>ROUTE: {String(intent?.route || '—')}</span><span>RAG: {intent?.rag_invoked === false ? 'SKIPPED' : latest(['backend_response_received']) ? 'DONE' : 'IDLE'}</span><span>LLM: {latest(['llm_finished']) ? 'DONE' : 'IDLE'}</span><span>ASSISTANT BUFFER: {String(responseBuffer?.detail || '—')}</span><span>TTS SEGMENTS: {String(events.filter((item) => item.event === 'tts_input_received').length)}</span><span>TTS: {latest(['piper_response_received']) ? 'DONE' : latest(['tts_input_received']) ? 'SYNTHESIZING' : 'IDLE'}</span><span>LAST EVENT: {String(last.event || '—')}</span><span>LAST SUCCESS: {String(last.event || '—')}</span><span>EXPECTED NEXT: {latest(['frontend_audio_play_resolved']) ? 'audio_playing / silence' : 'audio_play_resolved'}</span><span>ERROR CODE: {String(errorEvent?.error_code || errorEvent?.detail || '—')}</span><span>TURN LATENCY: {latency == null ? '—' : `${String(latency)} ms`}</span><details><summary>TURN TIMELINE</summary>{timeline.map((item, index) => <div key={`${String(item.event)}-${index}`}>{String(item.ts).slice(11, 23)} {String(item.event)}</div>)}</details></aside>;
}
