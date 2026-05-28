from pathlib import Path

from api_gateway.config import GatewayConfig, load_config


def test_sort_upstreams_by_prefix_length(tmp_path: Path) -> None:
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        """
listen:
  host: 0.0.0.0
  port: 18080
auth:
  enabled: false
upstreams:
  - path_prefix: /v1
    upstream_base: https://api.openai.com/v1
  - path_prefix: /v1/chat/completions
    upstream_base: https://api.openai.com/v1/chat
"""
    )
    config = load_config(config_file)
    assert len(config.upstreams) == 2
    assert config.upstreams[0].path_prefix == "/v1/chat/completions"
    assert config.upstreams[1].path_prefix == "/v1"


def test_load_gateway_config() -> None:
    payload = {
        "listen": {"host": "127.0.0.1", "port": 9000},
        "auth": {"enabled": True, "header_name": "X-KEY", "tokens": ["a", "b"]},
        "upstreams": [
            {
                "path_prefix": "v1/images",
                "upstream_base": "https://api.openai.com/v1/images",
                "api_key_env": "OPENAI_API_KEY",
                "api_key_prefix": "Bearer",
            }
        ],
    }
    cfg = GatewayConfig.model_validate(payload)
    assert cfg.listen.port == 9000
    assert cfg.auth.header_name == "X-KEY"
    assert cfg.upstreams[0].path_prefix == "/v1/images"
