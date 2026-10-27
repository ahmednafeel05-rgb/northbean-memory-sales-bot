"""Write path: consent -> PII filter -> extractor -> evaluator -> dedupe/conflict -> store +
audit (design brief §7). Runs as a FastAPI background task after the reply is already sent,
so a failure here never blocks a chat reply (I3, NFR-3)."""
import os

import psycopg
from psycopg.rows import dict_row

from . import embeddings, evaluator, extractor, pii_filter
from .memory_repo import MemoryRepository

DATABASE_URL = os.environ["DATABASE_URL"]


def process_message(customer_id, message_id, conversation_id, user_message, prev_assistant_reply):
    try:
        _run(customer_id, message_id, conversation_id, user_message, prev_assistant_reply)
        status = "done"
    except Exception:
        status = "failed"
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        conn.execute("UPDATE messages SET extraction_status = %s WHERE id = %s", (status, message_id))


def _run(customer_id, message_id, conversation_id, user_message, prev_assistant_reply):
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        repo = MemoryRepository(conn)

        if not repo.has_consent(customer_id):
            repo.log_skip(customer_id, "no consent")
            return

        masked, blocked_entities = pii_filter.mask(user_message)
        if blocked_entities:
            repo.log_block(customer_id, blocked_entities)

        candidates = extractor.extract(masked, prev_assistant_reply)
        if not candidates:
            return

        accepted, dropped = evaluator.evaluate(candidates)
        for d in dropped:
            repo.log_drop(customer_id, d["reason"], d["candidate"].get("category"))

        source = {"conversation_id": str(conversation_id), "message_id": str(message_id)}
        for memory in accepted:
            embedding = embeddings.embed(memory["content"])
            repo.write(customer_id, memory, embedding, source)
