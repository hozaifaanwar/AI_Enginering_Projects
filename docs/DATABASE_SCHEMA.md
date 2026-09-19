# Database Schema Proposal (Part 5)

## Scope

This is a design artifact only for sign-off. No persistence code is implemented in this part.

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

## JSON Payload Shape (board_json)

```json
{
  "schemaVersion": 1,
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

## Initialization Strategy (Part 6 Implementation Target)

On startup:

1. Open SQLite database file.
2. Execute `CREATE TABLE IF NOT EXISTS` statements.
3. Ensure the MVP user row exists if needed by the auth flow.
4. Ensure one board row exists for that user; if not, seed from initial board data.

## Planned API Implications (Part 6+)

- `GET /api/board` returns parsed `board_json` for the authenticated user.
- Mutation endpoints update board JSON and refresh `updated_at`.
- All write paths validate payload shape before persist.

## Tradeoffs

Pros:

- Minimal code and migration surface for MVP.
- Easy to keep frontend and backend board models aligned.
- Fast to implement and test.

Cons:

- Harder to query card-level analytics directly with SQL.
- Concurrency control requires whole-document update strategy.

## Future Upgrade Path (post-MVP)

If needed, split into normalized `columns` and `cards` tables while preserving JSON API shape at the service boundary.
