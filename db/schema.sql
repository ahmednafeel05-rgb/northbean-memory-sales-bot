CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE customers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  display_name text NOT NULL,
  region text NOT NULL CHECK (region IN ('EU','US')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE consents (
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  purpose text NOT NULL,
  granted boolean NOT NULL,
  granted_at timestamptz,
  withdrawn_at timestamptz,
  PRIMARY KEY (customer_id, purpose)
);

CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz
);

CREATE TABLE messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  role text NOT NULL,
  content text NOT NULL,
  extraction_status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- embedding dimension pinned to Gemini text-embedding-004 (768 dims); see adr/003-embedding-model.md
CREATE TABLE memories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  type text NOT NULL CHECK (type IN ('semantic','procedural','episodic')),
  category text NOT NULL,
  sensitivity text NOT NULL CHECK (sensitivity IN ('C1','C2')),
  content text,  -- NOT NULL except when status='deleted' (I2: nulled immediately on forget)
  embedding vector(768),
  content_tsv tsvector,
  importance smallint NOT NULL CHECK (importance BETWEEN 1 AND 10),
  confidence real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  weight real NOT NULL DEFAULT 1.0,
  reinforcement int NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived','deleted')),
  source jsonb NOT NULL,
  last_used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status = 'deleted' OR content IS NOT NULL)  -- I2: only a deleted memory may be null
);

CREATE INDEX memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX memories_content_tsv_gin ON memories USING gin (content_tsv);
CREATE INDEX memories_customer_status_category ON memories (customer_id, status, category);

CREATE TABLE memory_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  old_content text,
  new_content text,
  reason text,
  changed_by text,
  changed_at timestamptz NOT NULL DEFAULT now()
);

-- append-only; no PII values, entity type only (see write-path PII filter)
CREATE TABLE audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  memory_id uuid REFERENCES memories(id) ON DELETE SET NULL,
  action text NOT NULL,
  actor text NOT NULL,
  detail jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE retrieval_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid REFERENCES messages(id) ON DELETE CASCADE,
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  memory_ids uuid[] NOT NULL DEFAULT '{}',
  scores jsonb,
  latency_ms real,
  used_fallback boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('wrong','forget','useful')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- One row per customer, ever (design brief §8: apply_discount, "fixed 10% first-order code,
-- max once per customer, enforced in code"). The PK itself is the cap -- a second INSERT for
-- the same customer is structurally impossible, not just application discipline.
CREATE TABLE discounts (
  customer_id uuid PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
  code text NOT NULL,
  percent_off smallint NOT NULL CHECK (percent_off > 0 AND percent_off <= 10),
  granted_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE products (
  id text PRIMARY KEY,
  name text NOT NULL,
  origin text NOT NULL,
  roast text NOT NULL,
  taste_notes text[] NOT NULL DEFAULT '{}',
  acidity text NOT NULL,
  brew_methods text[] NOT NULL DEFAULT '{}',
  price_usd numeric NOT NULL,
  in_stock boolean NOT NULL DEFAULT true,
  decaf boolean NOT NULL DEFAULT false
);

-- Row-level security: every request sets app.customer_id; policies compare to it (I1).
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE retrieval_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY customer_isolation ON messages USING (customer_id = current_setting('app.customer_id', true)::uuid);
CREATE POLICY customer_isolation ON memories USING (customer_id = current_setting('app.customer_id', true)::uuid);
CREATE POLICY customer_isolation ON audit_log USING (customer_id = current_setting('app.customer_id', true)::uuid);
CREATE POLICY customer_isolation ON feedback USING (customer_id = current_setting('app.customer_id', true)::uuid);
CREATE POLICY customer_isolation ON retrieval_log USING (customer_id = current_setting('app.customer_id', true)::uuid);

-- Dedicated non-superuser role so RLS is actually enforced (the postgres superuser
-- bypasses RLS regardless of policy). Dev-only credential: synthetic data, local
-- compose network only, never a real secret.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN PASSWORD 'app_user_dev_only';
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
