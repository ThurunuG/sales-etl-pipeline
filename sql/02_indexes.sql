-- =====================================================================
-- 02_indexes.sql : indexes chosen for the analytical queries in 03
-- (the PRIMARY KEY on transaction_id and UNIQUE keys already have indexes)
-- =====================================================================

-- Date-range filters and monthly aggregations (queries 2 and 4)
CREATE INDEX IF NOT EXISTS idx_sales_order_date
    ON sales_transactions (order_date);

-- Foreign-key column + filtered category queries (e.g. "revenue of one category").
-- Postgres does NOT auto-index FK columns, so we add it. INCLUDE (total_amount) makes
-- it a covering index so such queries can use an index-only scan.
-- NOTE: a full "all categories" aggregate (Q1) reads every row anyway, so the planner
-- correctly keeps using a sequential scan there - indexes only help selective queries.
CREATE INDEX IF NOT EXISTS idx_sales_category_covering
    ON sales_transactions (category_id) INCLUDE (total_amount);

-- GROUP BY country + average rating (query 3). Partial index skips NULL ratings,
-- so it is smaller and every entry is useful for AVG(rating).
CREATE INDEX IF NOT EXISTS idx_sales_country_rating
    ON sales_transactions (country_id, rating)
    WHERE rating IS NOT NULL;

-- Range scans over very large, insert-ordered date columns: BRIN is tiny.
-- (Useful at 1M+ rows; harmless here.)
CREATE INDEX IF NOT EXISTS idx_sales_order_date_brin
    ON sales_transactions USING BRIN (order_date);

-- Refresh planner statistics after bulk loads
ANALYZE sales_transactions;
