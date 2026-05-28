from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator


class ListenConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 18080


class AuthConfig(BaseModel):
    enabled: bool = True
    header_name: str = "X-INTERNAL-KEY"
    tokens: list[str] = Field(default_factory=list)


class UpstreamConfig(BaseModel):
    path_prefix: str = Field(..., min_length=1)
    upstream_base: HttpUrl
    api_key_env: str | None = None
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    timeout_seconds: float = 60
    extra_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("path_prefix")
    @classmethod
    def normalize_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/"


class GatewayConfig(BaseModel):
    listen: ListenConfig = Field(default_factory=ListenConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    upstreams: list[UpstreamConfig]

    @field_validator("upstreams")
    @classmethod
    def sort_upstreams_by_prefix_length(cls, value: list[UpstreamConfig]) -> list[UpstreamConfig]:
        if not value:
            raise ValueError("至少需要配置一个 upstream")
        return sorted(value, key=lambda item: len(item.path_prefix), reverse=True)


def _read_yaml_file(path: str | Path) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {file_path}")
    with file_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_config(path: str | Path) -> GatewayConfig:
    data = _read_yaml_file(path)
    try:
        return GatewayConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"配置文件不合法: {exc}") from exc


__all__ = [
    "AuthConfig",
    "GatewayConfig",
    "ListenConfig",
    "UpstreamConfig",
    "load_config",
]
