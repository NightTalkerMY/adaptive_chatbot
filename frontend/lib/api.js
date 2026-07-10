export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listSessions() {
  const res = await fetch(`${API_BASE}/api/sessions`);
  if (!res.ok) throw new Error("Failed to load sessions");
  return res.json();
}

export async function getMessages(sessionId) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to load messages");
  return res.json();
}

export async function deleteSession(sessionId) {
  await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: "DELETE" });
}

/**
 * Calls the FastAPI SSE endpoint with POST and parses the event stream
 * manually (the browser's EventSource only supports GET).
 *
 * Callbacks: onMeta({session_id, intent, title, followups}),
 * onToken(text), onDone({session_id, text}), onError(detail).
 */
export async function streamChat(message, sessionId, cb) {
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

  const dispatch = (block) => {
    let event = "message";
    let dataRaw = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) dataRaw += line.slice(6);
    }
    if (!dataRaw) return;
    let data;
    try {
      data = JSON.parse(dataRaw);
    } catch {
      return;
    }
    if (event === "meta") cb.onMeta?.(data);
    else if (event === "token") cb.onToken?.(data.t);
    else if (event === "done") cb.onDone?.(data);
    else if (event === "error") cb.onError?.(data.detail);
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
