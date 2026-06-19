from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import TmuxConfig


_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
Runner = Callable[[list[str], str | None], Awaitable[str]]


class TmuxError(RuntimeError):
    pass


class TmuxNameError(ValueError):
    pass


@dataclass(frozen=True)
class TmuxSession:
    name: str
    tmux_name: str
    exists: bool
    created_at: int | None = None
    pane_path: str | None = None
    pane_command: str | None = None


def validate_session_name(name: str) -> None:
    if not name or len(name) > 64 or any(char not in _NAME_CHARS for char in name):
        raise TmuxNameError("session name must be 1-64 chars of letters, digits, _, ., -")


class TmuxManager:
    def __init__(self, config: TmuxConfig, *, runner: Runner | None = None) -> None:
        self._config = config
        self._runner = runner or self._run

    def tmux_name(self, name: str) -> str:
        validate_session_name(name)
        return f"{self._config.session_prefix}{name}"

    def public_name(self, tmux_name: str) -> str | None:
        if not tmux_name.startswith(self._config.session_prefix):
            return None
        return tmux_name[len(self._config.session_prefix) :]

    async def list(self) -> list[TmuxSession]:
        output = await self._runner(
            [
                self._config.binary,
                "list-sessions",
                "-F",
                "#{session_name}\t#{session_created}",
            ],
            None,
        )
        sessions: list[TmuxSession] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            tmux_name, _, created_text = line.partition("\t")
            name = self.public_name(tmux_name)
            if name is None:
                continue
            created_at = int(created_text) if created_text.isdigit() else None
            sessions.append(
                TmuxSession(
                    name=name,
                    tmux_name=tmux_name,
                    exists=True,
                    created_at=created_at,
                )
            )
        return sessions

    async def create(self, name: str, cwd: Path | None = None) -> TmuxSession:
        tmux_name = self.tmux_name(name)
        workdir = self._resolve_cwd(cwd)
        await self._runner(
            [
                self._config.binary,
                "new-session",
                "-d",
                "-s",
                tmux_name,
                "-c",
                str(workdir),
            ],
            None,
        )
        return TmuxSession(name=name, tmux_name=tmux_name, exists=True)

    async def get(self, name: str) -> TmuxSession:
        tmux_name = self.tmux_name(name)
        try:
            output = await self._runner(
                [
                    self._config.binary,
                    "display-message",
                    "-p",
                    "-t",
                    tmux_name,
                    "#{session_name}\t#{pane_current_path}\t#{pane_current_command}",
                ],
                None,
            )
        except TmuxError as exc:
            message = str(exc).lower()
            if "can't find" in message or "not found" in message or "no such session" in message:
                return TmuxSession(name=name, tmux_name=tmux_name, exists=False)
            raise
        if not output.strip():
            return TmuxSession(name=name, tmux_name=tmux_name, exists=False)
        raw_name, pane_path, pane_command = (output.rstrip("\n").split("\t") + ["", ""])[:3]
        return TmuxSession(
            name=name,
            tmux_name=raw_name or tmux_name,
            exists=True,
            pane_path=pane_path or None,
            pane_command=pane_command or None,
        )

    async def delete(self, name: str) -> None:
        await self._runner([self._config.binary, "kill-session", "-t", self.tmux_name(name)], None)

    def _resolve_cwd(self, cwd: Path | None) -> Path:
        path = cwd if cwd is not None else self._config.default_cwd
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise TmuxError(f"cwd does not exist: {resolved}")
        if not resolved.is_dir():
            raise TmuxError(f"cwd is not a directory: {resolved}")
        return resolved

    async def _run(self, argv: list[str], cwd: str | None = None) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise TmuxError(f"tmux command not found: {argv[0]}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._config.command_timeout_seconds,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise TmuxError(f"tmux command timed out: {' '.join(argv)}") from exc

        if proc.returncode != 0:
            message = stderr.decode(errors="replace").strip()
            raise TmuxError(message or f"tmux command failed: {' '.join(argv)}")
        return stdout.decode(errors="replace")
