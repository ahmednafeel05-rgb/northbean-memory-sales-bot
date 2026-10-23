# CLAUDE.md — Northbean Memory Sales Bot

Read this first in every session. Then read `docs/DESIGN_BRIEF.md`.

## What this project is
A **portfolio project** (not a production system) by Naf: an AI sales assistant for a
fictional D2C coffee brand, **Northbean Coffee**, with an **intelligent memory system**
that remembers each logged-in shopper across visits (taste, brew method, budget,
objections), lets them see/correct/delete memories (GDPR-first), and proves quality
with an evaluation.

The memory layer is the real product. The sales chat is the stage it performs on.

## How we build
- The build is driven by the **Genesis kit** (`.genesis/`: DONE.html, PLAN.md,
  implementation-notes.html, checkpoints/CURRENT.md, LOOPS.md, KICKOFF.md,
  context-graph.json) on top of the agentic-swe-master skills.
- If `.genesis/` does not exist yet: run the Genesis setup (G0–G6) using
  `docs/DESIGN_BRIEF.md` as the input. Every G0 answer is already in the brief —
  do not re-interview Naf on things the brief answers.
- Sprints and their demo commands are in the brief, section 13. Use them for PLAN.md.
- Invariants in brief section 10 go into DONE.html and context-graph.json. Never break them.

## Working with Naf
- Naf is new to AI engineering and knows only basic Python/Django. Explain what you
  built in plain, beginner-level words. After each sprint, give a short **dry run**:
  one example input traced through the files it touched.
- Ask Naf only for real decisions (brief section 15 lists the open ones and their
  defaults). Otherwise proceed.
- Scope is a portfolio project: prefer the simplest thing that demonstrates the
  concept. Items marked "deferred" in the brief stay out unless Naf asks.

## Ready-made inputs (do not regenerate)
- `data/products.json` — 18-coffee fake catalog (with deliberate traps)
- `data/personas.json` — 4 synthetic customers
- `evals/golden.jsonl` — 20 golden test cases
