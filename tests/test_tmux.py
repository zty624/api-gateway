from pathlib import Path

import pytest

from api_gateway.config import TmuxConfig
from api_gateway.tmux import TmuxManager, TmuxNameError


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.outputs: list[str] = []

    async def __call__(self, argv: list[str], cwd: str | None = None) -> str:
        self.calls.append((argv, cwd))
        if self.outputs:
            return self.outputs.pop(0)
        return ""


def _manager(fake: FakeRunner, tmp_path: Path) -> TmuxManager:
    return TmuxManager(
        TmuxConfig(session_prefix="gateway-", default_cwd=tmp_path),
        runner=fake,
    )


@pytest.mark.asyncio
async def test_create_session_uses_prefixed_tmux_name(tmp_path: Path) -> None:
    fake = FakeRunner()
    manager = _manager(fake, tmp_path)

    session = await manager.create("work", tmp_path)

    assert session.name == "work"
    assert session.tmux_name == "gateway-work"
    assert fake.calls[0][0] == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        "gateway-work",
        "-c",
        str(tmp_path),
    ]


@pytest.mark.asyncio
async def test_list_sessions_filters_prefix(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.outputs.append(
        "gateway-work\t1710000000\nother\t1710000001\ngateway-train\t1710000002\n"
    )
    manager = _manager(fake, tmp_path)

    sessions = await manager.list()

    assert [item.name for item in sessions] == ["work", "train"]


@pytest.mark.asyncio
async def test_get_session_reads_pane_details(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.outputs.append(f"gateway-work\t{tmp_path}\tzsh\n")
    manager = _manager(fake, tmp_path)

    session = await manager.get("work")

    assert session.exists is True
    assert session.pane_path == str(tmp_path)
    assert session.pane_command == "zsh"
    assert fake.calls[0][0] == [
        "tmux",
        "display-message",
        "-p",
        "-t",
        "gateway-work",
        "#{session_name}\t#{pane_current_path}\t#{pane_current_command}",
    ]


@pytest.mark.asyncio
async def test_delete_session_kills_prefixed_name(tmp_path: Path) -> None:
    fake = FakeRunner()
    manager = _manager(fake, tmp_path)

    await manager.delete("work")

    assert fake.calls[0][0] == ["tmux", "kill-session", "-t", "gateway-work"]


def test_reject_invalid_session_name(tmp_path: Path) -> None:
    manager = _manager(FakeRunner(), tmp_path)

    with pytest.raises(TmuxNameError):
        manager.tmux_name("bad name")
