"""The assistant: retrieve the most relevant help-page chunks, then let the model answer only from them."""
import time
from dataclasses import dataclass, field

from . import config

SYSTEM_PROMPT = """You are the customer service assistant of an online coffee shop in Poland.
Answer the customer's question using ONLY the numbered sources provided with it.
- Cite the sources you used in square brackets, e.g. [1] or [2][3].
- If the sources don't contain the answer, say that you don't have that information and suggest
  writing to hello@coffeeshop.example. Don't guess or use outside knowledge.
- Prices are in PLN. Keep the answer short and friendly.
- Answer in the language of the question (an English question gets an English answer, even though the shop is in Poland)."""

NO_ANSWER = "Sorry, I don't have that information. Please write to hello@coffeeshop.example."


@dataclass
class Answer:
    answer: str
    sources: list = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0


def build_prompt(question, hits):
    blocks = [f"[{n}] ({chunk.source} - {chunk.section})\n{chunk.text}" for n, (chunk, _score) in enumerate(hits, 1)]
    return "Sources:\n\n" + "\n\n".join(blocks) + f"\n\nCustomer question: {question}"


class Assistant:
    def __init__(self, store, embedder, generator, log=None, top_k=config.TOP_K):
        self.store = store
        self.embedder = embedder
        self.generator = generator
        self.log = log
        self.top_k = top_k

    def retrieve(self, question):
        return self.store.search(self.embedder.embed_query(question), k=self.top_k)

    def ask(self, question):
        start = time.perf_counter()
        hits = self.retrieve(question)
        sources = [{"n": n, "source": c.source, "section": c.section, "similarity": score, "text": c.text}
                   for n, (c, score) in enumerate(hits, 1)]
        try:
            generation = self.generator.generate(SYSTEM_PROMPT, build_prompt(question, hits))
        except Exception as exc:
            self._log(question, start, status="error", error=type(exc).__name__,
                      code=getattr(exc, "code", None))
            raise

        text = NO_ANSWER if generation.blocked or not generation.text else generation.text
        cost = config.estimate_cost(generation.model, generation.input_tokens, generation.output_tokens)
        answer = Answer(text, sources, generation.model, generation.input_tokens, generation.output_tokens,
                        cost, round((time.perf_counter() - start) * 1000))
        self._log(question, start, status="ok", model=generation.model, attempts=generation.attempts,
                  input_tokens=generation.input_tokens, output_tokens=generation.output_tokens,
                  estimated_cost_usd=cost, sources=[s["source"] for s in sources], latency_ms=answer.latency_ms)
        return answer

    def _log(self, question, start, **fields):
        if self.log is None:
            return
        fields.setdefault("latency_ms", round((time.perf_counter() - start) * 1000))
        self.log.write(question=question[:200], **fields)
