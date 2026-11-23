#!/usr/bin/env sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"

compose_project_name=${LTC_COMPOSE_PROJECT_NAME:-ltc-v36}
docker compose -p "$compose_project_name" --profile tools run --rm database-init
