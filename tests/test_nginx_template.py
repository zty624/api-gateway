from pathlib import Path


def test_nginx_template_routes_api_and_tunnel() -> None:
    template = Path("deploy/nginx.conf.template").read_text(encoding="utf-8")

    assert "location /api/" in template
    assert "proxy_pass http://127.0.0.1:18080" in template
    assert "location /tunnel/" in template
    assert "proxy_pass http://127.0.0.1:10022/" in template
    assert "proxy_set_header Upgrade $http_upgrade" in template
    assert "proxy_set_header Connection $connection_upgrade" in template
    assert "auth_request /_gateway_auth" in template
