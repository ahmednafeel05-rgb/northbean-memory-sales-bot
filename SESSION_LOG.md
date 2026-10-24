# SESSION_LOG.md — Northbean Memory Sales Bot

Narrative history, maintained by whichever Claude Code session is working on this repo.
Complements `.genesis/KICKOFF.md` (structured task/gate state) with the "why" and the
debugging context Genesis doesn't record. See `CLAUDE.md` → "Session log" for the
maintenance contract. **Newest entry on top.**

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
