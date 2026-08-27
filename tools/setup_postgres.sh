#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
db_role="${EVA_DB_ROLE:-$(id -un)}"

echo "Creating local PostgreSQL role '${db_role}', database 'eva', and pgvector extension."
sudo -u postgres psql --set="role=${db_role}" --file deployment/postgres/bootstrap.sql
echo "PostgreSQL bootstrap complete."
