import os
import secrets

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
DISCOUNT_PERCENT = 10


def search_products(query=None, brew_method=None, max_price=None, decaf=None, in_stock_only=True):
    sql = "SELECT id, name, origin, roast, taste_notes, acidity, brew_methods, price_usd::float AS price_usd, in_stock, decaf FROM products WHERE true"
    params = []
    if query:
        sql += " AND (name ILIKE %s OR origin ILIKE %s)"
        params += [f"%{query}%", f"%{query}%"]
    if brew_method:
        sql += " AND %s = ANY(brew_methods)"
        params.append(brew_method)
    if max_price is not None:
        sql += " AND price_usd <= %s"
        params.append(max_price)
    if decaf is not None:
        sql += " AND decaf = %s"
        params.append(decaf)
    if in_stock_only:
        sql += " AND in_stock = true"
    sql += " ORDER BY price_usd LIMIT 5"
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def check_stock(product_id):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT id, name, in_stock, price_usd::float AS price_usd FROM products WHERE id = %s",
            (product_id,),
        ).fetchone()


def apply_discount(customer_id):
    """Fixed 10% first-order code, max once per customer, enforced in code (design brief §8,
    I5) -- the `discounts` table's primary key on customer_id makes a second grant structurally
    impossible, not just a runtime check. Idempotent: asking again just returns the same code."""
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
        existing = conn.execute(
            "SELECT code, percent_off FROM discounts WHERE customer_id = %s", (customer_id,)
        ).fetchone()
        if existing:
            return {**existing, "newly_granted": False}
        code = f"WELCOME{DISCOUNT_PERCENT}-{secrets.token_hex(3).upper()}"
        row = conn.execute(
            "INSERT INTO discounts (customer_id, code, percent_off) VALUES (%s,%s,%s) "
            "ON CONFLICT (customer_id) DO NOTHING RETURNING code, percent_off",
            (customer_id, code, DISCOUNT_PERCENT),
        ).fetchone()
        if row is None:  # lost a race to a concurrent request; fall back to whatever won
            row = conn.execute(
                "SELECT code, percent_off FROM discounts WHERE customer_id = %s", (customer_id,)
            ).fetchone()
            return {**row, "newly_granted": False}
        return {**row, "newly_granted": True}
