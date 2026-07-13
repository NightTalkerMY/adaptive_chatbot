import json
from collections import Counter
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from . import config, db
from .db import ChatSession, Message, get_db, init_db
from .gemini_client import ResilientGeminiClient
from .schemas import ChatRequest, MessageOut, SessionOut

app = FastAPI(title="Adaptive Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def get_llm() -> ResilientGeminiClient:
    """Return the shared Gemini client used across requests."""
    return ResilientGeminiClient(config.API_KEYS, config.GEMINI_MODEL_NAME)


@app.on_event("startup")
def on_startup():
    """Create the database tables when the application starts."""
    init_db()


def sse_event(event: str, data: dict) -> str:
    """Format a named event and JSON payload as an SSE message."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stable_category(intents: list) -> str:
    """Choose the majority intent, breaking ties by most recent use."""
    if not intents:
        return "general"
    counts = Counter(intents)
    last_seen = {intent: i for i, intent in enumerate(intents)}
    return max(counts, key=lambda it: (counts[it], last_seen[it]))


@app.get("/api/health")
def health():
    """Report API availability and the configured Gemini model."""
    return {"status": "ok", "model": config.GEMINI_MODEL_NAME}


@app.get("/api/sessions", response_model=list[SessionOut])
def list_sessions(database: Session = Depends(get_db)):
    """Return all chat sessions, newest activity first."""
    return (
        database.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
    )


@app.get("/api/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_messages(session_id: str, database: Session = Depends(get_db)):
    """Return the complete message history for one chat session."""
    session = database.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.messages


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, database: Session = Depends(get_db)):
    """Delete a chat session and its related messages."""
    session = database.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    database.delete(session)
    database.commit()


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, llm: ResilientGeminiClient = Depends(get_llm)):
    """Stream an incremental Gemini response to the client using SSE."""

    def event_generator():
        """Run the streaming workflow while owning its database session."""
        # The DB session is managed inside the generator because the response
        # outlives the request handler while streaming.
        database = db.SessionLocal()
        try:
            # 1. Load or create the chat session.
            if req.session_id:
                session = database.get(ChatSession, req.session_id)
                if session is None:
                    yield sse_event("error", {"detail": "Session not found"})
                    return
            else:
                session = ChatSession()
                database.add(session)
                database.commit()

            # 2. Build history (previous messages) BEFORE saving the new one —
            #    this is what lets the LLM know what was asked previously.
            history = [
                {"role": m.role, "content": m.content} for m in session.messages
            ]
            recent_context = "\n".join(
                f"{m['role']}: {m['content'][:300]}" for m in history[-6:]
            )

            # 3. Classify intent (drives the adaptive UI + session category).
            classification = llm.classify(req.message, recent_context)

            # Per-message intents feed a majority vote so one off-topic
            # message doesn't flip the whole session's category/theme.
            prior_intents = [
                m.intent for m in session.messages if m.role == "user" and m.intent
            ]
            category = stable_category(prior_intents + [classification["intent"]])

            user_msg = Message(
                session_id=session.id,
                role="user",
                content=req.message,
                intent=classification["intent"],
            )
            database.add(user_msg)

            session.category = category
            if len(history) == 0 or session.title == "New chat":
                session.title = classification["title"]
            database.commit()

            yield sse_event(
                "meta",
                {
                    "session_id": session.id,
                    "intent": category,
                    "title": session.title,
                    "followups": classification["followups"],
                },
            )

            # 4. Stream response chunks from Gemini.
            full_text = ""
            try:
                for chunk in llm.stream_chat(history, req.message):
                    full_text += chunk
                    yield sse_event("token", {"t": chunk})
            except Exception as e:
                yield sse_event("error", {"detail": str(e)})
                return

            # 5. Persist the assistant reply.
            database.add(
                Message(session_id=session.id, role="assistant", content=full_text)
            )
            database.commit()

            yield sse_event("done", {"session_id": session.id, "text": full_text})
        finally:
            database.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
