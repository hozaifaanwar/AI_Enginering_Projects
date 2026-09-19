# Frontend Agent Guide

This document describes the current frontend implementation in `frontend/` so future changes can stay consistent with existing behavior.

## Purpose

The frontend is a Next.js app that currently provides a local-first Kanban board experience (no backend persistence yet).

## Stack

- Next.js 16 (App Router)
- React 19
- TypeScript
- Tailwind CSS v4
- dnd-kit for drag-and-drop
- Vitest + Testing Library for unit/integration tests
- Playwright for end-to-end tests

## Current Structure

- `src/app/page.tsx`
- Renders the `KanbanBoard` component at `/`.
- `src/components/KanbanBoard.tsx`
- Main stateful board component.
- Handles card drag/drop, column renaming, add card, and delete card.
- Uses in-memory React state initialized from `src/lib/kanban.ts`.
- `src/components/KanbanColumn.tsx`
- Column UI and actions (rename, add card, list cards).
- `src/components/KanbanCard.tsx`
- Individual card rendering and delete action.
- `src/components/KanbanCardPreview.tsx`
- Drag overlay preview content while dragging.
- `src/components/NewCardForm.tsx`
- Inline form for adding a card to a column.
- `src/lib/kanban.ts`
- Board types, initial seed data, card movement algorithm, id generation.

## Behavior Today

- Exactly five columns are seeded in initial data.
- Columns can be renamed inline.
- Cards can be:
- Added to a column
- Deleted from a column
- Reordered in the same column
- Moved across columns via drag/drop
- State is not persisted across page reloads.

## Styling Notes

- Global theme variables are in `src/app/globals.css`.
- Colors match project palette from root `AGENTS.md`.
- The board uses decorative radial backgrounds and card-based UI surfaces.

## Test Coverage Today

- Unit/integration tests:
- `src/components/KanbanBoard.test.tsx`
- `src/lib/kanban.test.ts`
- End-to-end tests:
- `tests/kanban.spec.ts`

Current e2e scenarios validate:
- Board renders at `/` with five columns
- Adding a card in a column
- Dragging a card between columns

## Commands

Run from `frontend/`:

- Install: `npm install`
- Dev server: `npm run dev`
- Build: `npm run build`
- Unit tests: `npm run test:unit`
- E2E tests: `npm run test:e2e`
- All tests: `npm run test:all`

## Conventions For Upcoming Work

- Keep UI behavior backward compatible unless the active phase explicitly changes it.
- Prefer focused tests for user-visible behavior over internal implementation assertions.
- Keep component responsibilities narrow: board-level state in `KanbanBoard`, presentational logic in smaller components.
- Avoid introducing global state libraries unless there is a proven need.
- Preserve existing accessibility labels and `data-testid` patterns used by tests.

## Expected Next Integrations

- Part 4: login gating before board render.
- Part 7: replace in-memory board state with backend API-backed state.
- Part 10: add an AI sidebar that can trigger board refresh from backend responses.
