# План работы v0.5 — выполнено

## Шаги разработки

| Шаг | Задача | Файл | Статус |
|-----|--------|------|--------|
| 1 | Добавить `project(action="send_files")` | `gigabot/agent/tools/filesystem.py` | ✅ |
| 2 | Промпт: «отправь файл» ≠ «прочитай», правило 2.1 | `gigabot/agent/context.py` | ✅ |
| 3 | Усилить ошибку при `file(write)` без content | `gigabot/agent/tools/filesystem.py` | ✅ |
| 4 | RAG: ограничение путей workspace | — | Отложено (не обязательно) |
| 4a | RAG: исправление вызова embeddings (texts=), EmbeddingsGigaR, батчинг; пути из [file:] в loop | `gigachat_provider.py`, `rag.py`, `config/schema.py`, `loop.py` | ✅ |
| 5 | Документ деплоя и тестов | `gigabot/docs/DEPLOY-v0.5.md` | ✅ |

## Изменённые файлы

- **filesystem.py**: enum и handler `send_files`; усиленное сообщение при пустом `content` в `_write`.
- **context.py**: правило для вложенных файлов (прислать/отправить → send_files + message); описание project с send_files; ПРАВИЛО 2.1.
- **gigachat_provider.py**: вызов `embeddings(texts=..., model=...)` вместо `input=` (совместимость с SDK).
- **config/schema.py**: модель эмбеддингов по умолчанию `EmbeddingsGigaR`.
- **rag.py**: пакетная обработка чанков (`_EMBED_BATCH_SIZE = 5`); использование `embed_model` из конфига.
- **loop.py**: подстановка `file_path` из `[file: ...]` для `index_file` (было и раньше, зафиксировано в доке).
- **docs/DEPLOY-v0.5.md**: команды деплоя, таблица тестов, чек-лист, описание RAG.

## Деплой и тесты

См. **docs/DEPLOY-v0.5.md**.

Команды деплоя (на сервере):

```bash
cd ~/gigabot && git pull origin main && pip install -e . && sudo systemctl restart gigabot
sudo journalctl -u gigabot -f
```

Тесты в системе (в Telegram):

1. «Пришли файлы из Тест/Сметы» → в чат приходят файлы.
2. «Пришли все файлы из Тест» → файлы из всего проекта.
3. «Создай файл и отправь» (без содержания) → бот спрашивает, что записать.
4. PDF + «Добавь в базу знаний test» → index_file OK.
5. «Найди в базе test информацию о …» → релевантные фрагменты.
