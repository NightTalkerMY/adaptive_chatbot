export type Intent = "code" | "creative" | "study" | "general";

export interface Session {
  id: string;
  title: string;
  category: Intent;
  created_at: string;
  updated_at: string;
}

export interface StreamStats {
  sentAt: number; // performance.now() when the request was sent
  firstTokenAt?: number;
  lastTokenAt?: number;
  chunks: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  intent?: Intent | null;
  streaming?: boolean;
  error?: string;
  stats?: StreamStats;
}

export const INTENT_META: Record<Intent, { label: string; emoji: string }> = {
  code: { label: "Code", emoji: "💻" },
  creative: { label: "Creative", emoji: "🎨" },
  study: { label: "Study", emoji: "📚" },
  general: { label: "General", emoji: "💬" },
};
