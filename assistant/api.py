"""REST API: uvicorn assistant.api:app"""
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from google.genai import errors
from pydantic import BaseModel, Field

from .llm import friendly_error

RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))  # protects the free-tier quota


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["Can I return an opened bag of coffee?"])


class Source(BaseModel):
    n: int
    source: str
    section: str
    similarity: float


class AnswerOut(BaseModel):
    answer: str
    sources: list[Source]
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int


class RateLimiter:
    """Allows `limit` requests per client in any 60-second window."""

    def __init__(self, limit):
        self.limit = limit
        self.calls = defaultdict(deque)

    def allow(self, client_id):
        now = time.monotonic()
        calls = self.calls[client_id]
        while calls and now - calls[0] > 60:
            calls.popleft()
        if len(calls) >= self.limit:
            return False
        calls.append(now)
        return True


def build_assistant():
    """The real assistant: Gemini + Chroma. Builds the index on first start."""
    from .embeddings import GeminiEmbedder
    from .ingest import build_index
    from .llm import GeminiGenerator
    from .monitoring import CallLog
    from .rag import Assistant
    from .store import VectorStore

    store, embedder = VectorStore(), GeminiEmbedder()
    if store.count() == 0:
        build_index(store, embedder)
    return Assistant(store, embedder, GeminiGenerator(), log=CallLog())


def create_app(assistant=None, rate_limit=RATE_LIMIT):
    @asynccontextmanager
    async def lifespan(app):
        app.state.assistant = assistant or build_assistant()
        yield

    app = FastAPI(title="Shop Assistant", version="1.0",
                  description="Answers customer questions from the shop's help pages, with sources.",
                  lifespan=lifespan)
    limiter = RateLimiter(rate_limit)

    @app.get("/")
    def root():
        return {"service": "shop-assistant", "docs": "/docs", "ask": "POST /ask", "stats": "/stats"}

    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "chunks": request.app.state.assistant.store.count()}

    @app.post("/ask", response_model=AnswerOut)
    def ask(body: Question, request: Request):
        if not limiter.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(429, "Too many questions. Please wait a minute.")
        try:
            answer = request.app.state.assistant.ask(body.question)
        except (errors.APIError, httpx.TransportError) as exc:
            raise HTTPException(503, friendly_error(exc)) from exc
        return AnswerOut(**answer.__dict__)

    @app.get("/stats")
    def stats(request: Request):
        log = request.app.state.assistant.log
        if log is None:
            raise HTTPException(404, "Logging is turned off.")
        return log.stats()

    return app


# uvicorn imports this; the real assistant is only built when the server starts,
# and tests call create_app() with their own assistant instead
app = create_app()
