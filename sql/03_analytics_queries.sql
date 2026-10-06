-- =====================================================================
-- 03_analytics_queries.sql : analytical queries
-- Run:  psql -f sql/03_analytics_queries.sql   (or python scripts/run_queries.py)
-- =====================================================================

-- Q1. Top 10 categories by revenue -------------------------------------
-- Optimisation: aggregate on the integer category_id first and join the tiny
-- categories table AFTER aggregation (joins ~7 rows, not every transaction).
-- This query touches 100% of rows, so a sequential scan is the right plan; an
-- index would not help (see scripts/benchmark_indexes.py, Q-E).
SELECT c.category_name,
       agg.orders,
       agg.revenue,
       ROUND(100 * agg.revenue / SUM(agg.revenue) OVER (), 2) AS pct_of_total
FROM (
        SELECT category_id,
               COUNT(*)          AS orders,
               SUM(total_amount) AS revenue
        FROM sales_transactions
        GROUP BY category_id
     ) agg
JOIN categories c USING (category_id)
ORDER BY agg.revenue DESC
LIMIT 10;

-- Q2. Monthly revenue and month-over-month growth ----------------------
-- Optimisation: aggregate first (one row per month), then apply the LAG window
-- function over ~36 rows instead of over every transaction.
WITH monthly AS (
    SELECT date_trunc('month', order_date)::date AS month,
           SUM(total_amount)                     AS revenue,
           COUNT(*)                              AS orders
    FROM sales_transactions
    GROUP BY 1
)
SELECT month,
       orders,
       revenue,
       LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
             / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 2) AS mom_growth_pct
FROM monthly
ORDER BY month;

-- Q3. Average rating by country ---------------------------------------
-- Optimisation: partial index (country_id, rating) WHERE rating IS NOT NULL
-- supports this exact access pattern. HAVING removes statistically weak groups.
SELECT co.country_name,
       COUNT(s.rating)           AS rated_orders,
       ROUND(AVG(s.rating), 2)   AS avg_rating
FROM sales_transactions s
JOIN countries co USING (country_id)
WHERE s.rating IS NOT NULL
GROUP BY co.country_name
HAVING COUNT(s.rating) >= 30
ORDER BY avg_rating DESC;

-- Q4. Top 3 products per category by revenue in the latest full year ----
-- Optimisation: the date predicate is a sargable range (not EXTRACT(year ...)),
-- so idx_sales_order_date can be used. ROW_NUMBER ranks inside each category.
WITH ranked AS (
    SELECT c.category_name,
           s.product_name,
           SUM(s.total_amount) AS revenue,
           ROW_NUMBER() OVER (PARTITION BY c.category_name
                              ORDER BY SUM(s.total_amount) DESC) AS rnk
    FROM sales_transactions s
    JOIN categories c USING (category_id)
    WHERE s.order_date >= DATE '2025-01-01'
      AND s.order_date <  DATE '2026-01-01'
    GROUP BY c.category_name, s.product_name
)
SELECT category_name, product_name, revenue, rnk
FROM ranked
WHERE rnk <= 3
ORDER BY category_name, rnk;

-- Q5. Revenue by payment method and country (top 15 combinations) ------
SELECT co.country_name,
       s.payment_method,
       COUNT(*)            AS orders,
       SUM(s.total_amount) AS revenue
FROM sales_transactions s
JOIN countries co USING (country_id)
GROUP BY co.country_name, s.payment_method
ORDER BY revenue DESC
LIMIT 15;
