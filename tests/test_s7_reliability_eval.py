"""S7 gate: discount cap (I5/AC-5), reply survives a full DB outage (I3/AC-3/NFR-3), and the
golden-set eval (NFR-2/AC-8: >=90% precision, strictly fewer repeated facts memory ON vs OFF)."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `from evals.run_eval import ...` resolves regardless of cwd

from evals.run_eval import run as run_eval  # noqa: E402

LEO_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:leo")


def _post_chat(customer_id, message, retries=4):
    data = json.dumps({"message": message, "customer_id": str(customer_id) if customer_id else None}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{API_URL}/chat", data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code != 500 or attempt == retries - 1:
                raise
            time.sleep(10)


def _reset_customer(customer_id):
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM discounts WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM retrieval_log WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM audit_log WHERE customer_id = %s", (customer_id,))
        conn.execute(
            "DELETE FROM memory_history WHERE memory_id IN (SELECT id FROM memories WHERE customer_id = %s)",
            (customer_id,),
        )
        conn.execute("DELETE FROM memories WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM messages WHERE customer_id = %s", (customer_id,))
        conn.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))


def test_discount_offered_once_and_never_exceeds_the_cap():
    _reset_customer(LEO_ID)

    _post_chat(LEO_ID, "That's way too expensive for me -- is there any discount for a first-time customer?")
    _post_chat(LEO_ID, "Still feels too pricey, any other discount available?")

    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT percent_off FROM discounts WHERE customer_id = %s", (LEO_ID,)).fetchall()
    assert len(rows) <= 1, "a customer must never be granted more than one discount (I5)"
    for row in rows:
        assert row["percent_off"] <= 10, "discount must never exceed the 10% cap (I5)"


def test_discount_primary_key_makes_a_second_grant_structurally_impossible():
    _reset_customer(LEO_ID)
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO discounts (customer_id, code, percent_off) VALUES (%s, 'WELCOME10-TEST', 10)",
            (LEO_ID,),
        )
        try:
            conn.execute(
                "INSERT INTO discounts (customer_id, code, percent_off) VALUES (%s, 'WELCOME10-AGAIN', 10)",
                (LEO_ID,),
            )
            raised = False
        except psycopg.errors.UniqueViolation:
            raised = True
    assert raised, "a second discount row for the same customer must be rejected at the schema level"


def test_reply_survives_a_full_database_outage():
    """I3/AC-3/NFR-3, the brief's own invariant test (§10): "Stop DB / force timeout; reply
    still returned." Exercises both guards added this sprint -- main.py's chat() no longer lets
    a bookkeeping failure crash the request, and agent.py's tool runner degrades a failed
    product lookup instead of raising."""
    subprocess.run(["docker", "compose", "stop", "db"], cwd=ROOT, check=True, timeout=30)
    try:
        result = _post_chat(None, "something for French press under $20")
        assert result and result.get("reply"), "a reply must still come back with the DB fully down"
    finally:
        subprocess.run(["docker", "compose", "start", "db"], cwd=ROOT, check=True, timeout=30)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with psycopg.connect(ADMIN_URL, connect_timeout=2) as conn:
                    conn.execute("SELECT 1")
                break
            except Exception:
                time.sleep(1)


def test_golden_set_eval_precision_and_repeat_rate():
    """NFR-2/AC-8: >=90% precision on the golden retrieval cases, and strictly fewer repeated
    facts with memory ON than memory OFF."""
    summary = run_eval()
    for r in summary["results"]:
        print(f"{r['id']} ({r['customer']}): pass={r['passed']} on_repeat={r['on_repeat_rate']} "
              f"off_repeat={r['off_repeat_rate']} violations={r['violations']}")
    print(f"precision={summary['precision']:.2f} total_on_repeat={summary['total_on_repeat']} "
          f"total_off_repeat={summary['total_off_repeat']}")

    assert summary["total_on_repeat"] < summary["total_off_repeat"], (
        "memory ON must produce strictly fewer repeated facts than memory OFF (AC-8)"
    )
    assert summary["precision"] >= 0.9, f"golden-set precision {summary['precision']:.2f} below the 90% target (NFR-2)"
