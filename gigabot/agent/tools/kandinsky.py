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
        import json as _json

        from gigachat.models import Chat, Messages, MessagesRole

        size_hint = ""
        if width and height:
            size_hint = f" Размер: {width}x{height}."

        chat = Chat(
            model=self._provider.default_model,
            messages=[
                Messages(role=MessagesRole.SYSTEM, content="Ты — Василий Кандинский."),
                Messages(role=MessagesRole.USER, content=f"Нарисуй: {prompt}.{size_hint}"),
            ],
            function_call="auto",
        )

        try:
            response = self._provider._client.chat(chat)
            content = response.choices[0].message.content or ""

            match = re.search(r'<img\s+src="([^"]+)"', content)
            if not match:
                return _json.dumps(
                    {"result": f"Изображение не было сгенерировано. Ответ модели: {content[:200]}"},
                    ensure_ascii=False,
                )

            file_id = match.group(1)
            image_bytes = self._provider.get_image(file_id)

            save_path = self._resolve_save_path(save_to)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(image_bytes)

            logger.info("Image generated and saved to {}", save_path)
            return _json.dumps(
                {"result": f"Изображение сохранено: {save_path}", "path": str(save_path)},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error("Kandinsky image generation failed: {}", e)
            return _json.dumps({"error": str(e)}, ensure_ascii=False)

    def _resolve_save_path(self, save_to: str | None) -> Path:
        if save_to:
            p = Path(save_to).expanduser()
            if not p.is_absolute():
                return self._workspace / p
            return p

        out_dir = self._workspace / "generated"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return out_dir / f"{timestamp}.jpg"
