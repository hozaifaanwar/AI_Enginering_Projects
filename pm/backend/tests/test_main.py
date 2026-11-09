import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import (
    AIChatLLMOutput,
    AIConversationMessage,
    AIPingResponse,
    BoardDataModel,
    create_app,
    request_openrouter_kanban_response,
    save_board,
)

AUTH_HEADERS = {
    "X-Demo-User": "user",
    "X-Demo-Password": "password",
}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "pm-test.sqlite"
    app = create_app(db_path=db_path, frontend_dist=tmp_path / "missing-frontend")
    with TestClient(app) as test_client:
        test_client.headers.update(AUTH_HEADERS)
        yield test_client


def test_root_returns_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PM MVP backend is running" in response.text


def test_health_route(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pm-backend"}


def test_get_board_seeds_default_data(client: TestClient) -> None:
    response = client.get("/api/board")
    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "user"
    assert payload["revision"] >= 1
    assert len(payload["board"]["columns"]) == 5
    assert "card-1" in payload["board"]["cards"]


def test_get_board_requires_auth(tmp_path: Path) -> None:
    db_path = tmp_path / "unauthorized.sqlite"
    app = create_app(db_path=db_path, frontend_dist=tmp_path / "missing-frontend")
    with TestClient(app) as unauth_client:
        response = unauth_client.get("/api/board")
    assert response.status_code == 401


def test_put_board_replaces_board(client: TestClient) -> None:
    current_payload = client.get("/api/board").json()
    current_revision = current_payload["revision"]
    current = current_payload["board"]
    current["columns"][0]["title"] = "Renamed from PUT"

    response = client.put(
        "/api/board",
        json={"revision": current_revision, "board": current},
    )
    assert response.status_code == 200
    assert response.json()["board"]["columns"][0]["title"] == "Renamed from PUT"


def test_put_board_rejects_stale_revision(client: TestClient) -> None:
    initial = client.get("/api/board").json()
    stale_revision = initial["revision"]
    board = initial["board"]

    first = client.put(
        "/api/board",
        json={"revision": stale_revision, "board": board},
    )
    assert first.status_code == 200

    board["columns"][0]["title"] = "Conflict write"
    second = client.put(
        "/api/board",
        json={"revision": stale_revision, "board": board},
    )
    assert second.status_code == 409


def test_operations_endpoint_applies_mutations(client: TestClient) -> None:
    response = client.post(
        "/api/board/operations",
        json={
            "operations": [
                {"type": "rename_column", "columnId": "col-backlog", "title": "Ideas"},
                {
                    "type": "add_card",
                    "columnId": "col-backlog",
                    "title": "New API card",
                    "details": "Created from backend operation",
                },
            ],
        },
    )
    assert response.status_code == 200
    board = response.json()["board"]
    assert board["columns"][0]["title"] == "Ideas"
    created_ids = [
        card_id
        for card_id, card in board["cards"].items()
        if card["title"] == "New API card"
    ]
    assert len(created_ids) == 1
    assert created_ids[0] in board["columns"][0]["cardIds"]


def create_movable_card(client: TestClient) -> str:
    revision = client.get("/api/board").json()["revision"]
    add_response = client.post(
        "/api/board/operations",
        json={
            "revision": revision,
            "operations": [
                {
                    "type": "add_card",
                    "columnId": "col-backlog",
                    "title": "Movable",
                    "details": "temp",
                }
            ],
        },
    )
    assert add_response.status_code == 200
    board = add_response.json()["board"]
    return next(
        card_id for card_id, card in board["cards"].items() if card["title"] == "Movable"
    )


def test_operations_update_and_move_card(client: TestClient) -> None:
    movable_card_id = create_movable_card(client)
    revision = client.get("/api/board").json()["revision"]

    update_move_response = client.post(
        "/api/board/operations",
        json={
            "revision": revision,
            "operations": [
                {
                    "type": "update_card",
                    "cardId": movable_card_id,
                    "title": "Updated",
                    "details": "updated details",
                },
                {
                    "type": "move_card",
                    "cardId": movable_card_id,
                    "targetColumnId": "col-review",
                },
            ],
        },
    )
    assert update_move_response.status_code == 200
    moved_board = update_move_response.json()["board"]
    assert moved_board["cards"][movable_card_id]["title"] == "Updated"
    assert movable_card_id in next(
        col for col in moved_board["columns"] if col["id"] == "col-review"
    )["cardIds"]


def test_operations_delete_card(client: TestClient) -> None:
    movable_card_id = create_movable_card(client)
    revision = client.get("/api/board").json()["revision"]

    delete_response = client.post(
        "/api/board/operations",
        json={
            "revision": revision,
            "operations": [{"type": "delete_card", "cardId": movable_card_id}],
        },
    )
    assert delete_response.status_code == 200
    deleted_board = delete_response.json()["board"]
    assert movable_card_id not in deleted_board["cards"]


def test_db_file_created_and_persists_board(tmp_path: Path) -> None:
    db_path = tmp_path / "persist.sqlite"
    app = create_app(db_path=db_path, frontend_dist=tmp_path / "missing-frontend")

    with TestClient(app) as first_client:
        first_client.headers.update(AUTH_HEADERS)
        initial_payload = first_client.get("/api/board").json()
        initial_revision = initial_payload["revision"]
        initial = initial_payload["board"]
        initial["columns"][0]["title"] = "Persisted Title"
        save = first_client.put(
            "/api/board",
            json={"revision": initial_revision, "board": initial},
        )
        assert save.status_code == 200

    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM boards").fetchone()
        assert row is not None
        assert row[0] == 1

    with TestClient(app) as second_client:
        second_client.headers.update(AUTH_HEADERS)
        persisted = second_client.get("/api/board").json()["board"]
        assert persisted["columns"][0]["title"] == "Persisted Title"


def test_invalid_board_rejected(client: TestClient) -> None:
    current = client.get("/api/board").json()
    invalid_board = current["board"]
    revision = current["revision"]
    invalid_board["columns"][0]["cardIds"].append("missing-card")

    response = client.put(
        "/api/board",
        json={"revision": revision, "board": invalid_board},
    )
    assert response.status_code == 422


def test_ai_ping_success(client: TestClient) -> None:
    with patch(
        "app.main.request_openrouter_completion",
        return_value=AIPingResponse(model="openai/gpt-oss-120b", answer="4"),
    ):
        response = client.post("/api/ai/ping", json={"question": "2+2"})

    assert response.status_code == 200
    assert response.json() == {"model": "openai/gpt-oss-120b", "answer": "4"}


def test_ai_ping_missing_api_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = client.post("/api/ai/ping", json={"question": "2+2"})
    assert response.status_code == 500
    assert response.json()["detail"] == "OPENROUTER_API_KEY is not configured."


def post_chat_with_output(client: TestClient, output: AIChatLLMOutput, side_effect=None):
    def fake_response(*_args, **_kwargs) -> AIChatLLMOutput:
        if side_effect is not None:
            side_effect()
        return output

    with patch("app.main.request_openrouter_kanban_response", side_effect=fake_response):
        return client.post("/api/ai/chat", json={"message": "anything", "history": []})


def test_ai_chat_without_board_updates(client: TestClient) -> None:
    revision = client.get("/api/board").json()["revision"]
    response = post_chat_with_output(
        client, AIChatLLMOutput(assistantResponse="No board changes needed.", operations=[])
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistantResponse"] == "No board changes needed."
    assert payload["boardUpdated"] is False
    assert payload["operationsApplied"] == 0
    assert payload["revision"] == revision


def test_ai_chat_with_board_update_persists(client: TestClient) -> None:
    response = post_chat_with_output(
        client,
        AIChatLLMOutput(
            assistantResponse="Renamed backlog to Ideas.",
            operations=[{"type": "rename_column", "columnId": "col-backlog", "title": "Ideas"}],
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["boardUpdated"] is True
    assert payload["operationsApplied"] == 1
    assert payload["board"]["columns"][0]["title"] == "Ideas"
    assert client.get("/api/board").json()["board"]["columns"][0]["title"] == "Ideas"


def test_ai_chat_does_not_lock_db_and_keeps_concurrent_edits(
    client: TestClient, tmp_path: Path
) -> None:
    db_path = tmp_path / "pm-test.sqlite"

    def edit_board_during_llm_call() -> None:
        # A short timeout fails fast if the chat request still holds a write lock.
        connection = sqlite3.connect(db_path, timeout=0.1)
        connection.row_factory = sqlite3.Row
        with connection:
            board = BoardDataModel.model_validate_json(
                connection.execute("SELECT board_json FROM boards").fetchone()[0]
            )
            board.columns[1].title = "Edited during AI call"
            save_board(connection, "user", board, None)
        connection.close()

    response = post_chat_with_output(
        client,
        AIChatLLMOutput(
            assistantResponse="Renamed backlog.",
            operations=[{"type": "rename_column", "columnId": "col-backlog", "title": "Ideas"}],
        ),
        side_effect=edit_board_during_llm_call,
    )

    assert response.status_code == 200
    columns = client.get("/api/board").json()["board"]["columns"]
    assert columns[0]["title"] == "Ideas"
    assert columns[1]["title"] == "Edited during AI call"


def test_ai_chat_invalid_operation_returns_502_and_keeps_board(client: TestClient) -> None:
    before = client.get("/api/board").json()
    response = post_chat_with_output(
        client,
        AIChatLLMOutput(
            assistantResponse="Deleting.",
            operations=[{"type": "delete_card", "cardId": "card-missing"}],
        ),
    )

    assert response.status_code == 502
    assert "card-missing" in response.json()["detail"]
    assert client.get("/api/board").json() == before


def test_username_comes_from_auth_not_request(client: TestClient, tmp_path: Path) -> None:
    response = client.get("/api/board?username=someone-else")
    assert response.json()["username"] == "user"

    with sqlite3.connect(tmp_path / "pm-test.sqlite") as connection:
        usernames = [row[0] for row in connection.execute("SELECT username FROM users")]
    assert usernames == ["user"]


def test_kanban_response_is_validated_against_schema() -> None:
    board = BoardDataModel.model_validate(
        {"columns": [{"id": "col-a", "title": "A", "cardIds": []}], "cards": {}}
    )
    valid = (
        '{"assistantResponse": "Added.", "operations": '
        '[{"type": "add_card", "columnId": "col-a", "title": "T", "details": "D"}]}'
    )
    with patch("app.main.call_openrouter", return_value=valid):
        output = request_openrouter_kanban_response(board, "add", [])
    assert output.operations[0].title == "T"

    invalid = '{"assistantResponse": "Added.", "operations": [{"type": "add_card"}]}'
    with (
        patch("app.main.call_openrouter", return_value=invalid),
        pytest.raises(HTTPException) as error,
    ):
        request_openrouter_kanban_response(board, "add", [])
    assert error.value.status_code == 502


def test_empty_titles_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/board/operations",
        json={"operations": [{"type": "rename_column", "columnId": "col-backlog", "title": ""}]},
    )
    assert response.status_code == 422


def test_kanban_request_sends_only_recent_history() -> None:
    board = BoardDataModel.model_validate({"columns": [], "cards": {}})
    history = [{"role": "user", "content": f"message {i}"} for i in range(30)]
    reply = '{"assistantResponse": "Hi.", "operations": []}'
    with patch("app.main.call_openrouter", return_value=reply) as call:
        request_openrouter_kanban_response(
            board, "hello", [AIConversationMessage.model_validate(m) for m in history]
        )
    sent = call.call_args.args[0]
    # System prompt, the last 20 history messages, then the new message.
    assert len(sent) == 22
    assert sent[1]["content"] == "message 10"
