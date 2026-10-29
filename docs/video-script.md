# Demo video script

Target length: 2-3 minutes. Screen recording of http://localhost:3000, narrated.

---

**[0:00-0:15] Hook**

"This is Northbean — a fictional coffee shop's sales chatbot. Most AI chatbot demos either
don't really have memory, or they can't prove the memory actually helps. This one does both,
and I can show you the proof, not just tell you."

**[0:15-0:40] First visit, no memory yet**

- Open the shop, click **Maya**.
- Consent prompt appears — accept it.
- Type: *"I use a French press, I hate sour coffee, I like chocolatey notes, keep it under
  $20."*
- Reply recommends something that actually matches (point out: no invented product — it only
  ever recommends from the real catalog).

**[0:40-1:10] The memory panel**

- Open the memory panel drawer. Point out: brew method, taste, budget are now stored, each
  with a source quote and date — not a black box, you can see exactly why it knows this.
- Start a **new chat** (same persona, fresh conversation).
- Type: *"Anything new for me?"*
- Reply personalizes without Maya repeating anything — this is the "memory ON" case from the
  eval, live.

**[1:10-1:40] Governance — the GDPR-first part**

- In the memory panel, click **"That's wrong"** on one memory, then **"Forget this"** on
  another — show both actually changing in real time, not just a toast message.
- Click **"Download my data"** — show the real JSON file that downloads.
- Mention: consent withdrawal and forget-everything work the same way — real endpoints, not
  mockups.

**[1:40-2:10] The ops dashboard and the proof**

- Switch to the ops dashboard. Point out: write/drop/block counts, retrieval fallback rate,
  p95 latency — real operational numbers, not vanity metrics.
- Cut to a terminal: run `python evals/run_eval.py`, show the printed table — 100% precision,
  memory ON producing far fewer repeated facts than memory OFF.

**[2:10-2:30] Close**

"Everything here — the memory extraction, the retrieval scoring, the governance, the
reliability fallbacks, the evaluation — is explained decision-by-decision in the repo's ADRs,
and the full build history, bugs found and fixed, is in SESSION_LOG.md. Link's in the
description."
