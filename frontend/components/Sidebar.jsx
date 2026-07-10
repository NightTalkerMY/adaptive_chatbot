"use client";

import { INTENT_META } from "@/lib/types";

const GROUP_ORDER = ["code", "creative", "study", "general"];

export default function Sidebar({ sessions, activeId, onSelect, onNew, onDelete }) {
  const groups = GROUP_ORDER.map((intent) => ({
    intent,
    items: sessions.filter((s) => s.category === intent),
  })).filter((g) => g.items.length > 0);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>🎭 Adaptive Chat</h1>
        <div className="tagline">The UI that reads the room</div>
      </div>
      <button className="new-chat-btn" onClick={onNew}>
        + New chat
      </button>
      <div className="session-list">
        {groups.map((group) => (
          <div key={group.intent}>
            <div className="session-group-label">
              {INTENT_META[group.intent].emoji} {INTENT_META[group.intent].label}
            </div>
            {group.items.map((s) => (
              <button
                key={s.id}
                className={`session-item ${s.id === activeId ? "active" : ""}`}
                onClick={() => onSelect(s.id)}
              >
                <span className="title">{s.title}</span>
                <span
                  className="delete"
                  role="button"
                  aria-label="Delete session"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.id);
                  }}
                >
                  ✕
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}
