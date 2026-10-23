# Northbean Memory Sales Bot — Design Brief

Source of truth for the build. Condensed from Naf's design doc ("Northbean Memory System —
Design (Stage A)") and roadmap ("Sales Bot with Intelligent Memory — End-to-End Roadmap"),
which are built on the "Designing a ChatGPT-Style Memory System" study and the Genesis kit.

**Scope: portfolio project, not production.** Show production *thinking* (invariants, write
gate, governance, evaluation). Defer production *operations* (see section 2).

---

## 0. Locked decisions

| Decision | Choice | Consequence |
|---|---|---|
| Domain | D2C coffee brand, *Northbean Coffee* (fictional, US/EU) | Categories: taste, brew method, budget, objections, orders |
| Identity | Logged-in customers only (simple login / user switcher) | Every memory keyed to `customer_id`; no anonymous merge |
| LLM | Free tier: Gemini / Groq via **LiteLLM** | Async writes, retries with backoff, fallback provider; synthetic data only |
| Region | US + EU, **GDPR-first** | Consent, access, export, correct, delete, retention built in |
| Test data | 4 personas, 20 golden cases | Files in `data/` and `evals/` |

## 1. Mission and the decision memory improves

- **Mission:** returning shoppers never repeat themselves, and recommendations improve because
  the assistant remembers what matters.
- **Decision improved:** which coffee to recommend, at what price, with what message. A memory
  that cannot change one of these three is not stored.
- **Success:** golden-set precision ≥ 90%, zero cross-customer leakage, zero invented products,
  fewer repeated facts with memory ON vs OFF.

## 2. Scope

**In scope (v1):** chat with catalog tools, write path (PII → extractor → evaluator → dedupe/
conflict → store), read path (always-loaded + hybrid search + scoring + composer), memory panel
(see/correct/forget, sources, scores), consent + export + forget-everything, fallbacks, discount
cap, simple decay job (manual/cron trigger), golden-set eval runner + memory ON/OFF comparison,
small ops dashboard (counts + metrics from DB), Docker Compose, README, demo video.

**Deferred (README "next steps"):** nightly reflection/merging, EU-region hosting, Langfuse/
Prometheus/Grafana, load testing, microservices, Temporal/Celery, multi-channel, anonymous users.

## 3. User experience

Three screens (Next.js):
1. **Shop chat** — storefront page + chat; user switcher (Maya, Leo, Ana, Sam); "New chat" button.
2. **Memory panel** (drawer) — "What I remember about you": each memory with type, category,
   importance, confidence, source ("from your message on Oct 21: '…'"); buttons *That's wrong*,
   *Forget this*, *Forget everything*, *Download my data*; plus "Memories used for this answer"
   with scores (from `retrieval_log`).
3. **Ops dashboard** — counts and metrics only, no customer memory content: writes, drops (by
   reason), blocks (by PII type), retrieval rate, correction rate, p95 retrieval latency, fallback
   rate, last eval results.

**Demo story (the video):** Maya visit 1 states French press, hates sour, under $20, says "too
expensive" → panel shows 3 semantic + 1 objection memory, small talk not stored → new chat
"anything new?" → personalised low-acid French-press pick under $20 + first-order offer → Maya
clicks "forget my budget" → gone everywhere → dashboard shows the numbers.

## 4. Requirements

| ID | Requirement |
|---|---|
| FR1 | Extract candidate memories from each customer message |
| FR2 | Keep only memories passing the write gate; block PII |
| FR3 | Store type, category, importance, confidence, source |
| FR4 | Retrieve relevant memories before every reply |
| FR5 | Recommend only catalog products at catalog prices (via tools) |
| FR6 | Show what is remembered and why |
| FR7 | Correct or delete any memory, or all |
| FR8 | Resolve conflicts when a new fact contradicts an old one |
| FR9 | Decay unused memories (job) |
| FR10 | Log every write, read, update, delete, block |

| ID | Non-functional | Target |
|---|---|---|
| NFR1 | Retrieval latency (DB part) | p95 < 100 ms |
| NFR2 | Golden-set precision | ≥ 90% |
| NFR3 | Chat survives memory/extractor failure | fallback tests pass |
| NFR4 | LLM cost | $0 (free tier) |
| NFR5 | Memory context budget | ≤ 400 tokens |

Constraints: free-tier rate limits (reply call has priority; extraction async with backoff);
free tiers may train on prompts → synthetic data only; solo builder → one backend service.

## 5. Memory taxonomy

**Types**

| Type | Behaviour | Update | Half-life |
|---|---|---|---|
| semantic | stable facts | overwrite, keep history | 180 days |
| procedural | how they like to be served | overwrite, always loaded | none |
| episodic | dated events | append-only | 30 days |
| working | current chat | not stored | — |

**Categories (closed list)**

| Category | Type | Example | Default importance |
|---|---|---|---|
| brew_method | semantic | uses a French press | 8 |
| taste | semantic | likes chocolatey, low-acid coffee | 9 |
| budget | semantic | under $20 a bag | 8 |
| dietary | semantic, C2 | decaf only | 7 |
| buying_context | semantic | buys for an office of 10 | 7 |
| preference | procedural | wants short answers | 9 |
| objection | episodic | said too expensive on <date> | 6 |
| purchase_intent | episodic | left a cart with Ethiopia Guji | 6 |
| issue | episodic | complained about late delivery | 7 |

**Sensitivity:** C1 normal (stored with consent) · C2 sensitive (health/family hints: store only
the usable fact, e.g. "decaf only", never the reason; flagged; excluded from merging) · C3 never
store (cards, passwords, addresses, phones, emails, IDs: blocked before any LLM; audit logs the
entity type only).

**Keep / drop examples:** "I brew with an AeroPress" → keep · "too pricey for me" → keep, objection
· "it's raining lol" → drop · card number → block · "maybe I'll try espresso someday" → keep,
confidence 0.4 (hedge).

## 6. Data model (PostgreSQL + pgvector)

```sql
customers      (id uuid pk, email, display_name, region text check (region in ('EU','US')), created_at)
consents       (customer_id fk, purpose text, granted bool, granted_at, withdrawn_at)  -- purpose 'personalisation'
conversations  (id uuid pk, customer_id fk, started_at, ended_at)
messages       (id uuid pk, conversation_id fk, customer_id fk, role text, content text,
                extraction_status text default 'pending', created_at)
memories (
  id uuid pk, customer_id uuid not null,
  type text check (type in ('semantic','procedural','episodic')),
  category text not null, sensitivity text check (sensitivity in ('C1','C2')),
  content text not null, embedding vector(<dim>), content_tsv tsvector,
  importance smallint check (importance between 1 and 10),
  confidence real check (confidence between 0 and 1),
  weight real default 1.0, reinforcement int default 0,
  status text check (status in ('active','archived','deleted')) default 'active',
  source jsonb not null,            -- {conversation_id, message_id, ts} or {merged_from:[...]}
  last_used_at timestamptz, created_at, updated_at)
memory_history (memory_id fk, old_content, new_content, reason, changed_by, changed_at)
audit_log      (id, customer_id, memory_id, action, actor, detail jsonb, created_at)  -- append-only, no PII values
retrieval_log  (id, message_id, customer_id, memory_ids uuid[], scores jsonb, latency_ms, used_fallback bool, created_at)
feedback       (id, memory_id, customer_id, kind, created_at)   -- wrong | forget | useful
products       (id, name, origin, roast, taste_notes text[], acidity, brew_methods text[],
                price_usd numeric, in_stock bool, decaf bool)
```

- **Row-level security** on memories, messages, audit_log, feedback, retrieval_log: each request
  sets `app.customer_id`; policies compare to it.
- **Forget this:** status='deleted', content and embedding nulled immediately. **Forget
  everything:** hard delete of the customer's memories, history, messages, retrieval logs.
- **Indexes (question 7):** HNSW on `embedding` (vector search); GIN on `content_tsv` (keyword
  search for exact names like "Guji"); B-tree on `(customer_id, status, category)` so every
  query filters to one customer's active memories *before* ranking. `<dim>` = embedding model's
  dimension, pinned in ADR-003.
- All memory access goes through one `MemoryRepository` interface (exit hatch).

## 7. Write path (async, after the reply)

1. **Consent check** — no personalisation consent → stop, log "skipped: no consent".
2. **PII filter** (Presidio + regex) on the raw message → mask C3 entities; log `block` with type only.
3. **Extractor** (cheap model, JSON mode) on masked message + previous assistant turn:
   ```json
   {"candidates": [{"content": "prefers chocolatey, low-acid coffee", "type": "semantic",
     "category": "taste", "evidence": "I hate sour coffee", "is_hedged": false}]}
   ```
   One fact per candidate, closed categories, third-person sentence, `[]` if nothing. Invalid JSON →
   retry once → skip.
4. **Evaluator (rules first):** invalid category → drop · importance = category default ·
   confidence 0.8 (0.4 if hedged; +0.1 if repeated in chat) · sensitive keywords → C2, keep usable
   fact only · drop if importance × confidence < 3 · every drop logged with reason. LLM judge only
   when rules are unsure (optional in v1).
5. **Dedupe / conflict** (same customer + same category + cosine > 0.85): same fact → reinforce
   (+1, confidence +0.1, cap 0.95) · semantic contradiction with confidence ≥ old → update +
   `memory_history` · new is hedged and lower confidence → keep old, add new separately ·
   episodic → always append.
6. **Write** with source + audit row.

Rate limits: in-process queue, exponential backoff on 429; failures leave
`extraction_status='pending'` for a retry job. Chat is never blocked.

## 8. Read path (before every reply, 200 ms timeout → fallback without memory)

1. **Always-loaded:** active procedural + semantic in budget, brew_method, taste, dietary.
2. **Hybrid search:** embed message once; vector top 15 + keyword top 15, filtered by customer and
   status='active'; merge with reciprocal rank fusion.
3. **Score:** `score = 0.40·S + 0.20·R + 0.15·F + 0.15·I + 0.10·C`
   (S fused relevance, R = exp(−days since last use / half-life), F = min(reinforcement/5, 1),
   I = importance/10, C = confidence). Weights in config. Drop < 0.35.
4. **Select:** always-loaded + top 5, cut to 400 tokens (procedural first). Log to `retrieval_log`.
5. **Compose:**
   ```text
   What you know about this customer (use it, do not recite it):
   - Brews with a French press.
   - Prefers chocolatey, low-acid coffee.
   - Budget: under $20 a bag.
   - Prefers short answers.
   - On <date> said a bag was too expensive.
   Rules: recommend only via search_products. Low-confidence items: ask, don't assert.
   ```
6. **Reinforce** used memories (+1, last_used_at = now).

Confidence < 0.6 → phrase as a question ("Last time you mentioned espresso — still interested?").

**Sales agent tools:** `search_products(filters)`, `check_stock(product_id)`,
`apply_discount(customer_id)` (fixed 10% first-order code, max once per customer, enforced in
code), `handoff_to_human(summary)`. A reply checker verifies every product name and price in the
reply exists in `products`.

## 9. Lifecycle and decay

States: candidate → dropped/blocked | active ⇄ updated/merged · active → archived (weight < 0.2)
→ deleted after 12 months · archived → active (mentioned again) · active → deleted (forget).

```
weight = (importance/10) × confidence × 0.5^(days_since_last_use / half_life) × (1 + 0.1 × reinforcement)
```
Example: objection, importance 6, confidence 0.8, unused 60 days, episodic → 0.6×0.8×0.25 = 0.12 → archived.
v1: decay runs via an admin endpoint / scheduled job. Reflection (merging) is deferred.

## 10. Invariants (lock in DONE.html) and their tests

| # | Invariant | Test |
|---|---|---|
| I1 | One customer's memory never returned for another | Seed Maya + Leo; queries as Leo → zero Maya ids in retrieval_log; direct DB query as Leo → 0 rows |
| I2 | Deleted memories never retrieved | Forget one; run golden queries; id never appears; content/embedding null |
| I3 | Memory failure never blocks a reply | Stop DB / force timeout; reply still returned |
| I4 | Every memory carries provenance | No active memory with null source (DB constraint + test) |
| I5 | No invented products, prices or discounts | 20+ sales queries; every product/price exists; discount ≤ cap |
| I6 | No consent, no memory | consent=false customer chats → 0 memory rows |
| I7 | No C3 data stored | Card/email/phone messages → absent from memories and audit_log |

## 11. Governance (GDPR-first, demo-level — not legal advice)

Consent prompt on first login (No = chat works, nothing stored) · withdraw toggle · access via
memory panel with sources · rectification via "That's wrong" (+ history) · erasure via "Forget
this" / "Forget everything" · portability via "Download my data" (JSON) · minimisation via write
gate and C2/C3 rules · retention: messages 90 days, archived memories 12 months · append-only
audit log without PII values · no admin view of memory content.

## 12. Failure modes

| Failure | Fallback |
|---|---|
| 429 on reply model | retry once, switch provider via LiteLLM |
| 429 on extractor | queue + backoff; pending retry |
| DB down | circuit breaker; reply without memory/tools ("can't check stock right now") |
| Retrieval > 200 ms | reply without memory; log fallback |
| Invalid extractor JSON | reject, retry once, skip |
| Hedge stored as fact | confidence < 0.6 asked as a question; "That's wrong" |
| Retrieval miss on exact names | keyword search alongside vector |
| LLM invents product/discount | products only via tools; reply checker; discount cap in code |
| Embedding model change | model pinned; re-embed script |

## 13. Build plan (PLAN.md) — target 3–5 days

| Sprint | Build | Demo command / proof |
|---|---|---|
| S1 Foundation | Docker Compose (Postgres+pgvector, api, web), schema, RLS, seed products + personas | `docker compose up`; products count = 18; cross-customer query returns 0 rows |
| S2 Chat + tools | FastAPI `/chat`, LiteLLM client with fallback, sales agent with tools, reply checker | "something for French press under $20" → only real in-stock catalog items |
| S3 Write path | PII → extractor → evaluator → dedupe/conflict → store + audit; async queue | Maya's setup messages → expected memories; small talk dropped; card number blocked |
| S4 Read path | always-loaded + hybrid search + scoring + composer + reinforce + retrieval_log | golden retrieval cases pass; precision printed |
| S5 Frontend | Next.js chat, user switcher, consent prompt, memory panel (sources, scores), ops dashboard | full demo story works in the browser |
| S6 Governance + decay | That's wrong / Forget / Forget everything / Download data / consent withdraw; decay job endpoint | I2, I6 pass; archived after simulated 60 days |
| S7 Reliability + eval | fallbacks, discount cap, eval runner over `evals/golden.jsonl`, memory ON vs OFF comparison | all invariant tests green; eval table printed |
| S8 Ship | README (problem, GIF, architecture, results table, ADRs, next steps), optional deploy, video script | repo ready to share |

Suggested days: D1 S1–S2 · D2 S3–S4 · D3 S5 · D4 S6–S7 · D5 S8. After each sprint: a plain-language
dry run for Naf.

## 14. Metrics and evaluation (question 10)

Metrics: precision, recall, write-gate accuracy, retrieval rate, correction rate, p95 retrieval
latency, reply latency, tokens per reply, fallback rate.

**Memory ON vs OFF:** run all retrieval cases twice. Report repeat rate (facts the user would have
to restate), recommendation fit (LLM-as-judge vs `expected_products_rule`), tokens, latency. This
table is the README's headline result.

## 15. Open decisions (defaults apply unless Naf changes them)

- Discount after a price objection: **10% first-order code, once per customer.**
- Retention: **messages 90 days, archived memories 12 months.**
- Human handoff: **mock support inbox page showing the summary.**
- Brand name: **Northbean Coffee.**

## 16. ADRs (write to `adr/` and `.genesis/decisions/`)

001 Postgres + pgvector (one DB, RLS, hybrid in SQL) · 002 FastAPI + Next.js, one backend
service · 003 free-tier Gemini/Groq via LiteLLM; embedding model pinned at S1 · 004 rules-first
evaluator · 005 async write path · 006 logged-in customers only · 007 simple job runner instead of
Celery/Temporal.

## 17. Stack

Next.js · FastAPI · PostgreSQL + pgvector · LiteLLM (Gemini/Groq) · provider embeddings (pinned)
· Microsoft Presidio · pytest + eval script · Docker Compose · optional deploy (Render/Railway +
Vercel).

## 18. Ten-question map (memory study L10)

1 decision → §1 · 2 remember → §5 · 3 forget → §5, §9, §11 · 4 extract → §7 · 5 validate → §7, §8
· 6 store → §6 · 7 index → §6 · 8 retrieve → §8 · 9 decay → §9 · 10 outcomes → §10, §14
