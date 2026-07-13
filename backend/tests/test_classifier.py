"""Unit tests for the classification parser — the LLM's structured output is
untrusted input, so every malformed shape must degrade to safe defaults
instead of crashing the stream."""

from app.gemini_client import parse_classification


def test_valid_payload():
    raw = '{"intent": "creative", "title": "Poem about the sea", "followups": ["a?", "b?", "c?"]}'
    result = parse_classification(raw)
    assert result == {
        "intent": "creative",
        "title": "Poem about the sea",
        "followups": ["a?", "b?", "c?"],
    }


def test_json_wrapped_in_code_fence():
    raw = '```json\n{"intent": "study", "title": "Learning SQL", "followups": []}\n```'
    result = parse_classification(raw)
    assert result["intent"] == "study"
    assert result["title"] == "Learning SQL"


def test_invalid_json_falls_back():
    assert parse_classification("not json at all") == {
        "intent": "general",
        "title": "New chat",
        "followups": [],
    }


def test_unknown_intent_falls_back_to_general():
    raw = '{"intent": "hacking", "title": "T", "followups": []}'
    assert parse_classification(raw)["intent"] == "general"


def test_non_dict_json_falls_back():
    raw = "[1, 2, 3]"
    assert parse_classification(raw)["intent"] == "general"


def test_followups_filtered_and_capped():
    raw = '{"intent": "code", "title": "T", "followups": ["a", 1, null, "b", "c", "d"]}'
    assert parse_classification(raw)["followups"] == ["a", "b", "c"]


def test_long_title_truncated():
    raw = '{"intent": "code", "title": "%s", "followups": []}' % ("x" * 200)
    assert len(parse_classification(raw)["title"]) <= 80
