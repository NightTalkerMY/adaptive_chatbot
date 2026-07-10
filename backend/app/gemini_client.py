"""Resilient Gemini client with API-key rotation, streaming and intent classification.

Adapted from the ResilientClient in the previous project (IBM_Bob_GroupWAX):
same key-rotation strategy on quota errors, extended with token streaming and
a structured-output classification call that powers the adaptive UI.
"""

import json
import time

from google import genai
from google.genai import types

INTENTS = ("code", "creative", "study", "general")

SYSTEM_INSTRUCTION = (
    "You are Adaptive Chat, a helpful and concise assistant. "
    "Use the conversation history to stay consistent with what the user asked previously. "
    "Format answers in Markdown; use fenced code blocks for code."
)

CLASSIFY_PROMPT = """Classify the user's latest message in a chat conversation.

Recent conversation context (may be empty):
{context}

Latest user message:
{message}

Respond with ONLY a JSON object with these exact keys:
- "intent": one of "code" (programming, debugging, technical), "creative" (writing, brainstorming, art), "study" (learning, explanations, planning, research), "general" (anything else)
- "title": a short 3-6 word title summarising the conversation topic
- "followups": an array of exactly 3 short follow-up questions the user might ask next
"""


def parse_classification(raw: str) -> dict:
    """Parse the classifier's JSON output, falling back to safe defaults."""
    fallback = {"intent": "general", "title": "New chat", "followups": []}
    try:
        # Models sometimes wrap JSON in a code fence despite instructions.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return fallback

    if not isinstance(data, dict):
        return fallback

    intent = data.get("intent")
    if intent not in INTENTS:
        intent = "general"

    title = data.get("title") or "New chat"
    if not isinstance(title, str):
        title = "New chat"

    followups = data.get("followups")
    if not isinstance(followups, list):
        followups = []
    followups = [f for f in followups if isinstance(f, str)][:3]

    return {"intent": intent, "title": title.strip()[:80], "followups": followups}


class ResilientGeminiClient:
    """Wraps google-genai with round-robin key rotation on quota errors."""

    def __init__(self, api_keys, model, verbose=True):
        self.keys = [k for k in api_keys if k]
        self.model = model
        self.verbose = verbose
        self.current_key_idx = 0

        if not self.keys:
            raise ValueError("No valid API keys provided.")
        self._init_client()

    def _init_client(self):
        self.client = genai.Client(api_key=self.keys[self.current_key_idx])

    def _rotate_key(self, reason):
        prev_idx = self.current_key_idx
        self.current_key_idx = (self.current_key_idx + 1) % len(self.keys)
        if self.verbose:
            print(f"[System] Key {prev_idx} unavailable ({reason}). Switching to key {self.current_key_idx}.")
        self._init_client()

    @staticmethod
    def _to_contents(history, user_message):
        """Convert stored messages (role: user/assistant) into Gemini contents."""
        contents = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
        return contents

    def stream_chat(self, history, user_message):
        """Yield response text chunks token-by-token, rotating keys on quota errors."""
        contents = self._to_contents(history, user_message)
        gen_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7,
        )

        attempts = 0
        while attempts < len(self.keys):
            try:
                stream = self.client.models.generate_content_stream(
                    model=self.model, contents=contents, config=gen_config
                )
                for chunk in stream:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as e:
                error_msg = str(e).upper()
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    self._rotate_key("Quota exhausted")
                    attempts += 1
                elif "503" in error_msg:
                    time.sleep(1)
                    attempts += 1
                else:
                    raise
        raise RuntimeError("All API keys are currently unavailable.")

    def classify(self, user_message, recent_context=""):
        """Classify intent + generate session title and follow-up suggestions."""
        prompt = CLASSIFY_PROMPT.format(context=recent_context or "(none)", message=user_message)
        gen_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )

        attempts = 0
        while attempts < len(self.keys):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=prompt, config=gen_config
                )
                return parse_classification(response.text)
            except Exception as e:
                error_msg = str(e).upper()
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    self._rotate_key("Quota exhausted")
                    attempts += 1
                elif "503" in error_msg:
                    time.sleep(1)
                    attempts += 1
                else:
                    break
        # Classification is a nice-to-have: never block the chat on it.
        return parse_classification("")
