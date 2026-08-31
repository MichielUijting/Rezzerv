#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${REZZERV_POSTGRES_MIGRATION_USER:?REZZERV_POSTGRES_MIGRATION_USER is required}"
: "${REZZERV_POSTGRES_MIGRATION_PASSWORD:?REZZERV_POSTGRES_MIGRATION_PASSWORD is required}"
: "${REZZERV_POSTGRES_RUNTIME_USER:?REZZERV_POSTGRES_RUNTIME_USER is required}"
: "${REZZERV_POSTGRES_RUNTIME_PASSWORD:?REZZERV_POSTGRES_RUNTIME_PASSWORD is required}"

case "$REZZERV_POSTGRES_MIGRATION_USER" in
  *[!A-Za-z0-9_]*|'')
    echo "Invalid REZZERV_POSTGRES_MIGRATION_USER" >&2
    exit 20
    ;;
esac
case "$REZZERV_POSTGRES_RUNTIME_USER" in
  *[!A-Za-z0-9_]*|'')
    echo "Invalid REZZERV_POSTGRES_RUNTIME_USER" >&2
    exit 21
    ;;
esac

if [ "$POSTGRES_USER" = "$REZZERV_POSTGRES_MIGRATION_USER" ] || \
   [ "$POSTGRES_USER" = "$REZZERV_POSTGRES_RUNTIME_USER" ] || \
   [ "$REZZERV_POSTGRES_MIGRATION_USER" = "$REZZERV_POSTGRES_RUNTIME_USER" ]; then
  echo "PostgreSQL bootstrap, migration and runtime roles must be distinct" >&2
  exit 22
fi

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=db_name="$POSTGRES_DB" \
  --set=migration_user="$REZZERV_POSTGRES_MIGRATION_USER" \
  --set=migration_password="$REZZERV_POSTGRES_MIGRATION_PASSWORD" \
  --set=runtime_user="$REZZERV_POSTGRES_RUNTIME_USER" \
  --set=runtime_password="$REZZERV_POSTGRES_RUNTIME_PASSWORD" <<'SQL'
CREATE ROLE :"migration_user" LOGIN PASSWORD :'migration_password';
CREATE ROLE :"runtime_user" LOGIN PASSWORD :'runtime_password';

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO :"migration_user", :"runtime_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"migration_user";
GRANT USAGE ON SCHEMA public TO :"runtime_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"runtime_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"runtime_user";
SQL

echo "REZZERV_POSTGRES_SPLIT_ROLES_INITIALIZED"
