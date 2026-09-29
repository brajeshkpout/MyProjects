/*
===============================================================================
Quality checks: Silver layer
===============================================================================
Every query is written so that EXPECTATION: NO ROWS RETURNED (unless noted).
Run after:  EXEC silver.load_silver;
===============================================================================
*/
USE DataWarehouse;
GO

-- crm_cust_info ---------------------------------------------------------------
-- Duplicate or NULL primary keys
SELECT cst_id, COUNT(*) AS n FROM silver.crm_cust_info
GROUP BY cst_id HAVING COUNT(*) > 1 OR cst_id IS NULL;

-- Unwanted spaces
SELECT cst_firstname, cst_lastname FROM silver.crm_cust_info
WHERE cst_firstname <> TRIM(cst_firstname) OR cst_lastname <> TRIM(cst_lastname);

-- Standardisation (expect only Single / Married / n/a and Male / Female / n/a)
SELECT DISTINCT cst_marital_status, cst_gndr FROM silver.crm_cust_info;

-- crm_prd_info ----------------------------------------------------------------
-- Duplicate product versions
SELECT prd_id, COUNT(*) FROM silver.crm_prd_info GROUP BY prd_id HAVING COUNT(*) > 1;

-- NULL / negative cost
SELECT * FROM silver.crm_prd_info WHERE prd_cost IS NULL OR prd_cost < 0;

-- Invalid date ranges
SELECT * FROM silver.crm_prd_info WHERE prd_end_dt < prd_start_dt;

-- Each prd_key must have exactly one current (open-ended) version
SELECT prd_key, COUNT(*) FROM silver.crm_prd_info
WHERE prd_end_dt IS NULL GROUP BY prd_key HAVING COUNT(*) <> 1;

-- crm_sales_details -----------------------------------------------------------
-- Order date after ship / due date
SELECT * FROM silver.crm_sales_details
WHERE sls_order_dt > sls_ship_dt OR sls_order_dt > sls_due_dt;

-- Sales = quantity * price, and no NULL / zero / negative values
SELECT * FROM silver.crm_sales_details
WHERE sls_sales <> sls_quantity * sls_price
   OR sls_sales IS NULL OR sls_quantity IS NULL OR sls_price IS NULL
   OR sls_sales <= 0 OR sls_quantity <= 0 OR sls_price <= 0;

-- Orphans: sales rows without a customer / product
SELECT sd.* FROM silver.crm_sales_details sd
WHERE NOT EXISTS (SELECT 1 FROM silver.crm_cust_info c WHERE c.cst_id = sd.sls_cust_id)
   OR NOT EXISTS (SELECT 1 FROM silver.crm_prd_info  p WHERE p.prd_key = sd.sls_prd_key);

-- erp_cust_az12 ---------------------------------------------------------------
-- NAS prefix must be gone; birthdates not in the future
SELECT * FROM silver.erp_cust_az12 WHERE cid LIKE 'NAS%' OR bdate > CAST(GETDATE() AS DATE);

-- Standardisation (expect Male / Female / n/a)
SELECT DISTINCT gen FROM silver.erp_cust_az12;

-- erp_loc_a101 ----------------------------------------------------------------
-- Dashes must be gone; review distinct countries (no DE / US / USA / blank)
SELECT * FROM silver.erp_loc_a101 WHERE cid LIKE '%-%';
SELECT DISTINCT cntry FROM silver.erp_loc_a101 ORDER BY cntry;

-- cross-source key match: every CRM customer should have ERP rows
SELECT c.cst_key FROM silver.crm_cust_info c
WHERE NOT EXISTS (SELECT 1 FROM silver.erp_cust_az12 a WHERE a.cid = c.cst_key)
   OR NOT EXISTS (SELECT 1 FROM silver.erp_loc_a101  l WHERE l.cid = c.cst_key);
GO
