import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]


def search_products(brew_method=None, max_price=None, decaf=None, in_stock_only=True):
    query = "SELECT id, name, origin, roast, taste_notes, acidity, brew_methods, price_usd::float AS price_usd, in_stock, decaf FROM products WHERE true"
    params = []
    if brew_method:
        query += " AND %s = ANY(brew_methods)"
        params.append(brew_method)
    if max_price is not None:
        query += " AND price_usd <= %s"
        params.append(max_price)
    if decaf is not None:
        query += " AND decaf = %s"
        params.append(decaf)
    if in_stock_only:
        query += " AND in_stock = true"
    query += " ORDER BY price_usd LIMIT 5"
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(query, params).fetchall()


def check_stock(product_id):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT id, name, in_stock, price_usd::float AS price_usd FROM products WHERE id = %s",
            (product_id,),
        ).fetchone()
