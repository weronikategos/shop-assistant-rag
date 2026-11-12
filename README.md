# Shop Assistant (RAG)

![tests](https://github.com/weronikategos/shop-assistant-rag/actions/workflows/tests.yml/badge.svg)

A customer help assistant for my online coffee shop, served as a REST API. It answers questions about shipping, returns, payments and products using only the shop's help pages, and cites the pages it used. If the answer isn't in the pages, it says so instead of making something up.

**Live demo:** [shop-assistant-rag-sjrl.onrender.com](https://shop-assistant-rag-sjrl.onrender.com) (chat) and [/dashboard](https://shop-assistant-rag-sjrl.onrender.com/dashboard) (stats). It runs on Render's free plan, so after 15 minutes without visitors it goes to sleep and the first page load takes about a minute. It also uses the free tier of the Gemini API, so an answer can take a while when the models are busy.

It is built as retrieval-augmented generation (RAG): the help pages are split into chunks, turned into embeddings and stored in a vector database (Chroma). For each question the closest chunks are retrieved and the Gemini model writes the answer from them. Every call is logged with its latency, token usage and estimated cost.

The help pages are in [`docs/`](docs/) and describe the same shop and products as my [flask-sql-shop](https://github.com/weronikategos/flask-sql-shop).

A real call from my test run on 9 November 2026 (sources shortened; the numbers differ from run to run):

```
POST /ask  {"question": "How much is shipping to a parcel locker?"}

{
  "answer": "Shipping to an InPost parcel locker costs 12.99 PLN. If your order is over 150 PLN, shipping to a parcel locker in Poland is free! [1]",
  "sources": [
    {"n": 1, "source": "shipping.md", "section": "Delivery options and prices", "similarity": 0.7133},
    {"n": 2, "source": "shipping.md", "section": "Damaged parcels", "similarity": 0.6638},
    ...
  ],
  "model": "gemini-3.6-flash",
  "input_tokens": 462,
  "output_tokens": 489,
  "estimated_cost_usd": 0.00218025,
  "latency_ms": 18854
}
```

The answer came from the fallback model because the main one was overloaded at the time (see [Evaluation](#evaluation)). Most of the 489 output tokens are the model's thinking tokens.

## How it works
1. **Chunking** ([`assistant/chunking.py`](assistant/chunking.py)): every Markdown page is split by its `##` sections, so a chunk is one topic (for example "Delivery options and prices"). The section heading stays in the chunk text, and sections longer than 900 characters are split again by paragraphs. The 6 pages give 29 chunks.
2. **Embeddings** ([`assistant/embeddings.py`](assistant/embeddings.py)): chunks are embedded with `gemini-embedding-2` (768 dimensions) in batches of 20. Documents and questions get different prefixes (`title: … | text: …` and `task: question answering | query: …`), which is how this model tells them apart.
3. **Vector store** ([`assistant/store.py`](assistant/store.py)): Chroma, saved on disk in `index/`, with cosine distance. A search returns the top 4 chunks with their similarity.
4. **Answer** ([`assistant/rag.py`](assistant/rag.py)): the retrieved chunks go into the prompt as numbered sources. The system instruction tells the model to answer only from those sources, cite them as `[1]`, `[2]`, point the customer to the shop's email when the sources don't cover the question, and answer in the language of the question.
5. **Reliability** ([`assistant/llm.py`](assistant/llm.py)): errors 429/500/502/503 are retried twice (after 2 s and 4 s), then the next model in the fallback list is used. A model that doesn't answer within 20 seconds, or returns 504, is skipped and the next one is asked straight away: a backup model that answers is better than a long wait. The model is asked to think at the `low` level, because a short answer from a few sources doesn't need long reasoning; this makes answers faster and uses fewer output tokens (models that don't support thinking levels are asked again without the setting). While a slow answer is on its way, the chat page tells the user that it's still working. A dropped connection is retried like a busy model; this covers both `httpx` and `httpx2`, which `google-genai` 3.x uses under the hood. A blocked answer is replaced by a polite "can't help with that".

## Chat page
The app also serves a small chat page at `/` (plain HTML, CSS and JavaScript in [`assistant/static/`](assistant/static/), no framework). It sends the question to `POST /ask` and shows the answer with clickable citations: clicking `[1]` opens the passage the answer came from. Under each answer you can see the model, the tokens, the estimated cost and the response time. The design uses frosted-glass panels over a coffee, cream and sage palette, follows the system's light or dark theme, works on phones and respects reduced-motion settings.

## Stats dashboard
`/dashboard` shows the call log in a readable form: summary tiles (questions and failures, average and p95 response time, tokens, estimated cost per answer), bar charts of the response time and tokens of the recent calls (coloured by the model that answered, so fallbacks are easy to spot), a table per model and a list of recent calls. The charts are drawn as SVG in plain JavaScript, without a chart library, and the page refreshes every 30 seconds. Questions are never shown on the dashboard; they stay in the log file.

## API
| Endpoint | What it does |
|---|---|
| `GET /` | the chat page |
| `GET /dashboard` | the stats dashboard |
| `POST /ask` | answer a question (3–500 characters) with sources (file, section, similarity and the passage text), model, tokens, estimated cost and latency |
| `GET /stats` | summary of the call log: requests, errors, average and p95 latency, tokens, cost and average latency per model |
| `GET /stats/recent?limit=50` | the last calls (time, status, model, attempts, latency, tokens, cost), without the questions |
| `GET /health` | status and the number of indexed chunks |
| `GET /docs` | interactive Swagger documentation (FastAPI) |

Each client can ask 10 questions per minute (`RATE_LIMIT_PER_MINUTE`), which protects the free-tier quota; above that the API returns 429. When Gemini is unavailable, `/ask` returns 503 with a readable message instead of a stack trace.

## Monitoring and cost
Every question is written to `logs/calls.jsonl` as one JSON line: time, question (cut to 200 characters), model, number of attempts, input and output tokens, estimated cost, latency, the sources used and the status (`ok` or `error`). `GET /stats` aggregates the log. This is the real output after my test run (the 17 eval questions plus a few API calls):

```json
{
  "requests": 22,
  "errors": 1,
  "latency_ms": {"avg": 51450, "p95": 84183},
  "tokens": {"input": 10377, "output": 10270},
  "estimated_cost_usd": 0.046029,
  "by_model": {
    "gemini-3.6-flash": {"requests": 19, "input_tokens": 9486, "output_tokens": 9848, "estimated_cost_usd": 0.044042},
    "gemini-3.8-flash": {"requests": 1, "input_tokens": 411, "output_tokens": 382, "estimated_cost_usd": 0.001741},
    "gemini-3.5-flash-lite": {"requests": 1, "input_tokens": 480, "output_tokens": 40, "estimated_cost_usd": 0.000244}
  },
  "note": "Costs are estimated at paid-tier list prices; requests on the free tier are not billed."
}
```

The one error is a dropped connection that crashed the first eval run; that bug is fixed now (see Reliability above).

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

**Results (9 November 2026, free tier):** retrieval found the right page for all 15 questions that have an answer in the help pages, and all 17 answers passed the checks (15 contained the key fact with a citation, 2 out-of-scope questions were declined with the shop's email). The main model, `gemini-3.8-flash`, was often overloaded or timed out on the free tier that day, so 19 of the 21 calls were answered by the fallback model `gemini-3.6-flash` (and one by `gemini-3.5-flash-lite`). That is also why the latency was high: about 51 s on average and 84 s at p95, most of it spent waiting for the main model before falling back. After this run the timeout was cut to 20 s, the thinking level set to `low`, and `gemini-3.6-flash` became the main model with `gemini-3.8-flash` as a fallback. The costs above are estimates at paid-tier list prices; nothing was billed.

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

Then open http://127.0.0.1:8000 for the chat page, or http://127.0.0.1:8000/docs to try the API. If the index doesn't exist yet, the API builds it on the first start.

With Docker:
```powershell
docker build -t shop-assistant .
docker run -p 8000:8000 -e GEMINI_API_KEY=your-key shop-assistant
```

Deploying on Render: [`render.yaml`](render.yaml) describes the service (Docker, free plan, Frankfurt, health check on `/health`), so it can be created with *New > Blueprint*; Render asks for `GEMINI_API_KEY` during setup. A free instance has no persistent disk, so the index is rebuilt from the help pages on every start (two embedding requests) and the call log starts empty after each restart or deploy. It also sleeps after 15 minutes without traffic, and the first request after that takes about a minute.

Settings (environment variables): `GEMINI_MODEL` (default `gemini-3.6-flash`), `GEMINI_FALLBACK_MODELS` (default `gemini-3.8-flash,gemini-3.5-flash-lite`), `TOP_K` (default 4), `REQUEST_TIMEOUT_S` (default 20), `THINKING_LEVEL` (default `low`, empty for the model's default), `RATE_LIMIT_PER_MINUTE` (default 10).

## Tests
```powershell
python -m pytest
```
41 tests, and none of them call the Gemini API: a bag-of-words embedder and a fake chat client stand in for it, so they run without a key and cost nothing. They cover chunking, the vector store, prompt building, retries and fallback models, the thinking level setting, timeouts and dropped connections (`httpx` and `httpx2`), cost estimates, the call log and stats, the API endpoints (validation, 503, rate limit, the chat page and the dashboard) and the eval checks. GitHub Actions runs them on every push and also builds the Docker image.

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
  static/         chat page and stats dashboard (HTML, CSS, JavaScript)
docs/             the shop's help pages (the knowledge base)
evals/            eval questions and the eval script
tests/
```
