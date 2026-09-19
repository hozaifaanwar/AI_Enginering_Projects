$ErrorActionPreference = "Stop"

Write-Host "Starting PM MVP container..."
docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
	throw "docker compose up failed with exit code $LASTEXITCODE"
}
Write-Host "App should be available at http://localhost:8000"
