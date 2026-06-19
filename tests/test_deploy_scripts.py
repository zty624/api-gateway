from pathlib import Path


def test_entrypoint_downloads_repo_local_rtunnel() -> None:
    entrypoint = Path("scripts/entrypoint.sh").read_text(encoding="utf-8")

    assert 'ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"' in entrypoint
    assert 'RTUNNEL_BINARY="${RTUNNEL_BINARY:-$ROOT_DIR/bin/rtunnel}"' in entrypoint
    assert "prepare_rtunnel" in entrypoint
    assert '"$ROOT_DIR/scripts/install_rtunnel.sh" "$RTUNNEL_BINARY"' in entrypoint


def test_install_rtunnel_script_downloads_binary() -> None:
    script = Path("scripts/install_rtunnel.sh").read_text(encoding="utf-8")

    assert "https://github.com/Sarfflow/rtunnel/releases/download/v1.0.0/rtunnel-linux" in script
    assert 'curl -L "$RTUNNEL_URL" -o "$target"' in script
    assert 'chmod +x "$target"' in script
