# ADR-003: Embedding model pinned at S1

**Status:** Accepted (S1)

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
itself still stands; only the model name changed. See `api/app/embeddings.py`.
