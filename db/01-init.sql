-- Ouro (Slurm-Link) Database Schema

CREATE TABLE active_jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slurm_job_id        INTEGER,
  payload             JSONB NOT NULL,
  status              TEXT NOT NULL DEFAULT 'pending',
  x402_tx_hash        TEXT,
  price_usdc          NUMERIC(18,6) NOT NULL,
  client_builder_code TEXT,
  submitter_address   TEXT,
  submitted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Processor hot path (runs every 5s)
CREATE INDEX idx_active_jobs_status_submitted ON active_jobs (status, submitted_at);
-- User job lookups (case-insensitive)
CREATE INDEX idx_active_jobs_submitter_lower ON active_jobs (lower(submitter_address));

CREATE TABLE historical_data (
  id                 UUID NOT NULL,
  slurm_job_id       INTEGER,
  payload            JSONB NOT NULL,
  status             TEXT NOT NULL,
  x402_tx_hash       TEXT,
  price_usdc         NUMERIC(18,6) NOT NULL,
  submitter_address  TEXT,
  gas_paid_wei       NUMERIC(30,0),
  gas_paid_usd       NUMERIC(18,6),
  output_hash        BYTEA,
  proof_tx_hash      TEXT,
  builder_reward_usd NUMERIC(18,6) DEFAULT 0,
  compute_duration_s FLOAT,
  llm_cost_usd       NUMERIC(18,6) DEFAULT 0,
  submitted_at       TIMESTAMPTZ NOT NULL,
  completed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id, completed_at)
) PARTITION BY RANGE (completed_at);

-- User job lookups (case-insensitive)
CREATE INDEX idx_historical_data_submitter_lower ON historical_data (lower(submitter_address));

CREATE TABLE agent_costs (
  id          SERIAL PRIMARY KEY,
  cost_type   TEXT NOT NULL,
  amount_usd  NUMERIC(18,6) NOT NULL,
  detail      JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stats cost aggregation
CREATE INDEX idx_agent_costs_type_created ON agent_costs (cost_type, created_at);

CREATE TABLE wallet_snapshots (
  id            SERIAL PRIMARY KEY,
  eth_balance   NUMERIC(30,0) NOT NULL,
  usdc_balance  NUMERIC(18,6) NOT NULL,
  eth_price_usd NUMERIC(18,2),
  recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payment_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status          TEXT NOT NULL DEFAULT 'pending',
  script          TEXT NOT NULL,
  nodes           INTEGER NOT NULL,
  time_limit_min  INTEGER NOT NULL,
  price           TEXT NOT NULL,
  agent_url       TEXT,
  job_id          UUID,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE attribution_log (
  id          SERIAL PRIMARY KEY,
  tx_hash     TEXT NOT NULL,
  codes       TEXT[] NOT NULL,
  is_multi    BOOLEAN GENERATED ALWAYS AS (array_length(codes, 1) > 1) STORED,
  gas_used    NUMERIC(30,0),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attribution_codes ON attribution_log USING GIN (codes);

-- Create monthly partitions for historical_data (12 months ahead)
DO $$
DECLARE
    start_date DATE := date_trunc('month', CURRENT_DATE);
    end_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..11 LOOP
        end_date := start_date + INTERVAL '1 month';
        partition_name := 'historical_data_' || to_char(start_date, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF historical_data
             FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );
        start_date := end_date;
    END LOOP;
END $$;
