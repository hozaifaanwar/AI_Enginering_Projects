# Code Review

Date: 2026-10-04. Scope: entire repo at commit `20edecf` (backend, frontend, Docker, scripts, tests, docs).

All test suites pass (backend 17, frontend unit 9, e2e 5, integrated e2e 2, lint clean). The findings below were found by reading the code and, where marked "Verified", reproduced with a script or against the running container.

## Summary

The MVP is functional and the structure is sound: a single FastAPI file, a Pydantic board model with integrity checks, a static Next.js export, and an optimistic-concurrency revision on the board. The main problems are:

1. Fast successive edits lose data (verified).
2. The AI chat endpoint holds a SQLite write lock for the full LLM call (verified).
3. Card editing, a stated business requirement, is not implemented.
4. The Docker image is polluted by host files and re-installs packages on every start (verified).
5. The AI path relies on a regex fallback that misfires instead of fixing the prompt and schema (verified).

## High

### H1. Rapid edits lose data (Verified)

`frontend/src/components/KanbanBoard.tsx:62-108`, `frontend/src/components/KanbanColumn.tsx:263-268`

Each change sends a full-board `PUT` with `boardRevisionRef.current` as the expected revision. When a second change is sent before the first response arrives, both requests carry the same revision, so the second gets a 409. The 409 handler then replaces local state with the server board, discarding the user's newer edits. Successful responses also call `setBoard(payload.board)`, overwriting any local edits made while the request was in flight. Column rename fires a `PUT` on every keystroke, so normal typing triggers this.

Evidence: against the Docker app, typing "Renamed Backlog" into the first column title produced PUT statuses `[200,200,200,409,409,200,200,200,200,200,200,409,200,409,409,200]`. The final title in both the UI and the DB was `"Remed Bakg"`.

Action:
- Serialize saves: allow one request in flight; when it completes, send the latest board if it changed.
- On success, update only the revision. Do not overwrite local board state with the response.
- Commit column renames on blur or Enter, not on every keystroke.

### H2. AI chat holds a SQLite write lock during the LLM call (Verified)

`backend/app/main.py:804-836`, `backend/app/main.py:275-302`

`ai_chat` opens a connection and calls `load_board`, which calls `ensure_user_and_board`. That runs `INSERT OR IGNORE INTO users`, and Python's sqlite3 opens an implicit write transaction for it, even when the row already exists. The connection stays open while `request_openrouter_kanban_response` waits up to 45 seconds. Any board save from the UI during that time blocks and then fails with `database is locked` after sqlite's 5-second default timeout. The frontend shows that failure as "Working locally".

Evidence: a script that runs `INSERT OR IGNORE` on an existing user without committing printed `in_transaction: True`. A second connection's `UPDATE` then failed with `database is locked`.

Action:
- In `ai_chat`, load the board and close the connection, call the LLM, then open a new connection to apply the operations and save with the revision check.
- Make reads not write: create the user and board once (at startup for the MVP user) instead of inside every `load_board` and `save_board`.

### H3. Card editing is not implemented

AGENTS.md: "The cards on the Kanban board can be moved with drag and drop, and edited". `KanbanCard.tsx` only supports delete. Only the AI path can edit a card (`update_card`).

Action: add inline editing of title and details to `KanbanCard`, saved through the same save path as other edits. Add unit and e2e coverage.

### H4. The Docker image copies host files and re-installs packages on every start (Verified)

`Dockerfile`, no `.dockerignore`

`COPY frontend .` copies host `node_modules` and `.next` over the `npm ci` result. `COPY backend backend` copies the host's Windows `.venv` over the one built by `uv sync`. `uv.lock` is never copied, so builds are not reproducible. At runtime `uv run` re-syncs the environment, including the dev group, because `--no-dev` is not passed.

Evidence:
- In the built image, `/app/backend/.venv` contains `Scripts` and `Lib` (Windows layout).
- Its `pyvenv.cfg` contains `home = C:\Users\USER\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none`.
- Running `uv run` in the image printed `Downloading pygments ... Installed 5 packages`.

Action:
- Add `.dockerignore` excluding `**/node_modules`, `**/.next`, `frontend/out`, `**/.venv`, `backend/data`, `frontend/test-results`, `.env`, `.git`.
- Install uv with `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv`.
- Copy `pyproject.toml` and `uv.lock`, then run `uv sync --locked --no-dev`.
- Run with `uv run --no-sync` (or `.venv/bin/uvicorn`) so nothing is installed at startup.

### H5. The AI regex fallback misfires; the real cause is an underspecified prompt and schema (Verified)

`backend/app/main.py:593-642`, `backend/app/main.py:655-708`

The system prompt never tells the model the operation field names, and the JSON schema only constrains `type` (`additionalProperties: True`). The model therefore often returns operations the normalizer drops, and `infer_operations_from_message` was added to cover for that. The fallback scans the whole message for keywords and acts even when the model chose not to.

Evidence:
- `"Add a card titled 'Progress report' to Review"` produces `add_card` into `col-progress`, the wrong column.
- `"Should I add a card titled 'X' to done? Don't do it yet."` still produces an `add_card`.

Action:
- Delete `infer_column_id_from_message` and `infer_operations_from_message`, and their test.
- Give the schema a full definition for each operation (an `anyOf` with required fields), and list the operation types and fields in the system prompt.
- Validate the model output directly with `AIChatLLMOutput.model_validate`, and drop the snake_case and key-alias handling in `normalize_operation` and `normalize_chat_output`. This is unneeded defensive code once the schema is strict.

## Medium

### M1. Username is taken from the request, not from auth

`backend/app/main.py:63-66, 113-116, 133-137, 762`

`enforce_demo_auth` checks the headers, but every route then uses `username` from the request body or query string. Any authenticated caller can read or overwrite any user's board, and `GET /api/board?username=anything` creates a new user row.

Action: have the auth dependency return the username, use that value in the routes, and remove `username` from the request models and the query string.

### M2. Invalid AI operations fail the whole chat with a misleading error

`backend/app/main.py:356-425`, `KanbanBoard.tsx:152-160`

If the model references a card or column that doesn't exist, `apply_operation` raises 404, the endpoint returns 404, and the UI says "I could not reach the AI service right now". The user's request is lost and the reason is hidden.

Action: return 502 with the detail for operation failures from the AI path, and show the server's `detail` in the sidebar.

### M3. Side effects inside state updaters

`KanbanBoard.tsx:214-275`

`persistBoard` is called inside `setBoard(prev => ...)` updaters. Updaters must be pure; React StrictMode (on by default in Next dev) calls them twice, which sends duplicate PUTs in development.

Action: compute the next board, call `setBoard(next)`, then save. The save queue from H1 fixes this naturally.

### M4. Chat uses a stale revision while a save is in flight

`KanbanBoard.tsx:123-126`

The chat sends the current revision. If a board save is still pending, the server revision moves on and the AI save returns 409, shown as "AI request failed". This has the same root cause as H1 and is fixed by the same change: wait for pending saves before sending the chat.

### M5. The fake "working locally" mode hides failures

`KanbanBoard.tsx:187-191`, `frontend/src/lib/kanban.ts:18-72`

When the load fails, the frontend silently shows its own seed board (a duplicate of `DEFAULT_BOARD` in the backend) and lets the user edit it. Those edits are never saved; once the backend returns, the first save gets a 409 and the edits are discarded.

Action: show a load error with a retry instead, and remove `initialData` from the frontend (except as test data).

### M6. Duplicate OpenRouter client code

`backend/app/main.py:428-474` and `645-742` repeat the key lookup, headers, POST, error mapping and content extraction.

Action: extract one `call_openrouter(messages, response_format=None) -> str` helper.

### M7. Frontend tests do not exercise the API

In Vitest, `fetch("/api/board")` fails on the relative URL, so every unit test runs the "working locally" offline path. Nothing tests the save requests, revision handling, 409 recovery, or rapid edits. The e2e test "handles chat errors" passes only because the dev server has no `/api`.

Action: mock `fetch` in the unit tests and assert request bodies and revisions. Add tests for save serialization (H1) and card editing (H3).

### M8. Documentation is out of date

- `docs/DATABASE_SCHEMA.md` lacks the `revision` column and the 409 behavior.
- `backend/AGENTS.md` and `scripts/AGENTS.md` describe Part 2 only.
- `frontend/AGENTS.md` says the board is in-memory and not persisted.
- In `docs/PLAN.md`, Gate A (plan approval) and Gate B (schema sign-off) are still unchecked although all parts are implemented.

Action: update the docs to match the code, and record or tick the approvals.

## Low

### L1. Ignore rules

- The `.gitignore` entry `.github\instructions\codacy.instructions.md` uses backslashes and matches nothing, so the file was committed. Use forward slashes and `git rm --cached` if it should stay local.
- `frontend/test-results/` is tracked. Ignore it and untrack it.
- `backend/data/` (the local SQLite file) and `frontend/out/` are not ignored.

### L2. Test tooling

- Backend tests only import `app` when run as `python -m pytest`. Add `[tool.pytest.ini_options] pythonpath = ["."]` to `backend/pyproject.toml` so `uv run pytest` works.
- Starlette warns that using `httpx` with `TestClient` is deprecated. Follow its suggestion when upgrading.

### L3. Unnecessary defensive code

Per the coding standards, remove:
- `typeof window === "undefined"` inside `useEffect` and `typeof fetch !== "function"` in `KanbanBoard.tsx`
- the `cardsById` `useMemo`, which just aliases `board.cards`
- the `RuntimeError` checks after selects that cannot return nothing (`main.py:284, 311, 351`)
- the `if data.get("choices")` guards

### L4. Chat history hygiene

On failure the frontend appends a canned assistant message ("I could not reach the AI service right now"), which is then sent to the model as real history. The initial greeting is sent too. History is unbounded and fully client-controlled.

Action: show the error without adding a fake message, skip the greeting, and cap the history length on the server.

### L5. Empty titles accepted

Clearing a column title saves `""`, and the backend accepts empty card and column titles.

Action: add `Field(min_length=1)` on the titles in the models.

### L6. Versions

The image uses Python 3.12 while newer stable versions exist, and `@types/node` is `^20` while the build uses Node 22. Align these with "latest versions" in AGENTS.md.

### L7. Auth is cosmetic

The credentials are hardcoded in the client bundle and sent on every request, and the login flag lives in `localStorage`. This is acceptable for the MVP as documented, but it should not be mistaken for security.

## Action Checklist

In priority order:

- [x] H1: Serialize board saves, stop overwriting local state from responses, and commit renames on blur or Enter
- [x] H2: Release the DB connection before the LLM call; move user and board creation out of the read path
- [x] H3: Implement card editing (UI plus tests)
- [x] H4: Add `.dockerignore`; use `uv.lock` with `--locked --no-dev`; run with `--no-sync`
- [x] H5: Delete the regex fallback; define full operation schemas in the prompt and response format; drop the normalizers
- [x] M1: Derive the username from the auth dependency only
- [x] M2: Return 502 with detail for invalid AI operations and surface it in the UI
- [x] M3/M4: Move saves out of state updaters; wait for pending saves before chat
- [x] M5: Replace the offline fallback with a load error and retry; remove the frontend seed data
- [x] M6: Extract a single OpenRouter call helper
- [x] M7: Mock `fetch` in unit tests; cover saves, 409 handling and editing
- [x] M8: Update `DATABASE_SCHEMA.md` and the `AGENTS.md` files (the PLAN approval gates still need explicit user sign-off)
- [x] L1-L6: Ignore rules, pytest config, defensive code cleanup, chat history, title validation, versions (L7 is a documented MVP limitation, no action)

## Remediation Notes (2026-10-04)

- H1: `KanbanBoard.tsx` uses a one-at-a-time save queue and updates only the revision from save responses. Column titles save on blur or Enter. Regression tests: the unit test "sends edits made during a save..." and the integrated test "keeps a quickly typed column rename intact".
- H2: `ai_chat` loads the board, closes the connection, calls the LLM, then applies the operations to the latest board in a new transaction. The user and board are seeded at startup; reads never write. Regression test: `test_ai_chat_does_not_lock_db_and_keeps_concurrent_edits`.
- H3: `KanbanCard` has inline Edit (title and details). Drag attributes are removed while editing, because dnd-kit's `aria-disabled` otherwise disables the form inputs.
- H3 follow-up: card titles with long unbroken words overflowed the narrow (156px) columns and covered the next column's buttons. The Edit and Remove buttons now sit on a row below the text, and the text wraps (`wrap-anywhere`).
- H4: Added `.dockerignore`, uv copied from its image, `uv sync --locked --no-dev`, and `uv run --no-sync`. Verified: build context 256 KB, and the image venv is Linux-only with nothing installed at startup.
- H5: Full per-operation strict schema and a system prompt that lists the operations. Output is validated directly with `AIChatLLMOutput`. The regex fallback and normalizers are removed.
- H5 follow-up: a probe of 30 live calls found schema violations only from the DeepInfra provider (3 of 5 calls returned prose instead of schema JSON). The other providers returned valid output on all 25 of their calls. DeepInfra is now excluded via OpenRouter provider preferences.
- The integrated AI test uses a short title: the model rewrote a 13-digit title as "AI Integrated 1793...".

## Cleanup Notes (2026-10-06)

- L1: `.gitignore` uses forward slashes and ignores `frontend/test-results/`, `frontend/playwright-report/` and `backend/data/`. The Codacy instructions file and test results are untracked.
- L2: `pythonpath = ["."]` in `backend/pyproject.toml`, so `uv run pytest` works. The Starlette `httpx` deprecation warning remains; it comes from the test client dependency, not app code.
- L3: Removed the unreachable "Unknown operation type" branch. The board logic raises `ValueError`, which routes map to 404 (operations endpoint) or 502 (AI chat).
- L4: The chat greeting is display only and is not sent as history. The server sends at most the last 20 history messages.
- L5: Column and card titles require at least one character.
- L6: Python 3.14 (Dockerfile, `requires-python`, `uv.lock`); `@types/node` ^22 to match Node 22. The vitest globals are now declared, so `tsc --noEmit` reports 0 errors.
- `main.py`: 4-space indentation, a `match` statement for operations, the seed board moved to `app/default_board.json`, the model fixed as `OPENROUTER_MODEL` per AGENTS.md, the old `revision` migration removed, and `ruff check` clean.
