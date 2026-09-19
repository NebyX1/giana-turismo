export type ConversationState = 'IDLE' | 'CONNECTING' | 'LISTENING' | 'TRANSCRIBING' | 'WAITING_TRANSCRIPT' | 'RETRIEVING' | 'THINKING' | 'WEB_SEARCHING' | 'SPEAKING' | 'INTERRUPTED' | 'ERROR';
export type VoiceState = ConversationState;
export type MessageRole = 'user' | 'assistant' | 'system_status';

export type EvidenceSource = {
  title: string;
  start_line: number;
  end_line: number;
  source_refs?: number[];
  text: string;
};

export type ConversationMessage = {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  state?: ConversationState;
  sources?: EvidenceSource[];
  pending?: boolean;
  local?: boolean;
};
