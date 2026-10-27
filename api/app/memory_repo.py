"""Single interface for all memory DB access (design brief §6: the "exit hatch"). FR-3, FR-8,
FR-10; I4/I6/I7 are enforced by going through here rather than ad hoc writes elsewhere."""
import json

from .embeddings import to_pgvector

DEDUPE_COSINE_THRESHOLD = 0.85
MAX_REINFORCED_CONFIDENCE = 0.95
# procedural is always loaded regardless of category (design brief SS5 taxonomy); these semantic
# categories are always loaded too (design brief SS8 step 1)
ALWAYS_LOADED_SEMANTIC_CATEGORIES = ("brew_method", "taste", "budget", "dietary")
MEMORY_COLUMNS = (
    "id, type, category, content, importance, confidence, reinforcement, last_used_at, created_at"
)


class MemoryRepository:
    def __init__(self, conn):
        self._conn = conn

    def has_consent(self, customer_id) -> bool:
        row = self._conn.execute(
            "SELECT granted FROM consents WHERE customer_id = %s AND purpose = 'personalisation'",
            (customer_id,),
        ).fetchone()
        return bool(row and row["granted"])

    def write(self, customer_id, memory: dict, embedding: list[float], source: dict) -> str:
        """Insert/reinforce/update per the dedupe-conflict rules (design brief §7.5)."""
        if memory["type"] != "episodic":
            match = self._find_match(customer_id, memory["category"], embedding)
            if match is not None:
                if match["content"] == memory["content"]:
                    self._reinforce(match["id"], match["confidence"])
                    self._audit(customer_id, match["id"], "write", {"action": "reinforce", "category": memory["category"]})
                    return "reinforced"
                if memory["confidence"] >= match["confidence"]:
                    self._update(match["id"], memory, embedding, source)
                    self._audit(customer_id, match["id"], "write", {"action": "update", "category": memory["category"]})
                    return "updated"
                # hedged/lower-confidence new fact: keep old, store the new one separately below

        memory_id = self._insert(customer_id, memory, embedding, source)
        self._audit(customer_id, memory_id, "write", {"action": "insert", "category": memory["category"]})
        return "inserted"

    def get_always_loaded(self, customer_id):
        """Design brief SS8 step 1: active procedural (any category) + active semantic in the
        budget/brew_method/taste/dietary categories."""
        return self._conn.execute(
            f"SELECT {MEMORY_COLUMNS} FROM memories WHERE customer_id = %s AND status = 'active' "
            "AND (type = 'procedural' OR category = ANY(%s))",
            (customer_id, list(ALWAYS_LOADED_SEMANTIC_CATEGORIES)),
        ).fetchall()

    def hybrid_search(self, customer_id, embedding, query_text, limit=15):
        """Design brief SS8 step 2: vector top N + keyword top N, filtered to this customer's
        active memories. Caller fuses the two lists (reciprocal rank fusion)."""
        vec = to_pgvector(embedding)
        vector_rows = self._conn.execute(
            f"SELECT {MEMORY_COLUMNS} FROM memories WHERE customer_id = %s AND status = 'active' "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (customer_id, vec, limit),
        ).fetchall()
        keyword_rows = self._conn.execute(
            f"SELECT {MEMORY_COLUMNS} FROM memories WHERE customer_id = %s AND status = 'active' "
            "AND content_tsv @@ plainto_tsquery('english', %s) "
            "ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %s)) DESC LIMIT %s",
            (customer_id, query_text, query_text, limit),
        ).fetchall()
        return vector_rows, keyword_rows

    def reinforce_used(self, memory_ids):
        """Design brief SS8 step 6: reinforce memories actually used in the composed context."""
        if not memory_ids:
            return
        self._conn.execute(
            "UPDATE memories SET reinforcement = reinforcement + 1, last_used_at = now() WHERE id = ANY(%s)",
            (list(memory_ids),),
        )

    def log_retrieval(self, message_id, customer_id, memory_ids, scores, latency_ms, used_fallback):
        self._conn.execute(
            "INSERT INTO retrieval_log (message_id, customer_id, memory_ids, scores, latency_ms, used_fallback) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (message_id, customer_id, list(memory_ids), json.dumps(scores), latency_ms, used_fallback),
        )

    def log_block(self, customer_id, entity_types):
        self._audit(customer_id, None, "block", {"entity_types": entity_types})

    def log_drop(self, customer_id, reason, category=None):
        self._audit(customer_id, None, "drop", {"reason": reason, "category": category})

    def log_skip(self, customer_id, reason):
        self._audit(customer_id, None, "skip", {"reason": reason})

    def soft_delete(self, customer_id, memory_id, reason) -> bool:
        """"That's wrong" / "Forget this" (FR-7, design brief §11): content/embedding nulled
        immediately per I2, with the old content kept in `memory_history` for the record. RLS
        means this only ever matches a row that belongs to `customer_id` (I1) -- returns False
        if the id doesn't exist or isn't theirs, so the caller can answer 404."""
        old = self._conn.execute("SELECT content FROM memories WHERE id = %s", (memory_id,)).fetchone()
        if old is None:
            return False
        self._conn.execute(
            "INSERT INTO memory_history (memory_id, old_content, new_content, reason, changed_by) "
            "VALUES (%s,%s,NULL,%s,%s)",
            (memory_id, old["content"], reason, "customer"),
        )
        updated = self._conn.execute(
            "UPDATE memories SET status = 'deleted', content = NULL, embedding = NULL, "
            "content_tsv = NULL, updated_at = now() WHERE id = %s AND customer_id = %s RETURNING id",
            (memory_id, customer_id),
        ).fetchone()
        if updated is None:
            return False
        self._audit(customer_id, memory_id, "delete", {"reason": reason})
        return True

    def log_feedback(self, customer_id, memory_id, kind):
        self._conn.execute(
            "INSERT INTO feedback (memory_id, customer_id, kind) VALUES (%s,%s,%s)",
            (memory_id, customer_id, kind),
        )

    def forget_everything(self, customer_id):
        """"Forget everything" (design brief §6, §11): hard delete of this customer's memories,
        history, messages, and retrieval logs -- `memory_history`/`feedback` cascade from
        `memories`, and `retrieval_log` cascades from `messages` (db/schema.sql FKs)."""
        self._audit(customer_id, None, "forget_everything", {})
        self._conn.execute("DELETE FROM memories WHERE customer_id = %s", (customer_id,))
        self._conn.execute("DELETE FROM messages WHERE customer_id = %s", (customer_id,))

    def withdraw_consent(self, customer_id):
        """Governance §11 "withdraw toggle": from this point on, write_path.has_consent() (I6)
        makes every future message a no-op -- existing memories are untouched (that's what
        "Forget everything" is for)."""
        self._conn.execute(
            "UPDATE consents SET granted = false, withdrawn_at = now() "
            "WHERE customer_id = %s AND purpose = 'personalisation'",
            (customer_id,),
        )
        self._audit(customer_id, None, "consent_withdrawn", {})

    def _find_match(self, customer_id, category, embedding):
        vec = to_pgvector(embedding)
        return self._conn.execute(
            "SELECT id, content, confidence FROM memories "
            "WHERE customer_id = %s AND category = %s AND status = 'active' "
            "AND 1 - (embedding <=> %s::vector) > %s "
            "ORDER BY embedding <=> %s::vector LIMIT 1",
            (customer_id, category, vec, DEDUPE_COSINE_THRESHOLD, vec),
        ).fetchone()

    def _insert(self, customer_id, memory, embedding, source):
        row = self._conn.execute(
            "INSERT INTO memories (customer_id, type, category, sensitivity, content, embedding, "
            "content_tsv, importance, confidence, source) "
            "VALUES (%s,%s,%s,%s,%s,%s::vector,to_tsvector('english',%s),%s,%s,%s) RETURNING id",
            (
                customer_id,
                memory["type"],
                memory["category"],
                memory["sensitivity"],
                memory["content"],
                to_pgvector(embedding),
                memory["content"],
                memory["importance"],
                memory["confidence"],
                json.dumps(source),
            ),
        ).fetchone()
        return row["id"]

    def _reinforce(self, memory_id, confidence):
        new_confidence = min(confidence + 0.1, MAX_REINFORCED_CONFIDENCE)
        self._conn.execute(
            "UPDATE memories SET reinforcement = reinforcement + 1, confidence = %s, "
            "last_used_at = now(), updated_at = now() WHERE id = %s",
            (new_confidence, memory_id),
        )

    def _update(self, memory_id, memory, embedding, source):
        old = self._conn.execute("SELECT content FROM memories WHERE id = %s", (memory_id,)).fetchone()
        self._conn.execute(
            "INSERT INTO memory_history (memory_id, old_content, new_content, reason, changed_by) "
            "VALUES (%s,%s,%s,%s,%s)",
            (memory_id, old["content"], memory["content"], "contradiction", "write_path"),
        )
        self._conn.execute(
            "UPDATE memories SET content = %s, embedding = %s::vector, content_tsv = to_tsvector('english', %s), "
            "confidence = %s, importance = %s, source = %s, updated_at = now() WHERE id = %s",
            (memory["content"], to_pgvector(embedding), memory["content"], memory["confidence"], memory["importance"], json.dumps(source), memory_id),
        )

    def _audit(self, customer_id, memory_id, action, detail):
        self._conn.execute(
            "INSERT INTO audit_log (customer_id, memory_id, action, actor, detail) VALUES (%s,%s,%s,%s,%s)",
            (customer_id, memory_id, action, "write_path", json.dumps(detail)),
        )
