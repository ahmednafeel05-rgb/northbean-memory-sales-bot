# ADR-001: PostgreSQL + pgvector, one database

**Status:** Accepted (S1)

**Context:** Need relational storage for customers/products plus vector similarity search
for memory retrieval, within a solo-builder portfolio timeline.

**Decision:** One PostgreSQL database (pgvector/pgvector:pg16 image) holds both relational
tables and the `memories.embedding vector(768)` column. Hybrid retrieval runs in SQL
(HNSW vector index + GIN tsvector index), no separate vector database.

**Consequences:** Simpler ops (one service, one backup target), row-level security can
scope both relational and vector queries to a customer in the same policy. Tradeoff:
vector search is only as scalable as this one Postgres instance — acceptable for a
portfolio project's data volumes.
