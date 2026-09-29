/*
===============================================================================
Create Database and Schemas
===============================================================================
Purpose:
    Drops and recreates the 'DataWarehouse' database, then creates the three
    medallion schemas: bronze, silver, gold.

WARNING:
    If the 'DataWarehouse' database exists it is DROPPED with all its data.
    Only run this against a development instance.
===============================================================================
*/

USE master;
GO

IF EXISTS (SELECT 1 FROM sys.databases WHERE name = 'DataWarehouse')
BEGIN
    ALTER DATABASE DataWarehouse SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE DataWarehouse;
END;
GO

CREATE DATABASE DataWarehouse;
GO

USE DataWarehouse;
GO

CREATE SCHEMA bronze;
GO
CREATE SCHEMA silver;
GO
CREATE SCHEMA gold;
GO
