import os

from dotenv import load_dotenv

load_dotenv()

# Empty strings in .env (e.g. "DATABASE_URL=") must behave like unset vars,
# hence `or` instead of os.getenv defaults.

# Model configuration
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME") or "gemini-3.1-flash-lite"

# Up to 5 API keys, rotated when quota is exhausted.
API_KEYS = [k for k in (os.getenv(f"GEMINI_API_KEY_{i}") for i in range(1, 6)) if k]

# SQLite by default; overridable for tests / Postgres deployments.
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./data/chat.db"

# Comma-separated list of allowed CORS origins ("*" for demo purposes).
CORS_ORIGINS = (os.getenv("CORS_ORIGINS") or "*").split(",")
