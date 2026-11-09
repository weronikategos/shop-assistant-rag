"""Measures retrieval and answer quality on questions with known answers.

    python -m evals.run_evals                   # retrieval + answers (uses the Gemini API)
    python -m evals.run_evals --retrieval-only  # only embeddings, no answer generation

Retrieval: is the page that holds the answer among the top-k chunks?
Answers: does the answer contain the key fact and cite a source? For questions the help pages
can't answer, the assistant should say it doesn't have the information.
"""
import argparse
import json
import re
from pathlib import Path

QUESTIONS = Path(__file__).with_name("questions.jsonl")
NO_ANSWER_PHRASES = ("don't have", "do not have", "no information", "not able to", "can't help", "cannot help",
                     "hello@coffeeshop.example")


def load_questions():
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


def retrieval_hit(hits, expected_source):
    return any(chunk.source == expected_source for chunk, _score in hits)


def answer_ok(answer_text, question):
    text = answer_text.lower().replace("’", "'")
    if question.get("expect_no_answer"):
        return any(phrase in text for phrase in NO_ANSWER_PHRASES)
    has_facts = all(fact.lower() in text for fact in question["must_include"])
    has_citation = re.search(r"\[\d+\]", answer_text) is not None
    return has_facts and has_citation


def run(assistant, questions, retrieval_only=False, out=print):
    """Returns a summary dict; API errors are counted, they don't stop the run."""
    from google.genai import errors
    from assistant.llm import TRANSPORT_ERRORS, friendly_error

    hits_ok = answered = correct = failed_calls = 0
    answerable = [q for q in questions if "source" in q]
    for q in questions:
        line = f"{q['id']} {q['question']}"
        if "source" in q:
            hit = retrieval_hit(assistant.retrieve(q["question"]), q["source"])
            hits_ok += hit
            line += f"\n      retrieval: {'hit' if hit else 'MISS'} (expected {q['source']})"
        if not retrieval_only:
            try:
                answer = assistant.ask(q["question"])
            except (errors.APIError, *TRANSPORT_ERRORS) as exc:
                failed_calls += 1
                out(f"[ERROR] {line}\n      {friendly_error(exc)}")
                continue
            ok = answer_ok(answer.answer, q)
            answered += 1
            correct += ok
            line = f"[{'PASS' if ok else 'FAIL'}] {line}\n      answer ({answer.model}): {answer.answer[:160]}"
        out(line)
    return {
        "retrieval_hit_rate": round(hits_ok / len(answerable), 3) if answerable else None,
        "answered": answered,
        "correct": correct,
        "api_errors": failed_calls,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate the shop assistant")
    parser.add_argument("--retrieval-only", action="store_true", help="skip answer generation")
    parser.add_argument("--only", nargs="+", metavar="ID", help="run only these questions")
    args = parser.parse_args()

    from assistant.api import build_assistant

    questions = [q for q in load_questions() if not args.only or q["id"] in args.only]
    summary = run(build_assistant(), questions, retrieval_only=args.retrieval_only)
    print(f"\nRetrieval hit rate (top-k): {summary['retrieval_hit_rate']:.0%}")
    if not args.retrieval_only:
        print(f"Answers: {summary['correct']}/{summary['answered']} correct"
              + (f", {summary['api_errors']} not answered because of API errors" if summary["api_errors"] else ""))


if __name__ == "__main__":
    main()
