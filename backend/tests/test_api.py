"""API tests.

Quality-assurance strategy:
- The Gemini client is replaced with a deterministic FakeLLM (dependency
  injection via FastAPI's dependency_overrides) so tests are fast, free and
  reproducible — no network, no API keys.
- Each test runs against a fresh SQLite schema (see conftest).
- Covers: streaming contract (SSE event order + incremental chunk delivery),
  persistence, context/memory across turns, session categorisation,
  and error handling.
"""

from tests.conftest import parse_sse


def stream_chat(client, message, session_id=None):
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    resp = client.post("/api/chat/stream", json=payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    return parse_sse(resp.text)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_stream_emits_meta_tokens_done_in_order(client, fake_llm):
    events = stream_chat(client, "Write me a python function")

    kinds = [e for e, _ in events]
    assert kinds[0] == "meta"
    assert kinds[-1] == "done"
    assert kinds[1:-1] == ["token"] * len(fake_llm.chunks)

    # Token-by-token: each SSE token event carries exactly one model chunk.
    tokens = [d["t"] for e, d in events if e == "token"]
    assert tokens == fake_llm.chunks

    # done event contains the assembled full text.
    done = events[-1][1]
    assert done["text"] == "".join(fake_llm.chunks)


def test_meta_contains_classification(client, fake_llm):
    events = stream_chat(client, "Debug my code")
    meta = events[0][1]
    assert meta["intent"] == "code"
    assert meta["title"] == "Fake test chat"
    assert len(meta["followups"]) == 3
    assert meta["session_id"]


def test_messages_persisted_to_database(client):
    events = stream_chat(client, "First question")
    session_id = events[0][1]["session_id"]

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "First question"
    assert messages[0]["intent"] == "code"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hello from fake LLM"


def test_llm_receives_previous_messages_as_history(client, fake_llm):
    """The requirement: the LLM must know what the user asked previously."""
    events = stream_chat(client, "What is FastAPI?")
    session_id = events[0][1]["session_id"]

    stream_chat(client, "Show me an example of it", session_id=session_id)

    # Second call must include the full first exchange as history.
    history, user_message = fake_llm.stream_calls[1]
    assert user_message == "Show me an example of it"
    assert {"role": "user", "content": "What is FastAPI?"} in history
    assert {"role": "assistant", "content": "Hello from fake LLM"} in history


def test_session_created_titled_and_categorised(client):
    events = stream_chat(client, "hello")
    session_id = events[0][1]["session_id"]

    resp = client.get("/api/sessions")
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["title"] == "Fake test chat"
    assert sessions[0]["category"] == "code"


def test_category_not_flipped_by_single_offtopic_message(client, fake_llm):
    """An established session keeps its majority category when one message
    classifies differently (e.g. a 'thanks!' in the middle of a code chat)."""
    events = stream_chat(client, "Fix my python bug")
    session_id = events[0][1]["session_id"]
    stream_chat(client, "Now optimise that function", session_id=session_id)

    # Third message classifies as general — majority (2x code) must hold.
    fake_llm.classification["intent"] = "general"
    events = stream_chat(client, "thanks, that's great!", session_id=session_id)

    assert events[0][1]["intent"] == "code"
    assert client.get("/api/sessions").json()[0]["category"] == "code"


def test_category_switches_on_sustained_topic_change(client, fake_llm):
    """A genuine topic change wins as soon as it ties the old majority,
    because ties break in favour of the most recent intent."""
    events = stream_chat(client, "Fix my python bug")
    session_id = events[0][1]["session_id"]

    fake_llm.classification["intent"] = "creative"
    events = stream_chat(client, "Write a poem about it", session_id=session_id)

    # 1x code vs 1x creative — recency tie-break flips to creative.
    assert events[0][1]["intent"] == "creative"
    assert client.get("/api/sessions").json()[0]["category"] == "creative"


def test_unknown_session_returns_error_event(client):
    events = stream_chat(client, "hi", session_id="does-not-exist")
    assert events == [("error", {"detail": "Session not found"})]


def test_get_messages_unknown_session_404(client):
    resp = client.get("/api/sessions/nope/messages")
    assert resp.status_code == 404


def test_delete_session(client):
    events = stream_chat(client, "hello")
    session_id = events[0][1]["session_id"]

    assert client.delete(f"/api/sessions/{session_id}").status_code == 204
    assert client.get("/api/sessions").json() == []


def test_empty_message_rejected(client):
    resp = client.post("/api/chat/stream", json={"message": ""})
    assert resp.status_code == 422
