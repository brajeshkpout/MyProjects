# Data Catalog — Gold Layer

## gold.dim_customers
| Column | Type | Description |
|--------|------|-------------|
| customer_key | BIGINT | Surrogate key (`ROW_NUMBER`) |
| customer_id | INT | CRM customer id |
| customer_number | NVARCHAR(50) | Business key, e.g. `AW00011000` (joins CRM ↔ ERP) |
| first_name / last_name | NVARCHAR(50) | Trimmed names |
| country | NVARCHAR(50) | From ERP `loc_a101`; `n/a` if unknown |
| marital_status | NVARCHAR(50) | Single / Married / n/a |
| gender | NVARCHAR(50) | Male / Female / n/a — CRM first, ERP as fallback |
| birthdate | DATE | From ERP `cust_az12`; NULL if invalid (future) |
| create_date | DATE | Customer creation date in CRM |

## gold.dim_products
| Column | Type | Description |
|--------|------|-------------|
| product_key | BIGINT | Surrogate key |
| product_id | INT | CRM product version id |
| product_number | NVARCHAR(50) | Business key, e.g. `FR-R92B-58` (joins to sales) |
| product_name | NVARCHAR(100) | Product name |
| category_id | NVARCHAR(50) | e.g. `CO_RF` |
| category / subcategory | NVARCHAR(50) | From ERP `px_cat_g1v2` |
| maintenance | NVARCHAR(50) | Yes / No |
| cost | INT | Base cost (NULL in source → 0) |
| product_line | NVARCHAR(50) | Mountain / Road / Touring / Other Sales / n/a |
| start_date | DATE | Start of the current version |

## gold.fact_sales
| Column | Type | Description |
|--------|------|-------------|
| order_number | NVARCHAR(50) | Sales order id (one order → many lines) |
| product_key | BIGINT | FK → dim_products |
| customer_key | BIGINT | FK → dim_customers |
| order_date / shipping_date / due_date | DATE | NULL when the source value was invalid |
| sales_amount | INT | quantity × price (repaired where the source was inconsistent) |
| quantity | INT | Units sold |
| price | INT | Unit price |
