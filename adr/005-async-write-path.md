# ADR-005: Async write path via FastAPI BackgroundTasks

**Status:** Accepted (S3)

**Context:** The write path (PII filter -> extractor LLM call -> evaluator -> embedding call
-> dedupe/conflict -> store + audit) involves two network round trips to an LLM provider. If
it ran inline inside the `/chat` request, the customer would wait on memory bookkeeping before
seeing their reply -- directly against I3 ("memory-layer failure/latency never blocks a chat
reply").

**Decision:** `/chat` persists the user's message, generates the reply, and returns it to the
customer first. Only then does it hand `write_path.process_message` to FastAPI's
`BackgroundTasks`, which runs it after the HTTP response is already sent, in the same process.
No external queue (Redis/SQS/etc.), no separate worker process.

**Consequences:** Reply latency never includes extraction latency, and there's one process to
run/deploy, not two. Tradeoffs: a background task only runs if the request reaches that point
without raising first (S7 found and fixed a real gap here -- see the 2026-10-28
`SESSION_LOG.md` entry, where an unguarded LLM-call exception in the reply path was skipping
this step entirely for that turn); and if the API process crashes mid-task, that one
extraction is lost rather than durably queued and retried --
acceptable for this scope, a real job queue would be the fix if write-path durability ever
became a hard requirement.
