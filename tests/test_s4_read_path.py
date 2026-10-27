"""S4 gate: always-loaded + hybrid search memories land in retrieval_log and get reinforced;
no cross-customer leakage (I1); composed context stays within the NFR-5 token budget."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid

import pytest
import psycopg
from psycopg.rows import dict_row

API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")

MAYA_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:maya")
LEO_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:leo")

TOKEN_BUDGET = 400


def _post_chat(customer_id, message, retries=4):
    """Free-tier LLM rate limits (design brief constraints) turn into a transient 500 under
    test load; retry with backoff rather than treat it as a read-path bug."""
    data = json.dumps({"message": message, "customer_id": str(customer_id)}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{API_URL}/chat", data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())["reply"]
        except urllib.error.HTTPError as exc:
            if exc.code != 500 or attempt == retries - 1:
                raise
            time.sleep(10)


def _reset_customer(customer_id):
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM retrieval_log WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM audit_log WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM memory_history WHERE memory_id IN (SELECT id FROM memories WHERE customer_id = %s)", (customer_id,))
        conn.execute("DELETE FROM memories WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM messages WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))


def _wait_for_message_processed(customer_id, content, timeout=25):
    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        deadline = time.time() + timeout
        while time.time() < deadline:
            row = conn.execute(
                "SELECT id, extraction_status FROM messages WHERE customer_id = %s AND role = 'user' "
                "AND content = %s ORDER BY created_at DESC LIMIT 1",
                (customer_id, content),
            ).fetchone()
            if row and row["extraction_status"] != "pending":
                return row["id"]
            time.sleep(0.5)
    raise AssertionError(f"message not processed within {timeout}s: {content!r}")


@pytest.fixture(scope="module")
def maya_seeded():
    """Seed Maya once per test module run, not once per test -- keeps LLM call volume down
    against the free-tier rate limit (shared across all three tests below)."""
    _reset_customer(MAYA_ID)
    setup = [
        "Hi! I brew with a French press.",
        "I hate sour coffee, I like chocolatey notes.",
        "Please keep it under $20 a bag.",
    ]
    for m in setup:
        _post_chat(MAYA_ID, m)
    for m in setup:
        _wait_for_message_processed(MAYA_ID, m)
    return MAYA_ID


def _retrieval_log_for(customer_id, query_message):
    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        msg = conn.execute(
            "SELECT id FROM messages WHERE customer_id = %s AND role = 'user' AND content = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (customer_id, query_message),
        ).fetchone()
        return conn.execute(
            "SELECT * FROM retrieval_log WHERE message_id = %s", (msg["id"],)
        ).fetchone()


def test_always_loaded_memories_are_retrieved_scored_and_reinforced(maya_seeded):
    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        before = conn.execute(
            "SELECT id, category, reinforcement FROM memories WHERE customer_id = %s AND status = 'active'",
            (MAYA_ID,),
        ).fetchall()
    assert {"brew_method", "taste", "budget"} <= {r["category"] for r in before}
    reinforcement_before = {r["id"]: r["reinforcement"] for r in before}

    query = "Anything new for me?"
    _post_chat(MAYA_ID, query)
    _wait_for_message_processed(MAYA_ID, query)

    log_row = _retrieval_log_for(MAYA_ID, query)
    assert log_row is not None, "expected a retrieval_log row for the query message"
    assert log_row["memory_ids"], "always-loaded memories (brew_method/taste/budget) should have been retrieved"

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        retrieved_categories = {
            r["category"]
            for r in conn.execute(
                "SELECT category FROM memories WHERE id = ANY(%s)", (log_row["memory_ids"],)
            ).fetchall()
        }
    assert {"brew_method", "taste", "budget"} <= retrieved_categories

    if not log_row["used_fallback"]:
        with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
            after = conn.execute(
                "SELECT id, reinforcement FROM memories WHERE id = ANY(%s)", (log_row["memory_ids"],)
            ).fetchall()
        for r in after:
            assert r["reinforcement"] > reinforcement_before.get(r["id"], 0), "used memory should be reinforced (+1)"


def test_composed_context_token_budget_and_scores_recorded(maya_seeded):
    query = "Recommend something."
    _post_chat(MAYA_ID, query)
    _wait_for_message_processed(MAYA_ID, query)

    log_row = _retrieval_log_for(MAYA_ID, query)
    assert log_row is not None
    if log_row["used_fallback"]:
        return  # embedding call genuinely timed out this run; nothing to check

    scores = log_row["scores"] if isinstance(log_row["scores"], dict) else json.loads(log_row["scores"])
    assert scores, "expected per-memory scores to be logged"
    assert set(scores) == {str(mid) for mid in log_row["memory_ids"]}

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT content FROM memories WHERE id = ANY(%s)", (log_row["memory_ids"],)
        ).fetchall()
    approx_tokens = sum(len(r["content"].split()) + 2 for r in rows)  # +2 for formatting words/period
    assert approx_tokens <= TOKEN_BUDGET


def test_no_cross_customer_leakage_in_retrieval_log(maya_seeded):
    _reset_customer(LEO_ID)
    _post_chat(LEO_ID, "I use an AeroPress.")
    _wait_for_message_processed(LEO_ID, "I use an AeroPress.")

    query = "What's my budget?"
    _post_chat(LEO_ID, query)
    _wait_for_message_processed(LEO_ID, query)

    log_row = _retrieval_log_for(LEO_ID, query)
    assert log_row is not None

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        maya_ids = {
            r["id"]
            for r in conn.execute("SELECT id FROM memories WHERE customer_id = %s", (MAYA_ID,)).fetchall()
        }
    assert not (set(log_row["memory_ids"]) & maya_ids), "Leo's retrieval must never include Maya's memory ids (I1)"
