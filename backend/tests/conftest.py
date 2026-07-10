import os
import sys

import pytest

# Use an isolated on-disk SQLite DB for tests, set BEFORE importing the app.
os.environ["DATABASE_URL"] = "sqlite:///./data/test_chat.db"
os.environ.setdefault("GEMINI_API_KEY_1", "test-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app, get_llm  # noqa: E402


class FakeLLM:
    """Deterministic stand-in for Gemini: records inputs, streams fixed chunks."""

    def __init__(self):
        self.stream_calls = []  # (history, user_message) tuples
        self.classify_calls = []
        self.chunks = ["Hello", " from", " fake", " LLM"]
        self.classification = {
            "intent": "code",
            "title": "Fake test chat",
            "followups": ["Follow up 1?", "Follow up 2?", "Follow up 3?"],
        }

    def stream_chat(self, history, user_message):
        self.stream_calls.append((list(history), user_message))
        yield from self.chunks

    def classify(self, user_message, recent_context=""):
        self.classify_calls.append((user_message, recent_context))
        return dict(self.classification)


@pytest.fixture()
def fake_llm():
    return FakeLLM()


@pytest.fixture()
def client(fake_llm):
    # Fresh schema per test for full isolation.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def parse_sse(raw: str):
    """Parse an SSE payload into a list of (event, data_dict) tuples."""
    import json

    events = []
    for block in raw.strip().split("\n\n"):
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event is not None:
            events.append((event, data))
    return events
