# SESSION_LOG.md — Northbean Memory Sales Bot

Narrative history, maintained by whichever Claude Code session is working on this repo.
Complements `.genesis/KICKOFF.md` (structured task/gate state) with the "why" and the
debugging context Genesis doesn't record. See `CLAUDE.md` → "Session log" for the
maintenance contract. **Newest entry on top.**

---

## 2026-10-28 — S7 resumed: migrated reply model to Vertex AI (paid), found and fixed two real
reliability bugs plus an eval false-positive; gate passed at 100% precision, task complete

**State at start:** S7 paused (see entry below) on exhausted free-tier LLM quota -- Gemini's
AI Studio free tier (20 requests/day, confirmed from the actual 429 error text) and Groq's
free TPM cap were both hit the same day. Naf had chosen to wait rather than rotate keys or
run a smaller eval.

**Quota re-check, then a real finding:** Brought the stack back up and probed Gemini directly
-- it answered a plain completion fine, but a `tools=`-bearing call (the actual chat/agent
path) still silently fell through to Groq and then hit Groq's TPM limit under the eval's call
volume, reproducing the original failure. Re-ran the previously-blocked golden-set eval
anyway to see the real signal: precision came back at **50%** (4/8 cases), not a clean pass --
this was no longer "wait for quota," it was a real bug surfacing under load.

**Bug 1 (real, not quota -- I3/AC-3/NFR-3 gap):** `main.py`'s `/chat` handler called
`agent.run_turn()` with no exception handling. `agent.py` already had a prepared fallback
reply string (`"Sorry, I'm having trouble right now..."`) sitting unused in `run_turn`, but
the actual `llm.complete()` call inside the tool-calling loop wasn't wrapped in try/except, so
when both LLM providers failed the `RuntimeError` propagated straight past that fallback, out
through `main.py`, and 500'd the whole turn -- directly contradicting SPEC.md:77 ("reply path
never blocked"). Worse: because the exception fired before `_finish_turn` ever ran, the
background `write_path.process_message` task never got scheduled, so that turn's facts were
silently lost from memory entirely -- explaining why G04/G06 showed *zero* categories
retrieved (matching memory OFF exactly). Fixed by wrapping the `llm.complete()` call in
`agent.py`'s loop in try/except and breaking to the existing fallback reply on failure; now
extraction is scheduled regardless of whether the reply itself succeeded. Also added logging
to `llm.py`'s `complete()` (previously silently swallowed every attempt's exception until all
three failed) -- this is what masked Gemini's failures with zero visible errors all last
session.
**Bug 2 (real, prompt-logic gap):** G07 ("Is the Guji back in stock?" after a memory saying
the customer liked "Ethiopia Guji") still named the forbidden trap product nb-005 ("Ethiopia
Guji Natural Reserve"). Root cause: the S5-era disambiguation instruction ("if search returns
more than one match, list them and ask which one") unconditionally overrode memory context,
so even with the right memory retrieved the agent still searched broadly and listed both
nb-004/nb-005 trap products. Added an explicit carve-out in `agent.py`'s `SYSTEM_PROMPT`: when
memory or the current message already names one match exactly, use that one and don't mention
the other similarly-named variant.
**Bug 3 (eval's own false positive, not an app bug):** after fixing 1 and 2, G07 was *still*
failing -- but the actual reply text only ever said "the Ethiopia Guji is back in stock,"
never mentioning nb-005 at all. `evals/run_eval.py`'s `_mentions_product` matched on full
product name *or* just the first word as an abbreviation fallback; since nb-004 and nb-005
share their first two words ("Ethiopia Guji"), any correct, legitimate mention of nb-004 was
structurally guaranteed to false-positive against nb-005's forbidden-product check -- "Ethiopia"
is the *only* first word shared by two products anywhere in the 18-item catalog (checked
directly). Fixed by only applying the first-word fallback when that word isn't ambiguous
across the catalog.

**Vertex AI migration (Naf's call, driven by "will this scale past a free-tier demo to
50-100 real users"):** free tiers alone (Gemini AI Studio 20/day, Groq's TPM cap) won't hold
up under any real deployment. Naf created a GCP project (`flash-spark-443119-s6`), attached a
debit card for the (refundable) free-trial prepayment, and generated a service-account key
(`northbean-sales-coffee-bot@flash-spark-443119-s6.iam.gserviceaccount.com`). Wired it in:
`api/requirements.txt` now installs `litellm[google]` (pulls in `google-cloud-aiplatform` and
friends -- confirmed via a direct probe that litellm's vertex path needs it, not just
`google-auth`); `docker-compose.yml` bind-mounts the key file from its *host* location
(outside the repo, same lesson as the earlier leaked-key incident) to `/run/secrets/gcp-key.json`
inside the `api` container and sets `GOOGLE_APPLICATION_CREDENTIALS` to that path; `.env` gained
`REPLY_MODEL_PRIMARY=vertex_ai/gemini-3.5-flash`, `VERTEX_PROJECT`, `VERTEX_LOCATION=global`,
and `GCP_KEY_HOST_PATH`; `llm.py` now passes `vertex_project`/`vertex_location` kwargs whenever
the model string starts with `vertex_ai/`.
Getting this live took a real chain of GCP-side fixes, each confirmed with a live probe rather
than assumed, in order: (1) Vertex AI API not enabled on the project (Google's error literally
calls it the **"Agent Platform API"** now -- Vertex AI has been rebranded; (2) billing not
linked to this specific project even though the trial was active on the account; (3) the
service account's IAM role search for "Vertex AI User" kept surfacing only Service-Agent
roles -- the role itself was renamed too, to **"Agent Platform User"**; (4) `gemini-2.5-flash`
returned 404 "not found" even with everything else correct -- it's been retired, same pattern
as the `gemini-2.0-flash`/`text-embedding-004` retirements hit earlier this project (see
10-25 entries) -- replaced with **`gemini-3.5-flash`**, confirmed as the current model via
Model Garden's own "View Code" sample; (5) that same sample revealed the region needs to be
**`global`**, not `us-central1` -- the regional endpoint 404'd on this model even with a valid
model ID. Also hit a real operational surprise along the way: `litellm[google]`'s import
is dramatically heavier (~37s just for `import litellm`, confirmed in isolation) than the
plain `litellm` the project shipped with before, which looked exactly like a hung process
(high sustained CPU, no response) until measured directly -- api container startup is now
correspondingly slower, and both `tests/test_s7_reliability_eval.py` and `evals/run_eval.py`'s
client-side HTTP timeouts were bumped from 30s to 60s to match Vertex AI's real per-call
latency (observed ~20s+ even for a trivial no-tool-call reply).

**Final verification:** `pytest tests/test_s7_reliability_eval.py` -- all 4 tests pass,
golden-set precision **100%** (8/8), 0 repeated facts memory ON vs 15 OFF (AC-8). `genesis gate
. S7` needed an explicit `--timeout 400000` (its default is 120000ms / 2 min, undocumented in
`--help`, too short for the suite's new ~5-minute runtime under Vertex AI's latency) --
otherwise passed clean. `genesis task complete . --id S7`, `genesis checkpoint .` -> Genesis
activated **S8** (Ship: README, GIF, architecture, results table, ADRs, next steps, optional
deploy, video script).

**Open items for next session:**
1. S8 is the active Genesis task (Ship) -- not started.
2. **Cost note, not a blocker:** the reply model now runs on Vertex AI's paid tier instead of
   two free tiers. Volume for a portfolio demo is trivial cost-wise, but this is a real change
   from "free" to "small real spend" worth calling out in the README/results table per Naf's
   own "will 50-100 people use this" framing.
3. **`embeddings.py` was *not* migrated** -- it still calls `gemini/gemini-embedding-001` via
   the old AI Studio `GEMINI_API_KEY`, a separate quota from the chat model's. Not blocking
   today (read path already degrades gracefully to no-context on embedding failure, I3), but
   worth the same Vertex AI migration if embedding-quota exhaustion ever shows up under real
   load -- flagging rather than silently leaving it inconsistent.
4. Gemini AI Studio key (`GEMINI_API_KEY`) is now only used by `embeddings.py`; Groq remains
   the reply-model fallback behind Vertex AI. Both still free-tier -- same quota ceilings as
   before apply if Vertex AI itself ever fails over to Groq under heavy load.
5. LOCATION/address PII detection still deferred (unchanged, long-standing item).

---

## 2026-10-27 (yet later) — S7 reliability + discount cap built; eval blocked on exhausted LLM quota, paused

**State at start:** S7 ("Reliability + eval: fallbacks, discount cap, eval runner over
evals/golden.jsonl, memory ON vs OFF comparison") active, not started. Requirements AC-3, AC-5,
AC-8, NFR-3.

**What was built:**
- **Discount cap (I5/AC-5):** new `discounts` table (`customer_id` as the *primary key* -- the
  cap is structural, not just app logic: a second grant for the same customer is a
  `UniqueViolation`, full stop). `tools.apply_discount(customer_id)`: idempotent, fixed 10%,
  first-order only. Wired into `agent.py` as a new `apply_discount` tool (only offered when
  `customer_id` is known) with a system-prompt instruction to call it on a price objection and
  never state a code/percent it didn't return. `reply_checker.py` now also flags any "N%"
  mentioned in a reply that doesn't match what `apply_discount` actually granted (same
  mechanism as the existing price-invention check) -- so even if the model tried to invent a
  bigger discount, the reply gets swapped for the safe fallback.
- **Fallback reliability (I3/AC-3/NFR-3):** found and fixed a real gap -- `main.py`'s `chat()`
  never wrapped `_start_turn`/`read_path.get_context` in a try/except, so a memory-layer DB
  failure would have crashed the *whole* `/chat` call instead of degrading to a reply without
  memory. Fixed. Also wrapped `agent.py`'s tool execution (`_run_tool`) so a failed product
  lookup returns `{"error": ...}` for the model to apologise with instead of crashing the turn,
  matching the design brief's own failure-mode table (§12: "DB down → reply without
  memory/tools"). Proved it the way the brief's own invariant test literally describes (§10):
  `docker compose stop db`, called `/chat`, got a real reply back, `docker compose start db`.
- **Eval runner (`evals/run_eval.py`, AC-8/NFR-2):** standalone script (`python
  evals/run_eval.py` for the full report) that runs each golden "retrieval" case memory ON
  (real setup → real memory → query) vs OFF (query alone, no memory ever existed), scoring
  precision (no forbidden product/text + every expected memory category actually retrieved)
  and repeat rate (expected categories the customer would have had to restate). Reusable from
  `tests/test_s7_reliability_eval.py` too.
- Wrote `tests/test_s7_reliability_eval.py`: two discount tests (cap via a live price-objection
  chat flow, cap via direct schema violation), one fallback test (the real DB-stop/start), and
  the golden-eval test.

**Verified so far:** discount cap -- real chat flow granted exactly one `WELCOME10-xxxxxx` code
at 10% to Leo on "too expensive, any discount?" and correctly declined a second ask; schema PK
test passed. Fallback -- `/chat` returned a real reply with the `db` container fully stopped,
every time. **3 of 4 gate tests pass.**

**Blocked, not a bug:** the golden-eval test (needs ~30-40 LLM calls for all 8 retrieval cases
ON+OFF) failed mid-run with `litellm.RateLimitError`. Checked the actual provider message, not
just a 500 -- Groq's **daily** token cap (TPD) was at 198,886/200,000 and climbing with every
retry; Gemini (the configured primary) has been silently failing with no logged error all
session, so every call all day has been riding on Groq's fallback alone, and today's heavy
S5/S6/S7 testing used it up. This is an external, time-bound quota ceiling, not a defect --
confirmed via the real error text, not inferred. Stopped immediately rather than keep retrying
(each retry was shrinking the remaining daily headroom further). Asked Naf how to proceed
(wait and retry later / get a fresh key now / run a smaller eval now) -- **he chose to wait.**
Ran `genesis control pause . S7 --reason "..."` to record the blocker in Genesis state rather
than leave it looking abandoned, then checkpointed. `phase/status` is now `build/paused`.

**Open items for next session:**
1. **Resume S7**: rerun `tests/test_s7_reliability_eval.py::test_golden_set_eval_precision_and_repeat_rate`
   (or `python evals/run_eval.py` directly for the full printed report) once LLM quota has
   recovered. The other 3 S7 gate tests already pass -- don't need rerunning unless source
   changes invalidate them. Once the eval passes, `genesis gate . S7` →
   `genesis task complete . --id S7` → checkpoint, same as every prior sprint.
2. **Gemini key rotation, now more urgent than before** (long-deferred, Naf's call): Gemini
   has produced *zero* visible errors all session despite apparently never successfully
   completing a call -- worth a direct `ListModels`/manual probe next session (same technique
   used in the 10-25 entry for the dead chat-model bug) to find out *why*, since right now every
   single `/chat` call's full weight falls on Groq alone, which is exactly what exhausted the
   daily quota today.
3. LOCATION/address PII detection still deferred (unchanged).
4. `handoff_to_human` / the "mock support inbox page" (design brief §8, §15) was never built --
   it's listed as one of the sales agent's tools in the brief, but no sprint's outcome text
   (S1-S8) explicitly owns it and no AC/invariant references it. Flagging rather than silently
   building or skipping; worth asking Naf whether it belongs in S8 (Ship) or is a "next steps"
   item for the README.

---

## 2026-10-27 (latest) — S6 governance + decay built, debugged, completed

**State at start:** S6 ("Governance + decay: That's wrong / Forget / Forget everything /
Download data / consent withdraw, decay job endpoint") active, not started. Requirements
FR-7, FR-9, AC-2 (I2), AC-6 (I6). No gate test file existed yet (`tests/test_s6_governance_decay.py`
had to be written this session, unlike S3/S4 which had theirs pre-staged).

**What was built:**
- `memory_repo.py` (the exit hatch) gained `soft_delete` (shared mechanics for "That's wrong"
  and "Forget this" -- I2: content/embedding nulled immediately, old content kept in
  `memory_history`), `log_feedback`, `forget_everything` (hard delete -- `memory_history`/
  `feedback` cascade from `memories`, `retrieval_log` cascades from `messages`, via the FKs
  already in `db/schema.sql`), and `withdraw_consent`.
- `main.py` gained the REST endpoints the S5 frontend was already calling:
  `PATCH /memories/{id}` (that's wrong), `DELETE /memories/{id}` (forget this),
  `DELETE /memories` (forget everything), `GET /memories/export` (download my data, as a real
  file download via `Content-Disposition`), `POST /consents/withdraw`, and
  `POST /admin/decay` (the decay job -- design brief §9's weight formula, admin-role since it
  sweeps every customer, which per-customer RLS would otherwise block).
- `web/lib/api.js` and `MemoryPanel.js`: the governance buttons built in S5 "wired for S6" now
  call the real endpoints with the right params (had to add `customer_id` to two of them --
  S5's placeholder calls didn't carry it, since there was nothing real to call yet). Added a
  "Withdraw consent" button. Removed the "ships in S6" fallback messaging now that it ships.
- Wrote `tests/test_s6_governance_decay.py` from scratch: forget-this nulls content/embedding
  immediately (I2) + logs feedback; that's-wrong same mechanics + `memory_history` row; forget-
  everything hard-deletes memories/messages/retrieval_log; consent withdrawal makes the very
  next chat message produce zero new memory rows (AC-6/I6); decay archives a memory built to
  match the design brief's own worked example (§9: episodic, importance 6, confidence 0.8,
  unused 60 days -> weight 0.12, archived) while a fresh memory and a procedural one (never
  decays) stay active; decay deletes a memory that's been archived over 12 months.

**Bug found and fixed (real schema gap, not a decision):** every governance test that actually
nulled a memory's content hit `psycopg.errors.NotNullViolation: null value in column "content"`.
`db/schema.sql`'s `memories.content` was `NOT NULL` -- nobody had hit this before because S1-S5
only ever *wrote* memories, never nulled one. I2 ("content/embedding nulled immediately") is
unimplementable under that constraint. Fixed by dropping the `NOT NULL` and adding
`CHECK (status = 'deleted' OR content IS NOT NULL)` instead, so the DB itself still guarantees
every active/archived memory has content -- only a deleted one may be null. Applied live via
`ALTER TABLE` against the running dev DB (no data loss) and updated `db/schema.sql` so a fresh
`docker compose up` gets it too.
- Reran S1/S2 (pass), S3/S4 (one transient 500 on the free-tier LLM -- passed clean in isolation
  seconds later, same known flakiness as prior sessions, nothing to do with S6's changes since
  neither `write_path.py` nor `extractor.py` were touched), and the full S5 Playwright suite
  (had to update its "Forget everything" assertion -- it used to check for the S5-era "ships in
  S6" placeholder text, which no longer appears now that the real endpoint exists; added a
  "Withdraw consent" check too). `genesis gate . S6` → passed, `genesis task complete . --id S6`,
  `genesis checkpoint .` → Genesis activated **S7** (Reliability + eval: fallbacks, discount cap,
  eval runner over `evals/golden.jsonl`, memory ON vs OFF comparison).

**Scope note for next session:** decay's "archived -> active again if the fact resurfaces"
transition (design brief §9) was deliberately not implemented -- `memory_repo._find_match` only
matches `status = 'active'` rows, so a repeated fact after archival inserts a new memory rather
than reactivating the old one. Reflection/merging is explicitly deferred per the brief; this
felt adjacent enough to flag rather than silently build or silently skip.

**Open items for next session:**
1. S7 is the active Genesis task (fallbacks, discount cap, eval runner, memory ON/OFF
   comparison) -- not started.
2. Gemini key rotation still deferred (Naf's call, unchanged). Worth noting: this session's
   LLM flakiness pointed at Gemini specifically going quiet with no logged error at all (likely
   free-tier daily quota, not just a per-minute limit like Groq's) -- everything was riding on
   Groq's fallback by the end of the session. Not blocking, but if S7's eval runner needs to
   fire 20+ LLM calls back-to-back, expect to hit this harder than previous sprints did.
3. LOCATION/address PII detection still deferred (unchanged).

---

## 2026-10-27 (even later) — Three bugs found by Naf manually using the S5 UI, fixed

**State at start:** S5 complete, S6 active (not yet started). Naf used the live app at
localhost:3000 and reported three problems from hands-on testing, not from a test suite.

**Bugs found and fixed (no Genesis task tied to this — straightforward defect fixes against
already-shipped sprints, not new scope):**
1. **Chat replies showed literal `**`/`*` markdown and ran all their lines together.** The LLM
   was replying in markdown (bold product names, bullet lists); the chat bubble just dumped the
   raw string into a `<div>` with no line-break handling. Fixed in two layers: told the model in
   `agent.py`'s `SYSTEM_PROMPT` to reply in plain sentences, no markdown, and added a defensive
   `stripMarkdown()` in `web/app/components/ChatWindow.js` (strips `**`, converts leading `* `
   bullets to `- `) plus `white-space: pre-wrap` on `.bubble` in `globals.css` — belt-and-suspenders
   since a free-tier fallback model won't always obey prompt instructions.
2. **"order Honduras for me" didn't work at all.** Root cause: `tools.search_products` (S2) only
   ever took `brew_method`/`max_price`/`decaf`/`in_stock_only` — there was no way to search by
   name or origin, so the agent had nothing to look "Honduras" up with regardless of phrasing.
   Added a `query` parameter (`name ILIKE OR origin ILIKE`) and told the agent (via the tool
   description and `SYSTEM_PROMPT`) to use it whenever the customer names a place, origin, or
   specific coffee, and to ask which one if a vague query matches more than one product. Confirmed
   against the catalog's two deliberately near-duplicate entries ("Ethiopia Guji" vs "Ethiopia
   Guji Natural Reserve", `nb-004`/`nb-005`, both flagged `_trap` in `products.json`) — the agent
   now lists both and asks which one, which is clearly what that trap was built to exercise and
   had never actually been wired up.
   - Also clarified in the prompt that "order"/"buy" means confirm the exact matching product
     enthusiastically — this app has no real checkout/order-placing tool, so the bot shouldn't
     claim to have processed a transaction.
3. **Off-topic questions (e.g. "what's the use of Python") got a "weird" answer.** The system
   prompt never told the model what to do outside its domain. Added an explicit instruction to
   state plainly that it's Northbean's coffee sales assistant and redirect, instead of attempting
   the unrelated question.
- Verified all three directly against the live API (`curl /chat`) before and after: Honduras now
  resolves to Honduras Marcala ($16, in stock); "I want the Guji" now lists both nb-004 and
  nb-005 and asks which one; the Python question now gets the redirect. Reran S1/S2 (pass) and
  the full S5 Playwright e2e suite (3/3 pass) to confirm no regression.
- **Docker aside, not a code bug:** mid-debugging, `docker compose up --build api` appeared to
  hang indefinitely (curl `000` for 60s+, container CPU pegged at 450%+). Bisected by killing the
  container and testing each import in isolation inside a fresh one (`python -c "from app import
  tools"`, then `agent`, then `read_path`, then the full `app.main`) — every one of them actually
  succeeded, just slower than my impatient 20-30s foreground timeouts (~20-25s total, versus the
  usual ~10-15s), because several heavy `docker compose`/`exec` calls were stacked up competing
  for the same CPU at once. Not caused by the agent.py/tools.py edits. Lesson: when a container
  seems stuck after a rebuild, check with patience (`docker compose top`, isolated imports) before
  assuming the new code is the cause, and don't stack more docker commands on top of one that's
  already slow.

**Open items for next session:** unchanged from the S5 entry below (S6 is still the active
Genesis task; Gemini key rotation and LOCATION/address PII detection still deferred).

---

## 2026-10-27 (later) — S5 frontend built, debugged, completed

**State at start:** `.genesis/KICKOFF.md` showed S5 ("Frontend: Next.js chat, user switcher,
consent prompt, memory panel, ops dashboard") active, not started — no `web/` directory existed.

**Scope decision (Naf's call):** FR-7's governance buttons (That's wrong / Forget this / Forget
everything / Download my data) appear on both the S5 and S6 task records, but the design brief's
own sprint table (§13) puts the backend for them in S6 (still `queued`). Asked Naf: build S5's
memory panel with those buttons wired to the exact REST shape S6 is scoped to implement (they
404 until S6 lands, shown honestly as "ships in S6"), rather than also building S6's backend now.
Naf picked that option — keeps the sprint boundary the brief already drew.

**What was built:**
- `web/` — a plain-JS (no TypeScript, no UI framework) Next.js 15 App Router app: shop chat page
  (user switcher, client-side consent modal gated on `localStorage`, chat window, "New chat"),
  a memory panel drawer (what's remembered + "memories used for this answer" + the four
  governance buttons), and an `/ops` dashboard page. Playwright e2e suite in `web/tests/e2e/`.
- Backend additions to `api/app/main.py` needed so those three required screens have something
  to call — judged in-scope for S5 because they're read-only listing/reporting, not governance
  (FR-7) itself: `GET /customers` (user switcher), `/chat` now also returns `message_id`,
  `GET /memories` enriched with `id`/`type`/a joined source quote+date (it was missing those),
  `GET /retrieval/{message_id}` ("memories used for this answer" with scores from
  `retrieval_log`), `GET /ops/metrics` (aggregate counts via the admin DB role, since it
  intentionally spans every customer and per-customer RLS would otherwise block it), and
  `POST /conversations/end` (backs "New chat").
- Added a `web` service to `docker-compose.yml` and a `web/Dockerfile`.

**Bugs found and fixed:**
- `npm install` flagged `next@14.2.18` with multiple known CVEs (including an unauthenticated
  Windows-hosted-server RCE advisory) — bumped to the patched `next@14.2.35`, then to
  `next@15.5.28` once peer deps were checked, plus an `overrides` pin on a transitive `postcss`
  version still inside the vulnerable range. `npm audit` is clean (0 vulnerabilities) with that
  combination.
- A `.gitignore` entry alone wasn't enough for Docker: there was no root `.dockerignore`, so
  every `docker compose build` was transferring the *entire* repo as build context (~430 MB,
  including `node_modules`, `.git`, `myenv/`) even for the `api` image. Added `.dockerignore`.
  Pre-existing inefficiency (every prior sprint's builds paid this cost too), not new.
- `docker compose up -d web` failed with a port-3000 bind conflict — a `npm run dev` I'd started
  directly on the host (to smoke-test the build before Docker was available) was still holding
  the port. Killed that process; not an app bug.
- First Playwright run: all 3 e2e tests failed — the user switcher rendered empty ("Pick a
  shopper above" with no persona buttons). Root cause: FastAPI had no CORS headers, so the
  browser silently blocked every `fetch()` from the frontend's origin (`localhost:3000`) to the
  API's (`localhost:8000`). Added `CORSMiddleware` allowing `http://localhost:3000`. Reran — 3/3
  passed.
- Reran S1-S4 Python suites to confirm the `main.py` edits (shared code) didn't regress anything
  — 4/5 passed immediately, `test_maya_setup_messages_produce_expected_memories` hit the same
  known free-tier rate-limit pattern documented in the two entries below (`RateLimitError` on
  Groq's TPM limit after S1-S4 plus manual testing shared the same quota); passed clean on retry
  once the window reset. Confirmed via container logs it was quota exhaustion, not my changes —
  the traceback bottoms out in `agent.py`/`llm.py`, nothing I touched.
- `genesis gate . S5` → passed, `genesis task complete . --id S5`, `genesis checkpoint .` →
  Genesis activated **S6** (Governance + decay: that's wrong / forget / forget everything /
  download data / consent withdraw, decay job endpoint).

**Dry run for Naf (traced through the files it touched):** Naf opens the shop page → the user
switcher calls `GET /customers` (new) and renders Maya/Leo/Ana/Sam as buttons. He clicks Maya →
since her browser has never seen a consent decision for her id, a client-side modal asks to
remember her; "Yes" just remembers that choice in `localStorage` and means her `customer_id` gets
attached to chat calls from here on (declining means it's omitted — same anonymous path as S2,
so nothing gets written, matching I6). He types a message → `POST /chat` runs exactly the S2-S4
pipeline unchanged, but the response now also carries `message_id`. The memory panel drawer then
makes two calls: `GET /memories` (what's remembered overall, now joined back to the original
message so it can show "from your message on <date>: '<quote>'") and
`GET /retrieval/{message_id}` (just the memories *this* reply actually used, with their scores,
read straight from the `retrieval_log` row S4 already writes). The four governance buttons in
that panel call `PATCH/DELETE /memories/...` — those endpoints don't exist yet, so today they
catch the 404 and show "ships in S6" instead of pretending to work. The `/ops` page calls
`GET /ops/metrics`, which — uniquely among these endpoints — connects with the Postgres admin
role instead of `app_user`, because it deliberately aggregates across every customer and the
per-customer RLS policy (I1) would otherwise zero it out.

**Open items for next session:**
1. S6 is the active Genesis task (governance backend + decay job) — not started. The frontend
   is already calling the exact endpoint shapes it needs (see `web/lib/api.js`): `PATCH
   /memories/{id}`, `DELETE /memories/{id}`, `DELETE /memories?customer_id=`, `GET
   /memories/export?customer_id=`. Implementing those (plus a consent-withdraw endpoint and the
   decay job) should make the existing buttons work with no frontend changes.
2. Gemini key rotation still deferred (Naf's call, unchanged from 10-25).
3. LOCATION/address PII detection still deferred (unchanged from 10-25, spaCy sandbox crash).
4. `web`'s dev server and anything run directly via `npm run dev` on the host both want port
   3000 — stop one before starting the other, same way `docker compose` vs. a bare `uvicorn`
   would collide on 8000.
5. Free-tier rate-limit flakiness under back-to-back test runs remains a known, non-blocking
   nuisance (see item above and the two entries below) — space out gate reruns if you see
   spurious 500s.

---

## 2026-10-27 — S4 read path: found & fixed, completed

**State at start:** `.genesis/KICKOFF.md` showed S4 ("Read path: always-loaded + hybrid search +
scoring + composer + reinforce + retrieval_log") active. Code already existed on disk from a
prior session that was never logged here: `api/app/read_path.py`, `main.py`/`agent.py` wiring,
and `tests/test_s4_read_path.py` — all untracked, gate still `pending`.

**What happened:**
- Rebuilt the API container (`docker compose up -d --build`) to make sure the running image
  actually had the on-disk S4 code — Docker Desktop's port-forward took ~30s to attach after
  the recreate, which looked like a hung container (host `curl`/`Invoke-RestMethod` timed out,
  `docker exec` into the container showed uvicorn already listening and serving fine
  internally). Not a bug, just a port-proxy delay; waiting resolved it.
- First gate run: 1 of 3 `test_s4_read_path.py` cases failed —
  `test_always_loaded_memories_are_retrieved_scored_and_reinforced` — because Maya's taste
  setup message ("I hate sour coffee, I like chocolatey notes.") got extracted into category
  `preference` instead of `taste`.
  - **Bug:** `api/app/extractor.py`'s prompt (S3-era) listed the 9 closed categories by name
    only, no descriptions or examples. The design brief (§7 step 3) gives a concrete few-shot
    example mapping that *exact* sentence to `taste`, but the prompt never included it, so the
    LLM had nothing to disambiguate `taste` (coffee flavor likes/dislikes) from `preference`
    (service style, e.g. "wants short answers", a totally different thing by brief §5's
    category table). Non-deterministic miscategorization, not a crash, so S3's own gate didn't
    catch it every run.
  - **Fix:** added a one-line description per category plus the brief's literal example to the
    extractor prompt. Rebuilt, reran — 3/3 passed.
- Confirmed no regression: reran S1+S2+S3 suites. S3's
  `test_maya_setup_messages_produce_expected_memories` hit a transient `500` (both free-tier
  LLM providers rate-limited back-to-back after the S4 suite's own chat volume) — same known
  pattern documented in the 10-25 entry below and in S4's own test comments; passed clean on
  retry 20s later, confirming it was load, not the extractor change.
  First `genesis gate . S4` run also failed for the same transient reason; reran clean.
- `genesis task complete . --id S4`, `genesis checkpoint .` → Genesis activated **S5**
  (frontend: Next.js chat, user switcher, consent prompt, memory panel, ops dashboard).

**Dry run for Naf (read path, traced through the files it touched):** Maya asks "Anything new
for me?" → `main.py` `/chat` sees her `customer_id`, inserts her message row first
(`_start_turn`), then calls `read_path.get_context(customer_id, message_id, message)` *before*
asking the sales agent anything. Inside `read_path.py`: it embeds her question (Gemini, own
generous timeout since that's a network call), then in one DB connection asks
`memory_repo.py` for two things — her "always-loaded" memories (brew method, taste, budget,
dietary; procedural notes) and a hybrid search (vector similarity + keyword) over everything
else. Those two lists get merged and scored (how well it matches + how recent + how often used
+ how important + how confident), the best ones get written into a short "What you know about
this customer" paragraph, trimmed to a word budget. That paragraph is handed to `agent.py` as
extra system-prompt context for this one reply, and `read_path.py` separately records which
memories got used into `retrieval_log` and bumps their "used" counter — so memories that keep
getting useful get surfaced more easily next time. If anything in that whole path is slow or
errors (bad network, DB hiccup), it just returns no context — the chat reply itself never waits
on it or breaks (I3).

**Open items for next session:**
1. Gemini key rotation still deferred (Naf's call, unchanged from 10-25).
2. S5 is the active Genesis task (frontend) — not started.
3. Nothing new blocking; free-tier rate-limit flakiness under back-to-back test runs remains a
   known, non-blocking nuisance — space out gate reruns if you see spurious 500s.

---

## 2026-10-25 (later) — Leaked key scrubbed from git history; S3 write path built, debugged, completed

**State at start:** `.genesis/KICKOFF.md` showed S3 ("Write path") active, not started. The
`d91818a "stage1"` commit still had a plaintext Gemini key in `test.py` (flagged in the
previous entry, unresolved).

**Git history cleanup (Naf's call, Naf ran every command):**
- Naf chose to keep the 2-commit history rather than squash it. Gave him `git filter-repo
  --force --replace-text <rule-file>` to swap the literal key for `REDACTED` across all
  history. He ran it; I verified afterward (`git log --all -p | grep` for the key string,
  full history, every file) — clean. Commit SHAs changed as expected (first commit's
  content changed, cascading to the rest). `origin` remote was dropped by filter-repo's
  default safety behaviour — a no-op here since none was configured yet.
- Gave Naf the `git remote add` + `git push` commands as text only, per standing instruction
  (never run git commit/push/remote-add myself in this repo) — did not execute them.
- Explained key rotation in plain terms (why rotate even after the git fix: the key sat in
  plaintext on disk independent of git, e.g. `.env`, so git-history exposure and "has this
  secret been seen" are two different risks). Naf deferred rotation to end of project —
  reasonable now that the GitHub exposure risk specifically is closed; flagged that terminal
  screenshots for his LinkedIn posts must not show `.env` or raw key values in the meantime.
- Drafted a LinkedIn post (sprint 1+2 recap, demo-the-no-hallucination angle) in Naf's voice
  per the `naf-writing-voice` skill. Not posted — his to publish.

**S3 implementation (write path: consent → PII filter → extractor → evaluator →
dedupe/conflict → store + audit, async via FastAPI `BackgroundTasks`):**
- New files: `api/app/pii_filter.py`, `embeddings.py`, `extractor.py`, `evaluator.py`,
  `memory_repo.py` (the brief's "exit hatch" — single interface for all memory DB writes),
  `write_path.py`. Edited `main.py` (`/chat` now takes an optional `customer_id`; S2's
  request shape still works unchanged) and `llm.py` (`complete()` now forwards `**kwargs`
  so the extractor can request JSON mode).
- **Bug 1:** `genesis brief` → `AnalyzerEngine(nlp_engine=NlpEngineProvider(... en_core_web_sm
  ...))` crashed on startup: `OverflowError: Python int too large to convert to C ssize_t`
  deep in spaCy's tokenizer deserialization — a spaCy/platform bug, not our code. None of the
  C3 PII types we actually need (cards, emails, phones, SSN/driver-license/passport IDs, IBAN,
  crypto, password phrases) need NER — they're all Presidio pattern/regex recognizers. Fixed
  by subclassing `SpacyNlpEngine` with a blank tokenizer-only pipeline (`spacy.blank`),
  skipping the trained-model load entirely. Cost: LOCATION (address) detection is out of
  scope until a real NER model can load somewhere that doesn't hit this crash — recorded as
  `KNOWLEDGE-fd98bbbb`.
- **Bug 2:** embeddings were silently failing — every write marked the source message
  `extraction_status='failed'`. Root cause: ADR-003's pinned `text-embedding-004` is retired
  (404 on `embedContent`). Probed live via `ListModels` (same technique as last session's dead
  chat-model fix) and confirmed `gemini-embedding-001` as the replacement; it defaults to 3072
  dims but accepts `dimensions=768`, so the existing `vector(768)` column needed no migration.
  Updated `api/app/embeddings.py` and `adr/003-embedding-model.md`. Recorded as
  `KNOWLEDGE-8a98b5f8`.
- **Environment note (not a bug, just noisy logs):** this sandbox blocks
  `raw.githubusercontent.com` specifically (other GitHub hosts, PyPI, and the Gemini/Groq
  APIs are all reachable). LiteLLM's own cost-map fetch retries against that host on every
  API container startup and falls back locally — harmless, just a ~7s delay in the logs.
  Also why the Dockerfile installs the spaCy model wheel via a direct `github.com` release URL
  instead of `spacy download` (which pings the blocked host for a version check) — though this
  became moot once the blank-pipeline fix above meant no spaCy model needs downloading at all;
  removed that Dockerfile step again.
- Wrote `tests/test_s3_write_path.py` (Maya's 4 setup messages → brew_method/taste/budget
  memories exist; Sam's small talk produces no memory; Sam's card number never appears in any
  memory or audit row, and a `block` audit row cites `CREDIT_CARD` as the type only).
- Ran `genesis gate . S3` → passed. Re-ran S1 + S2 gates first to confirm the optional
  `customer_id` change didn't regress them — still green. `genesis task complete . --id S3`,
  `genesis checkpoint .` → Genesis activated **S4** (read path: always-loaded + hybrid search +
  scoring + composer + reinforce + retrieval_log).

**Open items for next session:**
1. Gemini key rotation still deferred (Naf's call, see above) — not blocking, just don't let
   screenshots leak it.
2. S4 is the active Genesis task — not started.
3. LOCATION/address PII detection deferred (see Bug 1) — revisit if a real NER model is ever
   needed; would require an environment where `en_core_web_sm` actually loads.
4. The design brief's "+0.1 confidence if repeated in chat" evaluator bonus was deliberately
   skipped (no gate scenario exercises it) — see the `ponytail:` comment in `evaluator.py` if
   it's ever needed for a precision-tuning pass.

---

## 2026-10-25 — S2 debugged and completed; pre-commit security check; S1 dry run

**State at start:** Docker Desktop had just finished installing; `.genesis/KICKOFF.md`
showed S2 ("Chat + tools") active with its gate pending. Code for S2
(`api/app/{agent,llm,tools,reply_checker}.py`) already existed from a prior session but
had never been run against a live stack.

**What happened:**
- Brought the stack up with `docker compose up -d --build`. DB healthy, 18 products + 4
  personas seeded.
- Re-ran `tests/test_s1_foundation.py` to confirm S1 still holds on current code (it was
  marked "stale" by Genesis, not failed — source hash had moved) — 2/2 passed.
- Ran the S2 gate (`tests/test_s2_chat_tools.py`) — got a 500 on every `/chat` call.
  - **Bug 1:** the installed `litellm` version unconditionally imports an `mcp` package
    inside `completion()`, even for plain tool-calling; `mcp` wasn't in
    `api/requirements.txt`. Fixed by adding it.
  - **Bug 2:** both pinned model names were dead. Gemini rejected `gemini-2.0-flash`
    ("no longer available... use models/gemini-3.8-flash"); Groq rejected
    `llama-3.3-70b-versatile` ("does not exist or you do not have access to it"). Probed
    live candidates against the real API keys inside the container and confirmed working
    replacements: **`gemini/gemini-2.5-flash`** (primary) and
    **`groq/openai/gpt-oss-20b`** (fallback). Updated `api/app/llm.py` defaults.
- Rebuilt, reran — S2 gate passed. Full suite (`test_s1_foundation.py` +
  `test_s2_chat_tools.py`) — 3/3 passed.
- Ran `genesis gate . S2` → passed, `genesis task complete . --id S2`, `genesis
  checkpoint .` → Genesis activated **S3** (write path: PII filter → extractor →
  evaluator → dedupe/conflict → store + audit, async queue).
- Gave Naf the S2 dry run (traced "French press under $20" through main.py → agent.py →
  llm.py → tools.py → reply_checker.py).
- Naf asked to commit. Pre-commit check found no secrets in any new/untracked files
  (`.genesis/`, `SPEC.md`, `adr/`, `api/`, `db/`, `docker-compose.yml`,
  `requirements-dev.txt`, `tests/`) — **but** found that the existing commit `d91818a
  "stage1"` already has `test.py` with a **hardcoded, live Gemini API key in plaintext**
  (same key currently in `.env`). No remote is configured yet (nothing pushed). Flagged
  to Naf: rotate the key regardless, and optionally amend that one commit before ever
  pushing. **Not yet resolved — Naf hasn't decided.** Did not commit anything myself (per
  standing instruction: Naf does all git publishing).
- Helped Naf exercise `/chat` manually. `curl.exe` from PowerShell mangled the JSON body
  (PowerShell's quoting, not an API bug) — switched to `Invoke-RestMethod`. Naf then
  reported "sometimes not getting full answer" — root cause was PowerShell's default
  table formatting truncating long strings when `.reply` isn't chained onto the call;
  the API response itself was complete. No app bug.
- Noted from `docker compose logs`: Gemini intermittently throws before the fallback to
  Groq succeeds (every call still returns `200 OK`, just sometimes via fallback). Not
  blocking, worth watching if it gets worse.
- Gave Naf the S1 dry run (foundation: docker-compose, `db/schema.sql` RLS policies +
  dedicated `app_user` role so RLS is actually enforced, `db/seed.py`, and how
  `test_s1_foundation.py` proves cross-customer isolation (I1) rather than assuming it).

**Open items for next session:**
1. **Unresolved: leaked Gemini key in commit `d91818a`.** Naf needs to decide:
   rotate the key, and/or amend that commit before any `git push`.
2. S3 is the active Genesis task (write path: PII filter → extractor → evaluator →
   dedupe/conflict → store + audit log, async queue) — not started yet.
3. Watch whether Gemini's intermittent failures (see above) become frequent enough to
   need investigation; currently masked by the Groq fallback.

---

## Earlier (reconstructed from `.genesis/` state and git history — no prior SESSION_LOG.md existed)

- Project scaffolded with Genesis CLI v2.4.0 (`genesis init . --workflow new-product`).
  `SPEC.md`, ADRs (`adr/001-postgres-pgvector.md`, `adr/003-embedding-model.md`), and
  `.genesis/project.json` invariants/decisions recorded from `docs/DESIGN_BRIEF.md`.
- **S1 ("Foundation")** built and completed: `docker-compose.yml`, `db/schema.sql`
  (full schema + row-level security + dedicated `app_user` role), `db/seed.py`,
  `tests/test_s1_foundation.py`. Gate passed; task marked `done` in Genesis.
- Git: single commit `d91818a "stage1"` — contains the `test.py` plaintext-API-key issue
  noted above. No remote configured.
