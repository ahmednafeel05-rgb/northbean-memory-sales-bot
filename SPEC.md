# Product specification — Northbean Memory Sales Bot

> Status: draft. A coding agent must not implement product code until this specification is approved through Genesis.

## Problem

Returning shoppers at Northbean Coffee (a fictional D2C coffee brand) have to repeat their
taste, brew method, budget, and past objections every time they chat with the sales assistant.
This portfolio project (by Naf) builds an AI sales assistant with an intelligent, GDPR-first
memory system that remembers each logged-in shopper across visits, lets them see/correct/delete
what is remembered, and proves the memory actually improves recommendations with an evaluation.
The memory layer is the real product under test; the sales chat is the stage it performs on.
This is a demonstration of production *thinking* (invariants, write gate, governance,
evaluation), not a production deployment.

## Users

- **Logged-in shoppers** (4 synthetic personas: Maya, Leo, Ana, Sam) who chat with the Northbean
  sales assistant. Identity is required — no anonymous users, no cross-customer memory merge.
- **Naf (builder/reviewer)** who checks the ops dashboard (aggregate counts/metrics only, no
  memory content) and the golden-set evaluation results as proof of quality.

## Functional requirements

- FR-1: Extract candidate memories from each customer message (PII-masked, via a cheap LLM in JSON mode).
- FR-2: Keep only memories that pass the write gate (importance × confidence threshold, valid category); block all C3 PII before it reaches any LLM.
- FR-3: Store every memory with type (semantic/procedural/episodic), category, importance, confidence, and source.
- FR-4: Retrieve relevant memories (always-loaded + hybrid vector/keyword search, scored and ranked) before every reply.
- FR-5: Recommend only catalog products at catalog prices, via tools (`search_products`, `check_stock`), never invented.
- FR-6: Show the shopper what is remembered and why (memory panel: type, category, importance, confidence, source quote).
- FR-7: Let the shopper correct ("That's wrong") or delete any single memory, or forget everything.
- FR-8: Resolve conflicts when a new fact contradicts an old one (reinforce / update with history / keep both, per the dedupe rules).
- FR-9: Decay unused memories over time via a job (manual/cron-triggered in v1), archiving low-weight memories.
- FR-10: Log every memory write, read, update, delete, and block to an append-only audit log (no PII values).

## Non-functional requirements

- NFR-1: Retrieval latency (DB portion of the read path) — p95 < 100 ms.
- NFR-2: Golden-set recommendation precision — ≥ 90% against `evals/golden.jsonl`.
- NFR-3: Chat must survive memory/extractor failure — reply is still returned when DB/timeout/extractor fails (fallback tests pass).
- NFR-4: LLM cost — $0, using free-tier Gemini/Groq via LiteLLM with synthetic data only (free tiers may train on prompts).
- NFR-5: Memory context budget injected into the reply prompt — ≤ 400 tokens.

## Constraints

- Free-tier LLM rate limits: the reply call has priority; extraction is async with exponential backoff and retry.
- Free-tier providers may train on submitted prompts → synthetic/fake data only, never real PII.
- Solo builder, portfolio timeline (target 3–5 days) → one backend service, no microservices/Temporal/Celery.
- Region: US + EU, GDPR-first by design (consent, access, export, correct, delete, retention), demo-level — not legal advice.
- Identity: logged-in customers only; every memory keyed to `customer_id`; no anonymous merge.
- Stack is fixed: Next.js frontend, **FastAPI** backend, PostgreSQL + pgvector, LiteLLM (Gemini/Groq), Presidio for PII, Docker Compose.
- Ready-made inputs (`data/products.json`, `data/personas.json`, `evals/golden.jsonl`) are given and must not be regenerated.

## Non-goals

- Nightly reflection/merging of memories (deferred).
- Real EU-region hosting/data residency (deferred — demo-level governance only).
- Observability stack: Langfuse/Prometheus/Grafana (deferred).
- Load testing, microservices, Temporal/Celery orchestration (deferred).
- Multi-channel support (deferred — chat only).
- Anonymous/non-logged-in users (out of scope by design).
- Production security hardening, legal compliance sign-off, or real customer data (this is a portfolio project).

## Acceptance criteria

- AC-1: One customer's memory is never returned for another customer (I1) — cross-customer retrieval and direct DB query both return 0 rows.
- AC-2: A deleted ("forgotten") memory is never retrieved again, and its content/embedding are nulled (I2).
- AC-3: A memory-layer failure (DB down, timeout) never blocks a chat reply (I3).
- AC-4: Every active memory carries non-null provenance/source (I4), enforced by DB constraint and test.
- AC-5: No invented products, prices, or discounts ever appear in a reply; discounts never exceed the cap (I5), verified over 20+ sales queries.
- AC-6: A customer with no personalisation consent generates zero memory rows (I6).
- AC-7: No C3 PII (cards, passwords, addresses, phones, emails, IDs) is ever stored in memories or audit log (I7).
- AC-8: The golden-set evaluation shows ≥ 90% precision and strictly fewer repeated facts with memory ON vs memory OFF.

## Risks

- Free LLM tiers rate-limit or go down → mitigated by LiteLLM fallback provider + retry/backoff; reply path never blocked (NFR-3, I3).
- Extractor returns invalid/hallucinated JSON → reject, retry once, skip (never stored unvalidated).
- PII filter misses an entity type → mitigated by regex + Presidio layering before any LLM call; audit logs entity type only, never the value.
- LLM invents a product/price/discount in a reply → mitigated by reply checker (every product/price validated against `products` table) and a code-enforced discount cap.
- Scope creep beyond portfolio timeline → mitigated by the sprint plan (brief §13) and explicit deferred list above.

## Open questions

None. Brief §15 ("Open decisions") already fixes defaults for every outstanding choice (discount
policy, retention windows, human handoff UX, brand name); proceed with those defaults unless Naf
changes them.
