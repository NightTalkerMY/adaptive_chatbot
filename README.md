# 🎭 Adaptive Chat

A streaming LLM chat interface whose **entire UI adapts in real time to what you're talking about**. Ask a coding question and the app morphs into a dark terminal aesthetic; switch to creative writing and it warms into a serif, editorial look; start studying and it becomes a clean blue notebook. The same intent classification that drives the theme also **auto-categorizes and auto-titles every chat session** in the sidebar.

Built for Assessment Question 2: FastAPI token-by-token streaming endpoint + database-backed chat sessions + Gemini.

## Features

| Requirement | How it's met |
|---|---|
| REST endpoint streaming token-by-token (FastAPI) | `POST /api/chat/stream` — Server-Sent Events, one `token` event per Gemini chunk |
| Frontend framework | Next.js (React), deployable to Vercel |
| Chat session management with a database | SQLite via SQLAlchemy — sessions + messages persisted; full history replayed to the LLM every turn |
| LLM of choice | Google Gemini (`gemini-3.1-flash-lite`) with **5-key rotation** on quota errors |
| Test cases to assure quality | 19 pytest cases (streaming contract, persistence, memory, error paths) — see below |
| **Bonus:** Docker | `docker compose up` runs backend + frontend |
| **Bonus:** user-friendly UI | Adaptive themes, streaming cursor, follow-up chips, auto-titled sidebar |

### The unique bits

- **Mood-adaptive UI** — every user message is classified (`code` / `creative` / `study` / `general`) by a lightweight structured-output Gemini call. The intent is emitted as the first SSE event (`meta`), so the theme morphs *before* the answer even starts streaming.
- **Auto-categorized sessions** — the same classification tags the session in the DB; the sidebar groups chats by category with auto-generated titles. The category is a **majority vote over all message intents** (ties break toward the most recent), so one off-topic message never flips an established session, while a real topic change switches promptly.
- **⚡ Live stream stats** — every assistant reply shows its own streaming telemetry inline while it generates (chunk count, chunks/sec, time-to-first-token, total time): visible proof that the response arrives token-by-token from the REST endpoint.
- **Follow-up chips** — the classifier also predicts 3 likely follow-up questions, rendered as one-tap chips.

## Architecture

```
┌────────────────┐   POST /api/chat/stream    ┌─────────────────┐        ┌────────┐
│  Next.js (UI)  │ ─────────────────────────► │  FastAPI        │ ─────► │ Gemini │
│  Vercel/Docker │ ◄───── SSE event stream ── │  (Docker)       │ stream │  API   │
└────────────────┘   meta → token* → done     └───────┬─────────┘        └────────┘
                                                      │ SQLAlchemy
                                                ┌─────▼─────┐
                                                │  SQLite   │  sessions + messages
                                                └───────────┘
```

**SSE event sequence per request:**

1. `meta` — `{session_id, intent, title, followups}` (classification result; drives the adaptive UI)
2. `token` — `{t: "..."}` one event per streamed Gemini chunk
3. `done` — `{session_id, text}` full assembled reply (or `error` — `{detail}`)

**Why these choices (discussion / thought process):**

- **SSE over WebSockets** — chat streaming is strictly server→client; SSE works over plain HTTP, needs no connection state, and survives proxies/serverless better. The endpoint stays a genuine *REST* endpoint as the question asks.
- **History rebuilt from the DB every turn** — the server loads all prior messages for the session and passes them to Gemini as structured history. This is what makes the LLM "know what the user asked previously", and it survives restarts because it lives in SQLite, not in memory.
- **Classification as a separate cheap call** — decoupling it from generation means the theme/title/followups arrive instantly as the first event, and a classification failure can never break the chat (it degrades to `general`).
- **Key rotation** (carried over from a previous project's `ResilientClient`) — on `429 RESOURCE_EXHAUSTED` the client rotates through up to 5 Gemini API keys; on `503` it backs off and retries.
- **SQLite by default, Postgres-ready** — `DATABASE_URL` is env-configurable; SQLAlchemy makes swapping to a hosted Postgres (for a cloud backend) a one-line change.

## Project structure

```
adaptive_chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + SSE streaming endpoint
│   │   ├── gemini_client.py   # ResilientGeminiClient: streaming, key rotation, classifier
│   │   ├── db.py              # SQLAlchemy models: ChatSession, Message
│   │   ├── schemas.py         # Pydantic request/response models
│   │   └── config.py          # env-driven configuration
│   ├── tests/                 # pytest suite (FakeLLM, no network needed)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/                   # Next.js app router (page, layout, adaptive themes)
│   ├── components/            # Sidebar, NerdPanel
│   ├── lib/                   # API client + SSE parser, types
│   └── Dockerfile
└── docker-compose.yml
```

## Running locally

### Backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # add at least GEMINI_API_KEY_1
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000 (talks to :8000 by default)
```

### Docker (bonus)

```bash
cp backend/.env.example backend/.env   # add your Gemini key(s)
docker compose up --build
# frontend: http://localhost:3000, backend: http://localhost:8000/docs
```

### Deploying

- **Frontend → Vercel:** import the `frontend/` directory as a Vercel project and set `NEXT_PUBLIC_API_URL` to your backend's public URL.
- **Backend:** deploy the Docker image anywhere (Render / Railway / Fly.io free tiers work). Set `CORS_ORIGINS` to your Vercel URL. For serverless/multi-instance hosts, point `DATABASE_URL` at a hosted Postgres instead of SQLite.

## Testing methodology (quality assurance)

```bash
cd backend && .venv/bin/python -m pytest tests/ -v
```

19 tests, all runnable offline in <1s. The design principle: **the LLM is the only non-deterministic, slow, paid component — so it's swapped out at the seam.** `ResilientGeminiClient` is injected via FastAPI's dependency system, and tests override it with a deterministic `FakeLLM` that records its inputs and streams fixed chunks.

What's covered and why:

- **Streaming contract** (`test_stream_emits_meta_tokens_done_in_order`) — asserts the exact SSE event order (`meta` → `token`× n → `done`) and that each `token` event carries exactly one model chunk. This pins down the token-by-token requirement.
- **Session memory** (`test_llm_receives_previous_messages_as_history`) — sends two messages in one session and asserts the *recorded* history passed to the LLM on turn 2 contains the full first exchange. This directly verifies "the LLM knows what the user asked previously".
- **Persistence** (`test_messages_persisted_to_database`) — after a stream completes, both user and assistant messages are retrievable from the DB via the REST API.
- **Categorization** (`test_session_created_titled_and_categorised`) — session title/category in the DB reflect the classification.
- **Error paths** — unknown session → `error` SSE event; unknown session on history fetch → 404; empty message → 422 validation error.
- **Classifier robustness** (`test_classifier.py`, 7 cases) — the LLM's JSON output is treated as untrusted input: malformed JSON, code-fenced JSON, unknown intents, wrong types and oversized titles all degrade to safe defaults rather than crashing the stream.

Manual/demo testing: `/docs` (FastAPI's Swagger UI) exercises every endpoint, and the inline stream stats under each reply visualize the live token stream for eyeball verification.

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat/stream` | Stream a chat reply (SSE). Body: `{message, session_id?}` — omit `session_id` to start a new session |
| `GET` | `/api/sessions` | List sessions (id, title, category, timestamps) |
| `GET` | `/api/sessions/{id}/messages` | Full message history for a session |
| `DELETE` | `/api/sessions/{id}` | Delete a session and its messages |
| `GET` | `/api/health` | Health check |
