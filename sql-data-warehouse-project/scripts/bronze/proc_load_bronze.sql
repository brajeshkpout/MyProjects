/*
===============================================================================
Stored Procedure: bronze.load_bronze   (Source files -> Bronze)
===============================================================================
Truncates each bronze table and bulk-loads it from its CSV file.

Parameter:
    @data_path  Folder that CONTAINS 'source_crm' and 'source_erp'.
                MUST end with a path separator.
                Default matches the Docker setup in this repo.
                The path is resolved by the SQL Server *service*, so it must be
                a path visible to the server process (not your laptop's).

Usage:
    EXEC bronze.load_bronze;
    EXEC bronze.load_bronze @data_path = N'C:\data\datasets\';
===============================================================================
*/
USE DataWarehouse;
GO

CREATE OR ALTER PROCEDURE bronze.load_bronze
    @data_path NVARCHAR(400) = N'/var/opt/mssql/datasets/'
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @batch_start DATETIME2 = SYSDATETIME(),
            @start_time  DATETIME2,
            @sql         NVARCHAR(MAX),
            @i           INT = 1,
            @n           INT,
            @tbl         NVARCHAR(128),
            @file        NVARCHAR(260),
            @rows        INT;

    DECLARE @files TABLE (id INT, tbl NVARCHAR(128), rel_path NVARCHAR(260));
    INSERT INTO @files (id, tbl, rel_path) VALUES
        (1, N'bronze.crm_cust_info',     N'source_crm/cust_info.csv'),
        (2, N'bronze.crm_prd_info',      N'source_crm/prd_info.csv'),
        (3, N'bronze.crm_sales_details', N'source_crm/sales_details.csv'),
        (4, N'bronze.erp_cust_az12',     N'source_erp/cust_az12.csv'),
        (5, N'bronze.erp_loc_a101',      N'source_erp/loc_a101.csv'),
        (6, N'bronze.erp_px_cat_g1v2',   N'source_erp/px_cat_g1v2.csv');
    SELECT @n = COUNT(*) FROM @files;

    BEGIN TRY
        PRINT '================================================';
        PRINT 'Loading Bronze Layer';
        PRINT '================================================';

        WHILE @i <= @n
        BEGIN
            SELECT @tbl = tbl, @file = rel_path FROM @files WHERE id = @i;
            SET @start_time = SYSDATETIME();

            -- BULK INSERT cannot take a variable file name, hence dynamic SQL.
            SET @sql = N'TRUNCATE TABLE ' + @tbl + N'; '
                     + N'BULK INSERT ' + @tbl
                     + N' FROM ''' + REPLACE(@data_path + @file, N'''', N'''''') + N''''
                     + N' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','','
                     + N' ROWTERMINATOR = ''0x0a'', KEEPNULLS, TABLOCK);';
            EXEC sys.sp_executesql @sql;

            SET @sql = N'SELECT @r = COUNT(*) FROM ' + @tbl;
            EXEC sys.sp_executesql @sql, N'@r INT OUTPUT', @r = @rows OUTPUT;

            PRINT '>> ' + @tbl + ': ' + CAST(@rows AS NVARCHAR(20)) + ' rows loaded in '
                  + CAST(DATEDIFF(MILLISECOND, @start_time, SYSDATETIME()) AS NVARCHAR(20)) + ' ms';
            SET @i += 1;
        END;

        PRINT '================================================';
        PRINT 'Bronze load completed in '
              + CAST(DATEDIFF(SECOND, @batch_start, SYSDATETIME()) AS NVARCHAR(20)) + ' s';
        PRINT '================================================';
    END TRY
    BEGIN CATCH
        PRINT '================================================';
        PRINT 'ERROR DURING BRONZE LOAD (' + ISNULL(@tbl, N'?') + ')';
        PRINT 'Message: ' + ERROR_MESSAGE();
        PRINT 'Number : ' + CAST(ERROR_NUMBER() AS NVARCHAR(20));
        PRINT '================================================';
        THROW;
    END CATCH;
END;
GO
