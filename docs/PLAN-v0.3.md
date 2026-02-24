# GigaBot v0.3 — План исправлений

## Контекст

GigaBot — AI-агент на базе GigaChat-2-Max, работает через Telegram.
Репозиторий: https://github.com/SoapMaker101/gigabot
Код: `c:\Прочее\Крипта\nanobot-main\gigabot\`
Сервер: Ubuntu 24.04, 4 vCPU, 16 GB RAM, user=gigabot, path=~/gigabot

## Текущий статус (v0.2.0, тест 24.02.2026)

### Работает (14/22):
- Диалог, создание проектов, список проектов
- Веб-поиск (Brave)
- Чтение DOCX/PDF файлов из Telegram
- **SaluteSpeech STT** (голос → текст) — починено в v0.2
- OCR (Tesseract)
- **Shell exec** (df -h) — починено в v0.2
- **Добавление подпапок** (project add_folder) — починено в v0.2
- **Задачи** (tasks add/list) — починено в v0.2
- **Напоминания** (cron) — починено в v0.2
- **Kandinsky** (generate_image) — починено в v0.2, но не отправляет автоматически

### Не работает (8/22):

#### ПРОБЛЕМА 1: ЛУПЫ (P0 — КРИТИЧНО, сжигает 500k токенов)

**Симптом:** GigaChat вызывает один и тот же tool 10-20 раз подряд, не останавливаясь.

**Случаи:**
1. `file(action="move")` без параметра `destination` — 12+ раз
2. `file(action="read")` → текст ответа → снова read → 20 итераций при RAG index
3. `file(action="read")` при создании+отправке файла — 7 раз

**Корневая причина:** GigaChat получает ошибку "missing required destination" и повторяет вызов с теми же параметрами вместо исправления.

**Решение (3 уровня):**
1. **Anti-loop в `_run_agent_loop`**: если tool вызван 3 раза подряд с одним именем — прервать цикл, вернуть ошибку пользователю
2. **Снизить `max_iterations`**: с 20 до 7 (достаточно для любой задачи, ограничивает ущерб)
3. **Улучшить error messages** в tools: "missing destination. Пример: file(action='move', path='...', destination='...')"

**Файлы для правки:**
- `gigabot/agent/loop.py` — anti-loop + снизить max_iterations
- `gigabot/agent/tools/filesystem.py` — улучшить error messages для move

#### ПРОБЛЕМА 2: RAG не вызывается (P1)

**Симптом:** 
- "Создай базу знаний" → GigaChat отвечает "выходит за рамки моих возможностей" (не вызывает rag tool)
- "Добавь файл в базу знаний" → зацикливается на file("read") + текстовое описание rag вызова (пишет rag(...) в тексте, но не вызывает как function_call)

**Корневая причина:** GigaChat-2-Max не "видит" rag tool среди 12 functions. Возможно description слишком длинный или слишком похож на другие tools.

**Решение:**
1. Упростить description RAG tool до минимума
2. В system prompt добавить конкретный пример: "Для базы знаний вызови rag(action='create_project', project='имя')"
3. Возможно переименовать tool: `rag` → `knowledge` (более понятно для модели)
4. Проверить что rag tool реально регистрируется (может chromadb import падает?)

**Файлы:** `gigabot/agent/tools/rag.py`, `gigabot/agent/context.py`, `gigabot/agent/loop.py`

#### ПРОБЛЕМА 3: web_fetch не работает (P2)

**Симптом:** web(action="fetch", url="https://example.com") → "технические проблемы"

**Корневая причина:** Нужно посмотреть логи — возможно SSL или timeout.

**Файлы:** `gigabot/agent/tools/web.py`

#### ПРОБЛЕМА 4: Kandinsky не отправляет картинку автоматически (P2)

**Симптом:** Генерирует изображение, говорит "скажите куда отправить" вместо автоматической отправки.

**Решение:** В system prompt добавить правило: "После generate_image сразу отправь результат через message(media=[path])"

**Файлы:** `gigabot/agent/context.py`

#### ПРОБЛЕМА 5: Создание файла + отправка — лупы (P2)

**Симптом:** Создаёт файл через file(write), потом 7 раз file(read) прежде чем вызвать message.

**Решение:** Anti-loop из Проблемы 1 + улучшить prompt: "После write_file сразу вызови message"

## Приоритеты v0.3

| # | Задача | Файлы | Приоритет |
|---|--------|-------|-----------|
| 1 | Anti-loop защита (3 одинаковых вызова = стоп) | loop.py | P0 |
| 2 | max_iterations 20 → 7 | loop.py | P0 |
| 3 | Улучшить error messages в tools (примеры вызовов) | filesystem.py, rag.py | P1 |
| 4 | RAG: проверить регистрацию + упростить description | rag.py, loop.py | P1 |
| 5 | System prompt: примеры вызовов для RAG, Kandinsky, move | context.py | P1 |
| 6 | web_fetch: debug ошибки | web.py | P2 |
| 7 | Kandinsky auto-send после генерации | context.py | P2 |

## Что дать в следующем чате

1. Этот файл: `@gigabot/docs/PLAN-v0.3.md`
2. Ключевые файлы для правки:
   - `@gigabot/gigabot/agent/loop.py`
   - `@gigabot/gigabot/agent/context.py`
   - `@gigabot/gigabot/agent/tools/filesystem.py`
   - `@gigabot/gigabot/agent/tools/rag.py`
   - `@gigabot/gigabot/agent/tools/web.py`
3. Сказать: "Реализуй план из PLAN-v0.3.md"

## Конфигурация сервера

- Config: `~/.gigabot/config.json`
- SaluteSpeech: credentials = base64(client_id:client_secret) в поле "credentials"
- Обновление: `cd ~/gigabot && git pull && pip install -e . && sudo systemctl restart gigabot`
- Логи: `sudo journalctl -u gigabot -n 50 --no-pager`
- PowerShell на Windows не работает с кириллическими путями — git push через VPN или с сервера
