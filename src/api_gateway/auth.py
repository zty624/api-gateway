from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from pydantic import BaseModel

from .config import AuthConfig


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: datetime


@dataclass(frozen=True)
class _TokenRecord:
    username: str
    expires_at: datetime


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


def hash_password(password: str, *, salt: str | None = None, iterations: int = 600_000) -> str:
    if iterations <= 0:
        raise ValueError("iterations must be greater than 0")
    raw_salt = salt.encode("utf-8") if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(raw_salt)}${_b64(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = _unb64(salt_text)
        expected = _unb64(digest_text)
    except (ValueError, TypeError):
        return False
    if algorithm != "pbkdf2_sha256" or iterations <= 0:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


class AuthManager:
    def __init__(
        self,
        config: AuthConfig,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._now = now or (lambda: datetime.now(UTC))
        self._tokens: dict[str, _TokenRecord] = {}

    def login(self, username: str, password: str) -> TokenResponse:
        user = next((item for item in self._config.users if item.username == username), None)
        if user is None or not verify_password(password, user.password_hash):
            raise PermissionError("invalid username or password")

        token = secrets.token_urlsafe(32)
        expires_at = self._now() + timedelta(seconds=self._config.token_ttl_seconds)
        self._tokens[token] = _TokenRecord(username=username, expires_at=expires_at)
        return TokenResponse(
            access_token=token,
            expires_in=self._config.token_ttl_seconds,
            expires_at=expires_at,
        )

    def validate(self, token: str) -> str:
        record = self._tokens.get(token)
        if record is None:
            raise PermissionError("invalid token")
        if record.expires_at <= self._now():
            self._tokens.pop(token, None)
            raise PermissionError("token expired")
        return record.username

    def logout(self, token: str) -> None:
        self._tokens.pop(token, None)

    def active_count(self) -> int:
        now = self._now()
        expired = [token for token, record in self._tokens.items() if record.expires_at <= now]
        for token in expired:
            self._tokens.pop(token, None)
        return len(self._tokens)
