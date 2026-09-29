/*
===============================================================================
Stored Procedure: silver.load_silver   (Bronze -> Silver)
===============================================================================
Full-refresh ETL. For each of the 6 tables: TRUNCATE, then INSERT ... SELECT
from bronze applying cleansing and standardisation. CTEs are used for
de-duplication, versioning and derived-value steps.

Transformations (summary):
  crm_cust_info      drop NULL ids; keep latest row per cst_id (ROW_NUMBER);
                     TRIM names; decode marital status / gender.
  crm_prd_info       split prd_key into cat_id + prd_key; NULL cost -> 0;
                     decode product line; rebuild end date with LEAD().
  crm_sales_details  yyyymmdd ints -> DATE (bad values -> NULL);
                     recompute sales / price when missing or inconsistent.
  erp_cust_az12      strip 'NAS' prefix from cid; future birthdates -> NULL;
                     normalise gender.
  erp_loc_a101       strip '-' from cid; normalise country names.
  erp_px_cat_g1v2    loaded as-is (already clean).

Usage:
    EXEC silver.load_silver;
===============================================================================
*/
USE DataWarehouse;
GO

CREATE OR ALTER PROCEDURE silver.load_silver
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @batch_start DATETIME2 = SYSDATETIME(),
            @t           DATETIME2,
            @rc          INT,
            @step        NVARCHAR(100) = N'start';

    BEGIN TRY
        PRINT '================================================';
        PRINT 'Loading Silver Layer';
        PRINT '================================================';

        ----------------------------------------------------------------------
        -- 1. silver.crm_cust_info
        ----------------------------------------------------------------------
        SET @step = N'silver.crm_cust_info'; SET @t = SYSDATETIME();
        TRUNCATE TABLE silver.crm_cust_info;

        WITH ranked AS (
            SELECT  *,
                    ROW_NUMBER() OVER (PARTITION BY cst_id
                                       ORDER BY cst_create_date DESC) AS rn
            FROM    bronze.crm_cust_info
            WHERE   cst_id IS NOT NULL
        )
        INSERT INTO silver.crm_cust_info
            (cst_id, cst_key, cst_firstname, cst_lastname,
             cst_marital_status, cst_gndr, cst_create_date)
        SELECT  cst_id,
                TRIM(cst_key),
                TRIM(cst_firstname),
                TRIM(cst_lastname),
                CASE UPPER(TRIM(cst_marital_status))
                     WHEN 'S' THEN 'Single'
                     WHEN 'M' THEN 'Married'
                     ELSE 'n/a' END,
                CASE UPPER(TRIM(cst_gndr))
                     WHEN 'F' THEN 'Female'
                     WHEN 'M' THEN 'Male'
                     ELSE 'n/a' END,
                cst_create_date
        FROM    ranked
        WHERE   rn = 1;
        SET @rc = @@ROWCOUNT;
        PRINT '>> ' + @step + ': ' + CAST(@rc AS NVARCHAR(20)) + ' rows, '
              + CAST(DATEDIFF(MILLISECOND, @t, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';

        ----------------------------------------------------------------------
        -- 2. silver.crm_prd_info
        ----------------------------------------------------------------------
        SET @step = N'silver.crm_prd_info'; SET @t = SYSDATETIME();
        TRUNCATE TABLE silver.crm_prd_info;

        WITH versioned AS (
            SELECT  prd_id, prd_key, prd_nm, prd_cost, prd_line, prd_start_dt,
                    LEAD(prd_start_dt) OVER (PARTITION BY prd_key
                                             ORDER BY prd_start_dt) AS next_start_dt
            FROM    bronze.crm_prd_info
        )
        INSERT INTO silver.crm_prd_info
            (prd_id, cat_id, prd_key, prd_nm, prd_cost, prd_line, prd_start_dt, prd_end_dt)
        SELECT  prd_id,
                REPLACE(SUBSTRING(prd_key, 1, 5), '-', '_'),
                SUBSTRING(prd_key, 7, LEN(prd_key)),
                prd_nm,
                ISNULL(prd_cost, 0),
                CASE UPPER(TRIM(prd_line))
                     WHEN 'M' THEN 'Mountain'
                     WHEN 'R' THEN 'Road'
                     WHEN 'S' THEN 'Other Sales'
                     WHEN 'T' THEN 'Touring'
                     ELSE 'n/a' END,
                prd_start_dt,
                DATEADD(DAY, -1, next_start_dt)      -- NULL for the current version
        FROM    versioned;
        SET @rc = @@ROWCOUNT;
        PRINT '>> ' + @step + ': ' + CAST(@rc AS NVARCHAR(20)) + ' rows, '
              + CAST(DATEDIFF(MILLISECOND, @t, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';

        ----------------------------------------------------------------------
        -- 3. silver.crm_sales_details
        ----------------------------------------------------------------------
        SET @step = N'silver.crm_sales_details'; SET @t = SYSDATETIME();
        TRUNCATE TABLE silver.crm_sales_details;

        WITH fixed AS (
            -- Step 1: repair the sales amount.
            -- If sales is missing / non-positive / not equal to qty * |price|,
            -- rebuild it from quantity and absolute price.
            SELECT  *,
                    CASE WHEN sls_sales IS NULL
                           OR sls_sales <= 0
                           OR sls_sales <> sls_quantity * ABS(sls_price)
                         THEN sls_quantity * ABS(sls_price)
                         ELSE sls_sales END AS fixed_sales
            FROM    bronze.crm_sales_details
        )
        INSERT INTO silver.crm_sales_details
            (sls_ord_num, sls_prd_key, sls_cust_id, sls_order_dt, sls_ship_dt,
             sls_due_dt, sls_sales, sls_quantity, sls_price)
        SELECT  TRIM(sls_ord_num),
                TRIM(sls_prd_key),
                sls_cust_id,
                -- yyyymmdd integers -> DATE; 0 / wrong length / invalid -> NULL
                CASE WHEN LEN(sls_order_dt) = 8
                     THEN TRY_CONVERT(DATE, CAST(sls_order_dt AS VARCHAR(8)), 112) END,
                CASE WHEN LEN(sls_ship_dt) = 8
                     THEN TRY_CONVERT(DATE, CAST(sls_ship_dt AS VARCHAR(8)), 112) END,
                CASE WHEN LEN(sls_due_dt) = 8
                     THEN TRY_CONVERT(DATE, CAST(sls_due_dt AS VARCHAR(8)), 112) END,
                fixed_sales,
                sls_quantity,
                -- Step 2: repair the price from the repaired sales amount.
                CASE WHEN sls_price IS NULL OR sls_price <= 0
                     THEN fixed_sales / NULLIF(sls_quantity, 0)
                     ELSE sls_price END
        FROM    fixed;
        SET @rc = @@ROWCOUNT;
        PRINT '>> ' + @step + ': ' + CAST(@rc AS NVARCHAR(20)) + ' rows, '
              + CAST(DATEDIFF(MILLISECOND, @t, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';

        ----------------------------------------------------------------------
        -- 4. silver.erp_cust_az12
        ----------------------------------------------------------------------
        SET @step = N'silver.erp_cust_az12'; SET @t = SYSDATETIME();
        TRUNCATE TABLE silver.erp_cust_az12;

        INSERT INTO silver.erp_cust_az12 (cid, bdate, gen)
        SELECT  CASE WHEN TRIM(cid) LIKE 'NAS%' THEN SUBSTRING(TRIM(cid), 4, LEN(TRIM(cid)))
                     ELSE TRIM(cid) END,
                CASE WHEN bdate > CAST(GETDATE() AS DATE) THEN NULL ELSE bdate END,
                CASE WHEN UPPER(TRIM(gen)) IN ('F', 'FEMALE') THEN 'Female'
                     WHEN UPPER(TRIM(gen)) IN ('M', 'MALE')   THEN 'Male'
                     ELSE 'n/a' END
        FROM    bronze.erp_cust_az12;
        SET @rc = @@ROWCOUNT;
        PRINT '>> ' + @step + ': ' + CAST(@rc AS NVARCHAR(20)) + ' rows, '
              + CAST(DATEDIFF(MILLISECOND, @t, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';

        ----------------------------------------------------------------------
        -- 5. silver.erp_loc_a101
        ----------------------------------------------------------------------
        SET @step = N'silver.erp_loc_a101'; SET @t = SYSDATETIME();
        TRUNCATE TABLE silver.erp_loc_a101;

        INSERT INTO silver.erp_loc_a101 (cid, cntry)
        SELECT  REPLACE(TRIM(cid), '-', ''),
                CASE WHEN TRIM(cntry) = 'DE'                 THEN 'Germany'
                     WHEN TRIM(cntry) IN ('US', 'USA')       THEN 'United States'
                     WHEN TRIM(cntry) = '' OR cntry IS NULL  THEN 'n/a'
                     ELSE TRIM(cntry) END
        FROM    bronze.erp_loc_a101;
        SET @rc = @@ROWCOUNT;
        PRINT '>> ' + @step + ': ' + CAST(@rc AS NVARCHAR(20)) + ' rows, '
              + CAST(DATEDIFF(MILLISECOND, @t, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';

        ----------------------------------------------------------------------
        -- 6. silver.erp_px_cat_g1v2
        ----------------------------------------------------------------------
        SET @step = N'silver.erp_px_cat_g1v2'; SET @t = SYSDATETIME();
        TRUNCATE TABLE silver.erp_px_cat_g1v2;

        INSERT INTO silver.erp_px_cat_g1v2 (id, cat, subcat, maintenance)
        SELECT  TRIM(id), TRIM(cat), TRIM(subcat), TRIM(maintenance)
        FROM    bronze.erp_px_cat_g1v2;
        SET @rc = @@ROWCOUNT;
        PRINT '>> ' + @step + ': ' + CAST(@rc AS NVARCHAR(20)) + ' rows, '
              + CAST(DATEDIFF(MILLISECOND, @t, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';

        PRINT '================================================';
        PRINT 'Silver load completed in '
              + CAST(DATEDIFF(SECOND, @batch_start, SYSDATETIME()) AS NVARCHAR(20)) + ' s';
        PRINT '================================================';
    END TRY
    BEGIN CATCH
        PRINT '================================================';
        PRINT 'ERROR DURING SILVER LOAD (' + @step + ')';
        PRINT 'Message: ' + ERROR_MESSAGE();
        PRINT 'Number : ' + CAST(ERROR_NUMBER() AS NVARCHAR(20));
        PRINT '================================================';
        THROW;
    END CATCH;
END;
GO
