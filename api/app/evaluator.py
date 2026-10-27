"""Rule-based write gate (design brief §5 taxonomy, §7 step 4). FR-2, FR-3.

ponytail: skips the brief's "+0.1 confidence if repeated in chat" bonus -- no gate scenario
exercises it and it would need session-local repetition tracking with nothing to pin the
behaviour against. Add it if a precision-tuning pass ever needs it.
"""

CATEGORY_TYPE = {
    "brew_method": "semantic",
    "taste": "semantic",
    "budget": "semantic",
    "dietary": "semantic",
    "buying_context": "semantic",
    "preference": "procedural",
    "objection": "episodic",
    "purchase_intent": "episodic",
    "issue": "episodic",
}
DEFAULT_IMPORTANCE = {
    "brew_method": 8,
    "taste": 9,
    "budget": 8,
    "dietary": 7,
    "buying_context": 7,
    "preference": 9,
    "objection": 6,
    "purchase_intent": 6,
    "issue": 7,
}
SENSITIVE_CATEGORIES = {"dietary"}


def evaluate(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (accepted, dropped); every drop carries a reason (FR-10 logs it)."""
    accepted, dropped = [], []
    for c in candidates:
        category = c.get("category")
        if category not in CATEGORY_TYPE:
            dropped.append({"candidate": c, "reason": "invalid category"})
            continue

        importance = DEFAULT_IMPORTANCE[category]
        confidence = 0.4 if c.get("is_hedged") else 0.8
        if importance * confidence < 3:
            dropped.append({"candidate": c, "reason": "importance x confidence below threshold"})
            continue

        accepted.append(
            {
                "content": c["content"],
                "type": CATEGORY_TYPE[category],
                "category": category,
                "sensitivity": "C2" if category in SENSITIVE_CATEGORIES else "C1",
                "importance": importance,
                "confidence": confidence,
            }
        )
    return accepted, dropped


if __name__ == "__main__":
    demo_accepted, demo_dropped = evaluate(
        [
            {"content": "brews with a french press", "category": "brew_method", "is_hedged": False},
            {"content": "it is raining", "category": "weather", "is_hedged": False},
            {"content": "maybe espresso someday", "category": "brew_method", "is_hedged": True},
        ]
    )
    assert len(demo_accepted) == 2
    assert demo_dropped[0]["reason"] == "invalid category"
    print("evaluator self-check OK")
