# Northbean Memory Sales Bot

A portfolio project: an AI sales assistant for a fictional D2C coffee brand, **Northbean
Coffee**, built around one real product — an **intelligent memory system** that remembers
each logged-in shopper across visits (taste, brew method, budget, objections), lets them
see/correct/delete their own memories (GDPR-first), and proves its quality with a real
evaluation instead of a demo that just "looks like it works."

The memory layer is the product. The sales chat is the stage it performs on.

![demo](docs/demo.gif)

## The problem this demonstrates

Most "AI chatbot with memory" demos either don't actually have memory (the model just has a
long context window) or can't prove the memory helps. This project answers three questions
concretely, not anecdotally:

- **Does memory actually reduce repetition?** Measured: customers restate facts the assistant
  should already know far less often with memory ON than OFF (see Results below).
- **Does the assistant ever invent things?** Products, prices, and discounts only ever come
  from real catalog/discount tool calls — a separate reply checker verifies this on every
  turn and swaps in a safe fallback if the model tries to improvise one.
- **Can a customer trust and control their own data?** See/correct/forget/export/withdraw
  consent are real, working endpoints, not a roadmap item — built GDPR-first rather than
  retrofitted.

## Architecture

```
                 ┌────────────────────┐
  Shopper  ───►  │  Next.js frontend  │  chat · memory panel · ops dashboard
                 └─────────┬──────────┘
                           │ REST/JSON
                 ┌─────────▼──────────┐
                 │   FastAPI backend  │
                 │                    │
                 │  read path  ───────┼──► always-loaded + hybrid search (vector + keyword)
                 │  (before every     │    → scored (similarity/recency/frequency/importance/
                 │   reply)           │      confidence) → composed into the reply's context
                 │                    │
                 │  sales agent  ─────┼──► tool calls only (search/stock/discount);
                 │  (the reply)       │    reply checker validates the output after
                 │                    │
                 │  write path  ──────┼──► PII filter → extractor LLM → rule-based evaluator
                 │  (async, after     │    → dedupe/conflict → store + audit log
                 │   the reply)       │
                 └─────────┬──────────┘
                           │
                 ┌─────────▼──────────┐
                 │ PostgreSQL+pgvector│  one DB: relational tables + memories.embedding,
                 │  (row-level        │  hybrid retrieval (HNSW + GIN tsvector) in SQL,
                 │   security)        │  RLS enforces one customer never sees another's rows
                 └────────────────────┘

  LLM calls (reply + extraction) ──► Vertex AI (Gemini 3.5 Flash, primary) ──► Groq (fallback)
  Embeddings ──► Gemini (AI Studio, gemini-embedding-001)
```

Full reasoning behind each major choice is in `adr/` (ADR-001 through ADR-007) — one file per
decision, written as "what we chose, and what it costs," not just "what we chose."

## Quickstart

```bash
docker compose up -d --build
```

- Shop + memory panel + ops dashboard: http://localhost:3000
- API: http://localhost:8000 (see `GET /health`)
- Pick a persona (Maya / Leo / Ana / Sam) in the frontend to try the memory system as a
  returning shopper; decline the consent prompt to try it anonymously (no memory at all,
  same as any first run).

Requires `.env` with `GEMINI_API_KEY`, `GROQ_API_KEY`, and (for the Vertex AI reply model) a
GCP service-account key plus `VERTEX_PROJECT`/`VERTEX_LOCATION` — see `.env` for the exact
variable names. The service-account JSON itself is never committed; it's bind-mounted from a
host path outside the repo (see `docker-compose.yml`).

## Results

Golden-set evaluation (`evals/golden.jsonl`, 8 retrieval cases across 4 personas), run via
`python evals/run_eval.py` or `pytest tests/test_s7_reliability_eval.py`:

| Metric | Result | Target |
|---|---|---|
| Golden-set precision | **100%** (8/8) | ≥ 90% (NFR-2) |
| Repeated facts, memory ON | **0** | fewer than OFF (AC-8) |
| Repeated facts, memory OFF | 15 | — |
| Cross-customer memory leakage | **0** (enforced by Postgres RLS, not just app logic) | 0 (I1) |
| Invented products/prices/discounts across 20+ sales queries | **0** | 0 (I5) |
| Reply survives a full database outage | **yes** (`docker compose stop db` -> real reply still returned) | required (I3/NFR-3) |
| Credit-card/PII numbers reaching memory or audit log | **0** | 0 (I7) |

Every number above comes from an executable test, not a manual check — see
`tests/test_s1_foundation.py` through `tests/test_s7_reliability_eval.py` and
`evals/run_eval.py`.

## What's deliberately out of scope (v1)

Per the design brief's own scope line — defer production *operations*, show production
*thinking*:

- Nightly reflection/merging of memories (an archived memory never reactivates if the same
  fact resurfaces later — it's stored as a new one instead).
- EU-region hosting, Langfuse/Prometheus/Grafana, load testing, microservices,
  Temporal/Celery (the decay job is a single admin-triggered endpoint, not a scheduler — see
  ADR-007), multi-channel support, anonymous-to-account identity merging.
- LOCATION/address PII detection (spaCy's NER model doesn't load in this sandbox — covered
  PII types are pattern-based: cards, emails, phones, SSNs/IDs, IBANs, crypto addresses,
  password phrases).
- The `handoff_to_human` mock support-inbox page named in the design brief's defaults was
  never built — no sprint ended up owning it, and it's flagged here rather than silently
  skipped.
- A real signup/login system. Identity is four seeded demo personas (Maya/Leo/Ana/Sam), not
  open registration — see ADR-006. Fine for demonstrating the memory layer; a real product
  would need actual auth.
- `embeddings.py` still calls the original free-tier Gemini AI Studio key, not Vertex AI — the
  reply model was migrated (see ADR-003's update) but the embedding call wasn't, since it's a
  separate quota and wasn't the thing blocking S7's eval.

## Project structure

```
api/            FastAPI backend (chat/sales agent, memory read+write path, governance endpoints)
web/            Next.js frontend (chat, memory panel, ops dashboard)
db/             schema.sql (incl. row-level security), seed data
data/           products.json (18-item fake catalog), personas.json (4 synthetic customers)
evals/          golden.jsonl (20 golden cases) + run_eval.py (memory ON/OFF eval runner)
tests/          pytest suites, one per sprint (S1-S7)
adr/            architecture decision records, one per major choice
docs/           design brief, this README's demo GIF
.genesis/       Genesis kit state (spec/plan/decisions/invariants/task history)
SESSION_LOG.md  full narrative build history, bugs found and fixed, and why
```

## Video walkthrough

See `docs/video-script.md` for the recorded demo's script.
