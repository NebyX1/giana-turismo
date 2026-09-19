import { create } from 'zustand';
import type { ConversationMessage, ConversationState, EvidenceSource } from './types';

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

type ConversationStore = {
  messages: ConversationMessage[];
  conversationId: string;
  voiceState: ConversationState;
  connectionState: ConnectionState;
  currentGenerationId: string | null;
  pendingWebConsent: { query: string; requestId?: string } | null;
  audioLevel: number;
  liveTranscript: string;
  addUserMessage: (content: string) => string;
  addAssistantMessage: (content?: string, sources?: EvidenceSource[], pending?: boolean) => string;
  appendAssistantText: (id: string, content: string) => void;
  finishAssistant: (id: string, content: string, sources?: EvidenceSource[]) => void;
  setVoiceState: (state: ConversationState) => void;
  setConnectionState: (state: ConnectionState) => void;
  setGenerationId: (id: string | null) => void;
  setWebConsent: (consent: { query: string; requestId?: string } | null) => void;
  setAudioLevel: (level: number) => void;
  setLiveTranscript: (text: string) => void;
  clearConversation: () => void;
};

const id = () => `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
const greeting = (): ConversationMessage => ({ id: id(), role: 'assistant', content: 'Hola, soy Giana, la asistente turística de Lavalleja.\n\nPodés preguntarme por lugares, actividades, gastronomía, alojamiento y el Geoparque Manantiales Serranos. También podés tocar el micrófono y hablar conmigo.', timestamp: new Date().toISOString(), local: true, pending: false });

export const useConversationStore = create<ConversationStore>((set) => ({
  messages: [greeting()], conversationId: id(), voiceState: 'IDLE', connectionState: 'disconnected', currentGenerationId: null, pendingWebConsent: null, audioLevel: 0, liveTranscript: '',
  addUserMessage: (content) => { const messageId = id(); set((s) => ({ messages: [...s.messages, { id: messageId, role: 'user', content, timestamp: new Date().toISOString() }] })); return messageId; },
  addAssistantMessage: (content = '', sources, pending = true) => { const messageId = id(); set((s) => ({ messages: [...s.messages, { id: messageId, role: 'assistant', content, timestamp: new Date().toISOString(), sources, pending }] })); return messageId; },
  appendAssistantText: (messageId, content) => set((s) => ({ messages: s.messages.map((m) => m.id === messageId ? { ...m, content: m.content + content, pending: false } : m) })),
  finishAssistant: (messageId, content, sources) => set((s) => ({ messages: s.messages.map((m) => m.id === messageId ? { ...m, content, sources, pending: false } : m) })),
  setVoiceState: (voiceState) => set({ voiceState }), setConnectionState: (connectionState) => set({ connectionState }), setGenerationId: (currentGenerationId) => set({ currentGenerationId }),
  setWebConsent: (pendingWebConsent) => set({ pendingWebConsent }), setAudioLevel: (audioLevel) => set({ audioLevel }), setLiveTranscript: (liveTranscript) => set({ liveTranscript }),
  clearConversation: () => set({ messages: [greeting()], conversationId: id(), voiceState: 'IDLE', pendingWebConsent: null, currentGenerationId: null, liveTranscript: '' }),
}));
