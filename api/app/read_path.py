"""Read path: always-loaded + hybrid search + scoring + composer + reinforce + retrieval_log
(design brief SS8). Runs before every reply so the sales agent can personalise it (FR-4).

Two separate timeouts (DECISION-57fcb69e, Naf's call): the embedding call is a live network
round trip to Gemini (measured 700-800ms) and gets its own generous budget; the DB portion
(queries + in-process scoring/compose) gets the brief's tight ~200ms budget (matches NFR-1's
"DB portion p95 < 100ms" framing). Either budget blowing, or any other failure, falls back to
no memory context rather than ever blocking the reply (I3, NFR-3).
"""
import concurrent.futures
import os
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from . import embeddings
from .memory_repo import MemoryRepository

DATABASE_URL = os.environ["DATABASE_URL"]

HALF_LIFE_DAYS = {"semantic": 180, "episodic": 30}  # procedural: no decay, always loaded anyway
SCORE_WEIGHTS = {"S": 0.40, "R": 0.20, "F": 0.15, "I": 0.15, "C": 0.10}
SCORE_DROP_THRESHOLD = 0.35
RRF_K = 60
SELECT_TOP_N = 5
TOKEN_BUDGET = 400  # NFR-5; approximated as whitespace-split word count
LOW_CONFIDENCE_THRESHOLD = 0.6

EMBED_TIMEOUT_S = 3.0
DB_TIMEOUT_S = 0.2

HEADER = "What you know about this customer (use it, do not recite it):"
FOOTER = "Rules: recommend only via search_products. Low-confidence items: ask, don't assert."

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def get_context(customer_id, message_id, query_text) -> str:
    start = time.monotonic()
    embedding = _embed_with_timeout(query_text)
    if embedding is None:
        _log_fallback(customer_id, message_id, (time.monotonic() - start) * 1000)
        return ""

    try:
        future = _executor.submit(_build_context, customer_id, message_id, query_text, embedding)
        return future.result(timeout=DB_TIMEOUT_S)
    except Exception:
        _log_fallback(customer_id, message_id, (time.monotonic() - start) * 1000)
        return ""


def _embed_with_timeout(query_text):
    try:
        future = _executor.submit(embeddings.embed, query_text)
        return future.result(timeout=EMBED_TIMEOUT_S)
    except Exception:
        return None


def _build_context(customer_id, message_id, query_text, embedding):
    db_start = time.monotonic()  # NFR-1: DB portion only, excludes the embedding network call
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        repo = MemoryRepository(conn)

        always_loaded = repo.get_always_loaded(customer_id)
        vector_rows, keyword_rows = repo.hybrid_search(customer_id, embedding, query_text)
        scored = _score_candidates(vector_rows, keyword_rows)

        always_ids = {row["id"] for row in always_loaded}
        score_by_id = {row["id"]: s for row, s in scored}
        top = [row for row, s in scored if row["id"] not in always_ids and s >= SCORE_DROP_THRESHOLD][:SELECT_TOP_N]

        selected = _fit_to_budget(always_loaded, top)
        context_text, used_ids = _compose(selected)

        latency_ms = (time.monotonic() - db_start) * 1000
        if latency_ms > DB_TIMEOUT_S * 1000:
            # The caller already gave up (future.result() timed out) and logged its own
            # fallback row for this message. A ThreadPoolExecutor can't kill this thread, so
            # it ran to completion anyway -- but committing these writes now would reinforce
            # memories never actually shown to the customer and leave two contradictory
            # retrieval_log rows for one message_id. Finish quietly instead.
            return context_text

        scores = {str(row["id"]): round(score_by_id.get(row["id"], 1.0), 4) for row in selected}
        repo.reinforce_used(used_ids)
        repo.log_retrieval(message_id, customer_id, used_ids, scores, latency_ms, used_fallback=False)
    return context_text


def _score_candidates(vector_rows, keyword_rows):
    """Reciprocal rank fusion of the two search lists, normalised to S in [0, 1], then the
    full weighted score (design brief SS8 step 3)."""
    rows_by_id, rrf = {}, {}
    for rank, row in enumerate(vector_rows, start=1):
        rows_by_id[row["id"]] = row
        rrf[row["id"]] = rrf.get(row["id"], 0.0) + 1.0 / (RRF_K + rank)
    for rank, row in enumerate(keyword_rows, start=1):
        rows_by_id[row["id"]] = row
        rrf[row["id"]] = rrf.get(row["id"], 0.0) + 1.0 / (RRF_K + rank)
    if not rrf:
        return []

    max_rrf = max(rrf.values())
    scored = [(rows_by_id[mid], _score(rows_by_id[mid], fused / max_rrf)) for mid, fused in rrf.items()]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def _score(row, s_norm):
    half_life = HALF_LIFE_DAYS.get(row["type"])
    if half_life is None:
        recency = 1.0
    else:
        anchor = row["last_used_at"] or row["created_at"]
        days = (datetime.now(timezone.utc) - anchor).total_seconds() / 86400
        recency = 0.5 ** (days / half_life)
    reinforce_factor = min(row["reinforcement"] / 5, 1.0)
    importance_factor = row["importance"] / 10
    w = SCORE_WEIGHTS
    return (
        w["S"] * s_norm
        + w["R"] * recency
        + w["F"] * reinforce_factor
        + w["I"] * importance_factor
        + w["C"] * row["confidence"]
    )


def _fit_to_budget(always_loaded, top):
    """Design brief SS8 step 4: always-loaded + top 5, cut to the token budget, procedural
    first so it survives the cut before scored episodic/semantic extras do."""
    procedural = [r for r in always_loaded if r["type"] == "procedural"]
    rest_always_loaded = [r for r in always_loaded if r["type"] != "procedural"]
    ordered = procedural + rest_always_loaded + top

    selected, token_total = [], 0
    for row in ordered:
        tokens = len(_format_line(row).split())
        if selected and token_total + tokens > TOKEN_BUDGET:
            break
        selected.append(row)
        token_total += tokens
    return selected


def _format_line(row):
    content = row["content"].strip().rstrip(".")
    if row["type"] == "episodic":
        when = row["created_at"]
        date_str = when.date().isoformat() if when else "a previous visit"
        text = f"On {date_str} said {content}."
    else:
        text = content[0].upper() + content[1:] + "."
    prefix = "- (low-confidence) " if row["confidence"] < LOW_CONFIDENCE_THRESHOLD else "- "
    return prefix + text


def _compose(selected):
    lines = [HEADER] + [_format_line(row) for row in selected] + [FOOTER]
    return "\n".join(lines), [row["id"] for row in selected]


def _log_fallback(customer_id, message_id, latency_ms):
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
            conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
            MemoryRepository(conn).log_retrieval(message_id, customer_id, [], {}, latency_ms, used_fallback=True)
    except Exception:
        pass
