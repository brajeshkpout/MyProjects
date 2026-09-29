# Naming Conventions

- **Style:** `snake_case`, English, no reserved words.
- **Schemas:** `bronze`, `silver`, `gold`.
- **Bronze / Silver tables:** `<source>_<entity>` keeping the source names, e.g. `crm_cust_info`, `erp_loc_a101`. Column names are kept as in the source.
- **Gold views:** `<category>_<entity>` with business-friendly names — `dim_` for dimensions, `fact_` for facts.
- **Surrogate keys:** `<entity>_key` (e.g. `customer_key`).
- **Technical columns:** `dwh_<name>` (e.g. `dwh_create_date`).
- **Stored procedures:** `load_<layer>` in the layer's schema (`bronze.load_bronze`, `silver.load_silver`).
- **Unknown values:** the string `n/a` for missing categorical data; NULL for missing dates / numbers.
