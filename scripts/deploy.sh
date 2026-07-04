#!/usr/bin/env bash
# Redeploy flow for an already-configured production server (`.env` filled
# in, certs already issued — see README's Deploy section for first-time
# setup): pull latest code, rebuild images, migrate, restart.
#
# Migrations run as part of `up` itself — the `migrations` service's
# command is `alembic upgrade head`, and bot/api both `depends_on` it with
# `condition: service_completed_successfully`, so compose always runs it
# to completion before (re)starting them.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "==> git pull"
git pull --ff-only

echo "==> build + migrate + restart"
"${COMPOSE[@]}" up -d --build --remove-orphans

echo "==> pruning old images"
docker image prune -f

echo "deploy complete"
