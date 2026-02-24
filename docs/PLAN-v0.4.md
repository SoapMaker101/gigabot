ав# GigaBot v0.4 — План исправлений

## Контекст

GigaBot v0.3 — AI-агент на базе GigaChat-2-Max, работает через Telegram.
Сервер: Ubuntu 24.04, 4 vCPU, 16 GB RAM, user=gigabot, path=~/gigabot

## Результаты тестов v0.3 (24.02.2026)

### Работает:
- Anti-loop: 3 одинаковых вызова → стоп (file/move, file/write) — подтверждено
- knowledge tool вызывается (раньше rag игнорировался)
- write+send работает когда content указан явно (write → message, 2 шага)
- Список проектов, отчёт.docx — без проблем

### Не работает (4 проблемы):

#### ПРОБЛЕМА A: GigaChat не передаёт content при абстрактных write (P1)

**Симптом:** "Создай hello.txt и отправь" → file(write, path="hello.txt") БЕЗ content → ошибка → loop → стоп.
Когда content указан явно ("с содержанием Привет") — работает идеально.

**Корневая причина:** GigaChat не придумывает content самостоятельно если пользователь его не указал.

**Решение:** В system prompt добавить правило: "Если пользователь не указал содержание файла — спроси что записать. НЕ вызывай file(write) без content."

**Файлы:** `context.py`

#### ПРОБЛЕМА B: GigaChat не знает пути к проектам при move (P1)

**Симптом:** "Перемести файл в Коттедж/Договора" → file(move) без destination, или с неправильным путём. Модель не знает что projects/ — это workspace/projects/.

**Решение (Вариант А — новый action):** Добавить `project(action="move_file", name="Коттедж", folder="Договора", file_path="/path/to/file.pdf")`. Tool сам соберёт путь `workspace/projects/Коттедж/Договора/file.pdf`.

**Файлы:** `filesystem.py` (ProjectTool), `context.py` (промпт)

#### ПРОБЛЕМА C: ChromaDB v0.6.0 — сломан API (P1)

**Симптом:** knowledge(create_project) → ошибка `list_collections only returns collection names`.

**Корневая причина:** ChromaDB 0.6.0 изменил API: `list_collections()` теперь возвращает список строк (имён), а не объектов Collection. Код вызывает `c.name` на строке.

**Решение:** Обновить `_create_project`, `_list_projects` под новый API:
- `list_collections()` → возвращает `list[str]` в v0.6
- Использовать `get_collection(name)` для получения объекта

**Файлы:** `rag.py`

#### ПРОБЛЕМА D: web(fetch) не вызывается (P2)

**Симптом:** "Открой сайт example.com" → текстом "не могу открывать сайты" (tool не вызывается).

**Решение (промпт + переименование):**
1. Переименовать action `fetch` → `read_url` (более понятно для модели)
2. Добавить правило в промпт: "Когда пользователь просит открыть/прочитать сайт → web(action='read_url', url='...')"

**Файлы:** `web.py`, `context.py`

#### ПРОБЛЕМА E: pdfplumber не установлен на сервере (P2)

**Симптом:** При чтении PDF → "requires pdfplumber package".

**Решение:** Добавить pdfplumber в зависимости проекта.

**Файлы:** `pyproject.toml`

## Приоритеты v0.4

| # | Задача | Файлы | Приоритет |
|---|--------|-------|-----------|
| 1 | project(move_file) — новый action | filesystem.py | P1 |
| 2 | Промпт: правило для move_file + write без content + web fetch | context.py | P1 |
| 3 | ChromaDB v0.6 — обновить list_collections/create API | rag.py | P1 |
| 4 | web: rename fetch → read_url + промпт | web.py, context.py | P2 |
| 5 | pdfplumber в зависимости | pyproject.toml | P2 |

## Деплой

```bash
cd ~/gigabot
source .venv/bin/activate
git pull origin main
pip install -e .
sudo systemctl restart gigabot
sudo journalctl -u gigabot -f
```

## Тесты после деплоя

| # | Тест | Ожидаемый результат |
|---|------|---------------------|
| 1 | "Перемести файл X в Коттедж/Договора" | project(move_file) → файл перемещён |
| 2 | "Создай файл hello.txt и отправь" | Спросит содержание ИЛИ создаст с дефолтным |
| 3 | "Создай базу знаний test" | knowledge(create_project) → OK |
| 4 | "Открой сайт example.com" | web(read_url) → содержимое страницы |
| 5 | Отправить PDF файл | Прочитается через pdfplumber |
