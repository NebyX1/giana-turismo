import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { ConversationMessage, ConversationState, EvidenceSource } from './types';

type ConversationStore = {
  messages: ConversationMessage[];
  conversationId: string;
  status: ConversationState;
  currentGenerationId: string | null;
  pendingWebConsent: { query: string } | null;
  addUserMessage: (content: string) => void;
  addAssistantMessage: (content: string, sources?: EvidenceSource[]) => void;
  setStatus: (status: ConversationState) => void;
  setGenerationId: (id: string | null) => void;
  setWebConsent: (consent: { query: string } | null) => void;
  clearConversation: () => void;
};

const message = (role: ConversationMessage['role'], content: string, sources?: EvidenceSource[]): ConversationMessage => ({
  id: crypto.randomUUID(), role, content, sources, timestamp: new Date().toISOString(),
});

export const useConversationStore = create<ConversationStore>()(persist((set) => ({
  messages: [], conversationId: crypto.randomUUID(), status: 'IDLE', currentGenerationId: null, pendingWebConsent: null,
  addUserMessage: (content) => set(s => ({ messages: [...s.messages, message('user', content)] })),
  addAssistantMessage: (content, sources) => set(s => ({ messages: [...s.messages, message('assistant', content, sources)] })),
  setStatus: (status) => set({ status }),
  setGenerationId: (currentGenerationId) => set({ currentGenerationId }),
  setWebConsent: (pendingWebConsent) => set({ pendingWebConsent }),
  clearConversation: () => set({ messages: [], conversationId: crypto.randomUUID(), status: 'IDLE', currentGenerationId: null, pendingWebConsent: null }),
}), {
  name: 'giana-conversation-v1', version: 4,
  migrate: (value) => {
    const previous = value as { messages?: ConversationMessage[]; conversationId?: string };
    return { messages: (previous.messages || []).filter(m => m.role === 'user' || m.role === 'assistant'),
      conversationId: previous.conversationId || crypto.randomUUID() };
  },
  storage: createJSONStorage(() => sessionStorage),
  partialize: (s) => ({ messages: s.messages, conversationId: s.conversationId }),
}));
