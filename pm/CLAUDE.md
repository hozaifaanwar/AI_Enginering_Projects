# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `AGENTS.md` (business requirements, tech decisions, color scheme, coding standards) and `docs/PLAN.md` (phased execution plan with approval gates) before making changes. Key standards from AGENTS.md: keep it simple, no over-engineering or unnecessary defensive code, no extra features, minimal README, never use emojis, and always prove root cause with evidence before fixing an issue. Planning docs live in `docs/`.

## Commands

Full stack (Docker, serves everything at http://localhost:8000):
- Start: `scripts/start.sh` | `scripts/start.ps1` | `scripts/start.bat` (runs `docker compose up --build -d`)
- Stop: `scripts/stop.sh` | `scripts/stop.ps1` | `scripts/stop.bat`

Backend (run from `backend/`, uses `uv`):
- All tests: `uv run pytest -q`
- Single test: `uv run pytest tests/test_main.py::test_health_route`
- Lint: `uvx ruff check app tests`

Frontend (run from `frontend/`):
- Dev server: `npm run dev` (frontend only; `/api` calls have no backend unless one is proxied)
- Build: `npm run build` (static export to `frontend/out`)
- Lint: `npm run lint`
- Unit tests (Vitest): `npm run test:unit`; single file: `npx vitest run src/lib/kanban.test.ts`; by name: `npx vitest run -t "name"`
- E2E (Playwright, auto-starts dev server on :3000): `npm run test:e2e`
- Integrated E2E (`*.integrated.spec.ts`, against the running Docker stack on :8000, start it first): `npm run test:e2e:integrated`

## Architecture

Single Docker container: a multi-stage `Dockerfile` builds the Next.js app as a static export (`output: "export"`), then copies `frontend/out` into a Python 3.14 image where FastAPI (via uvicorn, deps managed by uv) serves both `/api/*` and the static site mounted at `/`. If the static build directory is missing, `/` returns a placeholder HTML page instead.

Backend is essentially all in `backend/app/main.py`:
- `create_app(db_path, frontend_dist)` is an app factory; tests call it with a temp SQLite path and a nonexistent frontend dir. Module-level `app = create_app()` is what uvicorn runs.
- Persistence: SQLite at `PM_DB_PATH` (default `backend/data/pm.sqlite`, a named Docker volume in compose; seed board in `backend/app/default_board.json`). Tables `users` and `boards`; each user has one board stored as a single JSON blob (`board_json`) with an integer `revision` used for optimistic concurrency on writes. The DB and the MVP user's seeded board are created on startup; read paths never write. Schema rationale is in `docs/DATABASE_SCHEMA.md`.
- Board shape (`BoardDataModel`): `columns` (ordered list with `id`, `title`, `cardIds`) plus a `cards` map keyed by id. Mutations go through typed operations (rename column, add/update/delete/move card) applied by `apply_operation`, then re-validated before saving.
- Auth is MVP-only: every `/api` route except health depends on `current_user`, which checks `X-Demo-User: user` / `X-Demo-Password: password` headers and returns the username; routes never take a username from the request. The frontend stores signed-in state in `localStorage` and sends these headers.
- AI: `/api/ai/chat` sends the current board, user message, and recent history (last 20 messages) to OpenRouter (`OPENROUTER_API_KEY` from root `.env`, model `openai/gpt-oss-120b`) with a strict per-operation JSON schema (`KANBAN_RESPONSE_FORMAT`), validates the reply with `AIChatLLMOutput`, then applies the operations to the latest board. No DB connection is held during the LLM call. Invalid output or operations return 502. DeepInfra is excluded from routing because it ignores the schema. `/api/ai/ping` is a connectivity check.

Frontend (`frontend/src`): `KanbanBoard.tsx` is the stateful root (login gate, board loading via `fetch` to `/api`, a one-at-a-time save queue carrying the board `revision`, drag-and-drop with dnd-kit, and the `AIChatSidebar` wiring); other components are presentational. Column titles save on blur or Enter; cards edit inline. There is no offline mode: a failed load shows a Retry button. Unit tests use `src/test/fakeApi.ts`, and dev-server e2e tests mock the API with `tests/mockBackend.ts`. `src/lib/kanban.ts` holds board types and the card-move algorithm. Preserve existing accessibility labels and `data-testid` attributes, which the tests rely on. Colors are CSS variables in `src/app/globals.css` matching the AGENTS.md palette.
