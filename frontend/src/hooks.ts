import { useEffect, useRef } from 'react';
import { RTVIEvent, PipecatClient } from '@pipecat-ai/client-js';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';
import { useConversationStore } from './store';
import type { ConversationState } from './types';

export const stateLabel: Record<ConversationState, string> = {
  IDLE: '', CONNECTING: 'Conectando…', LISTENING: 'Escuchando…', TRANSCRIBING: 'Procesando lo que dijiste…', WAITING_TRANSCRIPT: 'Procesando lo que dijiste…', RETRIEVING: 'Buscando en la guía de Lavalleja…', THINKING: 'Pensando…', WEB_SEARCHING: 'Buscando en la web…', SPEAKING: 'Giana está hablando', INTERRUPTED: '', ERROR: 'No pude completar esa acción. Probá de nuevo.',
};

export function useAutoScroll<T extends HTMLElement>(dependency: unknown) {
  const ref = useRef<T>(null);
  const pinned = useRef(true);
  useEffect(() => { const el = ref.current; if (el && pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }); }, [dependency]);
  useEffect(() => { const el = ref.current; if (!el) return; const onScroll = () => { pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }; el.addEventListener('scroll', onScroll, { passive: true }); return () => el.removeEventListener('scroll', onScroll); }, []);
  return ref;
}

export function useVoiceSession() {
  const client = useRef<PipecatClient | null>(null);
  const connectingPromise = useRef<Promise<void> | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const remoteStreamRef = useRef<MediaStream | null>(null);
  const assistantId = useRef<string | null>(null);
  const assistantText = useRef('');
  const assistantFinalized = useRef(false);
  const turnCounter = useRef(0);
  const activeTurnId = useRef('');
  const store = useConversationStore();
  const setState = store.setVoiceState;
  const trace = (event: string, detail = '', status = 'ok') => { const params = new URLSearchParams(window.location.search); if (params.get('debug') === '1' || status === 'error') { void fetch('/api/debug/trace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ component: 'frontend', event, source: 'human', qa_session_id: params.get('qa_session') || '', session_id: store.conversationId, turn_id: activeTurnId.current, generation_id: store.currentGenerationId || '', status, detail }) }).catch(() => undefined); } };

  useEffect(() => {
    const audio = document.createElement('audio');
    audio.autoplay = true;
    audio.setAttribute('playsinline', 'true');
    audio.controls = false;
    audio.setAttribute('aria-hidden', 'true');
    audio.style.display = 'none';
    document.body.appendChild(audio);
    remoteAudioRef.current = audio;
    const snapshot = () => JSON.stringify({ paused: audio.paused, muted: audio.muted, volume: audio.volume, readyState: audio.readyState, networkState: audio.networkState, srcObject: Boolean(audio.srcObject) });
    const events = ['loadedmetadata', 'canplay', 'play', 'playing', 'pause', 'ended', 'waiting', 'stalled', 'suspend', 'emptied', 'error', 'volumechange'];
    const handlers = new Map<string, EventListener>();
    events.forEach((event) => { const handler = () => trace(`frontend_audio_${event}`, snapshot(), event === 'error' ? 'error' : 'ok'); handlers.set(event, handler); audio.addEventListener(event, handler); });
    audio.muted = false;
    audio.volume = 1;
    trace('frontend_audio_element_created', snapshot());
    return () => { handlers.forEach((handler, event) => audio.removeEventListener(event, handler)); audio.pause(); audio.srcObject = null; audio.remove(); remoteAudioRef.current = null; remoteStreamRef.current = null; };
  }, []);

  const connect = async () => {
    if (connectingPromise.current) return connectingPromise.current;
    if (client.current?.connected) { client.current.enableMic(true); setState('LISTENING'); return; }
    const connection = (async () => {
      trace('frontend_mic_clicked'); setState('CONNECTING'); store.setConnectionState('connecting'); trace('frontend_webrtc_connect_start');
      const transport = new SmallWebRTCTransport({ waitForICEGathering: true });
      const pc = new PipecatClient({ transport, enableMic: true, enableCam: false, callbacks: {
      onConnected: () => { store.setConnectionState('connected'); setState('LISTENING'); trace('frontend_webrtc_connected'); },
      onBotStarted: () => trace('frontend_bot_started'),
      onBotReady: (data) => trace('frontend_bot_ready', JSON.stringify(data).slice(0, 300)),
      onTrackStarted: (track, participant) => {
        const audio = remoteAudioRef.current;
        const details = { track_id: track.id, readyState: track.readyState, muted: track.muted, enabled: track.enabled, kind: track.kind, participant: Boolean(participant) };
        trace('frontend_remote_track_started', JSON.stringify(details));
        // participant.local === true es el propio micrófono: reproducirlo genera eco.
        if (track.kind !== 'audio' || !audio || participant?.local) return;
        if (!remoteStreamRef.current || !remoteStreamRef.current.getTracks().some((item) => item.id === track.id)) {
          remoteStreamRef.current = new MediaStream([track]);
          if (audio.srcObject !== remoteStreamRef.current) audio.srcObject = remoteStreamRef.current;
          trace('frontend_audio_element_src_attached', JSON.stringify({ ...details, stream_active: remoteStreamRef.current.active }));
        }
        audio.muted = false;
        audio.volume = 1;
        trace('frontend_audio_play_called', JSON.stringify({ ...details, paused: audio.paused, muted: audio.muted, volume: audio.volume, readyState: audio.readyState }));
        void audio.play().then(() => trace('frontend_audio_play_resolved', JSON.stringify({ ...details, paused: audio.paused, muted: audio.muted, volume: audio.volume, readyState: audio.readyState }))).catch((error: unknown) => trace('frontend_audio_play_rejected', JSON.stringify({ ...details, name: error instanceof Error ? error.name : 'UnknownError', message: error instanceof Error ? error.message : String(error) }), 'error'));
      },
      onTrackStopped: (track, participant) => trace('frontend_remote_track_stopped', JSON.stringify({ track_id: track.id, readyState: track.readyState, muted: track.muted, enabled: track.enabled, kind: track.kind, participant: Boolean(participant), stack: new Error().stack?.split('\n').slice(1, 4).join(' <- ') })),
      onDeviceError: (error) => { trace('frontend_device_error', JSON.stringify(error).slice(0, 300), 'error'); store.setConnectionState('error'); setState('ERROR'); },
      onDisconnected: () => { store.setConnectionState('disconnected'); setState('IDLE'); },
      onTransportStateChanged: (state) => { if (state === 'error') { store.setConnectionState('error'); setState('ERROR'); trace('frontend_error_received', 'transport error', 'error'); } },
      onError: (message) => { const detail = typeof message === 'string' ? message : JSON.stringify(message).slice(0, 500); store.setConnectionState('error'); setState('ERROR'); trace('frontend_error_received', detail || 'client error', 'error'); },
      onUserStartedSpeaking: () => { turnCounter.current += 1; activeTurnId.current = `turn-${String(turnCounter.current).padStart(4, '0')}`; setState('LISTENING'); assistantId.current = null; assistantText.current = ''; assistantFinalized.current = false; trace('frontend_user_started_speaking', activeTurnId.current); },
      onUserStoppedSpeaking: () => setState('WAITING_TRANSCRIPT'),
      // Sección 9-10: el transcript visible NO significa que RAG esté
      // trabajando.  RETRIEVING sólo puede comenzar con backend_dispatch_started
      // (server-message del voice, disparado junto al dispatch real al backend).
      onUserTranscript: (data) => { store.setLiveTranscript(data.text); if (data.final && data.text.trim()) { store.addUserMessage(data.text.trim()); store.setLiveTranscript(''); setState('WAITING_TRANSCRIPT'); trace('frontend_user_message_visible', data.text.trim()); trace('frontend_status_changed', 'WAITING_TRANSCRIPT'); } },
      onServerMessage: (data: unknown) => { const event = (data as { event?: string; turn_id?: string; generation_id?: string; error_code?: string }) || {}; switch (event.event) { case 'backend_dispatch_started': store.setGenerationId(event.generation_id || null); setState('RETRIEVING'); trace('frontend_status_changed', 'RETRIEVING', 'ok'); break; case 'web_search_started': setState('WEB_SEARCHING'); trace('frontend_status_changed', 'WEB_SEARCHING', 'ok'); break; case 'stt_transcript_missing': setState('ERROR'); trace('frontend_status_changed', 'STT_TRANSCRIPT_MISSING_AFTER_TURN_COMPLETE', 'error'); break; default: break; } },
      onBotLlmStarted: () => { setState('THINKING'); assistantText.current = ''; assistantFinalized.current = false; trace('frontend_status_changed', 'THINKING'); assistantId.current = store.addAssistantMessage('', undefined, true); trace('frontend_assistant_message_created'); },
      onBotLlmText: (data) => { if (!assistantId.current) assistantId.current = store.addAssistantMessage('', undefined, true); assistantText.current += data.text; store.appendAssistantText(assistantId.current, data.text); trace('frontend_assistant_text_received', data.text); },
      onBotTtsStarted: () => { setState('SPEAKING'); trace('frontend_tts_synthesizing'); }, onBotTtsStopped: () => { setState('LISTENING'); if (!assistantFinalized.current && assistantId.current) { assistantFinalized.current = true; store.finishAssistant(assistantId.current, assistantText.current); trace('frontend_assistant_message_finalized', assistantText.current); } trace('frontend_tts_done'); },
      onBotStartedSpeaking: () => { setState('SPEAKING'); trace('frontend_transport_sending_audio'); }, onBotStoppedSpeaking: () => { setState('LISTENING'); trace('frontend_transport_audio_done'); },
      onLocalAudioLevel: (level) => store.setAudioLevel(level),
      onBotOutput: (data) => { const canonical = assistantText.current || data.text || ''; if (canonical && assistantId.current) { assistantFinalized.current = true; store.finishAssistant(assistantId.current, canonical); trace('frontend_assistant_message_finalized', canonical); } },
      } });
      client.current = pc;
      try {
        let timeoutId: number | undefined;
        // Cold model initialization can take longer than ICE itself. This is
        // only the connection bootstrap watchdog, not turn finalization.
        const timeout = new Promise<never>((_, reject) => { timeoutId = window.setTimeout(() => reject(new Error('WEBRTC_CONNECTION_TIMEOUT')), 30000); });
        trace('voice_start_requested', JSON.stringify({ endpoint: 'http://localhost:7860/start', origin: window.location.origin }));
        try { await Promise.race([pc.startBotAndConnect({ endpoint: 'http://localhost:7860/start', requestData: { transport: 'webrtc', enableDefaultIceServers: true } }), timeout]); trace('voice_start_response', 'ok'); }
        finally { if (timeoutId !== undefined) window.clearTimeout(timeoutId); }
      }
      catch (error) { const detail = error instanceof Error ? error.message : String(error); const code = detail.includes('Failed to fetch') ? 'VOICE_START_FETCH_ERROR' : detail.includes('WEBRTC') ? 'WEBRTC_ERROR' : 'SIGNALING_ERROR'; trace('frontend_connect_failed', JSON.stringify({ error_code: code, detail }), 'error'); store.setConnectionState('error'); setState('ERROR'); await pc.disconnect().catch(() => undefined); if (client.current === pc) client.current = null; throw new Error(`No pude conectar la sesión de voz: ${detail}`); }
    })();
    connectingPromise.current = connection;
    try { await connection; } finally { if (connectingPromise.current === connection) connectingPromise.current = null; }
  };

  const toggle = async () => { if (client.current?.connected) { client.current.enableMic(!client.current.isMicEnabled); setState(client.current.isMicEnabled ? 'LISTENING' : 'IDLE'); return; } await connect(); };
  const disconnect = async () => { await client.current?.disconnect(); client.current = null; store.setConnectionState('disconnected'); setState('IDLE'); };
  return { toggle, disconnect };
}
