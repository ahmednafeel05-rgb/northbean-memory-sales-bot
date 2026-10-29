# ADR-004: Rules-first evaluator for candidate memories

**Status:** Accepted (S3)

**Context:** After the extractor LLM proposes candidate memories from a chat message, each
one needs an importance score, a confidence score, and a type (semantic/episodic/procedural)
before it can be written. Could ask a second LLM call to judge each candidate, or decide with
fixed rules.

**Decision:** `api/app/evaluator.py` is pure Python, no LLM call: a fixed lookup table maps
each of the design brief's 9 categories to a type and a default importance (brief §5), a
hedged candidate (`is_hedged: true`, e.g. "maybe espresso someday") gets confidence 0.4 vs.
0.8 for a stated fact, and anything below an `importance * confidence` threshold is dropped
with a logged reason. An invalid/unrecognised category is dropped outright.

**Consequences:** Deterministic and instant -- no added LLM latency or cost per candidate, and
every accept/drop decision is reproducible and testable without hitting a model. Tradeoff: the
importance/confidence values are fixed per category rather than judged per-instance (a
"French press" mention is always importance 8, regardless of how enthusiastically it was
said) -- acceptable for a v1 portfolio scope; a learned or LLM-judged scorer is a reasonable
future upgrade, not solved here.
