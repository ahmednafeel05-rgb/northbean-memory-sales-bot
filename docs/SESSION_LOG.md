# Session Log

Running record of prompts given to Claude Code and what was produced, for Naf to refer
back to later. Appended after each meaningful exchange, newest entry at the bottom.

---

## 2026-10-22 — Setup questions

**Prompt (paraphrased):** Where should the Genesis kit folder live — inside
`northbean-handoff/` or referenced from Desktop? How do we proceed once the Genesis
kit is pasted in and the init prompt is given?

**Output:** Confirmed `.genesis/` must live inside this project folder (repo-native,
reads `docs/DESIGN_BRIEF.md` + `data/` + `evals/` relative to project root). Naf then
added `agentic-swe-kit/` and `genesis-kit/` folders into the repo.

---

## 2026-10-22 — Logging, free LLM APIs, D2C concept check

**Prompt (paraphrased):** (1) Want prompts/outputs saved somewhere for later reference.
(2) Need free-tier signup links for "Grok/Gemini" APIs, no card required. (3) Sanity-check
understanding: Northbean is an online-only D2C coffee brand (no physical store, delivery
only), and the memory system recommends coffee based on remembered preferences.

**Output:**
- Created this file (`docs/SESSION_LOG.md`) for ongoing prompt/output tracking.
- Corrected **Groq vs Grok**: the brief (`DESIGN_BRIEF.md` §0, §17) and `HANDOFF.md`
  specify **Gemini (Google AI Studio)** and **Groq** (fast-inference host of open models),
  not xAI's Grok. Links given: aistudio.google.com (Gemini key) and console.groq.com
  (Groq key). Both have no-card free tiers (rate-limited, not credit-limited).
- Confirmed D2C understanding is correct, with nuance: the chat is the surface, the
  memory layer (write path → read path → GDPR panel → eval) is the actual product being
  demonstrated, per brief §1.

**Next step:** paste the Genesis init prompt from `HANDOFF.md` §2 to run G0–G6 setup.
