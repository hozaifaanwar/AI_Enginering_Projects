# Scripts Agent Guide

Start and stop scripts for each OS. All run from the repository root and call `docker compose`.

- Windows PowerShell: `start.ps1`, `stop.ps1`
- Windows CMD: `start.bat`, `stop.bat`
- macOS/Linux: `start.sh`, `stop.sh`

Start builds and launches the container in detached mode (app at http://localhost:8000). Stop removes the container; the SQLite data persists in the `pm_data` volume. To reset the data, run `docker compose down -v`.
