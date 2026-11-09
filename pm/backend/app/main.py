import json
import os
import sqlite3
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, model_validator

Title = Annotated[str, Field(min_length=1)]


class CardModel(BaseModel):
    id: str
    title: Title
    details: str


class ColumnModel(BaseModel):
    id: str
    title: Title
    cardIds: list[str] = Field(default_factory=list)


class BoardDataModel(BaseModel):
    columns: list[ColumnModel]
    cards: dict[str, CardModel]

    @model_validator(mode="after")
    def validate_board_references(self) -> Self:
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
            raise ValueError(f"Card ids not assigned to any column: {', '.join(sorted(extra_cards))}.")
        return self


class BoardResponse(BaseModel):
    username: str
    revision: int
    board: BoardDataModel


class PutBoardRequest(BaseModel):
    revision: int | None = None
    board: BoardDataModel


class RenameColumnOperation(BaseModel):
    type: Literal["rename_column"]
    columnId: str
    title: Title


class AddCardOperation(BaseModel):
    type: Literal["add_card"]
    columnId: str
    title: Title
    details: str = "No details yet."


class UpdateCardOperation(BaseModel):
    type: Literal["update_card"]
    cardId: str
    title: Title | None = None
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
    RenameColumnOperation | AddCardOperation | UpdateCardOperation | DeleteCardOperation | MoveCardOperation,
    Field(discriminator="type"),
]


class ApplyOperationsRequest(BaseModel):
    revision: int | None = None
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
    message: str
    history: list[AIConversationMessage] = Field(default_factory=list)


class AIChatLLMOutput(BaseModel):
    assistantResponse: str
    operations: list[BoardOperation] = Field(default_factory=list)


class AIChatResponse(BaseModel):
    assistantResponse: str
    boardUpdated: bool
    operationsApplied: int
    revision: int
    board: BoardDataModel


MVP_USERNAME = "user"
MVP_PASSWORD = "password"
DEMO_USER_HEADER = "X-Demo-User"
DEMO_PASSWORD_HEADER = "X-Demo-Password"


def current_user(
    user: str | None = Header(default=None, alias=DEMO_USER_HEADER),
    password: str | None = Header(default=None, alias=DEMO_PASSWORD_HEADER),
) -> str:
    if user != MVP_USERNAME or password != MVP_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


DEFAULT_BOARD_PATH = Path(__file__).with_name("default_board.json")


def default_board_model() -> BoardDataModel:
    return BoardDataModel.model_validate_json(DEFAULT_BOARD_PATH.read_text())


def get_db_path() -> Path:
    configured = os.getenv("PM_DB_PATH")
    if configured:
        return Path(configured)
    return Path("backend/data/pm.sqlite")


@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
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
                revision INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                CHECK (json_valid(board_json))
            );

            CREATE INDEX IF NOT EXISTS idx_boards_user_id ON boards(user_id);
            """
        )
        ensure_user_and_board(connection, MVP_USERNAME)


def ensure_user_and_board(connection: sqlite3.Connection, username: str) -> None:
    connection.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
    connection.execute(
        """
        INSERT OR IGNORE INTO boards (user_id, board_json)
        SELECT id, ? FROM users WHERE username = ?
        """,
        (default_board_model().model_dump_json(), username),
    )


def load_board(connection: sqlite3.Connection, username: str) -> tuple[BoardDataModel, int]:
    row = connection.execute(
        """
        SELECT boards.board_json, boards.revision
        FROM boards JOIN users ON users.id = boards.user_id
        WHERE users.username = ?
        """,
        (username,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Board not found.")
    return BoardDataModel.model_validate_json(row["board_json"]), row["revision"]


def save_board(
    connection: sqlite3.Connection,
    username: str,
    board: BoardDataModel,
    expected_revision: int | None,
) -> int:
    query = """
        UPDATE boards
        SET board_json = ?, revision = revision + 1, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = (SELECT id FROM users WHERE username = ?)
    """
    params: list[str | int] = [board.model_dump_json(), username]
    if expected_revision is not None:
        query += " AND revision = ?"
        params.append(expected_revision)
    row = connection.execute(query + " RETURNING revision", params).fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="Board has changed. Please reload latest data.")
    return row["revision"]


def find_column(board: BoardDataModel, column_id: str) -> ColumnModel:
    for column in board.columns:
        if column.id == column_id:
            return column
    raise ValueError(f"Column '{column_id}' not found.")


def find_column_containing_card(board: BoardDataModel, card_id: str) -> ColumnModel:
    for column in board.columns:
        if card_id in column.cardIds:
            return column
    raise ValueError(f"Card '{card_id}' not found.")


def apply_operation(board: BoardDataModel, operation: BoardOperation) -> None:
    """Apply one operation to the board in place. Raises ValueError for unknown ids."""
    match operation:
        case RenameColumnOperation():
            find_column(board, operation.columnId).title = operation.title

        case AddCardOperation():
            column = find_column(board, operation.columnId)
            card_id = f"card-{uuid4().hex[:12]}"
            board.cards[card_id] = CardModel(id=card_id, title=operation.title, details=operation.details)
            column.cardIds.append(card_id)

        case UpdateCardOperation():
            if operation.cardId not in board.cards:
                raise ValueError(f"Card '{operation.cardId}' not found.")
            card = board.cards[operation.cardId]
            if operation.title is not None:
                card.title = operation.title
            if operation.details is not None:
                card.details = operation.details

        case DeleteCardOperation():
            find_column_containing_card(board, operation.cardId).cardIds.remove(operation.cardId)
            del board.cards[operation.cardId]

        case MoveCardOperation():
            source_column = find_column_containing_card(board, operation.cardId)
            target_column = find_column(board, operation.targetColumnId)
            source_column.cardIds.remove(operation.cardId)
            if operation.beforeCardId is None:
                target_column.cardIds.append(operation.cardId)
            elif operation.beforeCardId in target_column.cardIds:
                index = target_column.cardIds.index(operation.beforeCardId)
                target_column.cardIds.insert(index, operation.cardId)
            else:
                raise ValueError(
                    f"Card '{operation.beforeCardId}' not found in column '{target_column.id}'."
                )


def apply_operations(board: BoardDataModel, operations: list[BoardOperation]) -> BoardDataModel:
    for operation in operations:
        apply_operation(board, operation)
    # Re-validate invariants before persisting.
    return BoardDataModel.model_validate(board.model_dump())


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openai/gpt-oss-120b"


def call_openrouter(messages: list[dict], response_format: dict | None = None) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured.")

    payload: dict = {"model": OPENROUTER_MODEL, "messages": messages}
    if response_format is not None:
        payload["response_format"] = response_format
        # Only route to providers that honor structured outputs. DeepInfra accepts
        # response_format for this model but often returns prose instead of the schema.
        payload["provider"] = {"require_parameters": True, "ignore": ["DeepInfra"]}

    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
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

    content = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=502, detail="OpenRouter response did not contain text.")
    return content


def request_openrouter_completion(question: str) -> AIPingResponse:
    answer = call_openrouter(
        [
            {"role": "system", "content": "You are a concise assistant. Answer in plain text."},
            {"role": "user", "content": question},
        ]
    )
    return AIPingResponse(model=OPENROUTER_MODEL, answer=answer)


STRING = {"type": "string"}
NULLABLE_STRING = {"type": ["string", "null"]}


def operation_schema(operation_type: str, **properties: dict) -> dict:
    return {
        "type": "object",
        "properties": {"type": {"type": "string", "enum": [operation_type]}, **properties},
        "required": ["type", *properties],
        "additionalProperties": False,
    }


KANBAN_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "kanban_structured_output",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "assistantResponse": STRING,
                "operations": {
                    "type": "array",
                    "items": {
                        "anyOf": [
                            operation_schema("rename_column", columnId=STRING, title=STRING),
                            operation_schema("add_card", columnId=STRING, title=STRING, details=STRING),
                            operation_schema(
                                "update_card", cardId=STRING, title=NULLABLE_STRING, details=NULLABLE_STRING
                            ),
                            operation_schema("delete_card", cardId=STRING),
                            operation_schema(
                                "move_card", cardId=STRING, targetColumnId=STRING, beforeCardId=NULLABLE_STRING
                            ),
                        ]
                    },
                },
            },
            "required": ["assistantResponse", "operations"],
            "additionalProperties": False,
        },
    },
}

KANBAN_SYSTEM_PROMPT = """You are an assistant for a kanban board.
Each user message is JSON with "userQuestion" and the current "board".
Reply with "assistantResponse" (plain text for the user) and "operations" (board changes to apply).
Supported operations:
- rename_column: columnId, title
- add_card: columnId, title, details
- update_card: cardId, title, details (null keeps the current value)
- delete_card: cardId
- move_card: cardId, targetColumnId, beforeCardId (null appends to the end of the column)
Use only column and card ids that exist in the board.
Only include operations when the user asks for a change; otherwise return an empty array."""

# Only the most recent messages are sent, to bound prompt size.
MAX_HISTORY_MESSAGES = 20


def request_openrouter_kanban_response(
    board: BoardDataModel,
    message: str,
    history: list[AIConversationMessage],
) -> AIChatLLMOutput:
    messages = [{"role": "system", "content": KANBAN_SYSTEM_PROMPT}]
    messages += [{"role": entry.role, "content": entry.content} for entry in history[-MAX_HISTORY_MESSAGES:]]
    user_payload = {"userQuestion": message, "board": board.model_dump()}
    messages.append({"role": "user", "content": json.dumps(user_payload)})

    content = call_openrouter(messages, KANBAN_RESPONSE_FORMAT)
    try:
        return AIChatLLMOutput.model_validate_json(content)
    except ValidationError as error:
        raise HTTPException(
            status_code=502, detail="OpenRouter returned output that does not match the schema."
        ) from error


ROOT_PLACEHOLDER_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PM MVP Backend</title>
  </head>
  <body>
    <h1>PM MVP backend is running</h1>
    <p>Frontend build not found. Open <a href="/api/health">/api/health</a> for API status.</p>
  </body>
</html>
"""


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
    def get_board(username: str = Depends(current_user)) -> BoardResponse:
        with connect(resolved_db_path) as connection:
            board, revision = load_board(connection, username)
        return BoardResponse(username=username, revision=revision, board=board)

    @app.put("/api/board", response_model=BoardResponse)
    def put_board(payload: PutBoardRequest, username: str = Depends(current_user)) -> BoardResponse:
        with connect(resolved_db_path) as connection:
            revision = save_board(connection, username, payload.board, payload.revision)
        return BoardResponse(username=username, revision=revision, board=payload.board)

    @app.post("/api/board/operations", response_model=BoardResponse)
    def apply_board_operations(
        payload: ApplyOperationsRequest,
        username: str = Depends(current_user),
    ) -> BoardResponse:
        with connect(resolved_db_path) as connection:
            board, current_revision = load_board(connection, username)
            try:
                board = apply_operations(board, payload.operations)
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            expected_revision = payload.revision if payload.revision is not None else current_revision
            revision = save_board(connection, username, board, expected_revision)
        return BoardResponse(username=username, revision=revision, board=board)

    @app.post("/api/ai/ping", response_model=AIPingResponse)
    def ai_ping(payload: AIPingRequest, _: str = Depends(current_user)) -> AIPingResponse:
        return request_openrouter_completion(payload.question)

    @app.post("/api/ai/chat", response_model=AIChatResponse)
    def ai_chat(payload: AIChatRequest, username: str = Depends(current_user)) -> AIChatResponse:
        # No connection is held during the LLM call, so board saves are not blocked.
        with connect(resolved_db_path) as connection:
            board, revision = load_board(connection, username)

        llm_output = request_openrouter_kanban_response(board, payload.message, payload.history)

        if llm_output.operations:
            # Apply to the latest board so edits made during the LLM call are kept.
            with connect(resolved_db_path) as connection:
                board, current_revision = load_board(connection, username)
                try:
                    board = apply_operations(board, llm_output.operations)
                except ValueError as error:
                    raise HTTPException(
                        status_code=502, detail=f"AI proposed an invalid change: {error}"
                    ) from error
                revision = save_board(connection, username, board, current_revision)

        return AIChatResponse(
            assistantResponse=llm_output.assistantResponse,
            boardUpdated=bool(llm_output.operations),
            operationsApplied=len(llm_output.operations),
            revision=revision,
            board=board,
        )

    if resolved_frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(resolved_frontend_dist), html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        def root() -> str:
            return ROOT_PLACEHOLDER_HTML

    return app


app = create_app()
