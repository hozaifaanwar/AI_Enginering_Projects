import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, Union
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator


class CardModel(BaseModel):
  id: str
  title: str
  details: str


class ColumnModel(BaseModel):
  id: str
  title: str
  cardIds: list[str] = Field(default_factory=list)


class BoardDataModel(BaseModel):
  columns: list[ColumnModel]
  cards: dict[str, CardModel]

  @model_validator(mode="after")
  def validate_board_references(self) -> "BoardDataModel":
    card_keys = set(self.cards.keys())
    seen: set[str] = set()
    for key, card in self.cards.items():
      if key != card.id:
        raise ValueError(f"Card map key '{key}' does not match card id '{card.id}'.")

    for column in self.columns:
      for card_id in column.cardIds:
        if card_id not in card_keys:
          raise ValueError(f"Column '{column.id}' references unknown card id '{card_id}'.")
        if card_id in seen:
          raise ValueError(f"Card id '{card_id}' appears in more than one column.")
        seen.add(card_id)

    extra_cards = card_keys - seen
    if extra_cards:
      raise ValueError(
        f"Card ids not assigned to any column: {', '.join(sorted(extra_cards))}."
      )
    return self


class BoardResponse(BaseModel):
  username: str
  board: BoardDataModel


class PutBoardRequest(BaseModel):
  username: str = "user"
  board: BoardDataModel


class RenameColumnOperation(BaseModel):
  type: Literal["rename_column"]
  columnId: str
  title: str


class AddCardOperation(BaseModel):
  type: Literal["add_card"]
  columnId: str
  title: str
  details: str = "No details yet."


class UpdateCardOperation(BaseModel):
  type: Literal["update_card"]
  cardId: str
  title: str | None = None
  details: str | None = None


class DeleteCardOperation(BaseModel):
  type: Literal["delete_card"]
  cardId: str


class MoveCardOperation(BaseModel):
  type: Literal["move_card"]
  cardId: str
  targetColumnId: str
  beforeCardId: str | None = None


BoardOperation = Annotated[
  Union[
    RenameColumnOperation,
    AddCardOperation,
    UpdateCardOperation,
    DeleteCardOperation,
    MoveCardOperation,
  ],
  Field(discriminator="type"),
]


class ApplyOperationsRequest(BaseModel):
  username: str = "user"
  operations: list[BoardOperation]


class AIPingRequest(BaseModel):
  question: str = "2+2"


class AIPingResponse(BaseModel):
  model: str
  answer: str


class AIConversationMessage(BaseModel):
  role: Literal["user", "assistant"]
  content: str


class AIChatRequest(BaseModel):
  username: str = "user"
  message: str
  history: list[AIConversationMessage] = Field(default_factory=list)


class AIChatLLMOutput(BaseModel):
  assistantResponse: str
  operations: list[BoardOperation] = Field(default_factory=list)


class AIChatResponse(BaseModel):
  assistantResponse: str
  boardUpdated: bool
  operationsApplied: int
  board: BoardDataModel


DEFAULT_BOARD: dict = {
  "columns": [
    {"id": "col-backlog", "title": "Backlog", "cardIds": ["card-1", "card-2"]},
    {"id": "col-discovery", "title": "Discovery", "cardIds": ["card-3"]},
    {
      "id": "col-progress",
      "title": "In Progress",
      "cardIds": ["card-4", "card-5"],
    },
    {"id": "col-review", "title": "Review", "cardIds": ["card-6"]},
    {"id": "col-done", "title": "Done", "cardIds": ["card-7", "card-8"]},
  ],
  "cards": {
    "card-1": {
      "id": "card-1",
      "title": "Align roadmap themes",
      "details": "Draft quarterly themes with impact statements and metrics.",
    },
    "card-2": {
      "id": "card-2",
      "title": "Gather customer signals",
      "details": "Review support tags, sales notes, and churn feedback.",
    },
    "card-3": {
      "id": "card-3",
      "title": "Prototype analytics view",
      "details": "Sketch initial dashboard layout and key drill-downs.",
    },
    "card-4": {
      "id": "card-4",
      "title": "Refine status language",
      "details": "Standardize column labels and tone across the board.",
    },
    "card-5": {
      "id": "card-5",
      "title": "Design card layout",
      "details": "Add hierarchy and spacing for scanning dense lists.",
    },
    "card-6": {
      "id": "card-6",
      "title": "QA micro-interactions",
      "details": "Verify hover, focus, and loading states.",
    },
    "card-7": {
      "id": "card-7",
      "title": "Ship marketing page",
      "details": "Final copy approved and asset pack delivered.",
    },
    "card-8": {
      "id": "card-8",
      "title": "Close onboarding sprint",
      "details": "Document release notes and share internally.",
    },
  },
}


def default_board_model() -> BoardDataModel:
  return BoardDataModel.model_validate(DEFAULT_BOARD)


def get_db_path() -> Path:
  configured = os.getenv("PM_DB_PATH")
  if configured:
    return Path(configured)
  return Path("backend/data/pm.sqlite")


def get_connection(db_path: Path) -> sqlite3.Connection:
  db_path.parent.mkdir(parents=True, exist_ok=True)
  connection = sqlite3.connect(db_path)
  connection.row_factory = sqlite3.Row
  connection.execute("PRAGMA foreign_keys = ON")
  return connection


def init_database(db_path: Path) -> None:
  with get_connection(db_path) as connection:
    connection.executescript(
      """
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
      """
    )


def ensure_user_and_board(connection: sqlite3.Connection, username: str) -> int:
  connection.execute(
    "INSERT OR IGNORE INTO users (username) VALUES (?)",
    (username,),
  )
  user_row = connection.execute(
    "SELECT id FROM users WHERE username = ?",
    (username,),
  ).fetchone()
  if user_row is None:
    raise RuntimeError(f"Unable to resolve user id for username '{username}'.")

  user_id = int(user_row["id"])
  existing_board = connection.execute(
    "SELECT id FROM boards WHERE user_id = ?",
    (user_id,),
  ).fetchone()

  if existing_board is None:
    connection.execute(
      """
      INSERT INTO boards (user_id, board_json, schema_version)
      VALUES (?, ?, 1)
      """,
      (user_id, default_board_model().model_dump_json()),
    )

  return user_id


def load_board(connection: sqlite3.Connection, username: str) -> BoardDataModel:
  user_id = ensure_user_and_board(connection, username)
  row = connection.execute(
    "SELECT board_json FROM boards WHERE user_id = ?",
    (user_id,),
  ).fetchone()
  if row is None:
    raise RuntimeError(f"No board found for username '{username}'.")

  board_data = json.loads(row["board_json"])
  return BoardDataModel.model_validate(board_data)


def save_board(connection: sqlite3.Connection, username: str, board: BoardDataModel) -> None:
  user_id = ensure_user_and_board(connection, username)
  connection.execute(
    """
    UPDATE boards
    SET board_json = ?, schema_version = 1, updated_at = CURRENT_TIMESTAMP
    WHERE user_id = ?
    """,
    (board.model_dump_json(), user_id),
  )


def find_column(board: BoardDataModel, column_id: str) -> ColumnModel:
  for column in board.columns:
    if column.id == column_id:
      return column
  raise HTTPException(status_code=404, detail=f"Column '{column_id}' not found.")


def find_column_containing_card(board: BoardDataModel, card_id: str) -> ColumnModel:
  for column in board.columns:
    if card_id in column.cardIds:
      return column
  raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found in board columns.")


def apply_operation(board: BoardDataModel, operation: BoardOperation) -> BoardDataModel:
  if isinstance(operation, RenameColumnOperation):
    column = find_column(board, operation.columnId)
    column.title = operation.title
    return board

  if isinstance(operation, AddCardOperation):
    column = find_column(board, operation.columnId)
    card_id = f"card-{uuid4().hex[:12]}"
    board.cards[card_id] = CardModel(
      id=card_id,
      title=operation.title,
      details=operation.details,
    )
    column.cardIds.append(card_id)
    return board

  if isinstance(operation, UpdateCardOperation):
    card = board.cards.get(operation.cardId)
    if card is None:
      raise HTTPException(status_code=404, detail=f"Card '{operation.cardId}' not found.")
    if operation.title is not None:
      card.title = operation.title
    if operation.details is not None:
      card.details = operation.details
    return board

  if isinstance(operation, DeleteCardOperation):
    if operation.cardId not in board.cards:
      raise HTTPException(status_code=404, detail=f"Card '{operation.cardId}' not found.")
    del board.cards[operation.cardId]
    for column in board.columns:
      column.cardIds = [card_id for card_id in column.cardIds if card_id != operation.cardId]
    return board

  if isinstance(operation, MoveCardOperation):
    source_column = find_column_containing_card(board, operation.cardId)
    target_column = find_column(board, operation.targetColumnId)

    source_column.cardIds = [card_id for card_id in source_column.cardIds if card_id != operation.cardId]

    if operation.beforeCardId is None:
      target_column.cardIds.append(operation.cardId)
      return board

    if operation.beforeCardId not in target_column.cardIds:
      raise HTTPException(
        status_code=404,
        detail=f"Target card '{operation.beforeCardId}' not found in column '{target_column.id}'.",
      )

    index = target_column.cardIds.index(operation.beforeCardId)
    target_column.cardIds.insert(index, operation.cardId)
    return board

  raise HTTPException(status_code=400, detail="Unknown operation type.")


def request_openrouter_completion(question: str) -> AIPingResponse:
  api_key = os.getenv("OPENROUTER_API_KEY")
  if not api_key:
    raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured.")

  model = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
  payload = {
    "model": model,
    "messages": [
      {
        "role": "system",
        "content": "You are a concise assistant. Answer in plain text.",
      },
      {"role": "user", "content": question},
    ],
  }
  headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
  }

  try:
    response = httpx.post(
      "https://openrouter.ai/api/v1/chat/completions",
      headers=headers,
      json=payload,
      timeout=30.0,
    )
    response.raise_for_status()
  except httpx.HTTPStatusError as error:
    raise HTTPException(
      status_code=502,
      detail=f"OpenRouter returned HTTP {error.response.status_code}.",
    ) from error
  except httpx.HTTPError as error:
    raise HTTPException(status_code=502, detail="Failed to reach OpenRouter.") from error

  data = response.json()
  answer = ""
  if data.get("choices"):
    message = data["choices"][0].get("message", {})
    answer = str(message.get("content", "")).strip()

  if not answer:
    raise HTTPException(status_code=502, detail="OpenRouter response did not contain text.")

  return AIPingResponse(model=model, answer=answer)


def parse_json_object_from_text(text: str) -> dict:
  stripped = text.strip()
  try:
    value = json.loads(stripped)
    if isinstance(value, dict):
      return value
  except json.JSONDecodeError:
    pass

  decoder = json.JSONDecoder()
  start_index = stripped.find("{")
  while start_index != -1:
    try:
      candidate, _ = decoder.raw_decode(stripped[start_index:])
      if isinstance(candidate, dict):
        return candidate
    except json.JSONDecodeError:
      pass
    start_index = stripped.find("{", start_index + 1)

  raise HTTPException(status_code=502, detail="OpenRouter did not return valid JSON content.")


def normalize_operation(raw_operation: dict) -> dict | None:
  operation_type = str(raw_operation.get("type", "")).strip()
  if not operation_type:
    return None

  if operation_type == "rename_column":
    column_id = raw_operation.get("columnId") or raw_operation.get("column_id")
    title = raw_operation.get("title")
    if not column_id or not title:
      return None
    return {"type": "rename_column", "columnId": str(column_id), "title": str(title)}

  if operation_type == "add_card":
    column_id = raw_operation.get("columnId") or raw_operation.get("column_id")
    title = raw_operation.get("title")
    details = raw_operation.get("details", "No details yet.")
    if not column_id or not title:
      return None
    return {
      "type": "add_card",
      "columnId": str(column_id),
      "title": str(title),
      "details": str(details),
    }

  if operation_type == "update_card":
    card_id = raw_operation.get("cardId") or raw_operation.get("card_id")
    title = raw_operation.get("title")
    details = raw_operation.get("details")
    if not card_id:
      return None
    normalized: dict = {"type": "update_card", "cardId": str(card_id)}
    if title is not None:
      normalized["title"] = str(title)
    if details is not None:
      normalized["details"] = str(details)
    return normalized

  if operation_type == "delete_card":
    card_id = raw_operation.get("cardId") or raw_operation.get("card_id")
    if not card_id:
      return None
    return {"type": "delete_card", "cardId": str(card_id)}

  if operation_type == "move_card":
    card_id = raw_operation.get("cardId") or raw_operation.get("card_id")
    target_column_id = raw_operation.get("targetColumnId") or raw_operation.get("target_column_id")
    before_card_id = raw_operation.get("beforeCardId") or raw_operation.get("before_card_id")
    if not card_id or not target_column_id:
      return None
    normalized_move = {
      "type": "move_card",
      "cardId": str(card_id),
      "targetColumnId": str(target_column_id),
    }
    if before_card_id is not None:
      normalized_move["beforeCardId"] = str(before_card_id)
    return normalized_move

  return None


def normalize_chat_output(parsed: dict) -> AIChatLLMOutput:
  assistant_response = parsed.get("assistantResponse")
  if assistant_response is None:
    assistant_response = parsed.get("assistant_response")
  if assistant_response is None:
    assistant_response = parsed.get("response")
  if assistant_response is None:
    assistant_response = parsed.get("message")
  if not isinstance(assistant_response, str) or not assistant_response.strip():
    raise HTTPException(status_code=502, detail="OpenRouter JSON missing assistant response text.")

  raw_operations = parsed.get("operations", [])
  if not isinstance(raw_operations, list):
    raw_operations = []

  normalized_operations: list[dict] = []
  for raw_operation in raw_operations:
    if not isinstance(raw_operation, dict):
      continue
    normalized = normalize_operation(raw_operation)
    if normalized is not None:
      normalized_operations.append(normalized)

  return AIChatLLMOutput.model_validate(
    {
      "assistantResponse": assistant_response.strip(),
      "operations": normalized_operations,
    }
  )


def request_openrouter_kanban_response(
  board: BoardDataModel,
  message: str,
  history: list[AIConversationMessage],
) -> AIChatLLMOutput:
  api_key = os.getenv("OPENROUTER_API_KEY")
  if not api_key:
    raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured.")

  model = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
  messages = [
    {
      "role": "system",
      "content": (
        "You are an assistant for a kanban board. "
        "Always reply with strict JSON containing keys assistantResponse and operations. "
        "operations is an array of board operations using supported types only."
      ),
    }
  ]
  for entry in history:
    messages.append({"role": entry.role, "content": entry.content})

  user_payload = {
    "userQuestion": message,
    "board": board.model_dump(),
  }
  messages.append({"role": "user", "content": json.dumps(user_payload)})

  response_format = {
    "type": "json_schema",
    "json_schema": {
      "name": "kanban_structured_output",
      "strict": True,
      "schema": {
        "type": "object",
        "properties": {
          "assistantResponse": {"type": "string"},
          "operations": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "enum": [
                    "rename_column",
                    "add_card",
                    "update_card",
                    "delete_card",
                    "move_card",
                  ],
                }
              },
              "required": ["type"],
              "additionalProperties": True,
            },
          },
        },
        "required": ["assistantResponse", "operations"],
        "additionalProperties": False,
      },
    },
  }

  payload = {
    "model": model,
    "messages": messages,
    "response_format": response_format,
  }
  headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
  }

  try:
    response = httpx.post(
      "https://openrouter.ai/api/v1/chat/completions",
      headers=headers,
      json=payload,
      timeout=45.0,
    )
    response.raise_for_status()
  except httpx.HTTPStatusError as error:
    raise HTTPException(
      status_code=502,
      detail=f"OpenRouter returned HTTP {error.response.status_code}.",
    ) from error
  except httpx.HTTPError as error:
    raise HTTPException(status_code=502, detail="Failed to reach OpenRouter.") from error

  data = response.json()
  content = ""
  if data.get("choices"):
    content = str(data["choices"][0].get("message", {}).get("content", "")).strip()

  parsed = parse_json_object_from_text(content)
  return normalize_chat_output(parsed)


def create_app(db_path: Path | None = None, frontend_dist: Path | None = None) -> FastAPI:
  resolved_db_path = db_path or get_db_path()
  resolved_frontend_dist = frontend_dist or Path("/app/frontend/out")

  @asynccontextmanager
  async def lifespan(_: FastAPI):
    init_database(resolved_db_path)
    yield

  app = FastAPI(title="Project Management MVP API", lifespan=lifespan)

  @app.get("/api/health")
  def health() -> dict[str, str]:
    return {"status": "ok", "service": "pm-backend"}

  @app.get("/api/board", response_model=BoardResponse)
  def get_board(username: str = "user") -> BoardResponse:
    with get_connection(resolved_db_path) as connection:
      board = load_board(connection, username)
      return BoardResponse(username=username, board=board)

  @app.put("/api/board", response_model=BoardResponse)
  def put_board(payload: PutBoardRequest) -> BoardResponse:
    with get_connection(resolved_db_path) as connection:
      save_board(connection, payload.username, payload.board)
      board = load_board(connection, payload.username)
      return BoardResponse(username=payload.username, board=board)

  @app.post("/api/board/operations", response_model=BoardResponse)
  def apply_board_operations(payload: ApplyOperationsRequest) -> BoardResponse:
    with get_connection(resolved_db_path) as connection:
      board = load_board(connection, payload.username)
      for operation in payload.operations:
        board = apply_operation(board, operation)
      # Re-validate invariants before persisting.
      board = BoardDataModel.model_validate(board.model_dump())
      save_board(connection, payload.username, board)
      return BoardResponse(username=payload.username, board=board)

  @app.post("/api/ai/ping", response_model=AIPingResponse)
  def ai_ping(payload: AIPingRequest) -> AIPingResponse:
    return request_openrouter_completion(payload.question)

  @app.post("/api/ai/chat", response_model=AIChatResponse)
  def ai_chat(payload: AIChatRequest) -> AIChatResponse:
    with get_connection(resolved_db_path) as connection:
      board = load_board(connection, payload.username)
      llm_output = request_openrouter_kanban_response(
        board=board,
        message=payload.message,
        history=payload.history,
      )

      for operation in llm_output.operations:
        board = apply_operation(board, operation)

      board = BoardDataModel.model_validate(board.model_dump())
      board_updated = len(llm_output.operations) > 0
      if board_updated:
        save_board(connection, payload.username, board)

      return AIChatResponse(
        assistantResponse=llm_output.assistantResponse,
        boardUpdated=board_updated,
        operationsApplied=len(llm_output.operations),
        board=board,
      )

  if resolved_frontend_dist.exists():
    app.mount(
      "/",
      StaticFiles(directory=str(resolved_frontend_dist), html=True),
      name="frontend",
    )
  else:
    @app.get("/", response_class=HTMLResponse)
    def root() -> str:
      return """
      <!doctype html>
      <html lang=\"en\">
        <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>PM MVP Backend</title>
        </head>
        <body>
        <h1>PM MVP backend is running</h1>
        <p>Frontend build not found. Open <a href=\"/api/health\">/api/health</a> for API status.</p>
        </body>
      </html>
      """

  return app


app = create_app()
