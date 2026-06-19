from __future__ import annotations

import shutil
import shlex
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel

from .auth import AuthManager, TokenResponse
from .config import GatewayConfig
from .tmux import TmuxError, TmuxManager, TmuxNameError, TmuxSession, validate_session_name


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionCreateRequest(BaseModel):
    name: str
    cwd: Path | None = None


class ConnectResponse(BaseModel):
    name: str
    tmux_name: str
    tunnel_url: str
    rtunnel_command: str
    ssh_command: str


class AuthContext(BaseModel):
    username: str
    token: str


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return token


def _tunnel_url(cfg: GatewayConfig) -> str:
    return f"{cfg.public_base_url}{cfg.rtunnel.public_path}"


def _client_port(addr: str) -> int:
    _, _, port = addr.rpartition(":")
    try:
        return int(port)
    except ValueError as exc:
        raise ValueError(f"invalid client_local_addr: {addr}") from exc


def _connect_response(cfg: GatewayConfig, token: str, name: str) -> ConnectResponse:
    tmux_name = f"{cfg.tmux.session_prefix}{name}"
    tunnel_url = _tunnel_url(cfg)
    auth_header = f"Authorization: Bearer {token}"
    rtunnel_command = " ".join(
        [
            shlex.quote(cfg.rtunnel.binary),
            shlex.quote(tunnel_url),
            shlex.quote(cfg.rtunnel.client_local_addr),
            "-H",
            shlex.quote(auth_header),
        ]
    )
    ssh_command = " ".join(
        [
            "ssh",
            "-p",
            str(_client_port(cfg.rtunnel.client_local_addr)),
            f"{cfg.ssh.user}@localhost",
            "-t",
            shlex.quote(f"tmux new-session -A -s {tmux_name}"),
        ]
    )
    return ConnectResponse(
        name=name,
        tmux_name=tmux_name,
        tunnel_url=tunnel_url,
        rtunnel_command=rtunnel_command,
        ssh_command=ssh_command,
    )


async def _status_payload(cfg: GatewayConfig, auth: AuthManager, tmux: TmuxManager) -> dict:
    tmux_available = shutil.which(cfg.tmux.binary) is not None
    session_count = 0
    tmux_error = None
    if tmux_available:
        try:
            session_count = len(await tmux.list())
        except TmuxError as exc:
            tmux_error = str(exc)
    return {
        "status": "ok",
        "auth": {"active_tokens": auth.active_count()},
        "sshd": {
            "host": cfg.ssh.host,
            "port": cfg.ssh.port,
            "binary_available": shutil.which("sshd") is not None
            or shutil.which("/usr/sbin/sshd") is not None,
        },
        "rtunnel": {
            "target": cfg.rtunnel.target,
            "listen": cfg.rtunnel.listen,
            "binary_available": shutil.which(cfg.rtunnel.binary) is not None,
        },
        "nginx": {"binary_available": shutil.which("nginx") is not None},
        "tmux": {
            "binary_available": tmux_available,
            "session_count": session_count,
            "error": tmux_error,
        },
    }


def create_app(
    config: GatewayConfig,
    *,
    auth: AuthManager | None = None,
    tmux: TmuxManager | None = None,
) -> FastAPI:
    app = FastAPI(title="rtunnel tmux gateway", version="0.1.0")
    auth_manager = auth or AuthManager(config.auth)
    tmux_manager = tmux or TmuxManager(config.tmux)

    def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
        if not config.auth.enabled:
            return AuthContext(username="auth-disabled", token="")
        token = _bearer_token(authorization)
        try:
            username = auth_manager.validate(token)
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        return AuthContext(username=username, token=token)

    @app.post("/api/login", response_model=TokenResponse)
    async def login(payload: LoginRequest) -> TokenResponse:
        try:
            return auth_manager.login(payload.username, payload.password)
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid username or password",
            ) from exc

    @app.post("/api/logout")
    async def logout(ctx: AuthContext = Depends(require_auth)) -> dict[str, str]:
        if ctx.token:
            auth_manager.logout(ctx.token)
        return {"status": "ok"}

    @app.get("/api/internal/auth", status_code=status.HTTP_204_NO_CONTENT)
    async def internal_auth(_: AuthContext = Depends(require_auth)) -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def root_healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    async def status_route(_: AuthContext = Depends(require_auth)) -> dict:
        return await _status_payload(config, auth_manager, tmux_manager)

    @app.get("/api/sessions", response_model=list[TmuxSession])
    async def list_sessions(_: AuthContext = Depends(require_auth)) -> list[TmuxSession]:
        try:
            return await tmux_manager.list()
        except TmuxError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/sessions", response_model=TmuxSession)
    async def create_session(
        payload: SessionCreateRequest,
        _: AuthContext = Depends(require_auth),
    ) -> TmuxSession:
        if payload.cwd is not None and not payload.cwd.is_absolute():
            raise HTTPException(status_code=400, detail="cwd must be an absolute path")
        try:
            current = await tmux_manager.get(payload.name)
            if current.exists:
                return current
            return await tmux_manager.create(payload.name, payload.cwd)
        except TmuxNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TmuxError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sessions/{name}", response_model=TmuxSession)
    async def get_session(name: str, _: AuthContext = Depends(require_auth)) -> TmuxSession:
        try:
            session = await tmux_manager.get(name)
        except TmuxNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TmuxError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if not session.exists:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @app.delete("/api/sessions/{name}")
    async def delete_session(name: str, _: AuthContext = Depends(require_auth)) -> dict[str, str]:
        try:
            session = await tmux_manager.get(name)
            if not session.exists:
                raise HTTPException(status_code=404, detail="session not found")
            await tmux_manager.delete(name)
        except TmuxNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TmuxError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"status": "ok"}

    @app.get("/api/sessions/{name}/connect", response_model=ConnectResponse)
    async def connect_session(
        name: str,
        ctx: AuthContext = Depends(require_auth),
    ) -> ConnectResponse:
        try:
            validate_session_name(name)
            return _connect_response(config, ctx.token, name)
        except (TmuxNameError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
