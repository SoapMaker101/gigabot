"""Tasks tool — task management with JSON storage."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from gigabot.agent.tools.base import Tool
from gigabot.cron.service import CronService
from gigabot.cron.types import CronSchedule


class TasksTool(Tool):
    """Manage tasks: create, list, update status, complete, remove."""

    def __init__(
        self,
        workspace: Path,
        cron_service: CronService | None = None,
    ) -> None:
        self._workspace = workspace
        self._cron = cron_service
        self._storage_dir = workspace.parent / "tasks"
        self._storage_file = self._storage_dir / "tasks.json"
        self._channel = ""
        self._chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set session context for cron-based deadline reminders."""
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "tasks"

    @property
    def description(self) -> str:
        return "Управление задачами: создание, просмотр, обновление статуса"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "update", "remove", "complete"],
                    "description": "Действие: add, list, update, remove, complete",
                },
                "title": {
                    "type": "string",
                    "description": "Название задачи (для add/update)",
                },
                "project": {
                    "type": "string",
                    "description": "Проект, к которому привязана задача",
                },
                "deadline": {
                    "type": "string",
                    "description": "Дедлайн в формате ISO (например '2026-03-01T12:00:00')",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Приоритет задачи",
                },
                "task_id": {
                    "type": "string",
                    "description": "ID задачи (для update/remove/complete)",
                },
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done"],
                    "description": "Статус задачи (для update)",
                },
                "note": {
                    "type": "string",
                    "description": "Заметка к задаче",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        title: str | None = None,
        project: str | None = None,
        deadline: str | None = None,
        priority: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        note: str | None = None,
        **kwargs: Any,
    ) -> str:
        if action == "add":
            return self._add(title, project, deadline, priority, note)
        if action == "list":
            return self._list(project, status)
        if action == "update":
            return self._update(task_id, title, project, deadline, priority, status, note)
        if action == "remove":
            return self._remove(task_id)
        if action == "complete":
            return self._complete(task_id)
        return f"Неизвестное действие: {action}"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_tasks(self) -> list[dict[str, Any]]:
        if not self._storage_file.exists():
            return []
        try:
            data = json.loads(self._storage_file.read_text(encoding="utf-8"))
            return data.get("tasks", [])
        except Exception as e:
            logger.warning("Failed to load tasks: {}", e)
            return []

    def _save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "tasks": tasks}
        self._storage_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add(
        self,
        title: str | None,
        project: str | None,
        deadline: str | None,
        priority: str | None,
        note: str | None,
    ) -> str:
        if not title:
            return "Ошибка: необходимо указать title для создания задачи."

        now = datetime.now().isoformat(timespec="seconds")
        task: dict[str, Any] = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "project": project or "",
            "status": "todo",
            "priority": priority or "medium",
            "deadline": deadline or "",
            "notes": [],
            "created_at": now,
            "updated_at": now,
        }

        if note:
            task["notes"].append({"text": note, "at": now})

        tasks = self._load_tasks()
        tasks.append(task)
        self._save_tasks(tasks)

        self._schedule_deadline_reminder(task)

        lines = [
            f"Задача создана: {task['title']}",
            f"  ID: {task['id']}",
            f"  Приоритет: {task['priority']}",
        ]
        if task["project"]:
            lines.append(f"  Проект: {task['project']}")
        if task["deadline"]:
            lines.append(f"  Дедлайн: {task['deadline']}")
        return "\n".join(lines)

    def _list(self, project: str | None, status: str | None) -> str:
        tasks = self._load_tasks()

        if project:
            tasks = [t for t in tasks if t.get("project", "").lower() == project.lower()]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]

        if not tasks:
            return "Задач не найдено."

        priority_order = {"high": 0, "medium": 1, "low": 2}
        tasks.sort(key=lambda t: priority_order.get(t.get("priority", "medium"), 1))

        lines: list[str] = [f"Задачи ({len(tasks)}):"]
        for t in tasks:
            status_icon = {"todo": "⬜", "in_progress": "🔄", "done": "✅"}.get(
                t.get("status", "todo"), "⬜"
            )
            prio_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                t.get("priority", "medium"), "🟡"
            )
            line = f"  {status_icon} {prio_icon} [{t['id']}] {t['title']}"
            if t.get("project"):
                line += f" ({t['project']})"
            if t.get("deadline"):
                line += f" — до {t['deadline']}"
            lines.append(line)

        return "\n".join(lines)

    def _update(
        self,
        task_id: str | None,
        title: str | None,
        project: str | None,
        deadline: str | None,
        priority: str | None,
        status: str | None,
        note: str | None,
    ) -> str:
        if not task_id:
            return "Ошибка: необходимо указать task_id для обновления."

        tasks = self._load_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return f"Ошибка: задача {task_id} не найдена."

        now = datetime.now().isoformat(timespec="seconds")
        updated_fields: list[str] = []

        if title is not None:
            task["title"] = title
            updated_fields.append("title")
        if project is not None:
            task["project"] = project
            updated_fields.append("project")
        if deadline is not None:
            task["deadline"] = deadline
            updated_fields.append("deadline")
            self._schedule_deadline_reminder(task)
        if priority is not None:
            task["priority"] = priority
            updated_fields.append("priority")
        if status is not None:
            task["status"] = status
            updated_fields.append("status")
        if note is not None:
            task.setdefault("notes", []).append({"text": note, "at": now})
            updated_fields.append("note")

        task["updated_at"] = now
        self._save_tasks(tasks)

        return f"Задача {task_id} обновлена ({', '.join(updated_fields)}): {task['title']}"

    def _remove(self, task_id: str | None) -> str:
        if not task_id:
            return "Ошибка: необходимо указать task_id для удаления."

        tasks = self._load_tasks()
        before = len(tasks)
        tasks = [t for t in tasks if t["id"] != task_id]

        if len(tasks) == before:
            return f"Ошибка: задача {task_id} не найдена."

        self._save_tasks(tasks)
        return f"Задача {task_id} удалена."

    def _complete(self, task_id: str | None) -> str:
        if not task_id:
            return "Ошибка: необходимо указать task_id."

        tasks = self._load_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return f"Ошибка: задача {task_id} не найдена."

        task["status"] = "done"
        task["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_tasks(tasks)

        return f"Задача {task_id} завершена: {task['title']} ✅"

    # ------------------------------------------------------------------
    # Deadline reminders
    # ------------------------------------------------------------------

    def _schedule_deadline_reminder(self, task: dict[str, Any]) -> None:
        """Create a cron one-shot reminder for the task deadline."""
        if not self._cron or not task.get("deadline"):
            return
        if not self._channel or not self._chat_id:
            return

        try:
            dt = datetime.fromisoformat(task["deadline"])
            at_ms = int(dt.timestamp() * 1000)
        except (ValueError, TypeError):
            return

        if at_ms <= int(datetime.now().timestamp() * 1000):
            return

        try:
            self._cron.add_job(
                name=f"deadline:{task['id']}",
                schedule=CronSchedule(kind="at", at_ms=at_ms),
                message=f"⏰ Дедлайн задачи: {task['title']}",
                deliver=True,
                channel=self._channel,
                to=self._chat_id,
                delete_after_run=True,
            )
        except Exception as e:
            logger.warning("Failed to schedule deadline reminder for {}: {}", task["id"], e)
