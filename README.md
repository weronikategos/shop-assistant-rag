# Shop Assistant (RAG)

![tests](https://github.com/weronikategos/shop-assistant-rag/actions/workflows/tests.yml/badge.svg)

A customer help assistant for my online coffee shop, served as a REST API. It answers questions about shipping, returns, payments and products using only the shop's help pages, and cites the pages it used. If the answer isn't in the pages, it says so instead of making something up.

It is built as retrieval-augmented generation (RAG): the help pages are split into chunks, turned into embeddings and stored in a vector database (Chroma). For each question the closest chunks are retrieved and the Gemini model writes the answer from them. Every call is logged with its latency, token usage and estimated cost.

The help pages are in [`docs/`](docs/) and describe the same shop and products as my [flask-sql-shop](https://github.com/weronikategos/flask-sql-shop).

An example call (the numbers differ from run to run):

```
POST /ask  {"question": "Can I return an opened bag of coffee?"}

{
  "answer": "No. Opened coffee and tea can't be returned for hygiene reasons, unless they are faulty [1].",
  "sources": [
    {"n": 1, "source": "returns.md", "section": "Returning a product", "similarity": 0.81},
    {"n": 2, "source": "returns.md", "section": "Coffee that tastes wrong", "similarity": 0.74},
    ...
  ],
  "model": "gemini-3.8-flash",
  "input_tokens": 742,
  "output_tokens": 38,
  "estimated_cost_usd": 0.0007,
  "latency_ms": 1840
}
```

## How it works
1. **Chunking** ([`assistant/chunking.py`](assistant/chunking.py)): every Markdown page is split by its `##` sections, so a chunk is one topic (for example "Delivery options and prices"). The section heading stays in the chunk text, and sections longer than 900 characters are split again by paragraphs. The 6 pages give 29 chunks.
2. **Embeddings** ([`assistant/embeddings.py`](assistant/embeddings.py)): chunks are embedded with `gemini-embedding-2` (768 dimensions) in batches of 20. Documents and questions get different prefixes (`title: … | text: …` and `task: question answering | query: …`), which is how this model tells them apart.
3. **Vector store** ([`assistant/store.py`](assistant/store.py)): Chroma, saved on disk in `index/`, with cosine distance. A search returns the top 4 chunks with their similarity.
4. **Answer** ([`assistant/rag.py`](assistant/rag.py)): the retrieved chunks go into the prompt as numbered sources. The system instruction tells the model to answer only from those sources, cite them as `[1]`, `[2]`, and point the customer to the shop's email when the sources don't cover the question.
5. **Reliability** ([`assistant/llm.py`](assistant/llm.py)): errors 429/500/502/503 are retried twice (after 2 s and 4 s), then the next model in the fallback list is used. Timeouts (60 s) and 504 go straight to the next model. A blocked answer is replaced by a polite "can't help with that".

## API
| Endpoint | What it does |
|---|---|
| `POST /ask` | answer a question (3–500 characters) with sources, model, tokens, estimated cost and latency |
| `GET /stats` | summary of the call log: requests, errors, average and p95 latency, tokens and cost per model |
| `GET /health` | status and the number of indexed chunks |
| `GET /docs` | interactive Swagger documentation (FastAPI) |

Each client can ask 10 questions per minute (`RATE_LIMIT_PER_MINUTE`), which protects the free-tier quota; above that the API returns 429. When Gemini is unavailable, `/ask` returns 503 with a readable message instead of a stack trace.

## Monitoring and cost
Every question is written to `logs/calls.jsonl` as one JSON line: time, question (cut to 200 characters), model, number of attempts, input and output tokens, estimated cost, latency, the sources used and the status (`ok` or `error`). `GET /stats` aggregates the log (example output):

```json
{
  "requests": 24,
  "errors": 1,
  "latency_ms": {"avg": 1912, "p95": 3480},
  "tokens": {"input": 17630, "output": 1104},
  "estimated_cost_usd": 0.0174,
  "by_model": {"gemini-3.8-flash": {"requests": 21, "estimated_cost_usd": 0.0159}, "...": "..."},
  "note": "Costs are estimated at paid-tier list prices; requests on the free tier are not billed."
}
```

The project runs on the free tier, so nothing is actually billed. The cost is estimated from the paid-tier price list in [`assistant/config.py`](assistant/config.py), to see what the same traffic would cost in production. Output tokens include the model's thinking tokens, because they are billed as output.

## Evaluation
[`evals/questions.jsonl`](evals/questions.jsonl) has 17 questions: 15 with a known answer (the page it's on and the key fact, e.g. `12.99` for a parcel locker) and 2 that the help pages can't answer (espresso machine repairs, the weather). [`evals/run_evals.py`](evals/run_evals.py) checks two things:
- **retrieval**: is the right page among the top 4 chunks (hit rate)
- **answers**: does the answer contain the key fact and cite a source; for the 2 out-of-scope questions, does it say it doesn't have the information

```powershell
python -m evals.run_evals --retrieval-only   # embeddings only
python -m evals.run_evals                    # retrieval and answers
python -m evals.run_evals --only q05 q16     # chosen questions
```

API errors (for example the free-tier rate limit) are counted separately and don't stop the run.

## Running it locally
You need a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:GEMINI_API_KEY = "your-key"
python -m assistant.ingest            # builds the index in index/
uvicorn assistant.api:app --reload
```

Then open http://127.0.0.1:8000/docs and try `POST /ask`. If the index doesn't exist yet, the API builds it on the first start.

With Docker:
```powershell
docker build -t shop-assistant .
docker run -p 8000:8000 -e GEMINI_API_KEY=your-key shop-assistant
```

Settings (environment variables): `GEMINI_MODEL` (default `gemini-3.8-flash`), `GEMINI_FALLBACK_MODELS` (default `gemini-3.6-flash,gemini-3.5-flash-lite`), `TOP_K` (default 4), `RATE_LIMIT_PER_MINUTE` (default 10).

## Tests
```powershell
python -m pytest
```
33 tests, and none of them call the Gemini API: a bag-of-words embedder and a fake chat client stand in for it, so they run without a key and cost nothing. They cover chunking, the vector store, prompt building, retries and fallback models, timeouts, cost estimates, the call log and stats, the API endpoints (validation, 503, rate limit) and the eval checks. GitHub Actions runs them on every push and also builds the Docker image.

## Project structure
```
assistant/
  config.py       settings, models, price list
  chunking.py     splitting Markdown pages into chunks
  embeddings.py   Gemini embeddings
  store.py        Chroma vector store
  ingest.py       building the index
  llm.py          Gemini calls with retries and fallback models
  rag.py          retrieval, prompt and answer
  monitoring.py   call log and stats
  api.py          FastAPI app and rate limiter
docs/             the shop's help pages (the knowledge base)
evals/            eval questions and the eval script
tests/
```
