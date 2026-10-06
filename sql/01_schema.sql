-- =====================================================================
-- 01_schema.sql : tables, keys, constraints
-- Idempotent: safe to run many times.
-- =====================================================================

-- Lookup (dimension-style) tables ------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    category_id   SMALLSERIAL PRIMARY KEY,
    category_name VARCHAR(60) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS countries (
    country_id   SMALLSERIAL PRIMARY KEY,
    country_name VARCHAR(60) NOT NULL UNIQUE
);

-- Fact table -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS sales_transactions (
    transaction_id  VARCHAR(20)    PRIMARY KEY,
    customer_name   VARCHAR(120)   NOT NULL DEFAULT 'Unknown',
    product_name    VARCHAR(120)   NOT NULL,
    category_id     SMALLINT       NOT NULL REFERENCES categories (category_id),
    country_id      SMALLINT       NOT NULL REFERENCES countries (country_id),
    unit_price      NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    quantity        INTEGER        NOT NULL CHECK (quantity > 0),
    -- derived column stored by PostgreSQL so it can never drift from price * qty
    total_amount    NUMERIC(12, 2) GENERATED ALWAYS AS (unit_price * quantity) STORED,
    rating          NUMERIC(2, 1)  CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    payment_method  VARCHAR(30)    NOT NULL DEFAULT 'Unknown',
    order_date      DATE           NOT NULL CHECK (order_date BETWEEN DATE '2000-01-01' AND CURRENT_DATE),
    loaded_at       TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- ETL run audit table -------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id          SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'RUNNING',   -- RUNNING / SUCCESS / FAILED
    rows_extracted  INTEGER,
    rows_duplicates INTEGER,
    rows_rejected   INTEGER,
    rows_loaded     INTEGER,
    error_message   TEXT
);

-- Rejected rows are also kept in the DB for easy querying -------------
CREATE TABLE IF NOT EXISTS rejected_records (
    reject_id        BIGSERIAL PRIMARY KEY,
    run_id           INTEGER REFERENCES etl_runs (run_id),
    source_row       INTEGER,
    reason           TEXT NOT NULL,
    raw_record       JSONB,
    rejected_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
