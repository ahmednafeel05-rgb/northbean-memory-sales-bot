"""S2 gate: "something for French press under $20" -> reply cites only real catalog prices."""
import json
import os
import re
import urllib.request

import psycopg

API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")

_DOLLAR = re.compile(r"\$(\d+(?:\.\d{1,2})?)")


def _post_chat(message: str) -> str:
    data = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        f"{API_URL}/chat", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["reply"]


def test_french_press_under_20_cites_only_real_prices():
    reply = _post_chat("something for French press under $20")
    assert reply

    with psycopg.connect(ADMIN_URL) as conn:
        rows = conn.execute("SELECT price_usd FROM products").fetchall()
    catalog_prices = {round(float(price), 2) for (price,) in rows}

    mentioned = {round(float(a), 2) for a in _DOLLAR.findall(reply)}
    invented = mentioned - catalog_prices - {20.0}
    assert not invented, f"reply cited prices not in catalog: {invented}"
