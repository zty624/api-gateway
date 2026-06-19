from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")


def _valid_name(value: str) -> bool:
    return bool(value) and all(char in _NAME_CHARS for char in value)


class ListenConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 18080


class AuthUserConfig(BaseModel):
    username: str = Field(..., min_length=1)
    password_hash: str = Field(..., min_length=1)


class AuthConfig(BaseModel):
    enabled: bool = True
    token_ttl_seconds: int = 43_200
    users: list[AuthUserConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_auth(self) -> AuthConfig:
        if self.token_ttl_seconds <= 0:
            raise ValueError("token_ttl_seconds must be greater than 0")
        names = [user.username for user in self.users]
        if len(names) != len(set(names)):
            raise ValueError("username must be unique")
        if self.enabled and not self.users:
            raise ValueError("at least one auth user is required when auth is enabled")
        return self


class SSHConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 2222
    user: str = "root"
    authorized_keys_path: Path = Path("/root/.ssh/authorized_keys")

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise ValueError("ssh port must be between 1 and 65535")
        return value


class RtunnelConfig(BaseModel):
    binary: str = "rtunnel"
    listen: str = "127.0.0.1:10022"
    target: str = "127.0.0.1:2222"
    public_path: str = "/tunnel/"
    client_local_addr: str = "127.0.0.1:2226"

    @field_validator("public_path")
    @classmethod
    def validate_public_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("public_path must start with /")
        if not value.endswith("/"):
            value = f"{value}/"
        return value


class TmuxConfig(BaseModel):
    binary: str = "tmux"
    session_prefix: str = "gateway-"
    default_cwd: Path = Path(".")
    command_timeout_seconds: float = 10

    @field_validator("session_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not _valid_name(value):
            raise ValueError("session_prefix must contain only letters, digits, _, ., -")
        return value

    @field_validator("command_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("command_timeout_seconds must be greater than 0")
        return value


class GatewayConfig(BaseModel):
    listen: ListenConfig = Field(default_factory=ListenConfig)
    public_base_url: str = "http://127.0.0.1:8080"
    auth: AuthConfig = Field(default_factory=AuthConfig)
    ssh: SSHConfig = Field(default_factory=SSHConfig)
    rtunnel: RtunnelConfig = Field(default_factory=RtunnelConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)

    @field_validator("public_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("public_base_url must start with http:// or https://")
        return value


def _read_yaml_file(path: str | Path) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"config file does not exist: {file_path}")
    with file_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_config(path: str | Path) -> GatewayConfig:
    data = _read_yaml_file(path)
    try:
        return GatewayConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid config file: {exc}") from exc


__all__ = [
    "AuthConfig",
    "AuthUserConfig",
    "GatewayConfig",
    "ListenConfig",
    "RtunnelConfig",
    "SSHConfig",
    "TmuxConfig",
    "load_config",
]
