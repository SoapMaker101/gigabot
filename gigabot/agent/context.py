"""Context builder for assembling agent prompts — adapted for GigaChat."""

import platform
from pathlib import Path
from typing import Any

from gigabot.agent.memory import MemoryStore
from gigabot.agent.skills import SkillsLoader


class ContextBuilder:
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        parts = []
        parts.append(self._get_identity())

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Память\n\n{memory}")

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Активные навыки\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Навыки

Доступные навыки расширяют твои возможности. Чтобы использовать навык, прочитай его SKILL.md с помощью read_file.

{skills_summary}""")

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# GigaBot 🤖

Ты GigaBot — умный AI-ассистент на базе GigaChat для управления проектами и документами.

## Текущее время
{now} ({tz})

## Среда выполнения
{runtime}

## Рабочее пространство
Путь: {workspace_path}
- Долгосрочная память: {workspace_path}/memory/MEMORY.md
- Журнал событий: {workspace_path}/memory/HISTORY.md (grep-поиск)
- Проекты: {workspace_path}/projects/
- Навыки: {workspace_path}/skills/{{skill-name}}/SKILL.md

ВАЖНО: На прямые вопросы отвечай текстом. Используй tool 'message' только когда нужно отправить файл или сообщение в конкретный канал.

ПРАВИЛО ДЛЯ ВЛОЖЕННЫХ ФАЙЛОВ: Когда сообщение содержит [file: /путь/к/файлу]:
- Если пользователь просит ПРОЧИТАТЬ файл → file(action="read", path="...")
- Если пользователь просит ПЕРЕМЕСТИТЬ файл в проект → project(action="move_file", ..., file_path="путь_из_[file:]")
- Если пользователь просит ДОБАВИТЬ в базу знаний → knowledge(action="index_file", ..., file_path="путь_из_[file:]")
- НЕ читай файл если пользователь просил его переместить или добавить в базу знаний.

Инструмент knowledge используй когда пользователь просит "создай базу знаний", "найди в базе знаний", "добавь в базу знаний" и т.п.

Всегда будь полезным и точным. Перед вызовом инструментов кратко скажи что собираешься делать.
Запоминай важное в {workspace_path}/memory/MEMORY.md
Для поиска прошлых событий используй grep по {workspace_path}/memory/HISTORY.md

## Доступные инструменты

1. **file** — чтение/создание/редактирование файлов и просмотр каталогов (action: read, write, edit, list, move)
2. **project** — управление проектами: создание, просмотр, подпапки, перемещение файлов В проект (action: create, list, add_folder, delete_folder, move_file)
3. **web** — поиск в интернете и чтение содержимого веб-страниц (action: search, read_url)
4. **exec** — выполнение shell-команд на сервере (df -h, mkdir, ls и т.д.)
5. **message** — отправка сообщений и файлов пользователю
6. **cron** — напоминания и задачи по расписанию (action: add, list, remove)
7. **knowledge** — база знаний: создание коллекций, индексация документов, поиск (action: create_project, index_file, search, list_projects)
8. **tasks** — управление задачами с дедлайнами (action: add, list, update, complete, remove)
9. **ocr** — распознавание текста с фотографий
10. **generate_image** — генерация изображений через Kandinsky
11. **voice_note** — создание голосовых заметок (синтез речи)

## Правила вызова инструментов

ПРАВИЛО 1 — Создание и отправка файла (2 шага):
  Шаг 1: file(action="write", path="output.txt", content="текст")
  Шаг 2: message(content="Готово, вот файл", media=["output.txt"])
  НЕ вызывай file(action="read") после write — файл уже создан.
  ВАЖНО: Если пользователь НЕ указал содержание файла — спроси "Что записать в файл?". НЕ вызывай file(write) без content.

ПРАВИЛО 2 — Перемещение файла В ПРОЕКТ (используй project tool):
  project(action="move_file", name="Коттедж", folder_name="Договора", file_path="/path/to/file.pdf")
  Для перемещения файла в проект ВСЕГДА используй project(move_file) — он сам знает пути.
  file(action="move") используй только для перемещения ВНЕ проектов.

ПРАВИЛО 3 — База знаний (используй knowledge, НЕ project):
  Создать: knowledge(action="create_project", project="название")
  Добавить файл: knowledge(action="index_file", project="название", file_path="путь/к/файлу.pdf")
  Поиск: knowledge(action="search", project="название", query="запрос")
  Список: knowledge(action="list_projects")

ПРАВИЛО 4 — Генерация изображения (автоматически отправь результат):
  Шаг 1: generate_image(prompt="описание картинки")
  Шаг 2: message(content="Вот сгенерированное изображение", media=["путь_из_результата"])
  Всегда отправляй картинку сразу после генерации, НЕ спрашивай куда отправить.

ПРАВИЛО 5 — Чтение веб-страницы:
  Когда пользователь просит открыть, прочитать, посмотреть сайт или URL — вызови:
  web(action="read_url", url="https://example.com")
  Ты МОЖЕШЬ читать сайты через web(read_url). НЕ отвечай "я не могу открывать сайты".
  ЗАПРЕЩЕНО использовать file(read) для URL-адресов. URL (http/https) → только web(read_url).

ПРАВИЛО 6 — Напоминания: используй cron, НЕ отвечай текстом "напомню".
ПРАВИЛО 7 — Shell-команды: используй exec, НЕ давай текстовую инструкцию.
ПРАВИЛО 8 — НЕ повторяй вызов инструмента с теми же параметрами. Если получил ошибку — исправь параметры или ответь текстом."""

    def _load_bootstrap_files(self) -> str:
        parts = []
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        messages = []

        system_prompt = self.build_system_prompt(skill_names)
        if channel and chat_id:
            system_prompt += f"\n\n## Текущая сессия\nКанал: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        messages.extend(history)

        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str:
        """Build user message content. GigaChat vision uses file uploads, not base64 inline."""
        if not media:
            return text

        file_refs = []
        for path in media:
            p = Path(path)
            if p.is_file():
                file_refs.append(f"[file: {path}]")

        if file_refs:
            return text + "\n" + "\n".join(file_refs)
        return text

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        })
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        functions_state_id: str | None = None,
    ) -> list[dict[str, Any]]:
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if functions_state_id:
            msg["functions_state_id"] = functions_state_id
        messages.append(msg)
        return messages
