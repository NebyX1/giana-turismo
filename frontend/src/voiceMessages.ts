import type { EvidenceSource } from './types';
import { useConversationStore } from './store';
import { stripCitationMarkers } from './presentation';

export type TurnEvent = { type?: string; event?: string; session_id?: string; turn_id?: string; generation_id?: string; text?: string; error_code?: string; sources?: EvidenceSource[] };

// Server turn IDs are stable across STT segments. Speech/TTS callbacks are
// transport notifications, not a reliable boundary for conversation history.
export function applyTurnMessage(value: unknown): TurnEvent | null {
  if (!value || typeof value !== 'object') return null;
  const event = value as TurnEvent;
  if (event.type !== 'giana-turn-event') return null;
  const store = useConversationStore.getState();
  if (event.session_id) store.setVoiceSessionId(event.session_id);
  if (event.session_id && event.turn_id && typeof event.text === 'string') {
    const key = `voice:${event.session_id}:${event.turn_id}`;
    if (event.event === 'user_transcript_updated' || event.event === 'user_turn_finalized') {
      store.upsertVoiceMessage(`${key}:user`, 'user', event.text);
      store.setLiveTranscript('');
    } else if (event.event === 'assistant_response_finalized') {
      store.upsertVoiceMessage(`${key}:assistant:${event.generation_id}`, 'assistant', stripCitationMarkers(event.text), event.sources);
      store.setGenerationId(event.generation_id || null);
    }
  }
  return event;
}
