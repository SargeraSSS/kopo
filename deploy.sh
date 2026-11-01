#!/usr/bin/env bash
# Usage: ./deploy.sh          deploy the latest main
#        ./deploy.sh v1.2     roll back to a tag or commit
set -euo pipefail
cd "$(dirname "$0")"

./backup.sh
git fetch --tags origin
git checkout --detach "${1:-origin/main}"
docker compose -f docker-compose.yml up -d --build --wait
docker compose -f docker-compose.yml ps
