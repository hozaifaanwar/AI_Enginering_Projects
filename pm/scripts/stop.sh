#!/usr/bin/env bash
set -euo pipefail

echo "Stopping PM MVP container..."
docker compose down --remove-orphans
