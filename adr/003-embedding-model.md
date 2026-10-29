# ADR-003: LLM reply-model provider, and embedding model pinned at S1

**Status:** Accepted (S1), reply-model provider superseded S7 (see Update below)

## Embedding model

**Context:** `memories.embedding` needs a fixed vector dimension before any row is written;
changing the embedding model later requires a re-embed script for every existing row.

**Decision:** Pin to Gemini `text-embedding-004` (768 dimensions) for v1, matching the
free-tier LLM choice (LiteLLM/Gemini) already locked in brief §0. `memories.embedding` is
`vector(768)` in `db/schema.sql`.

**Consequences:** Changing providers or model later requires a migration (`ALTER COLUMN
... TYPE vector(N)`) and a re-embed script over existing rows. Acceptable for a v1
portfolio project; flagged as a deferred concern, not solved now.

**Update (S3):** `text-embedding-004` has been retired by Google (`404 Not Found` on
`embedContent`, confirmed live via `ListModels`). Replacement: `gemini-embedding-001`
(litellm model string `gemini/gemini-embedding-001`), called with `dimensions=768` to match
the existing column width exactly -- no schema migration needed. The 768-dimension decision
itself still stands; only the model name changed. See `api/app/embeddings.py`. This path is
still on the free-tier AI Studio key (`GEMINI_API_KEY`), unlike the reply model below -- not
migrated to Vertex AI, flagged as an open item in the 2026-10-28 `SESSION_LOG.md` entry.

## LLM reply-model provider

**Context:** The sales agent's reply model (`api/app/llm.py`) needs an LLM provider. Brief §0
specified free tier only, citing data-privacy concerns (free tiers may train on prompts),
reasonable for a synthetic-data demo.

**Decision (S1-S6):** Free tier only -- Gemini (AI Studio) as primary, Groq as fallback, via
LiteLLM, with retry-then-switch-provider on failure.

**Consequences (as it stood through S6):** Zero cost, matched the brief's original intent.
Untested at any real load.

**Update (S7, 2026-10-28, supersedes this decision -- Naf's call):** Running the S7 eval
suite at realistic volume (~30-40 calls) exposed the real cost of "free tier only": Gemini AI
Studio's free tier caps at **20 requests/day** (confirmed from the literal 429 error text),
far too low for any real use beyond a handful of manual tests, so in practice every call was
already falling through to Groq alone and hitting *its* per-minute cap under load. Naf's own
framing -- "this needs to actually hold up if 50-100 real people try it, not just survive a
demo" -- made free-tier-only no longer viable. Migrated the reply model to **Vertex AI**
(`vertex_ai/gemini-3.5-flash`, GCP project `flash-spark-443119-s6`, paid tier, service-account
auth, `global` region), with Groq's free tier kept as the fallback. Cost for demo-scale
traffic is small but real -- a genuine change from the original all-free setup, not a free
substitution. Getting this working required a full chain of GCP-side fixes (Vertex AI API not
enabled -> billing not linked -> the IAM role renamed to "Agent Platform User" -> the model
itself renamed/retired in favor of `gemini-3.5-flash` -> the endpoint needing `global`, not a
specific region) -- see `SESSION_LOG.md`'s 2026-10-28 entry for the full trail, and
`DECISION-8dc2c78d` in `.genesis/project.json`. The embedding model above was *not* migrated
and still runs on the original free-tier AI Studio key.
