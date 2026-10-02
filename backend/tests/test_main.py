import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import AIPingResponse, AIChatLLMOutput, create_app, normalize_chat_output


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
        json={"username": "user", "revision": current_revision, "board": current},
    )
    assert response.status_code == 200
    assert response.json()["board"]["columns"][0]["title"] == "Renamed from PUT"


def test_put_board_rejects_stale_revision(client: TestClient) -> None:
    initial = client.get("/api/board").json()
    stale_revision = initial["revision"]
    board = initial["board"]

    first = client.put(
        "/api/board",
        json={"username": "user", "revision": stale_revision, "board": board},
    )
    assert first.status_code == 200

    board["columns"][0]["title"] = "Conflict write"
    second = client.put(
        "/api/board",
        json={"username": "user", "revision": stale_revision, "board": board},
    )
    assert second.status_code == 409


def test_operations_endpoint_applies_mutations(client: TestClient) -> None:
    response = client.post(
        "/api/board/operations",
        json={
            "username": "user",
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
            "username": "user",
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
            "username": "user",
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
            "username": "user",
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
            json={"username": "user", "revision": initial_revision, "board": initial},
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
        json={"username": "user", "revision": revision, "board": invalid_board},
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


def test_ai_chat_without_board_updates(client: TestClient) -> None:
    revision = client.get("/api/board").json()["revision"]
    with patch(
        "app.main.request_openrouter_kanban_response",
        return_value=AIChatLLMOutput(
            assistantResponse="No board changes needed.",
            operations=[],
        ),
    ):
        response = client.post(
            "/api/ai/chat",
            json={
                "username": "user",
                "revision": revision,
                "message": "Do I need to move anything?",
                "history": [{"role": "user", "content": "status check"}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistantResponse"] == "No board changes needed."
    assert payload["boardUpdated"] is False
    assert payload["operationsApplied"] == 0


def test_ai_chat_with_board_update_persists(client: TestClient) -> None:
    revision = client.get("/api/board").json()["revision"]
    with patch(
        "app.main.request_openrouter_kanban_response",
        return_value=AIChatLLMOutput(
            assistantResponse="Renamed backlog to Ideas.",
            operations=[
                {
                    "type": "rename_column",
                    "columnId": "col-backlog",
                    "title": "Ideas",
                }
            ],
        ),
    ):
        response = client.post(
            "/api/ai/chat",
            json={
                "username": "user",
                "revision": revision,
                "message": "Rename backlog to ideas",
                "history": [],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistantResponse"] == "Renamed backlog to Ideas."
    assert payload["boardUpdated"] is True
    assert payload["operationsApplied"] == 1
    assert payload["board"]["columns"][0]["title"] == "Ideas"

    verify = client.get("/api/board?username=user")
    assert verify.status_code == 200
    assert verify.json()["board"]["columns"][0]["title"] == "Ideas"


def test_ai_chat_infers_add_card_when_operations_missing(client: TestClient) -> None:
    revision = client.get("/api/board").json()["revision"]
    title = "Inferred Backend Card"

    with patch(
        "app.main.request_openrouter_kanban_response",
        return_value=AIChatLLMOutput(
            assistantResponse=f"Added card '{title}' to backlog.",
            operations=[],
        ),
    ):
        response = client.post(
            "/api/ai/chat",
            json={
                "username": "user",
                "revision": revision,
                "message": f"Add one card to col-backlog titled '{title}' with details 'from fallback'.",
                "history": [],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["boardUpdated"] is True
    assert payload["operationsApplied"] == 1
    assert any(card["title"] == title for card in payload["board"]["cards"].values())


def test_normalize_chat_output_accepts_snake_case_operations() -> None:
    normalized = normalize_chat_output(
        {
            "assistant_response": "Done.",
            "operations": [
                {
                    "type": "rename_column",
                    "column_id": "col-backlog",
                    "title": "Ideas",
                }
            ],
        }
    )

    assert normalized.assistantResponse == "Done."
    assert len(normalized.operations) == 1
