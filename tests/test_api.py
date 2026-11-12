import pytest
from fastapi.testclient import TestClient

from assistant import llm
from assistant.api import RateLimiter, create_app
from assistant.llm import GeminiGenerator
from assistant.monitoring import CallLog
from assistant.rag import Assistant
from tests.test_answering import FakeChatClient, api_error, gemini_response


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)


def make_client(store, embedder, tmp_path, chat_client, rate_limit=10):
    generator = GeminiGenerator(client=chat_client, model="main-model", fallback_models=[])
    assistant = Assistant(store, embedder, generator, log=CallLog(tmp_path / "calls.jsonl"))
    return TestClient(create_app(assistant=assistant, rate_limit=rate_limit))


def test_health_reports_indexed_chunks(store, embedder, tmp_path):
    with make_client(store, embedder, tmp_path, FakeChatClient()) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok" and body["chunks"] == store.count()


def test_ask_returns_answer_sources_and_usage(store, embedder, tmp_path):
    chat = FakeChatClient([gemini_response("Yes, within 14 days [1].")])
    with make_client(store, embedder, tmp_path, chat) as client:
        response = client.post("/ask", json={"question": "Can I return a dripper?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Yes, within 14 days [1]."
    assert body["sources"][0]["source"] == "returns.md"
    assert body["model"] == "main-model"
    assert body["input_tokens"] == 120 and body["output_tokens"] == 40


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "x" * 501}])
def test_invalid_questions_are_rejected(store, embedder, tmp_path, payload):
    with make_client(store, embedder, tmp_path, FakeChatClient()) as client:
        assert client.post("/ask", json=payload).status_code == 422


def test_unavailable_model_gives_503_with_a_readable_message(store, embedder, tmp_path):
    chat = FakeChatClient(errors_by_model={"main-model": [api_error(503)] * 3})
    with make_client(store, embedder, tmp_path, chat) as client:
        response = client.post("/ask", json={"question": "Do you ship abroad?"})
    assert response.status_code == 503
    assert "busy" in response.json()["detail"]


def test_stats_reflect_the_calls(store, embedder, tmp_path):
    chat = FakeChatClient([gemini_response(), gemini_response()])
    with make_client(store, embedder, tmp_path, chat) as client:
        client.post("/ask", json={"question": "Do you ship abroad?"})
        client.post("/ask", json={"question": "Which payment methods do you accept?"})
        stats = client.get("/stats").json()
    assert stats["requests"] == 2
    assert stats["tokens"] == {"input": 240, "output": 80}
    assert stats["by_model"]["main-model"]["requests"] == 2


def test_rate_limit(store, embedder, tmp_path):
    chat = FakeChatClient([gemini_response(), gemini_response()])
    with make_client(store, embedder, tmp_path, chat, rate_limit=2) as client:
        codes = [client.post("/ask", json={"question": "Do you ship abroad?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_rate_limiter_window_resets(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("assistant.api.time.monotonic", lambda: now[0])
    limiter = RateLimiter(1)
    assert limiter.allow("a") and not limiter.allow("a")
    assert limiter.allow("b")  # limits are per client
    now[0] += 61
    assert limiter.allow("a")


def test_chat_page_and_its_files_are_served(store, embedder, tmp_path):
    with make_client(store, embedder, tmp_path, FakeChatClient()) as client:
        page = client.get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "/static/app.js" in page.text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200


def test_sources_include_the_passage_text(store, embedder, tmp_path):
    chat = FakeChatClient([gemini_response("Yes [1].")])
    with make_client(store, embedder, tmp_path, chat) as client:
        source = client.post("/ask", json={"question": "Can I return a dripper?"}).json()["sources"][0]
    assert source["text"].startswith("Returning a product")


def test_recent_calls_leave_out_the_questions(store, embedder, tmp_path):
    chat = FakeChatClient([gemini_response(), gemini_response(), gemini_response()])
    with make_client(store, embedder, tmp_path, chat) as client:
        for question in ("Do you ship abroad?", "Can I pay by card?", "Is the mug dishwasher safe?"):
            client.post("/ask", json={"question": question})
        recent = client.get("/stats/recent", params={"limit": 2}).json()
        assert client.get("/dashboard").status_code == 200
    assert len(recent) == 2
    assert recent[-1]["model"] == "main-model" and recent[-1]["input_tokens"] == 120
    assert all("question" not in call and "sources" not in call for call in recent)


def test_stats_include_latency_per_model(store, embedder, tmp_path):
    with make_client(store, embedder, tmp_path, FakeChatClient()) as client:
        client.post("/ask", json={"question": "Do you ship abroad?"})
        by_model = client.get("/stats").json()["by_model"]
    assert by_model["main-model"]["avg_latency_ms"] >= 0
