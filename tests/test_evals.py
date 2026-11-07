from assistant.llm import GeminiGenerator
from assistant.rag import Assistant
from evals.run_evals import answer_ok, load_questions, run
from tests.test_answering import FakeChatClient, api_error, gemini_response


def test_questions_file_is_valid():
    questions = load_questions()
    assert len({q["id"] for q in questions}) == len(questions)
    assert all(("source" in q and q["must_include"]) or q.get("expect_no_answer") for q in questions)


def test_answer_needs_the_fact_and_a_citation():
    question = {"must_include": ["12.99"]}
    assert answer_ok("A parcel locker costs 12.99 PLN [1].", question)
    assert not answer_ok("A parcel locker costs 12.99 PLN.", question)  # no citation
    assert not answer_ok("It costs 16.99 PLN [1].", question)


def test_no_answer_questions():
    question = {"expect_no_answer": True}
    assert answer_ok("Sorry, I don't have that information.", question)
    assert not answer_ok("Yes, we repair espresso machines.", question)


def test_retrieval_finds_most_expected_pages_with_the_fake_embedder(store, embedder):
    assistant = Assistant(store, embedder, generator=None)
    summary = run(assistant, load_questions(), retrieval_only=True, out=lambda _: None)
    # a bag-of-words fake is much weaker than real embeddings; this guards the pipeline, not quality
    assert summary["retrieval_hit_rate"] >= 0.6


def test_api_errors_are_counted(store, embedder):
    chat = FakeChatClient([gemini_response("Free over 150 PLN [1].")], errors_by_model={"m": [api_error(400)]})
    assistant = Assistant(store, embedder, GeminiGenerator(client=chat, model="m", fallback_models=[]))
    questions = [q for q in load_questions() if q["id"] in ("q01", "q02")]
    summary = run(assistant, questions, out=lambda _: None)
    assert summary["api_errors"] == 1 and summary["answered"] == 1 and summary["correct"] == 1
