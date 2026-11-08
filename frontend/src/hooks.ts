import { useEffect, useRef, useState } from 'react';
import { useConversationStore } from './store';
import type { ConversationState } from './types';

export const stateLabel: Record<ConversationState, string> = {
  IDLE: '', RETRIEVING: 'Buscando en la guía de Lavalleja…',
  WEB_SEARCHING: 'Buscando en la web…', ERROR: '',
};

export function useBackendStatus() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const check = async () => {
      try {
        const response = await fetch('/api/ready', { cache: 'no-store', signal: controller.signal });
        if (!controller.signal.aborted) setReady(response.ok);
      } catch { if (!controller.signal.aborted) setReady(false); }
    };
    void check();
    const timer = window.setInterval(check, 30000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  return ready;
}

export function useWebSearchProgress() {
  const sessionId = useConversationStore(s => s.conversationId);
  const generationId = useConversationStore(s => s.currentGenerationId);
  const status = useConversationStore(s => s.status);
  useEffect(() => {
    if (!generationId || !['RETRIEVING', 'WEB_SEARCHING'].includes(status)) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const params = new URLSearchParams({ session_id: sessionId, generation_id: generationId });
        const response = await fetch(`/api/turn-progress?${params}`, { cache: 'no-store', signal: controller.signal });
        if (response.ok) {
          const progress = await response.json() as { state?: string };
          const current = useConversationStore.getState();
          if (!controller.signal.aborted && current.conversationId === sessionId && current.currentGenerationId === generationId
            && current.status === 'RETRIEVING' && progress.state === 'WEB_SEARCHING') current.setStatus('WEB_SEARCHING');
        }
      } catch { /* The question request reports connection failures. */ }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 600);
    };
    void poll();
    return () => { controller.abort(); if (timer !== undefined) window.clearTimeout(timer); };
  }, [sessionId, generationId, status]);
}

export function useAutoScroll<T extends HTMLElement>(dependency: unknown) {
  const ref = useRef<T>(null);
  const pinned = useRef(true);
  useEffect(() => {
    const element = ref.current;
    if (element && pinned.current) element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' });
  }, [dependency]);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const onScroll = () => { pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80; };
    element.addEventListener('scroll', onScroll, { passive: true });
    return () => element.removeEventListener('scroll', onScroll);
  }, []);
  return ref;
}
