"""Golden-set eval runner (design brief §14, NFR-2, AC-8): loads evals/golden.jsonl's
"retrieval" cases, runs each memory ON (real setup -> real memory -> query) vs OFF (the query
alone, no memory ever existed), and reports precision + repeat rate. This table -- "fewer
repeated facts with memory ON vs OFF" -- is the README's headline result.

Run directly for the full report: `python evals/run_eval.py`
"""
import json
import os
import re
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
PRODUCTS = {p["id"]: p for p in json.loads((ROOT / "data" / "products.json").read_text())}
_NB_ID = re.compile(r"\bnb-\d{3}\b")


def _customer_id(persona_id):
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"northbean:{persona_id}")


def _post_chat(customer_id, message, retries=4):
    """Free-tier LLM rate limits turn into a transient 500 under load; retry with backoff
    rather than treat it as an eval failure (same pattern as the other test suites)."""
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


def _wait_for_processed(customer_id, content, timeout=25):
    with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
        deadline = time.time() + timeout
        while time.time() < deadline:
            row = conn.execute(
                "SELECT extraction_status FROM messages WHERE customer_id = %s AND role = 'user' "
                "AND content = %s ORDER BY created_at DESC LIMIT 1",
                (customer_id, content),
            ).fetchone()
            if row and row["extraction_status"] != "pending":
                return
            time.sleep(0.5)


def _mentions_product(reply, product_id):
    name = PRODUCTS[product_id]["name"].lower()
    return name in reply.lower() or name.split()[0] in reply.lower()


def evaluate_retrieval_case(case):
    """Runs one "retrieval" golden case memory ON and OFF (design brief §14). Returns a dict
    scoring both: pass/fail (precision) and each condition's repeat rate."""
    customer_id = _customer_id(case["customer"])
    expected_categories = {m.split(":")[0] for m in case.get("expected_memories", [])}

    # --- memory ON: real setup -> real memory -> the query ---
    _reset_customer(customer_id)
    for msg in case.get("setup", []):
        _post_chat(customer_id, msg)
    for msg in case.get("setup", []):
        _wait_for_processed(customer_id, msg)
    on_result = _post_chat(customer_id, case["query"])
    on_reply = on_result["reply"]

    found_categories = set()
    if on_result.get("message_id"):
        with psycopg.connect(ADMIN_URL, row_factory=dict_row) as conn:
            log = conn.execute(
                "SELECT memory_ids FROM retrieval_log WHERE message_id = %s", (on_result["message_id"],)
            ).fetchone()
            if log and log["memory_ids"]:
                rows = conn.execute(
                    "SELECT category FROM memories WHERE id = ANY(%s)", (log["memory_ids"],)
                ).fetchall()
                found_categories = {r["category"] for r in rows}
    on_repeat_rate = len(expected_categories - found_categories)

    # --- memory OFF: the query alone -- no customer identity, so nothing was ever remembered
    # and nothing could have been restated to avoid repeating it ---
    off_result = _post_chat(None, case["query"])
    off_repeat_rate = len(expected_categories)

    forbidden_products = case.get("must_not_recommend", [])
    forbidden_text = case.get("must_not_include_text", [])
    violations = [pid for pid in forbidden_products if _mentions_product(on_reply, pid)]
    violations += [t for t in forbidden_text if t.lower() in on_reply.lower()]

    return {
        "id": case["id"],
        "customer": case["customer"],
        "passed": not violations and on_repeat_rate == 0,
        "on_repeat_rate": on_repeat_rate,
        "off_repeat_rate": off_repeat_rate,
        "violations": violations,
        "on_reply": on_reply,
        "off_reply": off_result["reply"],
    }


def load_retrieval_cases(ids=None):
    lines = (ROOT / "evals" / "golden.jsonl").read_text().splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    cases = [c for c in cases if c["kind"] == "retrieval"]
    if ids is not None:
        cases = [c for c in cases if c["id"] in ids]
    return cases


def run(ids=None):
    results = [evaluate_retrieval_case(c) for c in load_retrieval_cases(ids)]
    passed = sum(r["passed"] for r in results)
    return {
        "results": results,
        "precision": passed / len(results) if results else 0.0,
        "total_on_repeat": sum(r["on_repeat_rate"] for r in results),
        "total_off_repeat": sum(r["off_repeat_rate"] for r in results),
    }


def print_report(summary):
    print(f"\n{'ID':5}{'customer':10}{'pass':6}{'on-repeat':11}{'off-repeat':11}")
    for r in summary["results"]:
        mark = "yes" if r["passed"] else "NO"
        print(f"{r['id']:5}{r['customer']:10}{mark:6}{r['on_repeat_rate']:<11}{r['off_repeat_rate']:<11}")
    n = len(summary["results"])
    passed = round(summary["precision"] * n)
    print(f"\nPrecision: {summary['precision'] * 100:.1f}% ({passed}/{n})")
    print(f"Repeated facts -- memory ON: {summary['total_on_repeat']}, memory OFF: {summary['total_off_repeat']}")


if __name__ == "__main__":
    print_report(run())
