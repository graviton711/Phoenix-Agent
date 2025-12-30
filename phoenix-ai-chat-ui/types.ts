
export type ThemeColor = 'blue' | 'purple' | 'rose' | 'emerald' | 'amber' | string;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  executionResult?: string;
  timestamp: string;
  projectName?: string;  // Reference to built project in workspace/builds
}

export interface ChatSession {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: string;
  messages?: ChatMessage[];
}

export interface UserProfile {
  id: string;
  name: string;
  avatar: string;
  isDarkMode?: boolean;
  accentColor?: ThemeColor;
}

