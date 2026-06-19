from pathlib import Path

import pytest

from api_gateway.config import GatewayConfig, load_config


def _hash() -> str:
    return "pbkdf2_sha256$1000$c2FsdA==$LZQe7Pz7pCD1BI0swzPW4iD3mfnaTkFm0OcU4vO0G2Y="


def test_load_gateway_config(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        f"""
listen:
  host: 127.0.0.1
  port: 18080
public_base_url: https://example.com/proxy/18080
auth:
  enabled: true
  token_ttl_seconds: 43200
  users:
    - username: admin
      password_hash: {_hash()}
ssh:
  host: 127.0.0.1
  port: 2222
  user: root
  authorized_keys_path: /root/.ssh/authorized_keys
rtunnel:
  binary: rtunnel
  listen: 127.0.0.1:10022
  target: 127.0.0.1:2222
  public_path: /tunnel/
  client_local_addr: 127.0.0.1:2226
tmux:
  binary: tmux
  session_prefix: gateway-
  default_cwd: {tmp_path}
  command_timeout_seconds: 5
""",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.public_base_url == "https://example.com/proxy/18080"
    assert cfg.auth.users[0].username == "admin"
    assert cfg.ssh.port == 2222
    assert cfg.rtunnel.public_path == "/tunnel/"
    assert cfg.tmux.session_prefix == "gateway-"


def test_reject_duplicate_auth_users() -> None:
    payload = {
        "auth": {
            "users": [
                {"username": "admin", "password_hash": _hash()},
                {"username": "admin", "password_hash": _hash()},
            ]
        }
    }

    with pytest.raises(ValueError, match="username"):
        GatewayConfig.model_validate(payload)


def test_reject_invalid_tmux_prefix() -> None:
    payload = {
        "auth": {"users": [{"username": "admin", "password_hash": _hash()}]},
        "tmux": {"session_prefix": "bad prefix"},
    }

    with pytest.raises(ValueError, match="session_prefix"):
        GatewayConfig.model_validate(payload)


def test_reject_non_positive_token_ttl() -> None:
    payload = {
        "auth": {
            "token_ttl_seconds": 0,
            "users": [{"username": "admin", "password_hash": _hash()}],
        }
    }

    with pytest.raises(ValueError, match="token_ttl_seconds"):
        GatewayConfig.model_validate(payload)
