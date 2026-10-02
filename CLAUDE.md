# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `AGENTS.md` (business requirements, tech decisions, color scheme, coding standards) and `docs/PLAN.md` (phased execution plan with approval gates) before making changes. Key standards from AGENTS.md: keep it simple, no over-engineering or unnecessary defensive code, no extra features, minimal README, never use emojis, and always prove root cause with evidence before fixing an issue. Planning docs live in `docs/`.

## Commands

Full stack (Docker, serves everything at http://localhost:8000):
- Start: `scripts/start.sh` | `scripts/start.ps1` | `scripts/start.bat` (runs `docker compose up --build -d`)
- Stop: `scripts/stop.sh` | `scripts/stop.ps1` | `scripts/stop.bat`

Backend (run from `backend/`, uses `uv`):
- All tests: `uv run python -m pytest -q` (use `python -m` so `app` is importable from cwd)
- Single test: `uv run python -m pytest tests/test_main.py::test_health_route`

Frontend (run from `frontend/`):
- Dev server: `npm run dev` (frontend only; `/api` calls have no backend unless one is proxied)
- Build: `npm run build` (static export to `frontend/out`)
- Lint: `npm run lint`
- Unit tests (Vitest): `npm run test:unit`; single file: `npx vitest run src/lib/kanban.test.ts`; by name: `npx vitest run -t "name"`
- E2E (Playwright, auto-starts dev server on :3000): `npm run test:e2e`
- Integrated E2E (`*.integrated.spec.ts`, against the running Docker stack on :8000, start it first): `npm run test:e2e:integrated`

## Architecture

Single Docker container: a multi-stage `Dockerfile` builds the Next.js app as a static export (`output: "export"`), then copies `frontend/out` into a Python 3.12 image where FastAPI (via uvicorn, deps managed by uv) serves both `/api/*` and the static site mounted at `/`. If the static build directory is missing, `/` returns a placeholder HTML page instead.

Backend is essentially all in `backend/app/main.py`:
- `create_app(db_path, frontend_dist)` is an app factory; tests call it with a temp SQLite path and a nonexistent frontend dir. Module-level `app = create_app()` is what uvicorn runs.
- Persistence: SQLite at `PM_DB_PATH` (default `backend/data/pm.sqlite`, a named Docker volume in compose). Tables `users` and `boards`; each user has one board stored as a single JSON blob (`board_json`) with an integer `revision` used for optimistic concurrency on writes. The DB and default seeded board are created on startup/first access. Schema rationale is in `docs/DATABASE_SCHEMA.md`.
- Board shape (`BoardDataModel`): `columns` (ordered list with `id`, `title`, `cardIds`) plus a `cards` map keyed by id. Mutations go through typed operations (rename column, add/update/delete/move card) applied by `apply_operation`, then re-validated before saving.
- Auth is MVP-only: every `/api` route except health depends on `enforce_demo_auth`, which checks `X-Demo-User: user` / `X-Demo-Password: password` headers. The frontend stores signed-in state in `localStorage` and sends these headers.
- AI: `/api/ai/chat` sends the current board, user message, and history to OpenRouter (`OPENROUTER_API_KEY` from root `.env`, model `OPENROUTER_MODEL` defaulting to `openai/gpt-oss-120b`), parses/normalizes the JSON reply into `assistantResponse` + `operations`, falls back to inferring operations from the message text if the model returns none, applies them, and returns the updated board. `/api/ai/ping` is a connectivity check.

Frontend (`frontend/src`): `KanbanBoard.tsx` is the stateful root (login gate, board loading/saving via `fetch` to `/api`, drag-and-drop with dnd-kit, and the `AIChatSidebar` wiring); other components are presentational. `src/lib/kanban.ts` holds board types and the card-move algorithm. Preserve existing accessibility labels and `data-testid` attributes, which the tests rely on. Colors are CSS variables in `src/app/globals.css` matching the AGENTS.md palette.
