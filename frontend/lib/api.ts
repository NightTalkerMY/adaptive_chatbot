import { Session } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listSessions(): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/api/sessions`);
  if (!res.ok) throw new Error("Failed to load sessions");
  return res.json();
}

export async function getMessages(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to load messages");
  return res.json() as Promise<
    { id: number; role: "user" | "assistant"; content: string; intent: string | null }[]
  >;
}

export async function deleteSession(sessionId: string) {
  await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: "DELETE" });
}

export interface StreamCallbacks {
  /** Raw hook for every SSE event — feeds the nerd-mode panel. */
  onEvent?: (event: string, data: unknown) => void;
  onMeta?: (meta: {
    session_id: string;
    intent: string;
    title: string;
    followups: string[];
  }) => void;
  onToken?: (token: string) => void;
  onDone?: (data: { session_id: string; text: string }) => void;
  onError?: (detail: string) => void;
}

/**
 * Calls the FastAPI SSE endpoint with POST and parses the event stream
 * manually (EventSource only supports GET).
 */
export async function streamChat(
  message: string,
  sessionId: string | null,
  cb: StreamCallbacks
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? undefined }),
  });

  if (!res.ok || !res.body) {
    cb.onError?.(`Request failed (${res.status})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (block: string) => {
    let event = "message";
    let dataRaw = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) dataRaw += line.slice(6);
    }
    if (!dataRaw) return;
    let data: unknown;
    try {
      data = JSON.parse(dataRaw);
    } catch {
      return;
    }
    cb.onEvent?.(event, data);
    if (event === "meta") cb.onMeta?.(data as Parameters<NonNullable<StreamCallbacks["onMeta"]>>[0]);
    else if (event === "token") cb.onToken?.((data as { t: string }).t);
    else if (event === "done") cb.onDone?.(data as { session_id: string; text: string });
    else if (event === "error") cb.onError?.((data as { detail: string }).detail);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE events are separated by a blank line.
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (block.trim()) dispatch(block);
    }
  }
}
