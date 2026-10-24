"""Seed products.json and personas.json into Postgres. Idempotent (safe to rerun)."""
import json
import os
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")


def persona_customer_id(persona_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"northbean:{persona_id}")


def seed_products(conn):
    products = json.loads((ROOT / "data" / "products.json").read_text())
    for p in products:
        conn.execute(
            """
            INSERT INTO products (id, name, origin, roast, taste_notes, acidity, brew_methods, price_usd, in_stock, decaf)
            VALUES (%(id)s, %(name)s, %(origin)s, %(roast)s, %(taste_notes)s, %(acidity)s, %(brew_methods)s, %(price_usd)s, %(in_stock)s, %(decaf)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, origin = EXCLUDED.origin, roast = EXCLUDED.roast,
                taste_notes = EXCLUDED.taste_notes, acidity = EXCLUDED.acidity,
                brew_methods = EXCLUDED.brew_methods, price_usd = EXCLUDED.price_usd,
                in_stock = EXCLUDED.in_stock, decaf = EXCLUDED.decaf
            """,
            p,
        )


def seed_personas(conn):
    personas = json.loads((ROOT / "data" / "personas.json").read_text())
    for persona in personas:
        customer_id = persona_customer_id(persona["id"])
        conn.execute(
            """
            INSERT INTO customers (id, email, display_name, region)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name, region = EXCLUDED.region
            """,
            (customer_id, persona["email"], persona["display_name"], persona["region"]),
        )
        conn.execute(
            """
            INSERT INTO consents (customer_id, purpose, granted, granted_at)
            VALUES (%s, 'personalisation', %s, now())
            ON CONFLICT (customer_id, purpose) DO UPDATE SET granted = EXCLUDED.granted
            """,
            (customer_id, persona["consent_personalisation"]),
        )


def main():
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        seed_products(conn)
        seed_personas(conn)
    print("Seeded 18 products and 4 personas.")


if __name__ == "__main__":
    main()
