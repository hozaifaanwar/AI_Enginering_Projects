# Database Schema

## Scope

SQLite schema used by the backend (`backend/app/main.py`). Designed in Part 5, implemented in Part 6.

## Goals

- Keep MVP persistence simple and deterministic.
- Support one board per user now.
- Keep a clean path to multiple boards per user later.
- Store board state as JSON as requested.

## Proposed SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS boards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL UNIQUE,
  board_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  schema_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CHECK (json_valid(board_json))
);

CREATE INDEX IF NOT EXISTS idx_boards_user_id ON boards(user_id);
```

## Why This Schema

- `users` table exists now so backend can support multiple users later without redesign.
- `boards.user_id UNIQUE` enforces the MVP rule: one board per user.
- `board_json` keeps board persistence simple and aligned with frontend state shape.
- `schema_version` allows controlled JSON migrations in future parts.
- `revision` increments on every write and is used for optimistic concurrency (see below).

## JSON Payload Shape (board_json)

```json
{
  "columns": [
    { "id": "col-backlog", "title": "Backlog", "cardIds": ["card-1", "card-2"] },
    { "id": "col-progress", "title": "In Progress", "cardIds": ["card-3"] }
  ],
  "cards": {
    "card-1": {
      "id": "card-1",
      "title": "Align roadmap themes",
      "details": "Draft quarterly themes with impact statements and metrics."
    }
  }
}
```

## Deterministic Ordering Rules

- Column order is the order of `columns` array.
- Card order inside each column is the order of `cardIds` array.
- The `cards` object is treated as an ID map, not as an ordering source.

## Initialization

On startup:

1. Create the database file and directory if missing.
2. Execute `CREATE TABLE IF NOT EXISTS` statements, and add the `revision` column to older databases.
3. Ensure the MVP user row and its board exist, seeding the board from the default data.

Read paths never write.

## API Behavior

- The username always comes from the auth headers, never from the request body or query.
- `GET /api/board` returns the board and its `revision`.
- `PUT /api/board` and `POST /api/board/operations` take the `revision` the client last saw. The update only applies when it matches (`UPDATE ... WHERE revision = ?`); otherwise the API returns 409 and the client reloads.
- `POST /api/ai/chat` does not hold a connection during the LLM call. It then applies the AI operations to the latest board in one transaction.
- All write paths validate the board shape before saving.

## Tradeoffs

Pros:

- Minimal code and migration surface for MVP.
- Easy to keep frontend and backend board models aligned.
- Fast to implement and test.

Cons:

- Harder to query card-level analytics directly with SQL.
- Concurrency control is whole-document, via the `revision` check.

## Future Upgrade Path (post-MVP)

If needed, split into normalized `columns` and `cards` tables while preserving JSON API shape at the service boundary.
