import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { ConversationMessage, ConversationState, EvidenceSource } from './types';

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

type ConversationStore = {
  messages: ConversationMessage[];
  conversationId: string;
  voiceSessionId: string | null;
  voiceState: ConversationState;
  connectionState: ConnectionState;
  currentGenerationId: string | null;
  pendingWebConsent: { query: string; requestId?: string } | null;
  audioLevel: number;
  liveTranscript: string;
  upsertVoiceMessage: (id: string, role: 'user' | 'assistant', content: string, sources?: EvidenceSource[]) => void;
  addUserMessage: (content: string) => string;
  addAssistantMessage: (content?: string, sources?: EvidenceSource[], pending?: boolean) => string;
  appendAssistantText: (id: string, content: string) => void;
  finishAssistant: (id: string, content: string, sources?: EvidenceSource[]) => void;
  setVoiceState: (state: ConversationState) => void;
  setConnectionState: (state: ConnectionState) => void;
  setGenerationId: (id: string | null) => void;
  setVoiceSessionId: (id: string | null) => void;
  setWebConsent: (consent: { query: string; requestId?: string } | null) => void;
  setAudioLevel: (level: number) => void;
  setLiveTranscript: (text: string) => void;
  clearConversation: () => void;
};

const id = () => `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
const greeting = (): ConversationMessage => ({ id: id(), role: 'assistant', content: 'Hola, soy Gianna, la asistente turística de Lavalleja.\n\nPodés preguntarme por lugares, actividades, gastronomía, alojamiento y el Geoparque Manantiales Serranos. También podés tocar el micrófono y hablar conmigo.', timestamp: new Date().toISOString(), local: true, pending: false });
const migrateAssistantName = (messages: ConversationMessage[] | undefined) => messages?.map((message) => message.role === 'assistant'
  ? { ...message, content: message.content.replace(/\bGiana\b/g, 'Gianna').replace(/\bGIANA\b/g, 'GIANNA') }
  : message);

export const useConversationStore = create<ConversationStore>()(persist((set) => ({
  messages: [greeting()], conversationId: id(), voiceSessionId: null, voiceState: 'IDLE', connectionState: 'disconnected', currentGenerationId: null, pendingWebConsent: null, audioLevel: 0, liveTranscript: '',
  addUserMessage: (content) => { const messageId = id(); set((s) => ({ messages: [...s.messages, { id: messageId, role: 'user', content, timestamp: new Date().toISOString() }] })); return messageId; },
  upsertVoiceMessage: (messageId, role, content, sources) => set((s) => ({ messages: s.messages.some(m => m.id === messageId)
    ? s.messages.map(m => m.id === messageId ? { ...m, content, sources: sources ?? m.sources, pending: false } : m)
    : [...s.messages, { id: messageId, role, content, sources, pending: false, timestamp: new Date().toISOString() }] })),
  addAssistantMessage: (content = '', sources, pending = true) => { const messageId = id(); set((s) => ({ messages: [...s.messages, { id: messageId, role: 'assistant', content, timestamp: new Date().toISOString(), sources, pending }] })); return messageId; },
  appendAssistantText: (messageId, content) => set((s) => ({ messages: s.messages.map((m) => m.id === messageId ? { ...m, content: m.content + content, pending: false } : m) })),
  finishAssistant: (messageId, content, sources) => set((s) => ({ messages: s.messages.map((m) => m.id === messageId ? { ...m, content, sources, pending: false } : m) })),
  setVoiceState: (voiceState) => set({ voiceState }), setConnectionState: (connectionState) => set({ connectionState }), setGenerationId: (currentGenerationId) => set({ currentGenerationId }),
  setVoiceSessionId: (voiceSessionId) => set({ voiceSessionId }),
  setWebConsent: (pendingWebConsent) => set({ pendingWebConsent }), setAudioLevel: (audioLevel) => set({ audioLevel }), setLiveTranscript: (liveTranscript) => set({ liveTranscript }),
  clearConversation: () => set({ messages: [greeting()], conversationId: id(), voiceState: 'IDLE', pendingWebConsent: null, currentGenerationId: null, liveTranscript: '' }),
}), { name: 'giana-conversation-v1', version: 2, migrate: (persisted) => { const state = persisted as { messages?: ConversationMessage[]; conversationId?: string }; return { ...state, messages: migrateAssistantName(state.messages) }; }, storage: createJSONStorage(() => sessionStorage), partialize: (s) => ({ messages: s.messages, conversationId: s.conversationId }) }));
