# CLAUDE.md — Northbean Memory Sales Bot

Read this first in every session. Then read `docs/DESIGN_BRIEF.md`, then `SESSION_LOG.md`
for narrative context `.genesis/KICKOFF.md` doesn't carry (debugging history, deferred
human decisions, environment-specific fixes).

## What this project is
A **portfolio project** (not a production system) by Naf: an AI sales assistant for a
fictional D2C coffee brand, **Northbean Coffee**, with an **intelligent memory system**
that remembers each logged-in shopper across visits (taste, brew method, budget,
objections), lets them see/correct/delete memories (GDPR-first), and proves quality
with an evaluation.

The memory layer is the real product. The sales chat is the stage it performs on.

## How we build
- The build is driven by the **Genesis kit** (`genesis-kit/`, CLI v2.4.0), which scaffolds
  `.genesis/` as: `project.json` (requirements, decisions, invariants, task state — the
  source of truth), `PLAN.md` (generated from `project.json`, do not edit directly),
  `KICKOFF.md` (resume pointer for cold sessions), `dashboard.html` (read-only control
  panel), and `index/` (code index for `genesis query`). The product specification lives
  in `SPEC.md` at the repo root. There is no `DONE.html`, `implementation-notes.html`,
  `LOOPS.md`, or `context-graph.json` in this version — those were an earlier Genesis
  format; ignore any instruction that assumes they exist.
- If `.genesis/` does not exist yet: run `genesis init . --workflow new-product
  --objective "..."`, then fill `SPEC.md` using `docs/DESIGN_BRIEF.md` as the input and
  run `genesis spec check` / `genesis spec approve`. Every spec answer is already in the
  brief — do not re-interview Naf on things the brief answers.
- Sprints and their demo commands are in the brief, section 13. Turn each sprint into a
  Genesis task (`genesis task add` with `--requirement` ids and an executable `--gate`),
  then `genesis plan check` / `genesis plan approve` to produce `PLAN.md`.
- Invariants in brief section 10 go into `.genesis/project.json` via `genesis record
  invariant`. Never break them.

## Working with Naf
- Naf is new to AI engineering and knows only basic Python/Django. Explain what you
  built in plain, beginner-level words. After each sprint, give a short **dry run**:
  one example input traced through the files it touched.
- Ask Naf only for real decisions (brief section 15 lists the open ones and their
  defaults). Otherwise proceed.
- Scope is a portfolio project: prefer the simplest thing that demonstrates the
  concept. Items marked "deferred" in the brief stay out unless Naf asks.

## Session log (SESSION_LOG.md)
- `SESSION_LOG.md` is a running, human-readable history that complements `.genesis/KICKOFF.md`.
  KICKOFF.md is Genesis's structured state (active task, gates, blocker); SESSION_LOG.md is
  the narrative Genesis doesn't record — bugs found and fixed, deferred decisions, anything
  Naf needs to remember that isn't a `project.json` record.
- **Every session, before ending or handing off, append a new dated entry** (new entries on
  top, most recent first) covering: what was done, bugs found/fixed and why, decisions made
  or still open, and the next action. Do this without being asked — the same way Genesis
  regenerates KICKOFF.md on checkpoint, but by hand since this file isn't Genesis-native.
- Do not rewrite history in this file — append, don't edit old entries, unless correcting a
  factual error in a past entry (mark it as a correction, don't silently change it).
- This file is not Genesis's source of truth — `.genesis/project.json` still is. If the two
  disagree, trust `.genesis/` for task/requirement state and this file for *why* things
  happened.

## Ready-made inputs (do not regenerate)
- `data/products.json` — 18-coffee fake catalog (with deliberate traps)
- `data/personas.json` — 4 synthetic customers
- `evals/golden.jsonl` — 20 golden test cases
