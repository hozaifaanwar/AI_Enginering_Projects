# Frontend Agent Guide

This document describes the current frontend implementation in `frontend/` so future changes can stay consistent with existing behavior.

## Purpose

A Next.js app, exported as static files and served by the FastAPI backend. It shows a sign-in screen, then a Kanban board loaded from and saved to the backend, plus an AI chat sidebar.

## Stack

- Next.js 16 (App Router, `output: "export"`)
- React 19
- TypeScript
- Tailwind CSS v4
- dnd-kit for drag-and-drop
- Vitest + Testing Library for unit/integration tests
- Playwright for end-to-end tests

## Structure

- `src/components/KanbanBoard.tsx`: stateful root. Handles the login gate (`localStorage` flag), loading the board from `/api/board`, saving changes, and the chat wiring.
- `src/components/KanbanColumn.tsx`: column UI. The title is saved on blur or Enter, not per keystroke.
- `src/components/KanbanCard.tsx`: card display, inline edit (title and details), delete.
- `src/components/NewCardForm.tsx`: inline add-card form.
- `src/components/AIChatSidebar.tsx`: chat UI.
- `src/lib/kanban.ts`: board types, card move algorithm, id generation.
- `src/test/`: test setup, seed board fixture (mirrors the backend `DEFAULT_BOARD`), fake API for unit tests.

## Behavior

- Every board change updates local state, then saves the whole board with `PUT /api/board` and the last known `revision`.
- Saves run one at a time. Changes made while a save is in flight are sent when it completes, with the new revision.
- On 409 the board is reloaded and a message is shown.
- If the board fails to load, an error with a Retry button is shown. There is no offline mode.
- Chat waits for pending saves, then sends the message and prior history. If the AI changed the board, the returned board and revision replace local state. Server error details are shown in the sidebar.

## Tests

- Unit (`npm run test:unit`): `src/components/KanbanBoard.test.tsx` (uses `src/test/fakeApi.ts`) and `src/lib/kanban.test.ts`.
- E2E against the dev server (`npm run test:e2e`): `tests/kanban.spec.ts`, with the API mocked by `tests/mockBackend.ts`.
- E2E against the Docker app on :8000 (`npm run test:e2e:integrated`): `tests/kanban.integrated.spec.ts`. The AI test calls OpenRouter and is skipped when it is unreachable.

## Commands

Run from `frontend/`:

- Install: `npm install`
- Dev server: `npm run dev`
- Build: `npm run build`
- Lint: `npm run lint`
- Unit tests: `npm run test:unit`
- E2E tests: `npm run test:e2e`
- Integrated E2E: `npm run test:e2e:integrated`

## Conventions

- Keep component responsibilities narrow: board state in `KanbanBoard`, presentation in smaller components.
- Avoid global state libraries unless there is a proven need.
- Preserve the existing accessibility labels and `data-testid` patterns used by tests.
