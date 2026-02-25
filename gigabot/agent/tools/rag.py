"""RAG tool — ChromaDB + GigaChat Embeddings for knowledge base management."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from loguru import logger

from gigabot.agent.tools.base import Tool
from gigabot.agent.tools.filesystem import _smart_read
from gigabot.config.schema import RAGConfig

_SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".doc", ".xlsx", ".xls"}

_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _normalize_collection_name(name: str) -> str:
    """Convert arbitrary project name to ChromaDB-compatible collection name.

    ChromaDB requires: 3-63 chars, alphanumeric start/end,
    only alphanumeric/underscore/hyphen inside.
    """
    lowered = name.lower().strip()
    result: list[str] = []
    for ch in lowered:
        if ch in _CYRILLIC_TO_LATIN:
            result.append(_CYRILLIC_TO_LATIN[ch])
        elif ch.isascii() and ch.isalnum():
            result.append(ch)
        elif ch in (" ", "_", "-", "."):
            result.append("_")
        else:
            result.append("_")
    normalized = re.sub(r"_+", "_", "".join(result)).strip("_")
    if len(normalized) < 3:
        normalized = normalized.ljust(3, "x")
    if len(normalized) > 63:
        normalized = normalized[:63].rstrip("_")
    return normalized


class RAGTool(Tool):
    """RAG: создание проектов базы знаний, индексация файлов, поиск по документам."""

    def __init__(self, provider: Any, rag_config: RAGConfig) -> None:
        import chromadb

        self._provider = provider
        self._config = rag_config

        chroma_dir = str(Path(rag_config.chroma_dir).expanduser())
        os.makedirs(chroma_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=chroma_dir)

        self._embed_model = rag_config.embed_model
        self._chunk_size = rag_config.chunk_size
        self._chunk_overlap = rag_config.chunk_overlap
        self._top_k = rag_config.top_k

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "knowledge"

    @property
    def description(self) -> str:
        return "База знаний: создать коллекцию, добавить файл, искать по документам"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create_project",
                        "delete_project",
                        "list_projects",
                        "index_file",
                        "index_folder",
                        "search",
                    ],
                    "description": "Действие над базой знаний",
                },
                "project": {
                    "type": "string",
                    "description": "Имя проекта (коллекции)",
                },
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос",
                },
                "file_path": {
                    "type": "string",
                    "description": "Путь к файлу для индексации",
                },
                "folder_path": {
                    "type": "string",
                    "description": "Путь к папке для пакетной индексации",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Количество результатов поиска",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        dispatch = {
            "create_project": self._create_project,
            "delete_project": self._delete_project,
            "list_projects": self._list_projects,
            "index_file": self._index_file,
            "index_folder": self._index_folder,
            "search": self._search,
        }
        handler = dispatch.get(action)
        if handler is None:
            return f"Ошибка: неизвестное действие '{action}'. Допустимые: {', '.join(dispatch)}"
        try:
            return await handler(**kwargs)
        except Exception as e:
            logger.error("RAG tool error (action={}): {}", action, e)
            return f"Ошибка RAG ({action}): {e}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _list_collection_names(self) -> list[str]:
        """Get collection names — compatible with ChromaDB v0.5 and v0.6+."""
        raw = self._client.list_collections()
        if not raw:
            return []
        if isinstance(raw[0], str):
            return raw
        return [c.name for c in raw]

    def _get_or_create_collection(self, project: str):
        col_name = _normalize_collection_name(project)
        return self._client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine", "display_name": project},
        )

    @staticmethod
    def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        if not text or not text.strip():
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start += chunk_size - chunk_overlap
        return chunks

    @staticmethod
    def _read_file(file_path: str) -> str:
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        if not p.is_file():
            raise ValueError(f"Не является файлом: {file_path}")
        return _smart_read(p)

    _MAX_EMBED_CHARS = 6000
    _EMBED_BATCH_SIZE = 5

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        safe = [t[:self._MAX_EMBED_CHARS] if len(t) > self._MAX_EMBED_CHARS else t for t in texts]
        all_embeddings: list[list[float]] = []
        for i in range(0, len(safe), self._EMBED_BATCH_SIZE):
            batch = safe[i : i + self._EMBED_BATCH_SIZE]
            all_embeddings.extend(self._provider.get_embeddings(batch, model=self._embed_model))
        return all_embeddings

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _create_project(self, **kwargs: Any) -> str:
        project = kwargs.get("project")
        if not project:
            return "Ошибка: не указано имя проекта. Пример: knowledge(action='create_project', project='мой_проект')"

        col_name = _normalize_collection_name(project)
        existing = self._list_collection_names()
        if col_name in existing:
            return f"Проект '{project}' уже существует."

        self._client.create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine", "display_name": project},
        )
        return f"Проект '{project}' успешно создан."

    async def _delete_project(self, **kwargs: Any) -> str:
        project = kwargs.get("project")
        if not project:
            return "Ошибка: не указано имя проекта (project)"
        col_name = _normalize_collection_name(project)
        try:
            self._client.delete_collection(name=col_name)
            return f"Проект '{project}' удалён."
        except ValueError:
            return f"Ошибка: проект '{project}' не найден."

    async def _list_projects(self, **kwargs: Any) -> str:
        names = self._list_collection_names()
        if not names:
            return "Нет созданных проектов базы знаний."
        lines: list[str] = []
        for name in names:
            c = self._client.get_collection(name)
            display = (c.metadata or {}).get("display_name", name)
            lines.append(f"  • {display} ({c.count()} документов)")
        return f"Проекты ({len(names)}):\n" + "\n".join(lines)

    async def _index_file(self, **kwargs: Any) -> str:
        project = kwargs.get("project")
        file_path = kwargs.get("file_path")
        if not project:
            return "Ошибка: не указано имя проекта. Пример: knowledge(action='index_file', project='мой_проект', file_path='docs/file.pdf')"
        if not file_path:
            return "Ошибка: не указан путь к файлу. Пример: knowledge(action='index_file', project='мой_проект', file_path='docs/file.pdf')"

        text = self._read_file(file_path)
        if text.startswith("Error"):
            return f"Ошибка чтения файла: {text}"

        chunks = self._chunk_text(text, self._chunk_size, self._chunk_overlap)
        if not chunks:
            return f"Файл '{file_path}' не содержит текста для индексации."

        embeddings = self._embed_texts(chunks)
        collection = self._get_or_create_collection(project)

        source_name = Path(file_path).name
        ids = [f"{source_name}__chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": source_name, "chunk_index": i} for i in range(len(chunks))]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

        return (
            f"Файл '{source_name}' проиндексирован в проект '{project}': "
            f"{len(chunks)} фрагментов."
        )

    async def _index_folder(self, **kwargs: Any) -> str:
        project = kwargs.get("project")
        folder_path = kwargs.get("folder_path")
        if not project:
            return "Ошибка: не указано имя проекта (project)"
        if not folder_path:
            return "Ошибка: не указан путь к папке (folder_path)"

        folder = Path(folder_path).expanduser().resolve()
        if not folder.exists():
            return f"Ошибка: папка не найдена: {folder_path}"
        if not folder.is_dir():
            return f"Ошибка: не является папкой: {folder_path}"

        files = [
            f for f in folder.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
        ]

        if not files:
            return f"В папке '{folder_path}' не найдено поддерживаемых файлов ({', '.join(_SUPPORTED_EXTENSIONS)})."

        indexed = 0
        errors: list[str] = []
        total_chunks = 0

        for file in sorted(files):
            result = await self._index_file(
                action="index_file",
                project=project,
                file_path=str(file),
            )
            if result.startswith("Ошибка") or result.startswith("Файл") and "не содержит" in result:
                errors.append(f"  • {file.name}: {result}")
            else:
                indexed += 1
                try:
                    count = int(result.split(": ")[1].split(" ")[0])
                    total_chunks += count
                except (IndexError, ValueError):
                    pass

        summary = f"Индексация папки '{folder_path}' в проект '{project}' завершена.\n"
        summary += f"Файлов обработано: {indexed}/{len(files)}, фрагментов: {total_chunks}."
        if errors:
            summary += "\n\nОшибки:\n" + "\n".join(errors)
        return summary

    async def _search(self, **kwargs: Any) -> str:
        project = kwargs.get("project")
        query = kwargs.get("query")
        top_k = kwargs.get("top_k", self._top_k)
        if not project:
            return "Ошибка: не указано имя проекта. Пример: knowledge(action='search', project='мой_проект', query='текст запроса')"
        if not query:
            return "Ошибка: не указан поисковый запрос. Пример: knowledge(action='search', project='мой_проект', query='текст запроса')"

        col_name = _normalize_collection_name(project)
        try:
            collection = self._client.get_collection(col_name)
        except ValueError:
            return f"Ошибка: проект '{project}' не найден."

        display = (collection.metadata or {}).get("display_name", project)

        if collection.count() == 0:
            return f"Проект '{display}' пуст — сначала проиндексируйте файлы."

        top_k = min(top_k, collection.count())
        query_embedding = self._embed_texts([query])[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not documents:
            return f"По запросу '{query}' ничего не найдено в проекте '{display}'."

        parts: list[str] = [f"Результаты поиска в '{display}' по запросу: «{query}» (топ-{len(documents)}):\n"]
        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), 1):
            source = meta.get("source", "?") if meta else "?"
            score = 1 - dist
            parts.append(f"--- Результат {i} (релевантность: {score:.2f}, источник: {source}) ---")
            parts.append(doc.strip())
            parts.append("")

        return "\n".join(parts)
