import os
import uuid

import json
from datetime import datetime, timezone

import psycopg
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel

from . import agent, read_path, write_path
from .memory_repo import MemoryRepository

app = FastAPI(title="Northbean Sales Bot API")

# The S5 frontend (web/, port 3000) is a different origin than this API (port 8000); without
# this the browser silently blocks every fetch() from it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ["DATABASE_URL"]
# Ops dashboard (S5) aggregates counts across all customers for the "small ops dashboard"
# requirement (design brief §3.3) -- RLS is per-customer by design (I1), so this one
# read-only, no-memory-content reporting path uses the admin role to see every row.
ADMIN_DATABASE_URL = os.environ["ADMIN_DATABASE_URL"]


@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


class ChatRequest(BaseModel):
    message: str
    customer_id: uuid.UUID | None = None  # omit for anonymous/no-memory chat (S2 behaviour)


class ChatResponse(BaseModel):
    reply: str
    message_id: uuid.UUID | None = None  # lets the frontend fetch /retrieval/{message_id} (FR-6)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    """I3/NFR-3: a memory-layer failure (DB down, timeout) must never block the reply itself --
    bookkeeping (saving the message, building memory context) is best-effort; if it raises for
    any reason, the customer still gets a reply, just without personalisation this turn."""
    memory_context = ""
    message_id = conversation_id = prev_assistant_reply = None
    if req.customer_id:
        try:
            message_id, conversation_id, prev_assistant_reply = _start_turn(req.customer_id, req.message)
            memory_context = read_path.get_context(req.customer_id, message_id, req.message)
        except Exception:
            message_id = conversation_id = prev_assistant_reply = None
            memory_context = ""

    reply = agent.run_turn(req.message, memory_context=memory_context, customer_id=req.customer_id)

    if req.customer_id and message_id is not None:
        try:
            _finish_turn(background_tasks, req.customer_id, message_id, conversation_id, prev_assistant_reply, req.message, reply)
        except Exception:
            pass
    return ChatResponse(reply=reply, message_id=message_id)


@app.get("/customers")
def customers():
    """Lists the seeded personas for the frontend's user switcher (design brief §3.1). No RLS
    on `customers` -- display_name/email here are synthetic demo data, not real PII."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT id, display_name, region FROM customers ORDER BY display_name").fetchall()
    return {"customers": rows}


def _start_turn(customer_id, user_message):
    """Persist the user's message before the reply is generated, so the read path (FR-4) has a
    message_id to log retrieval against (design brief §8)."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        conversation_id = _get_or_create_conversation(conn, customer_id)

        prev = conn.execute(
            "SELECT content FROM messages WHERE conversation_id = %s AND role = 'assistant' "
            "ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        prev_assistant_reply = prev["content"] if prev else ""

        user_msg = conn.execute(
            "INSERT INTO messages (conversation_id, customer_id, role, content) "
            "VALUES (%s, %s, 'user', %s) RETURNING id",
            (conversation_id, customer_id, user_message),
        ).fetchone()
    return user_msg["id"], conversation_id, prev_assistant_reply


def _finish_turn(background_tasks, customer_id, message_id, conversation_id, prev_assistant_reply, user_message, assistant_reply):
    """Persist the reply, then hand extraction to the in-process async queue (design brief §7).
    The reply is already computed and returned to the caller; this only adds bookkeeping."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        conn.execute(
            "INSERT INTO messages (conversation_id, customer_id, role, content, extraction_status) "
            "VALUES (%s, %s, 'assistant', %s, 'done')",
            (conversation_id, customer_id, assistant_reply),
        )

    background_tasks.add_task(
        write_path.process_message,
        customer_id=customer_id,
        message_id=message_id,
        conversation_id=conversation_id,
        user_message=user_message,
        prev_assistant_reply=prev_assistant_reply,
    )


@app.get("/memories")
def memories(customer_id: uuid.UUID, target_customer_id: uuid.UUID | None = None):
    """The FR-6 "memory panel" feed: type, category, importance, confidence, and a source quote
    (the customer message the memory came from). `customer_id` is who's logged in (sets the RLS
    session); `target_customer_id` -- defaults to yourself -- is whose memories to fetch. Logged
    in as one customer but passing another's id here is exactly the cross-customer-leak scenario
    I1 guards against: the database enforces it regardless of what this endpoint asks for."""
    target_customer_id = target_customer_id or customer_id
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        rows = conn.execute(
            "SELECT m.id, m.type, m.category, m.content, m.importance, m.confidence, "
            "msg.content AS source_quote, msg.created_at AS source_date "
            "FROM memories m LEFT JOIN messages msg ON msg.id = (m.source->>'message_id')::uuid "
            "WHERE m.customer_id = %s AND m.status = 'active' ORDER BY m.created_at",
            (target_customer_id,),
        ).fetchall()
    return {"memories": rows}


@app.get("/retrieval/{message_id}")
def retrieval(message_id: uuid.UUID, customer_id: uuid.UUID):
    """"Memories used for this answer" (design brief §3.2, §8 step 4): the scored memories the
    read path actually selected for one chat turn, from `retrieval_log`."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        log = conn.execute(
            "SELECT memory_ids, scores, used_fallback FROM retrieval_log "
            "WHERE message_id = %s AND customer_id = %s ORDER BY created_at DESC LIMIT 1",
            (message_id, customer_id),
        ).fetchone()
        if not log or not log["memory_ids"]:
            return {"used_fallback": bool(log and log["used_fallback"]), "memories": []}
        rows = conn.execute(
            "SELECT id, category, content FROM memories WHERE id = ANY(%s)",
            (log["memory_ids"],),
        ).fetchall()
    for row in rows:
        row["score"] = log["scores"].get(str(row["id"]))
    return {"used_fallback": log["used_fallback"], "memories": rows}


class CorrectMemoryRequest(BaseModel):
    action: str = "correct"


@app.patch("/memories/{memory_id}")
def correct_memory(memory_id: uuid.UUID, customer_id: uuid.UUID, req: CorrectMemoryRequest):
    """"That's wrong" (FR-7, design brief §11 rectification): same mechanics as "Forget this"
    (I2 -- content/embedding nulled immediately, old content kept in `memory_history`), logged
    as customer-flagged feedback so the ops dashboard's correction rate reflects it."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        repo = MemoryRepository(conn)
        repo.log_feedback(customer_id, memory_id, "wrong")
        if not repo.soft_delete(customer_id, memory_id, "customer_flagged_wrong"):
            raise HTTPException(status_code=404, detail="memory not found")
    return {"status": "ok"}


@app.delete("/memories/{memory_id}")
def forget_memory(memory_id: uuid.UUID, customer_id: uuid.UUID):
    """"Forget this" (FR-7, I2): content/embedding nulled immediately, never retrieved again."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        repo = MemoryRepository(conn)
        repo.log_feedback(customer_id, memory_id, "forget")
        if not repo.soft_delete(customer_id, memory_id, "customer_forget"):
            raise HTTPException(status_code=404, detail="memory not found")
    return {"status": "ok"}


@app.delete("/memories")
def forget_everything(customer_id: uuid.UUID):
    """"Forget everything" (FR-7, design brief §6/§11): hard delete, not a soft one -- the
    customer wants no trace, not an audit-only erasure."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        MemoryRepository(conn).forget_everything(customer_id)
    return {"status": "ok"}


@app.get("/memories/export")
def export_data(customer_id: uuid.UUID):
    """"Download my data" (FR-7, design brief §11 portability): the customer's profile,
    consent record, and active memories as a JSON file."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(customer_id),))
        customer = conn.execute(
            "SELECT id, email, display_name, region FROM customers WHERE id = %s", (customer_id,)
        ).fetchone()
        consents = conn.execute(
            "SELECT purpose, granted, granted_at, withdrawn_at FROM consents WHERE customer_id = %s",
            (customer_id,),
        ).fetchall()
        memories_rows = conn.execute(
            "SELECT id, type, category, content, importance, confidence, created_at FROM memories "
            "WHERE customer_id = %s AND status = 'active' ORDER BY created_at",
            (customer_id,),
        ).fetchall()
    payload = {"customer": customer, "consents": consents, "memories": memories_rows}
    body = json.loads(json.dumps(payload, default=str))
    return JSONResponse(
        content=body,
        headers={"Content-Disposition": f'attachment; filename="northbean-data-{customer_id}.json"'},
    )


class WithdrawConsentRequest(BaseModel):
    customer_id: uuid.UUID


@app.post("/consents/withdraw")
def withdraw_consent(req: WithdrawConsentRequest):
    """Consent withdraw toggle (design brief §11). Existing memories are untouched -- from this
    point on write_path.has_consent() (I6) makes every future message a no-op."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(req.customer_id),))
        MemoryRepository(conn).withdraw_consent(req.customer_id)
    return {"status": "ok"}


DECAY_HALF_LIFE_DAYS = {"semantic": 180, "episodic": 30}  # procedural never decays (design brief §5)
ARCHIVE_WEIGHT_THRESHOLD = 0.2
DELETE_AFTER_ARCHIVED_DAYS = 365


@app.post("/admin/decay")
def run_decay():
    """Decay job (FR-9, design brief §9): active -> archived (weight < 0.2) -> deleted after 12
    months archived. v1 is an admin-triggered endpoint, not a scheduler (brief's own call).
    Runs with the admin role: it sweeps every customer's memories, which per-customer RLS (I1)
    would otherwise block."""
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        candidates = conn.execute(
            "SELECT id, customer_id, type, importance, confidence, reinforcement, "
            "COALESCE(last_used_at, created_at) AS anchor FROM memories "
            "WHERE status = 'active' AND type != 'procedural'"
        ).fetchall()
        archived = 0
        for row in candidates:
            half_life = DECAY_HALF_LIFE_DAYS[row["type"]]
            days = (datetime.now(timezone.utc) - row["anchor"]).total_seconds() / 86400
            weight = (
                (row["importance"] / 10)
                * row["confidence"]
                * (0.5 ** (days / half_life))
                * (1 + 0.1 * row["reinforcement"])
            )
            if weight < ARCHIVE_WEIGHT_THRESHOLD:
                conn.execute(
                    "UPDATE memories SET status = 'archived', weight = %s, updated_at = now() WHERE id = %s",
                    (weight, row["id"]),
                )
                conn.execute(
                    "INSERT INTO audit_log (customer_id, memory_id, action, actor, detail) "
                    "VALUES (%s,%s,'archive','decay_job',%s)",
                    (row["customer_id"], row["id"], json.dumps({"weight": round(weight, 4)})),
                )
                archived += 1
            else:
                conn.execute("UPDATE memories SET weight = %s WHERE id = %s", (weight, row["id"]))

        expired = conn.execute(
            "SELECT id, customer_id FROM memories WHERE status = 'archived' "
            "AND updated_at < now() - (%s || ' days')::interval",
            (DELETE_AFTER_ARCHIVED_DAYS,),
        ).fetchall()
        for row in expired:
            conn.execute(
                "UPDATE memories SET status = 'deleted', content = NULL, embedding = NULL, "
                "content_tsv = NULL, updated_at = now() WHERE id = %s",
                (row["id"],),
            )
            conn.execute(
                "INSERT INTO audit_log (customer_id, memory_id, action, actor, detail) "
                "VALUES (%s,%s,'delete','decay_job','{}')",
                (row["customer_id"], row["id"]),
            )
    return {"archived": archived, "deleted": len(expired)}


@app.get("/ops/metrics")
def ops_metrics():
    """Ops dashboard (design brief §3.3): counts and metrics only, no customer memory content.
    Reads with the admin role because these aggregates intentionally span every customer, which
    per-customer RLS (I1) would otherwise block."""
    with psycopg.connect(ADMIN_DATABASE_URL, row_factory=dict_row) as conn:
        writes = conn.execute("SELECT count(*) AS n FROM audit_log WHERE action = 'write'").fetchone()["n"]
        drops = conn.execute(
            "SELECT detail->>'reason' AS reason, count(*) AS n FROM audit_log "
            "WHERE action = 'drop' GROUP BY 1 ORDER BY 1"
        ).fetchall()
        blocks = conn.execute(
            "SELECT entity_type, count(*) AS n FROM audit_log, "
            "jsonb_array_elements_text(detail->'entity_types') AS entity_type "
            "WHERE action = 'block' GROUP BY 1 ORDER BY 1"
        ).fetchall()
        retrieval = conn.execute(
            "SELECT count(*) AS n, avg(used_fallback::int) AS fallback_rate, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms "
            "FROM retrieval_log"
        ).fetchone()
        corrections = conn.execute("SELECT count(*) AS n FROM feedback WHERE kind = 'wrong'").fetchone()["n"]
    return {
        "writes": writes,
        "drops_by_reason": drops,
        "blocks_by_entity_type": blocks,
        "retrievals": retrieval["n"],
        "fallback_rate": retrieval["fallback_rate"],
        "p95_retrieval_latency_ms": retrieval["p95_latency_ms"],
        "corrections": corrections,
        "last_eval": None,  # no eval runner yet (S7)
    }


class EndConversationRequest(BaseModel):
    customer_id: uuid.UUID


@app.post("/conversations/end")
def end_conversation(req: EndConversationRequest):
    """"New chat" button (design brief §3.1): ends the customer's open conversation so the next
    `/chat` call starts a fresh one instead of continuing the old thread."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(req.customer_id),))
        conn.execute(
            "UPDATE conversations SET ended_at = now() "
            "WHERE customer_id = %s AND ended_at IS NULL",
            (req.customer_id,),
        )
    return {"status": "ok"}


def _get_or_create_conversation(conn, customer_id):
    row = conn.execute(
        "SELECT id FROM conversations WHERE customer_id = %s AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "INSERT INTO conversations (customer_id) VALUES (%s) RETURNING id", (customer_id,)
    ).fetchone()
    return row["id"]
