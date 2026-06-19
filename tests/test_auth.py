from datetime import UTC, datetime, timedelta

import pytest

from api_gateway.auth import AuthManager, hash_password
from api_gateway.config import AuthConfig


def _cfg() -> AuthConfig:
    return AuthConfig(
        users=[
            {
                "username": "admin",
                "password_hash": hash_password("secret", salt="testsalt", iterations=1000),
            }
        ],
        token_ttl_seconds=10,
    )


def test_login_issues_bearer_token() -> None:
    auth = AuthManager(_cfg(), now=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    token = auth.login("admin", "secret")

    assert token.token_type == "bearer"
    assert token.expires_in == 10
    assert auth.validate(token.access_token) == "admin"


def test_login_rejects_bad_password() -> None:
    auth = AuthManager(_cfg())

    with pytest.raises(PermissionError):
        auth.login("admin", "wrong")


def test_expired_token_is_rejected() -> None:
    current = datetime(2026, 1, 1, tzinfo=UTC)
    auth = AuthManager(_cfg(), now=lambda: current)
    token = auth.login("admin", "secret")

    auth._now = lambda: current + timedelta(seconds=11)

    with pytest.raises(PermissionError):
        auth.validate(token.access_token)


def test_logout_revokes_token() -> None:
    auth = AuthManager(_cfg())
    token = auth.login("admin", "secret")

    auth.logout(token.access_token)

    with pytest.raises(PermissionError):
        auth.validate(token.access_token)
