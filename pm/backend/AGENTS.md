# Backend Agent Guide

FastAPI backend for the Project Management MVP. Everything lives in `app/main.py`.

## Routes

- `GET /api/health`: status payload (no auth).
- `GET /api/board`, `PUT /api/board`: read or replace the board. Writes take the client's last `revision`; a mismatch returns 409.
- `POST /api/board/operations`: apply typed operations (rename column, add/update/delete/move card).
- `POST /api/ai/chat`: send the board, message and history to OpenRouter, apply the returned operations, and return the reply plus the updated board.
- `POST /api/ai/ping`: OpenRouter connectivity check.
- `/`: the static frontend build (`/app/frontend/out`), or a placeholder page if it is missing.

## Key Behavior

- Auth: `current_user` checks the `X-Demo-User` / `X-Demo-Password` headers and returns the username. Routes use only that username.
- Persistence: SQLite at `PM_DB_PATH` (default `backend/data/pm.sqlite`). The MVP user and board are seeded at startup. See `docs/DATABASE_SCHEMA.md`.
- AI: structured output via a strict JSON schema with one definition per operation. The output is validated with `AIChatLLMOutput`; invalid output or operations return 502. Requests route only to providers that honor `response_format`. DeepInfra is excluded because it often ignores the schema.
- No DB connection is held during the LLM call.

## Commands

Run from `backend/`:

- Tests: `uv run pytest -q`
- Single test: `uv run pytest tests/test_main.py::test_health_route`
- Lint: `uvx ruff check app tests`
