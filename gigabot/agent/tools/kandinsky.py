"""Kandinsky tool — image generation via GigaChat."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from loguru import logger

from gigabot.agent.tools.base import Tool
from gigabot.providers.gigachat_provider import GigaChatProvider


class KandinskyTool(Tool):
    """Generate images using Kandinsky through GigaChat API."""

    def __init__(self, provider: GigaChatProvider, workspace: Path) -> None:
        self._provider = provider
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return "Сгенерировать изображение по описанию с помощью Kandinsky через GigaChat"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Описание изображения для генерации",
                },
                "save_to": {
                    "type": "string",
                    "description": "Путь для сохранения (необязательно)",
                },
                "width": {
                    "type": "integer",
                    "description": "Ширина изображения в пикселях",
                },
                "height": {
                    "type": "integer",
                    "description": "Высота изображения в пикселях",
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        save_to: str | None = None,
        width: int | None = None,
        height: int | None = None,
        **kwargs: Any,
    ) -> str:
        size_hint = ""
        if width and height:
            size_hint = f" Размер: {width}x{height}."

        generation_prompt = f"Нарисуй изображение: {prompt}.{size_hint}"

        try:
            response = await self._provider.chat(
                messages=[{"role": "user", "content": generation_prompt}],
                model="GigaChat-2-Max",
            )
        except Exception as e:
            logger.error("GigaChat image generation request failed: {}", e)
            return f"Ошибка при запросе генерации изображения: {e}"

        file_id = self._extract_file_id(response)
        if not file_id:
            content = response.content or ""
            if content:
                return f"GigaChat не вернул изображение. Ответ: {content}"
            return "Ошибка: GigaChat не вернул идентификатор изображения."

        try:
            image_bytes = self._provider.get_image(file_id)
        except Exception as e:
            logger.error("Failed to download generated image {}: {}", file_id, e)
            return f"Ошибка при загрузке изображения: {e}"

        save_path = self._resolve_save_path(save_to)
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(image_bytes)
        except Exception as e:
            return f"Ошибка при сохранении изображения: {e}"

        logger.info("Image generated and saved to {}", save_path)
        return str(save_path)

    def _extract_file_id(self, response: Any) -> str | None:
        """Extract image file_id from GigaChat response content or function_call."""
        if response.tool_calls:
            for tc in response.tool_calls:
                args = tc.arguments or {}
                if "file_id" in args:
                    return args["file_id"]

        content = response.content or ""
        match = re.search(r'<img\s+src="([^"]+)"', content)
        if match:
            return match.group(1)

        match = re.search(r"file_id[\"']?\s*[:=]\s*[\"']([a-f0-9\-]+)[\"']", content)
        if match:
            return match.group(1)

        return None

    def _resolve_save_path(self, save_to: str | None) -> Path:
        if save_to:
            p = Path(save_to).expanduser()
            if not p.is_absolute():
                return self._workspace / p
            return p

        out_dir = self._workspace / "generated"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return out_dir / f"{timestamp}.jpg"
