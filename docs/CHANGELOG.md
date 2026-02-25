# Changelog

## 0.5.0 (2026-02-25)

### Отправка файлов из проекта (P0)
- **project(send_files)** — новый action: по имени проекта и опционально папке возвращает пути файлов и инструкцию вызвать `message(media=[...])` для отправки пользователю.
- **Промпт**: правило 2.1 и блок про вложения — «пришли/отправь файл» → не `file(read)`, а `project(send_files)` + `message(media=[...])`.

### file(write) без content (P1)
- При пустом `content` возвращается жёсткая ошибка с требованием спросить у пользователя, что записать, и не вызывать `file(write)` повторно без content.

### RAG (база знаний)
- Исправлен вызов API эмбеддингов в провайдере: `embeddings(texts=..., model=...)` вместо `input=` (совместимость с SDK GigaChat).
- Модель эмбеддингов по умолчанию: **EmbeddingsGigaR** (настраивается в `RAGConfig.embed_model`).
- Пакетная обработка чанков при индексации (размер батча 5) для стабильной работы API.
- Пути к файлам из Telegram (`[file: путь]`) подставляются в `knowledge(index_file)` через патч в loop.

### Документация
- **DEPLOY-v0.5.md** — команды деплоя на сервер, таблица тестов после деплоя (в т.ч. отправка файлов, RAG), чек-лист и откат.
- **PLAN-v0.5.md** — добавлен итог v0.5 с таблицей выполненных задач.
- **WORK-PLAN-v0.5-done.md** — отражены изменения по RAG (embeddings, EmbeddingsGigaR, батчинг).

---

## 0.4.0 (2026-02-25)

### project(move_file) — перемещение файлов в проекты
- Новый action `move_file` в ProjectTool — бот сам знает пути к проектам
- Если подпапка не указана — возвращает список доступных подпапок (не кладёт в корень)
- Очистка Telegram ID из имени файла (`BQACAgI..._05_Руководство...pdf` → `Руководство...pdf`)

### Auto-fill file_path
- Когда модель вызывает move_file/index_file без file_path, а в сообщении есть `[file:]` — путь подставляется автоматически
- Решает проблему GigaChat, который видит путь в тексте, но не кладёт в аргументы tool call

### ChromaDB v0.6 совместимость
- `_list_collection_names()` работает и с v0.5 (объекты) и v0.6 (строки)
- knowledge(create_project) и knowledge(list_projects) — подтверждено тестами

### web(read_url)
- Переименование fetch → read_url (+ обратная совместимость)
- Web fallback: если модель не вызвала web tool при запросе с URL — вызывается автоматически
- Усилено описание tool для лучшего matching моделью

### System prompt v3
- Контекстное правило для `[file:]`: читай / перемещай / индексируй в зависимости от запроса
- Правила для write без content, web(read_url), project(move_file)
- Явный запрет file(read) для URL-адресов

### PDF чтение
- Исправлен cffi на сервере (libffi-dev + python3.11-dev)
- Обновлена SERVER-INSTALL.md с раздел "Решение проблем"

### Известные проблемы (решены в v0.5)
- "Создай файл и отправь" без содержания — исправлено в v0.5 (жёсткая ошибка + промпт)
- "Пришли файл из проекта" — исправлено в v0.5 (project(send_files) + правило 2.1)
- RAG (index_file, search) — исправлено в v0.5 (embeddings API, EmbeddingsGigaR, батчинг)
- readability-lxml на сервере — по-прежнему серверная задача (P2)

---

## 0.3.0 (2026-02-24)

### Защита от зацикливания (P0)
- Anti-loop: если tool вызван 3 раза подряд с одинаковыми аргументами — цикл прерывается, бот отвечает текстом
- `max_iterations` снижен с 20 до 7 — ограничивает расход токенов даже без цикла
- Подтверждено в тесте: `file(move)` без destination — 3 вызова + стоп (было 12+)

### Переименование RAG → knowledge (P1)
- Tool `rag` переименован в `knowledge` — GigaChat теперь его видит и вызывает
- Description упрощён до 1 строки
- Подтверждено в тесте: "Создай базу знаний test" → `knowledge(create_project)` вызван (раньше отвечал "за рамками возможностей")

### Системный промпт переписан (P1)
- 7 конкретных правил вызова с пошаговыми примерами вместо абстрактных ВАЖНО
- Правила для write+send, move с destination, knowledge, generate_image+auto-send, cron, exec, anti-repeat

### Улучшенные сообщения об ошибках (P1)
- `file(read/write/move)` и `knowledge(create/index/search)` — ошибки содержат пример правильного вызова

### web_fetch — отладка (P2)
- Подробное логирование: URL → статус → тип ошибки
- Раздельные catch: ConnectError, Timeout, HTTPStatusError
- Проверка import readability с понятным сообщением

### Известные проблемы (остались на v0.4)
- GigaChat не передаёт content при абстрактных запросах ("создай файл и отправь" без указания содержимого)
- GigaChat не знает пути к проектам при move — не может составить `projects/Коттедж/Договора/`
- ChromaDB v0.6.0: `list_collections` API изменился — ломает create_project/list_projects
- web(fetch) не вызывается — модель отвечает текстом "не могу открывать сайты"

---

## 0.2.0 (2026-02-24)

### Исправления по результатам тестирования

**SaluteSpeech (критичное)**
- Исправлен OAuth: `Authorization: Basic {base64}` + `RqUID` + body без `grant_type`
- Content-Type для ogg: `audio/ogg;codecs=opus`
- Config упрощён: одно поле `credentials` (base64) вместо client_id + client_secret

**Консолидация tools (17 → 12)**
- `file` — объединил read/write/edit/list/move (5 actions)
- `project` — объединил create/list/add_folder/delete_folder (4 actions)
- `web` — объединил search/fetch (2 actions)
- GigaChat лучше различает 12 tools чем 17

**System prompt**
- Явный список всех 12 инструментов с описаниями
- Правила: "сначала write, потом message", "для напоминаний — cron", "для команд — exec"
- RAG vs project разграничение

**Файлы**
- message tool проверяет существование файлов перед отправкой
- DOCX: теперь читает таблицы (не только параграфы)
- RAG description обновлён: "НЕ путать с project"

**Kandinsky**
- Генерация через отдельный вызов GigaChat без functions (text2image)
- Парсинг `<img src="FILE_ID"/>` из ответа

---

## 0.1.0 (2026-02-24)

### Первый релиз

- Полноценный AI-агент на базе GigaChat-2-Max
- Прямая интеграция через gigachat SDK (без litellm/gpt2giga)
- Telegram-бот с поддержкой текста, фото, голоса, документов

### Инструменты (17 штук)

- **Файловая система**: read_file, write_file, edit_file, list_dir, create_project, move_file, list_projects
- **RAG**: rag (create_project, index_file, index_folder, search, list_projects, delete_project)
- **OCR**: ocr (Tesseract, русский + английский)
- **Kandinsky**: generate_image (генерация через GigaChat)
- **Задачи**: tasks (add, list, update, remove, complete с дедлайнами)
- **Голос**: voice_note (SaluteSpeech TTS)
- **Веб**: web_search (Brave), web_fetch
- **Система**: exec, message, spawn, cron

### Каналы

- Telegram (python-telegram-bot, long polling)
- SaluteSpeech STT для голосовых сообщений

### Инфраструктура

- Долгосрочная память (MEMORY.md + HISTORY.md)
- Система навыков (SKILL.md)
- Фоновые подагенты
- Cron-планировщик
- Heartbeat (проверка задач каждые 30 мин)
- Systemd-сервис

### Исправления при первом деплое

- GigaChat API требует JSON для результатов функций — автооборачивание в `{"result": ...}`
- Поддержка `functions_state_id` для корректных цепочек вызовов
- `function_call: "auto"` при наличии функций
