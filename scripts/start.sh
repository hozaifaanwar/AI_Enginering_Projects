#!/usr/bin/env bash
set -euo pipefail

echo "Starting PM MVP container..."
docker compose up --build -d
echo "App should be available at http://localhost:8000"
