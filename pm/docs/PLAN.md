# Project Plan

This document is the execution plan for the MVP described in [AGENTS.md](../AGENTS.md).

## Working Agreements

- Keep scope to MVP only.
- Prioritize simple, explicit implementations over abstractions.
- Use root-cause debugging before any fix.
- Prefer tests that validate behavior (not implementation details).
- Pause at explicit approval gates before continuing.

## Part 1: Planning And Baseline Documentation

### Checklist

- [x] Expand this plan into detailed, testable phases.
- [x] Create frontend-specific implementation notes in `frontend/AGENTS.md`.
- [ ] Get user approval on this plan before Part 2.

### Tests

- Manual review that each part has: scope, implementation checklist, tests, and success criteria.

### Success Criteria

- Plan is approved by the user.
- Team can execute each part without ambiguous requirements.

## Part 2: Scaffolding (Docker + FastAPI + Scripts)

### Checklist

- [x] Create backend app skeleton in `backend/` using FastAPI.
- [x] Add container configuration to run app locally in Docker.
- [x] Add start and stop scripts for Windows, macOS, and Linux in `scripts/`.
- [x] Implement minimal backend route(s):
- [x] `GET /` returns simple hello-world HTML (temporary for scaffolding validation).
- [x] `GET /api/health` (or equivalent) returns JSON status payload.
- [x] Document how to run locally with scripts.

### Tests

- [x] Script-level smoke test: start stack, wait for server readiness, stop stack.
- [x] API test: verify JSON health response shape and status code.
- [x] Browser/manual check: root route displays hello-world content from backend container.

### Success Criteria

- Single command per OS starts and stops the app reliably.
- Running container serves HTML and API response locally.

## Part 3: Serve Existing Frontend Through Backend

### Checklist

- [x] Configure frontend build output for production serving.
- [x] Update backend so `/` serves the built frontend app.
- [x] Ensure static assets are served correctly by backend.
- [x] Remove temporary hello-world root behavior from Part 2.

### Tests

- Frontend unit tests pass (`npm run test:unit` in `frontend/`).
- Frontend integration/e2e tests pass against served app (`npm run test:e2e`).
- Container smoke test confirms board renders at `/` with five columns.

### Success Criteria

- Deployed local container shows the current Kanban UI at root route.
- No broken asset paths in production mode.

## Part 4: Fake Sign-In Flow

### Checklist

- [x] Add login screen at first visit to `/`.
- [x] Validate hardcoded credentials (`user` / `password`).
- [x] Store authenticated session state (MVP-safe local approach).
- [x] Add logout action that clears session and returns to login.
- [x] Protect board route so unauthenticated users cannot access it.

### Tests

- [x] Unit tests for authentication state transitions (login success/failure/logout).
- [x] Integration tests for route protection and redirect behavior.
- [x] E2E test: login -> access board -> logout -> blocked from board.

### Success Criteria

- [x] User must sign in to access the board.
- [x] Invalid credentials do not grant access.
- [x] Logout always returns app to signed-out state.

## Part 5: Database Modeling (Design + Sign-Off Only)

### Checklist

- [x] Propose SQLite schema for users, board, columns, cards, and ordering.
- [x] Define JSON representation for board payload persistence and transport.
- [x] Document migrations/initialization strategy (db created if missing).
- [x] Document tradeoffs and rationale in `docs/`.
- [ ] Get explicit user sign-off on schema design.
- [x] Do not implement persistence code in this part.

### Tests

- Design review checklist:
- User-to-board relationship supports one board per user today.
- Schema can extend to multiple boards per user later.
- Card ordering and column ordering are deterministic.

### Success Criteria

- [ ] Signed-off design artifact exists in docs.
- [x] Backend implementation work starts only in Part 6.

## Part 6: Backend CRUD APIs + Persistence

### Checklist

- [x] Implement DB initialization at startup (create db if missing).
- [x] Implement API routes to read board for authenticated user.
- [x] Implement API routes to mutate board data (rename column, create/edit/move/delete card).
- [x] Validate payloads with explicit request/response models.
- [x] Keep API operations deterministic and idempotent where appropriate.

### Tests

- [x] Backend unit tests for domain operations.
- [x] API tests for route behavior and validation errors.
- [x] Persistence tests confirming changes survive server restart.

### Success Criteria

- [x] Backend can fully represent and mutate board state for one user.
- [x] DB file is created automatically when absent.

## Part 7: Frontend Integration With Backend

### Checklist

- [x] Replace local in-memory board initialization with API-driven state.
- [x] Wire board actions to backend mutations.
- [x] Add loading, optimistic update (if used), and error recovery behavior.
- [x] Keep UX parity with existing drag/drop and editing flow.

### Tests

- [x] Frontend unit tests for API adapters/state transitions.
- [x] Integration tests with mocked backend errors and retries.
- [x] E2E tests for full flow: login, load board, mutate cards, reload, verify persistence.

### Success Criteria

- [x] Board state persists and reloads from backend.
- [x] Core interactions remain stable under normal and error cases.

## Part 8: OpenRouter Connectivity

### Checklist

- [x] Add backend OpenRouter client using `OPENROUTER_API_KEY` from root `.env`.
- [x] Add simple diagnostic route/service call using configured model.
- [x] Implement connectivity check prompt (`2+2`) and parse response.
- [x] Add error handling for missing key, timeouts, and upstream failures.

### Tests

- [x] Unit tests for client wrapper behavior.
- [x] Integration test for success path (with controlled stub/mock where needed).
- [x] Manual or gated live check for real API key path.

### Success Criteria

- [x] Backend can successfully call OpenRouter with configured model.
- [x] Failures produce actionable and safe error responses.

## Part 9: Structured AI Updates For Kanban

### Checklist

- [x] Define structured output schema containing:
- [x] Assistant text response.
- [x] Optional board mutation operation(s).
- [x] Include board JSON + user message + conversation history in prompt.
- [x] Validate LLM output strictly against schema before applying.
- [x] Apply mutation atomically and persist to DB.
- [x] Return updated board and assistant response to frontend.

### Tests

- [x] Unit tests for schema validation and mutation mapping.
- [x] Integration tests for:
- valid response with no board change,
- valid response with board change,
- invalid/malformed response rejected safely.
- [x] Regression tests for idempotent handling of duplicate requests (if retry policy used).

### Success Criteria

- [x] AI can reply conversationally and optionally update board safely.
- [x] Invalid AI output never corrupts persisted state.

## Part 10: AI Sidebar UI + Live Board Refresh

### Checklist

- [x] Build sidebar chat UI integrated into board page.
- [x] Send chat messages to backend AI endpoint with conversation history.
- [x] Render assistant responses and loading/error states.
- [x] If backend returns board mutation, refresh board state automatically.
- [x] Ensure responsive layout on desktop and mobile.

### Tests

- [x] Component tests for sidebar interactions and rendering states.
- [x] Integration tests for chat request/response flow.
- [x] E2E tests for end-to-end AI-assisted board updates.

### Success Criteria

- [x] User can chat with AI from sidebar while using board.
- [x] AI-triggered updates appear in UI without manual refresh.
- [x] Experience remains stable across viewport sizes.

## Approval Gates

- Gate A (required): approve Part 1 plan before Part 2 implementation.
- Gate B (required): approve Part 5 schema design before Part 6 implementation.