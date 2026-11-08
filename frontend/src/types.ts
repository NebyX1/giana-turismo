export type ConversationState = 'IDLE' | 'RETRIEVING' | 'WEB_SEARCHING' | 'ERROR';

export type EvidenceSource = {
  title: string;
  start_line?: number | null;
  end_line?: number | null;
  source_refs?: (number | string)[];
  text?: string;
  url?: string;
  kind?: string;
  retrieved_at?: string;
  consulted_only?: boolean;
};

export type ConversationMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources?: EvidenceSource[];
};
