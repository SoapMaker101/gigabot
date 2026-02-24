"""SaluteSpeech tool — voice synthesis (TTS) for creating voice notes."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from gigabot.agent.tools.base import Tool
from gigabot.config.schema import SaluteSpeechConfig


SALUTE_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
SALUTE_TTS_URL = "https://smartspeech.sber.ru/rest/v1/text:synthesize"


class _TokenCache:
    """Reusable OAuth token with expiry tracking."""

    def __init__(self) -> None:
        self.token: str | None = None
        self.expires_at: float = 0.0

    @property
    def valid(self) -> bool:
        return self.token is not None and time.time() < self.expires_at


class SaluteSpeechTool(Tool):
    """Synthesize speech from text using SaluteSpeech TTS API."""

    def __init__(
        self,
        salute_speech_config: SaluteSpeechConfig,
        workspace: Path,
    ) -> None:
        self._config = salute_speech_config
        self._workspace = workspace
        self._token_cache = _TokenCache()

    @property
    def name(self) -> str:
        return "voice_note"

    @property
    def description(self) -> str:
        return "Создать голосовую заметку (синтез речи через SaluteSpeech)"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Текст для озвучивания",
                },
                "save_to": {
                    "type": "string",
                    "description": "Путь для сохранения файла (необязательно)",
                },
                "voice": {
                    "type": "string",
                    "description": "Голос для синтеза (необязательно)",
                },
            },
            "required": ["text"],
        }

    async def execute(
        self,
        text: str,
        save_to: str | None = None,
        voice: str | None = None,
        **kwargs: Any,
    ) -> str:
        if not self._config.credentials:
            return (
                "Ошибка: не настроены учётные данные SaluteSpeech "
                "(credentials)."
            )

        token = await self._get_token()
        if not token:
            return "Ошибка: не удалось получить токен SaluteSpeech."

        tts_voice = voice or self._config.tts_voice

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    SALUTE_TTS_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/text",
                    },
                    params={"voice": tts_voice, "format": "wav16"},
                    content=text.encode("utf-8"),
                    timeout=60.0,
                )
                resp.raise_for_status()
                audio_bytes = resp.content
        except httpx.HTTPStatusError as e:
            logger.error("SaluteSpeech TTS HTTP error: {} {}", e.response.status_code, e.response.text[:200])
            return f"Ошибка синтеза речи: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error("SaluteSpeech TTS request failed: {}", e)
            return f"Ошибка синтеза речи: {e}"

        save_path = self._resolve_save_path(save_to)
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(audio_bytes)
        except Exception as e:
            return f"Ошибка при сохранении аудио: {e}"

        logger.info("Voice note saved to {}", save_path)
        return str(save_path)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_token(self) -> str | None:
        """Obtain or reuse a cached SaluteSpeech OAuth token."""
        if self._token_cache.valid:
            return self._token_cache.token

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    SALUTE_OAUTH_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                        "RqUID": str(uuid.uuid4()),
                        "Authorization": f"Basic {self._config.credentials}",
                    },
                    data={"scope": self._config.scope},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
                self._token_cache.token = data["access_token"]
                self._token_cache.expires_at = (
                    time.time() + data.get("expires_in", 1800) - 60
                )
                return self._token_cache.token
        except Exception as e:
            logger.error("Failed to obtain SaluteSpeech token: {}", e)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_save_path(self, save_to: str | None) -> Path:
        if save_to:
            p = Path(save_to).expanduser()
            if not p.is_absolute():
                return self._workspace / p
            return p

        out_dir = self._workspace.parent / "voice_notes"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return out_dir / f"{timestamp}.wav"
