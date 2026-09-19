# Backend Agent Guide

This folder contains the FastAPI backend for the Project Management MVP.

## Current Scope (Part 2)

- Provides a minimal scaffold to validate local Docker execution.
- Exposes:
- `GET /` returning temporary hello-world HTML.
- `GET /api/health` returning JSON service status.

## File Layout

- `app/main.py`: FastAPI app and routes.
- `tests/test_main.py`: route smoke tests with FastAPI TestClient.
- `pyproject.toml`: Python dependencies and dev dependencies.

## Runtime Approach

- Intended to run inside Docker.
- Uses `uv` in container to manage and execute dependencies.

## Next Planned Changes

- Part 3 will replace temporary HTML at `/` by serving the frontend build.
- Part 6 will add data persistence routes and DB initialization.