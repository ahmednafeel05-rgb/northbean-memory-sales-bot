import re

_DOLLAR = re.compile(r"\$(\d+(?:\.\d{1,2})?)")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
DISCOUNT_CAP = 10  # design brief §8/§15: fixed 10% first-order code, never more (I5)


# ponytail: only catches invented $ amounts and discount percentages, not invented product
# names (that would need NLP over free text). Name invention is guarded structurally instead:
# the agent may only mention products it actually got back from search_products/check_stock.
# Upgrade path if that guard is ever bypassed: match reply text against known product names too.
def check(reply: str, seen_products: list[dict], user_message: str = "", discount_result: dict | None = None) -> list[str]:
    valid = {round(float(p["price_usd"]), 2) for p in seen_products}
    echoed = {round(float(a), 2) for a in _DOLLAR.findall(user_message)}
    violations = []
    for amount in _DOLLAR.findall(reply):
        value = round(float(amount), 2)
        if value not in valid and value not in echoed:
            violations.append(f"unverified price ${amount}")

    granted_percent = discount_result["percent_off"] if discount_result else None
    for amount in _PERCENT.findall(reply):
        value = float(amount)
        if value > DISCOUNT_CAP or granted_percent is None or value != granted_percent:
            violations.append(f"unverified discount {amount}%")
    return violations


def safe_fallback(seen_products: list[dict]) -> str:
    if not seen_products:
        return "I couldn't find a matching coffee in stock right now — want me to check something else?"
    lines = [f"- {p['name']} (${p['price_usd']})" for p in seen_products[:3]]
    return "Here's what I found in the catalog:\n" + "\n".join(lines)
