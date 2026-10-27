"""S6 gate: governance actions (that's wrong / forget this / forget everything / consent
withdraw) and the decay job -- AC-2 (I2), AC-6 (I6), and archival after simulated time passing
(design brief §13 S6 demo proof: "I2, I6 pass; archived after simulated 60 days")."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid

import psycopg
from psycopg.rows import dict_row

API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")

MAYA_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:maya")
SAM_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:sam")


def _post_chat(customer_id, message, retries=4):
    """Free-tier LLM rate limits (design brief constraints) turn into a transient 500 under
    test load; retry with backoff rather than treat it as a bug."""
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


def _api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_URL}{path}", data=data, headers={"Content-Type": "application/json"}, method=method
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def _reset_customer(customer_id):
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM retrieval_log WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM feedback WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM audit_log WHERE customer_id = %s", (customer_id,))
        conn.execute(
            "DELETE FROM memory_history WHERE memory_id IN (SELECT id FROM memories WHERE customer_id = %s)",
            (customer_id,),
        )
        conn.execute("DELETE FROM memories WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM messages WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))
        conn.execute(
            "UPDATE consents SET granted = true, withdrawn_at = NULL "
            "WHERE customer_id = %s AND purpose = 'personalisation'",
            (customer_id,),
        )


def _insert_memory(customer_id, **overrides):
    defaults = dict(
        type="semantic", category="taste", sensitivity="C1", content="test memory",
        importance=8, confidence=0.8, reinforcement=0, status="active",
        source=json.dumps({"test": True}),
    )
    defaults.update(overrides)
    defaults["customer_id"] = customer_id
    with psycopg.connect(ADMIN_URL, row_factory=dict_row, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO memories (customer_id, type, category, sensitivity, content, importance, "
            "confidence, reinforcement, status, source) VALUES (%(customer_id)s, %(type)s, %(category)s, "
            "%(sensitivity)s, %(content)s, %(importance)s, %(confidence)s, %(reinforcement)s, "
            "%(status)s, %(source)s::jsonb) RETURNING id",
            defaults,
        ).fetchone()
    return row["id"]


def _backdate(memory_id, column, days_ago):
    assert column in ("last_used_at", "created_at", "updated_at")  # fixed set, not user input
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(
            f"UPDATE memories SET {column} = now() - (%s || ' days')::interval WHERE id = %s",
            (days_ago, memory_id),
        )


def _memory_row(memory_id):
    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        return conn.execute("SELECT * FROM memories WHERE id = %s", (memory_id,)).fetchone()


def test_forget_this_nulls_content_immediately():
    _reset_customer(MAYA_ID)
    memory_id = _insert_memory(MAYA_ID, content="brews with a Chemex")

    _api("DELETE", f"/memories/{memory_id}?customer_id={MAYA_ID}")

    row = _memory_row(memory_id)
    assert row["status"] == "deleted"
    assert row["content"] is None  # I2
    assert row["embedding"] is None  # I2

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        kinds = {r["kind"] for r in conn.execute("SELECT kind FROM feedback WHERE memory_id = %s", (memory_id,)).fetchall()}
    assert kinds == {"forget"}


def test_that_is_wrong_marks_feedback_and_removes_the_memory():
    _reset_customer(MAYA_ID)
    memory_id = _insert_memory(MAYA_ID, content="prefers dark roast")

    _api("PATCH", f"/memories/{memory_id}?customer_id={MAYA_ID}", {"action": "correct"})

    row = _memory_row(memory_id)
    assert row["status"] == "deleted"
    assert row["content"] is None

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        kinds = {r["kind"] for r in conn.execute("SELECT kind FROM feedback WHERE memory_id = %s", (memory_id,)).fetchall()}
        history = conn.execute(
            "SELECT old_content FROM memory_history WHERE memory_id = %s", (memory_id,)
        ).fetchall()
    assert kinds == {"wrong"}
    assert history and history[0]["old_content"] == "prefers dark roast"


def test_forget_everything_hard_deletes_memories_messages_and_retrieval_log():
    _reset_customer(SAM_ID)
    memory_id = _insert_memory(SAM_ID, content="uses a moka pot")
    with psycopg.connect(ADMIN_URL, autocommit=True, row_factory=dict_row) as conn:
        conv = conn.execute(
            "INSERT INTO conversations (customer_id) VALUES (%s) RETURNING id", (SAM_ID,)
        ).fetchone()
        msg = conn.execute(
            "INSERT INTO messages (conversation_id, customer_id, role, content) "
            "VALUES (%s,%s,'user','hi') RETURNING id",
            (conv["id"], SAM_ID),
        ).fetchone()
        conn.execute(
            "INSERT INTO retrieval_log (message_id, customer_id, memory_ids, scores, latency_ms, used_fallback) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (msg["id"], SAM_ID, [memory_id], json.dumps({}), 1.0, False),
        )

    _api("DELETE", f"/memories?customer_id={SAM_ID}")

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        assert conn.execute("SELECT count(*) AS n FROM memories WHERE customer_id = %s", (SAM_ID,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM messages WHERE customer_id = %s", (SAM_ID,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM retrieval_log WHERE customer_id = %s", (SAM_ID,)).fetchone()["n"] == 0


def test_consent_withdrawal_stops_future_memory_writes():
    """AC-6/I6: withdrawing consent must make the very next message produce zero new memory
    rows, exactly like a customer who never consented."""
    _reset_customer(MAYA_ID)
    _api("POST", "/consents/withdraw", {"customer_id": str(MAYA_ID)})

    _post_chat(MAYA_ID, "I brew with a Chemex and love fruity coffee.")
    time.sleep(3)  # give the (should-be-skipped) async write path a moment to prove it didn't run

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        count = conn.execute("SELECT count(*) AS n FROM memories WHERE customer_id = %s", (MAYA_ID,)).fetchone()["n"]
    assert count == 0


def test_decay_archives_a_stale_low_weight_memory_after_simulated_60_days():
    """Mirrors the design brief's own worked example (§9): episodic, importance 6, confidence
    0.8, unused 60 days -> weight 0.6*0.8*0.25 = 0.12, below the 0.2 archive threshold. A fresh
    memory and a procedural one (never decays, design brief §5) must stay active."""
    _reset_customer(MAYA_ID)
    stale_id = _insert_memory(
        MAYA_ID, type="episodic", category="objection", content="said too expensive",
        importance=6, confidence=0.8,
    )
    _backdate(stale_id, "last_used_at", 60)
    _backdate(stale_id, "created_at", 60)

    fresh_id = _insert_memory(MAYA_ID, type="semantic", category="taste", content="likes chocolatey notes")
    procedural_id = _insert_memory(
        MAYA_ID, type="procedural", category="preference", content="wants short answers",
        importance=1, confidence=0.3,
    )
    _backdate(procedural_id, "last_used_at", 9999)
    _backdate(procedural_id, "created_at", 9999)

    result = _api("POST", "/admin/decay")
    assert result["archived"] >= 1

    assert _memory_row(stale_id)["status"] == "archived"
    assert _memory_row(fresh_id)["status"] == "active"
    assert _memory_row(procedural_id)["status"] == "active"  # procedural never decays


def test_decay_deletes_a_memory_archived_more_than_12_months_ago():
    _reset_customer(MAYA_ID)
    memory_id = _insert_memory(
        MAYA_ID, type="episodic", category="objection", content="said too expensive",
        importance=6, confidence=0.8, status="archived",
    )
    _backdate(memory_id, "updated_at", 400)

    result = _api("POST", "/admin/decay")
    assert result["deleted"] >= 1

    row = _memory_row(memory_id)
    assert row["status"] == "deleted"
    assert row["content"] is None
    assert row["embedding"] is None
