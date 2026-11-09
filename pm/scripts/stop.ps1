$ErrorActionPreference = "Stop"

Write-Host "Stopping PM MVP container..."
docker compose down --remove-orphans
if ($LASTEXITCODE -ne 0) {
	throw "docker compose down failed with exit code $LASTEXITCODE"
}
