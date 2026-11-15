#!/bin/bash
# Creates the runtime login roles on first start of the local PostgreSQL container.
# The container's POSTGRES_USER is the schema owner that runs migrations.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$APP_DB_PASSWORD" \
  -v admin_password="$ADMIN_DB_PASSWORD" <<'SQL'
CREATE ROLE app_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
  PASSWORD :'app_password';
CREATE ROLE admin_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
  PASSWORD :'admin_password';
SQL
