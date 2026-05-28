import json

from fastapi.testclient import TestClient

from api_gateway.config import GatewayConfig, UpstreamConfig
from api_gateway.app import _find_upstream, _should_stream_request, create_app


def test_should_stream_request_detects_stream_payload():
    body = json.dumps({"model": "x", "stream": True}).encode()
    assert _should_stream_request(body, "application/json")
    assert not _should_stream_request(b'{"stream":false}', "application/json")
    assert not _should_stream_request(b"not-json", "application/json")


def test_find_upstream_by_prefix():
    up1 = UpstreamConfig(
        path_prefix="/v1/chat", upstream_base="https://api.openai.com/v1/chat"
    )
    up2 = UpstreamConfig(path_prefix="/v1", upstream_base="https://api.openai.com/v1")
    assert _find_upstream("/v1/chat/completions", [up1, up2]) is up1
    assert _find_upstream("/v1/models", [up1, up2]) is up2


def test_gateway_blocks_missing_token():
    cfg = GatewayConfig(
        listen={"host": "0.0.0.0", "port": 18080},
        auth={"enabled": True, "tokens": ["good"], "header_name": "X-INTERNAL-KEY"},
        upstreams=[
            {
                "path_prefix": "/v1",
                "upstream_base": "https://api.openai.com/v1",
            }
        ],
    )
    app = create_app(cfg)
    client = TestClient(app)
    response = client.get("/v1/models")
    assert response.status_code == 401
