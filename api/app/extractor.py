"""Candidate-memory extraction (design brief §7 step 3, FR-1). Reuses the same free-tier
models as the sales reply (llm.py) -- that's already the "cheap" model, no separate client."""
import json

from . import llm

_PROMPT = """Extract candidate memories from the customer's latest message.

Categories (pick exactly one per candidate):
- brew_method: how they brew, e.g. uses a French press
- taste: flavor/acidity likes or dislikes of the coffee itself, e.g. likes chocolatey, \
low-acid coffee, hates sour coffee
- budget: price limits, e.g. under $20 a bag
- dietary: decaf/diet constraints
- buying_context: who/why they're buying, e.g. buys for an office of 10
- preference: how they want to be served/talked to (NOT coffee flavor), e.g. wants short answers
- objection: a stated pushback, e.g. said too expensive on this date
- purchase_intent: a product they showed intent to buy
- issue: a complaint, e.g. late delivery

Rules: one fact per candidate, write content as a third-person sentence about the customer, \
include the exact supporting quote as "evidence", set is_hedged true for maybes/somedays. \
Ignore small talk, weather, and greetings with no shoppable fact -- return no candidate for \
those. The message may already contain tokens like [REDACTED_CREDIT_CARD]; never invent a \
candidate about those, treat them as already removed.

Example: message "I hate sour coffee" -> {{"candidates": [{{"content": "prefers chocolatey, \
low-acid coffee", "type": "semantic", "category": "taste", "evidence": "I hate sour coffee", \
"is_hedged": false}}]}}

Reply with JSON only, no prose: {{"candidates": [{{"content": "...", "type": "...", \
"category": "...", "evidence": "...", "is_hedged": false}}]}}. Use {{"candidates": []}} if \
nothing qualifies.

Previous assistant reply: {prev}
Customer message: {message}"""


def extract(masked_message: str, prev_assistant_reply: str = "") -> list[dict]:
    prompt = _PROMPT.format(prev=prev_assistant_reply or "(none)", message=masked_message)
    messages = [{"role": "user", "content": prompt}]
    for _ in range(2):  # invalid JSON -> retry once -> skip (design brief §7.3)
        try:
            response = llm.complete(messages, response_format={"type": "json_object"})
            data = json.loads(response.choices[0].message.content)
            return data.get("candidates", [])
        except Exception:
            continue
    return []
