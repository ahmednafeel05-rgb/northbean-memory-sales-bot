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
