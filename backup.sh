#!/usr/bin/env bash
# Dump the database into backups/ and keep the last 14 days.
set -euo pipefail
cd "$(dirname "$0")"

umask 077
mkdir -p backups
docker compose -f docker-compose.yml exec -T db \
    sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip > "backups/fintrack-$(date +%F-%H%M).sql.gz"
find backups -name 'fintrack-*.sql.gz' -mtime +14 -delete
