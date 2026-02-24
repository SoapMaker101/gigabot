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
Когда пользователь просит создать и отправить файл: используй write_file(path, content), затем message(content="...", media=[path]).

ПРАВИЛО ДЛЯ ВЛОЖЕННЫХ ФАЙЛОВ: Когда сообщение содержит [file: /путь/к/файлу], вызови read_file с этим путём.
RAG-инструменты используй только когда пользователь явно просит "найди в базе знаний" или "добавь в RAG".

Всегда будь полезным и точным. Перед вызовом инструментов кратко скажи что собираешься делать.
Запоминай важное в {workspace_path}/memory/MEMORY.md
Для поиска прошлых событий используй grep по {workspace_path}/memory/HISTORY.md"""

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
    ) -> list[dict[str, Any]]:
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        messages.append(msg)
        return messages
