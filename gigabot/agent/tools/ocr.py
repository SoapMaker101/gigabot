"""OCR tool — text recognition from images using Tesseract."""

from pathlib import Path
from typing import Any

from gigabot.agent.tools.base import Tool


class OCRTool(Tool):
    """Extract text from images via Tesseract OCR."""

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def description(self) -> str:
        return "Распознать текст с изображения (OCR через Tesseract)"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Путь к изображению для распознавания",
                },
                "lang": {
                    "type": "string",
                    "description": "Языки распознавания (например 'rus+eng')",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, file_path: str, lang: str = "rus+eng", **kwargs: Any) -> str:
        try:
            import pytesseract
        except ImportError:
            return (
                "Ошибка: pytesseract не установлен. "
                "Установите: pip install pytesseract  "
                "и убедитесь, что Tesseract OCR доступен в PATH."
            )

        try:
            from PIL import Image
        except ImportError:
            return "Ошибка: Pillow не установлен. Установите: pip install Pillow"

        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Ошибка: файл не найден: {file_path}"
        if not p.is_file():
            return f"Ошибка: не является файлом: {file_path}"

        try:
            image = Image.open(p)
            text = pytesseract.image_to_string(image, lang=lang)
            text = text.strip()
            if not text:
                return "Текст на изображении не обнаружен."
            return text
        except pytesseract.TesseractNotFoundError:
            return (
                "Ошибка: Tesseract не найден в системе. "
                "Установите Tesseract OCR: https://github.com/tesseract-ocr/tesseract"
            )
        except Exception as e:
            return f"Ошибка OCR: {e}"
