#!/usr/bin/env bash
# Runs the whole pipeline inside the Docker SQL Server container:
#   create DB -> bronze DDL/proc -> silver DDL/proc -> gold views -> load -> checks
# Prereq: cp .env.example .env ; docker compose up -d   (wait ~20s for startup)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

SQLCMD=/opt/mssql-tools18/bin/sqlcmd
run() {
  docker compose exec -T sqlserver "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b "$@"
}

for f in init_database bronze/ddl_bronze bronze/proc_load_bronze \
         silver/ddl_silver silver/proc_load_silver gold/ddl_gold; do
  echo "==> /scripts/$f.sql"
  run -i "/scripts/$f.sql"
done

echo "==> Loading bronze and silver"
run -d DataWarehouse -Q "EXEC bronze.load_bronze; EXEC silver.load_silver;"

echo "==> Quality checks (silver: expect empty result sets except DISTINCT lists)"
run -d DataWarehouse -i /tests/quality_checks_silver.sql
echo "==> Quality checks (gold)"
run -d DataWarehouse -i /tests/quality_checks_gold.sql
