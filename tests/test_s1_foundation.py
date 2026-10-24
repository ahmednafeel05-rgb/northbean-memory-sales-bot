"""S1 gate: docker compose up; products count = 18; cross-customer query returns 0 rows."""
import os
import uuid

import psycopg

ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/northbean")
APP_URL = os.environ.get("DATABASE_URL", "postgresql://app_user:app_user_dev_only@localhost:5432/northbean")


def test_products_seeded():
    with psycopg.connect(ADMIN_URL) as conn:
        count = conn.execute("SELECT count(*) FROM products").fetchone()[0]
    assert count == 18


def test_cross_customer_isolation():
    maya_id = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:maya")
    leo_id = uuid.uuid5(uuid.NAMESPACE_DNS, "northbean:leo")

    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(
            "INSERT INTO memories (customer_id, type, category, sensitivity, content, importance, confidence, source) "
            "VALUES (%s, 'semantic', 'taste', 'C1', 'rls test row', 5, 0.9, '{}'::jsonb)",
            (maya_id,),
        )
    try:
        with psycopg.connect(APP_URL) as conn:
            conn.execute("SELECT set_config('app.customer_id', %s, false)", (str(leo_id),))
            rows = conn.execute(
                "SELECT * FROM memories WHERE customer_id = %s", (maya_id,)
            ).fetchall()
        assert rows == []
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute("DELETE FROM memories WHERE content = 'rls test row'")
