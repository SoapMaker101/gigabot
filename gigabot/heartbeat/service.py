"""Heartbeat service - periodic agent wake-up."""

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60

HEARTBEAT_PROMPT = """Прочитай HEARTBEAT.md в workspace (если он существует).
Выполни задачи, перечисленные в нём.
Если ничего не требуется, ответь: HEARTBEAT_OK"""

HEARTBEAT_OK_TOKEN = "HEARTBEAT_OK"


def _is_heartbeat_empty(content: str | None) -> bool:
    if not content:
        return True
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        return False
    return True


class HeartbeatService:
    def __init__(
        self,
        workspace: Path,
        on_heartbeat: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        interval_s: int = DEFAULT_HEARTBEAT_INTERVAL_S,
        enabled: bool = True,
    ):
        self.workspace = workspace
        self.on_heartbeat = on_heartbeat
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Heartbeat started (every {}s)", self.interval_s)

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat error: {}", e)

    async def _tick(self) -> None:
        content = self._read_heartbeat_file()
        if _is_heartbeat_empty(content):
            logger.debug("Heartbeat: no tasks")
            return
        logger.info("Heartbeat: checking for tasks...")
        if self.on_heartbeat:
            try:
                response = await self.on_heartbeat(HEARTBEAT_PROMPT)
                if HEARTBEAT_OK_TOKEN.replace("_", "") in response.upper().replace("_", ""):
                    logger.info("Heartbeat: OK")
                else:
                    logger.info("Heartbeat: completed task")
            except Exception as e:
                logger.error("Heartbeat execution failed: {}", e)
