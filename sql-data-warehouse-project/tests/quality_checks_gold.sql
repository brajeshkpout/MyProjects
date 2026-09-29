/*
===============================================================================
Quality checks: Gold layer
===============================================================================
EXPECTATION: NO ROWS RETURNED, except the row-count summary at the end.
===============================================================================
*/
USE DataWarehouse;
GO

-- Surrogate keys must be unique
SELECT customer_key, COUNT(*) FROM gold.dim_customers GROUP BY customer_key HAVING COUNT(*) > 1;
SELECT product_key,  COUNT(*) FROM gold.dim_products  GROUP BY product_key  HAVING COUNT(*) > 1;

-- Business keys must be unique (joins must not fan out the fact table)
SELECT customer_id,     COUNT(*) FROM gold.dim_customers GROUP BY customer_id     HAVING COUNT(*) > 1;
SELECT product_number,  COUNT(*) FROM gold.dim_products  GROUP BY product_number  HAVING COUNT(*) > 1;

-- Referential integrity: fact -> dimensions
SELECT f.* FROM gold.fact_sales f
LEFT JOIN gold.dim_customers c ON c.customer_key = f.customer_key
LEFT JOIN gold.dim_products  p ON p.product_key  = f.product_key
WHERE c.customer_key IS NULL OR p.product_key IS NULL;

-- Summary (informational)
SELECT 'dim_customers' AS dataset, COUNT(*) AS row_count FROM gold.dim_customers
UNION ALL SELECT 'dim_products', COUNT(*) FROM gold.dim_products
UNION ALL SELECT 'fact_sales',   COUNT(*) FROM gold.fact_sales;
GO
