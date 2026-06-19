from pathlib import Path

from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.auth import AuthManager, hash_password
from api_gateway.config import GatewayConfig
from api_gateway.tmux import TmuxSession


class FakeTmux:
    def __init__(self) -> None:
        self.created: list[tuple[str, Path | None]] = []
        self.deleted: list[str] = []
        self.sessions: dict[str, TmuxSession] = {}

    async def list(self) -> list[TmuxSession]:
        return list(self.sessions.values())

    async def create(self, name: str, cwd: Path | None) -> TmuxSession:
        self.created.append((name, cwd))
        session = TmuxSession(name=name, tmux_name=f"gateway-{name}", exists=True)
        self.sessions[name] = session
        return session

    async def get(self, name: str) -> TmuxSession:
        return self.sessions.get(
            name,
            TmuxSession(name=name, tmux_name=f"gateway-{name}", exists=False),
        )

    async def delete(self, name: str) -> None:
        self.deleted.append(name)
        self.sessions.pop(name, None)


def _cfg(tmp_path: Path) -> GatewayConfig:
    return GatewayConfig(
        public_base_url="https://example.com/proxy/8080",
        auth={
            "users": [
                {
                    "username": "admin",
                    "password_hash": hash_password("secret", salt="testsalt", iterations=1000),
                }
            ],
            "token_ttl_seconds": 43200,
        },
        tmux={"session_prefix": "gateway-", "default_cwd": tmp_path},
    )


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/login",
        json={"username": "admin", "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_success_and_failure(tmp_path: Path) -> None:
    app = create_app(_cfg(tmp_path), tmux=FakeTmux())
    client = TestClient(app)

    ok = client.post("/api/login", json={"username": "admin", "password": "secret"})
    bad = client.post("/api/login", json={"username": "admin", "password": "bad"})

    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"
    assert bad.status_code == 401


def test_status_requires_token(tmp_path: Path) -> None:
    app = create_app(_cfg(tmp_path), tmux=FakeTmux())
    client = TestClient(app)

    response = client.get("/api/status")

    assert response.status_code == 401


def test_create_and_list_sessions(tmp_path: Path) -> None:
    fake = FakeTmux()
    app = create_app(_cfg(tmp_path), tmux=fake)
    client = TestClient(app)
    token = _login(client)

    created = client.post(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "work", "cwd": str(tmp_path)},
    )
    listed = client.get(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert created.status_code == 200
    assert created.json()["tmux_name"] == "gateway-work"
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "work"


def test_connect_command_uses_rtunnel_and_ssh(tmp_path: Path) -> None:
    app = create_app(_cfg(tmp_path), tmux=FakeTmux())
    client = TestClient(app)
    token = _login(client)

    response = client.get(
        "/api/sessions/work/connect",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "https://example.com/proxy/8080/tunnel/" in payload["rtunnel_command"]
    assert f"Authorization: Bearer {token}" in payload["rtunnel_command"]
    assert "ssh -p 2226 root@localhost" in payload["ssh_command"]
    assert "tmux new-session -A -s gateway-work" in payload["ssh_command"]


def test_internal_auth_endpoint_accepts_bearer_token(tmp_path: Path) -> None:
    auth = AuthManager(_cfg(tmp_path).auth)
    app = create_app(_cfg(tmp_path), auth=auth, tmux=FakeTmux())
    client = TestClient(app)
    token = auth.login("admin", "secret").access_token

    response = client.get(
        "/api/internal/auth",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
