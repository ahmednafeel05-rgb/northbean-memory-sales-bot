"""Embedding model pinned at S1 (ADR-003), 768 dims to match memories.embedding's column type.

text-embedding-004 (the model ADR-003 originally named) has been retired by Google; probed
live and confirmed at S3 that gemini-embedding-001 is the current replacement. It defaults to
3072 dims but supports truncating the output via `dimensions=`, so the column width in
db/schema.sql doesn't need to change. Changing providers later still needs a migration +
re-embed script over existing rows -- not solved here."""
import litellm

EMBED_MODEL = "gemini/gemini-embedding-001"
EMBED_DIMENSIONS = 768


def embed(text: str) -> list[float]:
    response = litellm.embedding(model=EMBED_MODEL, input=[text], dimensions=EMBED_DIMENSIONS)
    return response.data[0]["embedding"]


def to_pgvector(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"
