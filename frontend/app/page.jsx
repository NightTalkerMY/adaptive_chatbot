"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import Sidebar from "@/components/Sidebar";
import Icon from "@/components/Icons";
import * as api from "@/lib/api";
import { INTENT_META } from "@/lib/types";

/** Live token-stream stats shown under an assistant reply while it streams. */
function StreamStatsLine({ stats, streaming }) {
  if (!stats) return null;

  if (stats.chunks === 0) {
    return streaming ? (
      <div className="stream-stats">
        <Icon name="zap" size={12} /> waiting for first token…
      </div>
    ) : null;
  }

  const ttft = stats.firstTokenAt
    ? ((stats.firstTokenAt - stats.sentAt) / 1000).toFixed(2)
    : null;
  const span =
    stats.firstTokenAt && stats.lastTokenAt
      ? (stats.lastTokenAt - stats.firstTokenAt) / 1000
      : 0;
  const rate = span > 0 ? ((stats.chunks - 1) / span).toFixed(1) : null;
  const elapsed = stats.lastTokenAt
    ? ((stats.lastTokenAt - stats.sentAt) / 1000).toFixed(1)
    : null;

  return (
    <div className="stream-stats">
      <Icon name="zap" size={12} /> {stats.chunks} chunk
      {stats.chunks > 1 ? "s" : ""}
      {rate && <> · {rate}/s</>}
      {ttft && <> · first token {ttft}s</>}
      {elapsed && <> · {elapsed}s total</>}
      {streaming && <> · streaming…</>}
    </div>
  );
}

export default function Home() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [intent, setIntent] = useState("general");
  const [followups, setFollowups] = useState([]);
  const [backendDown, setBackendDown] = useState(false);

  const messagesRef = useRef(null);
  const textareaRef = useRef(null);

  // The adaptive-theme hook: the classified intent morphs the whole UI.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", intent);
  }, [intent]);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.listSessions());
      setBackendDown(false);
    } catch {
      setBackendDown(true);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const selectSession = async (id) => {
    setActiveId(id);
    setFollowups([]);
    const msgs = await api.getMessages(id);
    setMessages(
      msgs.map((m) => ({
        role: m.role,
        content: m.content,
        intent: m.intent,
      }))
    );
    const session = sessions.find((s) => s.id === id);
    if (session) setIntent(session.category);
  };

  const newChat = () => {
    setActiveId(null);
    setMessages([]);
    setFollowups([]);
    setIntent("general");
  };

  const removeSession = async (id) => {
    await api.deleteSession(id);
    if (id === activeId) newChat();
    refreshSessions();
  };

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;

    setInput("");
    setFollowups([]);
    setIsStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: trimmed },
      {
        role: "assistant",
        content: "",
        streaming: true,
        stats: { sentAt: performance.now(), chunks: 0 },
      },
    ]);

    const appendToDraft = (updater) =>
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = updater(next[next.length - 1]);
        return next;
      });

    // Typewriter smoothing: Gemini delivers text in a few large, near-
    // instant chunks, so rendering on arrival looks like it "pops in".
    // We buffer what the network delivers (`received`) and reveal it at a
    // steady pace, while the stats line still reports real network chunks.
    let received = "";
    let shown = 0;
    let doneReceived = false;
    let failed = false;

    const finish = (timer) => {
      clearInterval(timer);
      appendToDraft((m) => ({ ...m, streaming: false }));
      setIsStreaming(false);
      refreshSessions();
    };

    const timer = setInterval(() => {
      if (failed) {
        clearInterval(timer);
        return;
      }
      const backlog = received.length - shown;
      if (backlog > 0) {
        // Reveal faster when far behind, but never fewer than 2 chars/tick.
        shown = Math.min(
          received.length,
          shown + Math.max(2, Math.floor(backlog / 20))
        );
        const visible = received.slice(0, shown);
        appendToDraft((m) => ({ ...m, content: visible }));
      } else if (doneReceived) {
        finish(timer);
      }
    }, 24);

    const fail = (detail) => {
      failed = true;
      clearInterval(timer);
      appendToDraft((m) => ({
        ...m,
        content: received,
        streaming: false,
        error: detail,
      }));
      setIsStreaming(false);
      refreshSessions();
    };

    try {
      await api.streamChat(trimmed, activeId, {
        onMeta: (meta) => {
          setActiveId(meta.session_id);
          setIntent(meta.intent);
          setFollowups(meta.followups);
        },
        onToken: (t) => {
          received += t;
          appendToDraft((m) => {
            const now = performance.now();
            const stats = m.stats
              ? {
                  ...m.stats,
                  chunks: m.stats.chunks + 1,
                  firstTokenAt: m.stats.firstTokenAt ?? now,
                  lastTokenAt: now,
                }
              : undefined;
            return { ...m, stats };
          });
        },
        onDone: () => {
          doneReceived = true;
        },
        onError: fail,
      });
      // Stream ended without an explicit done event (e.g. connection drop).
      doneReceived = true;
    } catch {
      fail("Could not reach the backend. Is it running on port 8000?");
    }
  };

  const activeSession = sessions.find((s) => s.id === activeId);

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={selectSession}
        onNew={newChat}
        onDelete={removeSession}
      />

      <main className="chat-area">
        <header className="chat-header">
          <span className="intent-badge">
            <Icon name={INTENT_META[intent].icon} size={13} />
            {INTENT_META[intent].label} mode
          </span>
          <span className="session-title">
            {activeSession?.title ?? "New chat"}
          </span>
        </header>

        <div className="messages" ref={messagesRef}>
          <div className="messages-inner">
            {messages.length === 0 && (
              <div className="empty-hero">
                <div className="big">What are we talking about today?</div>
                <div>
                  {backendDown ? (
                    <>
                      <Icon name="alert" size={14} /> Backend unreachable —
                      start it with: uvicorn app.main:app (port 8000)
                    </>
                  ) : (
                    "The interface adapts to the conversation. Try one of these:"
                  )}
                </div>
                {!backendDown && (
                  <div className="modes">
                    <button
                      className="mode-chip"
                      onClick={() => send("Write a Python function that merges two sorted lists")}
                    >
                      <Icon name="code" size={14} /> Debug some code
                    </button>
                    <button
                      className="mode-chip"
                      onClick={() => send("Write a short poem about the sea at night")}
                    >
                      <Icon name="pen" size={14} /> Write a poem
                    </button>
                    <button
                      className="mode-chip"
                      onClick={() => send("Explain how photosynthesis works, step by step")}
                    >
                      <Icon name="book" size={14} /> Learn something
                    </button>
                  </div>
                )}
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className={`bubble ${m.error ? "error" : ""}`}>
                  {m.role === "assistant" ? (
                    <>
                      {m.error ? (
                        <p>
                          <Icon name="alert" size={14} /> {m.error}
                        </p>
                      ) : (
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      )}
                      {m.streaming && <span className="cursor" />}
                      <StreamStatsLine stats={m.stats} streaming={m.streaming} />
                    </>
                  ) : (
                    m.content
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {followups.length > 0 && !isStreaming && (
          <div className="followups">
            {followups.map((f, i) => (
              <button key={i} className="followup-chip" onClick={() => send(f)}>
                {f}
              </button>
            ))}
          </div>
        )}

        <div className="composer">
          <div className="composer-inner">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              placeholder="Ask anything…"
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
            />
            <button
              className="send"
              disabled={isStreaming || !input.trim()}
              onClick={() => send(input)}
            >
              {isStreaming ? "…" : "Send"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
