"""S3 gate: Maya's setup messages -> expected memories; small talk dropped; card number blocked."""
import json
import os
import time
import urllib.request
import uuid

import psycopg
from psycopg.rows import dict_row

API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")

MAYA_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:maya")
SAM_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:sam")


def _post_chat(customer_id, message):
    data = json.dumps({"message": message, "customer_id": str(customer_id)}).encode()
    req = urllib.request.Request(
        f"{API_URL}/chat", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["reply"]


def _reset_customer(customer_id):
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
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


def test_maya_setup_messages_produce_expected_memories():
    _reset_customer(MAYA_ID)
    messages = [
        "Hi! I brew with a French press.",
        "I hate sour coffee, I like chocolatey notes.",
        "Please keep it under $20 a bag.",
        "Hmm, that's too expensive for me right now, maybe later.",
    ]
    for m in messages:
        _post_chat(MAYA_ID, m)
    for m in messages:
        _wait_for_message_processed(MAYA_ID, m)

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT category FROM memories WHERE customer_id = %s AND status = 'active'", (MAYA_ID,)
        ).fetchall()
    categories = {r["category"] for r in rows}
    assert {"brew_method", "taste", "budget"} <= categories


def test_small_talk_dropped_and_card_number_blocked():
    _reset_customer(SAM_ID)
    small_talk = "It's raining here lol."
    card_message = "My card is 4111 1111 1111 1111, can you save it?"

    _post_chat(SAM_ID, small_talk)
    small_talk_msg_id = _wait_for_message_processed(SAM_ID, small_talk)

    _post_chat(SAM_ID, card_message)
    _wait_for_message_processed(SAM_ID, card_message)

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        memories = conn.execute("SELECT content, source FROM memories WHERE customer_id = %s", (SAM_ID,)).fetchall()
        audit_rows = conn.execute("SELECT action, detail FROM audit_log WHERE customer_id = %s", (SAM_ID,)).fetchall()

    small_talk_memories = [m for m in memories if m["source"].get("message_id") == str(small_talk_msg_id)]
    assert small_talk_memories == [], "small talk with no shoppable fact should not become a memory"

    assert all("4111" not in m["content"] for m in memories), "card number leaked into a memory"
    assert all("4111" not in json.dumps(a["detail"]) for a in audit_rows), "card number leaked into the audit log"

    block_rows = [a for a in audit_rows if a["action"] == "block"]
    assert block_rows, "expected a 'block' audit row for the card number"
    assert any("CREDIT_CARD" in json.dumps(r["detail"]) for r in block_rows)
