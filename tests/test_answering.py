from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from assistant import config, llm
from assistant.llm import GeminiGenerator, friendly_error
from assistant.monitoring import CallLog
from assistant.rag import NO_ANSWER, Assistant, build_prompt


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)


def gemini_response(text="OK", prompt_tokens=120, output_tokens=30, thoughts=10, finish="STOP"):
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=output_tokens,
                            thoughts_token_count=thoughts)
    candidate = SimpleNamespace(finish_reason=SimpleNamespace(name=finish))
    return SimpleNamespace(text=text, candidates=[candidate], usage_metadata=usage)


def api_error(code):
    return errors.ServerError(code, {"error": {"code": code, "message": "busy", "status": "UNAVAILABLE"}})


class FakeChatClient:
    """Stands in for client.models.generate_content: raises the scripted errors per model, then answers."""

    def __init__(self, responses=None, errors_by_model=None):
        self.responses = list(responses or [gemini_response()])
        self.errors_by_model = {m: list(e) for m, e in (errors_by_model or {}).items()}
        self.requests = []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        scripted = self.errors_by_model.get(model)
        if scripted:
            raise scripted.pop(0)
        return self.responses.pop(0)


def make_assistant(store, embedder, tmp_path, client, **generator_args):
    generator = GeminiGenerator(client=client, model="main-model", fallback_models=generator_args.get("fallbacks", []),
                                on_status=generator_args.get("on_status"))
    return Assistant(store, embedder, generator, log=CallLog(tmp_path / "calls.jsonl"))


def test_answer_comes_with_sources_and_usage(store, embedder, tmp_path):
    client = FakeChatClient([gemini_response("Parcel lockers usually take 1-2 working days [1].")])
    assistant = make_assistant(store, embedder, tmp_path, client)
    answer = assistant.ask("How long does delivery to a parcel locker take?")

    assert answer.answer.endswith("[1].")
    assert answer.sources[0]["source"] == "shipping.md"
    assert (answer.input_tokens, answer.output_tokens) == (120, 40)  # thinking tokens count as output
    prompt = client.requests[0]["contents"]
    assert prompt.startswith("Sources:") and "[1] (shipping.md" in prompt
    assert "ONLY the numbered sources" in client.requests[0]["config"].system_instruction


def test_prompt_numbers_every_source(store, embedder):
    hits = store.search(embedder.embed_query("return a grinder"), k=3)
    prompt = build_prompt("Can I return a grinder?", hits)
    assert all(f"[{n}]" in prompt for n in (1, 2, 3))
    assert prompt.endswith("Customer question: Can I return a grinder?")


def test_blocked_or_empty_answer_falls_back_to_a_safe_reply(store, embedder, tmp_path):
    client = FakeChatClient([gemini_response("", finish="SAFETY")])
    answer = make_assistant(store, embedder, tmp_path, client).ask("?")
    assert answer.answer == NO_ANSWER


def test_cost_is_estimated_at_paid_prices(store, embedder, tmp_path):
    client = FakeChatClient([gemini_response(prompt_tokens=1_000_000, output_tokens=1_000_000, thoughts=0)])
    generator = GeminiGenerator(client=client, model="gemini-3.8-flash", fallback_models=[])
    answer = Assistant(store, embedder, generator).ask("Do you ship abroad?")
    assert answer.estimated_cost_usd == pytest.approx(0.75 + 3.75)
    assert config.estimate_cost("unknown-model", 100, 100) == 0.0


def test_busy_model_is_retried_then_falls_back(store, embedder, tmp_path):
    status = []
    client = FakeChatClient(errors_by_model={"main-model": [api_error(503)] * 3})
    assistant = make_assistant(store, embedder, tmp_path, client, fallbacks=["backup"], on_status=status.append)
    answer = assistant.ask("Do you ship abroad?")
    assert answer.model == "backup"
    assert [r["model"] for r in client.requests] == ["main-model"] * 3 + ["backup"]
    assert status[-1] == "[fallback] switching to backup"
    assert assistant.log.records()[-1]["attempts"] == 4


def test_deadline_and_timeouts_go_straight_to_fallback(store, embedder, tmp_path):
    client = FakeChatClient([gemini_response(), gemini_response()],
                            errors_by_model={"main-model": [api_error(504), httpx.ReadTimeout("slow")]})
    assistant = make_assistant(store, embedder, tmp_path, client, fallbacks=["backup"])
    assert assistant.ask("?").model == "backup"
    assert assistant.ask("?").model == "backup"
    assert [r["model"] for r in client.requests] == ["main-model", "backup", "main-model", "backup"]


def test_dropped_connection_is_retried(store, embedder, tmp_path):
    client = FakeChatClient(errors_by_model={"main-model": [httpx.ReadError("reset")]})
    assert make_assistant(store, embedder, tmp_path, client).ask("?").model == "main-model"


def test_other_errors_are_raised_and_logged(store, embedder, tmp_path):
    bad_request = errors.ClientError(400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}})
    client = FakeChatClient(errors_by_model={"main-model": [bad_request]})
    assistant = make_assistant(store, embedder, tmp_path, client, fallbacks=["backup"])
    with pytest.raises(errors.ClientError):
        assistant.ask("?")
    assert [r["model"] for r in client.requests] == ["main-model"]
    assert assistant.log.records()[-1]["status"] == "error"


def test_friendly_errors():
    assert "busy" in friendly_error(api_error(503))
    assert "limit" in friendly_error(errors.ClientError(429, {"error": {"code": 429, "message": "x", "status": "X"}}))
    assert "interrupted" in friendly_error(httpx.ReadError("reset"))


def test_stats_summarise_the_log(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    log.write(status="ok", model="m1", input_tokens=100, output_tokens=20, estimated_cost_usd=0.001, latency_ms=900)
    log.write(status="ok", model="m2", input_tokens=50, output_tokens=10, estimated_cost_usd=0.0005, latency_ms=1100)
    log.write(status="error", latency_ms=60000)
    stats = log.stats()
    assert (stats["requests"], stats["errors"]) == (3, 1)
    assert stats["tokens"] == {"input": 150, "output": 30}
    assert stats["estimated_cost_usd"] == pytest.approx(0.0015)
    assert stats["latency_ms"]["avg"] == 1000
    assert set(stats["by_model"]) == {"m1", "m2"}


def test_empty_log_has_no_latency(tmp_path):
    assert CallLog(tmp_path / "none.jsonl").stats()["latency_ms"] == {"avg": None, "p95": None}


def test_network_errors_from_the_sdk_transport_are_handled(store, embedder, tmp_path):
    """google-genai 3.x raises httpx2 errors, which are not subclasses of the httpx ones."""
    httpx2 = pytest.importorskip("httpx2")
    dropped = FakeChatClient(errors_by_model={"main-model": [httpx2.ReadError("reset")]})
    assistant = make_assistant(store, embedder, tmp_path, dropped, fallbacks=["backup"])
    assert assistant.ask("?").model == "main-model"  # dropped connection: retried on the same model
    assert [r["model"] for r in dropped.requests] == ["main-model", "main-model"]

    slow = FakeChatClient(errors_by_model={"main-model": [httpx2.ReadTimeout("slow")]})
    assistant = make_assistant(store, embedder, tmp_path, slow, fallbacks=["backup"])
    assert assistant.ask("?").model == "backup"  # timeout: straight to the next model
    assert [r["model"] for r in slow.requests] == ["main-model", "backup"]

    assert "interrupted" in friendly_error(httpx2.ReadError("reset"))
