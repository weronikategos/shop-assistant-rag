"""Settings, read from environment variables with sensible defaults."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = Path(os.environ.get("DOCS_DIR", ROOT / "docs"))
INDEX_DIR = Path(os.environ.get("INDEX_DIR", ROOT / "index"))
LOG_FILE = Path(os.environ.get("LOG_FILE", ROOT / "logs" / "calls.jsonl"))
COLLECTION = "shop-docs"

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIM = 768
CHAT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite").split(",")
                   if m.strip()]
TOP_K = int(os.environ.get("TOP_K", "4"))

# Paid-tier list prices in USD per 1M tokens (Gemini API pricing page, valid through 2026-12-31).
# On the free tier requests cost nothing; the log shows what the same traffic would cost on the paid tier.
PRICES = {
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
    "gemini-3.6-flash": {"input": 0.75, "output": 3.75},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "gemini-embedding-2": {"input": 0.20, "output": 0.0},
}


def estimate_cost(model, input_tokens, output_tokens):
    """Estimated USD cost at paid-tier prices; 0 for models without a known price."""
    price = PRICES.get(model)
    if not price:
        return 0.0
    return round((input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000, 8)
