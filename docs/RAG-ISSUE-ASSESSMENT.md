# Оценка проблемы RAG: индексация не работает (PDF/DOCX)

## Что видно из логов

### 1. Основная ошибка (причина падения)

```
RAG tool error (action=index_file): GigaChatSyncClient.embeddings() got an unexpected keyword argument 'input'
```

- Возникает при **каждом** вызове `knowledge(index_file, project="Building_Norms", file_path="...")`.
- Не зависит от формата файла: падает и на PDF, и на DOCX.
- Цепочка: пользователь отправляет файл → в сообщении есть `[file: /home/gigabot/.gigabot/media/...]` → модель правильно вызывает `knowledge(index_file, project="Building_Norms", file_path="...")` → RAG tool читает файл, режет на чанки, вызывает **провайдер** за эмбеддингами → провайдер дергает `self._client.embeddings(input=texts, model=model)` → **SDK GigaChat выбрасывает ошибку**: аргумент `input` не поддерживается.

Итог: проблема не в PDF/DOCX и не в путях к файлам, а в том, **как мы вызываем API эмбеддингов** в коде провайдера.

---

### 2. Где именно ошибка в коде

Файл: **`gigabot/providers/gigachat_provider.py`**, метод `get_embeddings`:

```python
def get_embeddings(self, texts: list[str], model: str = "Embeddings") -> list[list[float]]:
    """Get embeddings for RAG via GigaChat Embeddings API."""
    response = self._client.embeddings(input=texts, model=model)  # <-- здесь
    return [item.embedding for item in response.data]
```

Мы передаём в SDK аргументы по имени: `input=texts`, `model=model`.  
Ошибка говорит: у `GigaChatSyncClient.embeddings()` нет параметра с именем `input`. То есть **сигнатура публичного API пакета `gigachat` не совпадает с тем, как мы его вызываем**.

---

### 3. Что говорит документация GigaChat

- В **REST API** (спека в «Документация gigachat.ini»): тело запроса к `/embeddings` действительно содержит поля `input` (массив строк) и `model`. То есть на уровне HTTP мы бы слали `input` и `model`.
- В **официальном примере для Python SDK** в той же доке указано:
  ```python
  response = giga.embeddings(["Hello world!"])
  ```
  То есть в примере передаётся **один позиционный аргумент** — список строк, **без** имени `input`. Отсюда вывод: в Python-обёртке `gigachat` метод, скорее всего, принимает список как первый позиционный аргумент, а не как `input=...`.

Версия пакета в проекте: **`gigachat>=0.2.0,<0.3.0`**. В разных минорных версиях сигнатура могла быть разной (например, только позиционный аргумент или другое имя параметра).

---

### 4. Вторичное сообщение в логах (ChromaDB)

```
Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
```

- Появляется при создании коллекции ChromaDB (например, при `knowledge(create_project, ...)`).
- Это внутренняя телеметрия ChromaDB: колбэк вызывается с другой сигнатурой, чем ожидает код. На работу RAG это не влияет напрямую (коллекция создаётся), но засоряет логи. Решается обновлением ChromaDB или отключением телеметрии.

---

## Почему «ни PDF, ни DOCX не считал»

- Файлы **доходят** до RAG: путь из Telegram подставляется в `file_path`, вызов `knowledge(index_file, project="Building_Norms", file_path="...")` идёт с правильным путём.
- Чтение файла и разбиение на чанки в `rag.py` (в т.ч. через `_smart_read` для PDF/DOCX) **выполняются до** запроса эмбеддингов. То есть сам по себе факт «PDF/DOCX» не является причиной ошибки.
- Падение происходит **на этапе получения эмбеддингов**: вызов `self._client.embeddings(input=texts, model=model)` в провайдере. Из-за этого пользователь видит общую «ошибку при добавлении документа», и кажется, что «ни PDF, ни DOCX не считал» — на самом деле оба не доходят до записи в ChromaDB из-за одной и той же ошибки в вызове SDK.

---

## Варианты исправления (без правок кода — только план)

### Вариант A: Привести вызов в соответствие с текущим SDK (рекомендуется первым шагом)

- Посмотреть актуальную сигнатуру в установленном пакете, например:
  ```bash
  python -c "import gigachat; help(gigachat.GigaChat.embeddings)"
  ```
  или открыть исходник в site-packages: `gigachat/...` и найти метод `embeddings`.
- По документации GigaChat пример — позиционный аргумент: `giga.embeddings(["Hello world!"])`. Значит, разумная гипотеза:
  - вызывать так: `self._client.embeddings(texts)` или `self._client.embeddings(texts, model)` (оба аргумента позиционно), **без** `input=texts`;
  - после проверки на сервере — зафиксировать в коде один стабильный вариант (с учётом версии `gigachat` в `pyproject.toml`).

Это минимальное изменение (по сути, один вызов в `gigachat_provider.py`), без смены архитектуры RAG.

### Вариант B: Явно зафиксировать версию gigachat и сигнатуру

- В `pyproject.toml` зафиксировать конкретную версию, например `gigachat==0.2.x`, после того как найдём версию, где `embeddings` стабильно работает с выбранным способом вызова.
- В коде или в комментарии явно указать: «вызов embeddings совместим с gigachat==X.Y.Z».

Это снизит риск поломки после обновления пакета.

### Вариант C: Обход через REST (если SDK продолжит ломаться)

- Не использовать `self._client.embeddings(...)`, а самому сформировать POST на `/embeddions` с телом `{"input": texts, "model": model}` и тем же токеном, что и для чата. Тогда мы не зависим от сигнатуры метода в SDK. Минус — дублирование логики авторизации и разбора ответа.

### Вариант D: ChromaDB telemetry

- Либо обновить `chromadb` до версии, где исправлен вызов телеметрии.
- Либо отключить телеметрию при создании клиента ChromaDB, если в их API есть такая опция (часто через переменную окружения или параметр при инициализации).

---

## Исправление (внесено)

По сигнатуре SDK `embeddings(self, texts: List[str], model: str = 'Embeddings')` параметр называется **`texts`**, не `input`. В `gigachat_provider.py` вызов заменён на:

```python
response = self._client.embeddings(texts=texts, model=model)
```

После деплоя индексация PDF/DOCX должна проходить без ошибки `unexpected keyword argument 'input'`.

---

## Проверка цепочки RAG (чтение → чанки → эмбеддинги)

Логика не менялась, проверено по коду:

| Шаг | Где | Что происходит |
|-----|-----|----------------|
| 1. Чтение файла | `rag._read_file` → `filesystem._smart_read` | По расширению: `.pdf` → `_read_pdf` (pdfplumber), `.docx`/`.doc` → `_read_docx` (python-docx). Путь резолвится через `Path(file_path).expanduser().resolve()`. |
| 2. Ошибки чтения | `_index_file` | Если `text.startswith("Error")` — возвращаем сообщение об ошибке, в Chroma не пишем. |
| 3. Нарезка на чанки | `_chunk_text(text, chunk_size, chunk_overlap)` | Слайды по `chunk_size` с перекрытием `chunk_overlap`; пустые куски не попадают в список. Параметры из `RAGConfig` (по умолчанию 1000 / 200). |
| 4. Эмбеддинги | `_embed_texts(chunks)` → `provider.get_embeddings(texts, model)` | Список строк передаётся в GigaChat; исправлен только аргумент вызова SDK (`texts=` вместо `input=`). |
| 5. Запись в Chroma | `collection.upsert(ids, embeddings, documents=chunks, metadatas)` | ID вида `{имя_файла}__chunk_{i}`, метаданные `source` и `chunk_index`. |

PDF и DOCX поддерживаются через `_smart_read`; зависимости `pdfplumber` и `python-docx` указаны в `pyproject.toml`. Цепочка не нарушена.

---

## Рекомендуемый порядок действий (если что-то останется)

1. **На сервере (или в том же окружении, где падает бот)** выполнить:
   ```bash
   python -c "import gigachat; c = gigachat.GigaChat(credentials='...'); help(c.embeddings)"
   ```
   или посмотреть исходник `embeddings` в установленном пакете `gigachat`. Записать точную сигнатуру (имена и порядок аргументов).

2. **В `gigachat_provider.py`** заменить вызов так, чтобы он соответствовал этой сигнатуре (скорее всего — убрать `input=` и передавать список и модель позиционно).

3. **Проверить** на том же сервере:
   - Создать базу знаний.
   - Один раз вызвать `knowledge(index_file, project="...", file_path="путь/к/любому.pdf")` (или через бота: отправить PDF и написать «добавь в базу знаний X»).
   - Убедиться, что в логах нет `unexpected keyword argument 'input'` и что в ответе — успешная индексация.

4. При желании — отдельно разобраться с телеметрией ChromaDB (вариант D), чтобы убрать предупреждение из логов.

---

## Краткий итог

| Вопрос | Ответ |
|--------|--------|
| Почему не работают ни PDF, ни DOCX? | Оба формата доходят до RAG; падение из‑за вызова `embeddings(input=texts, model=model)` — SDK не принимает аргумент `input`. |
| Где баг? | `gigabot/providers/gigachat_provider.py`, метод `get_embeddings`: неверный способ вызова `self._client.embeddings(...)`. |
| Что править? | Привести вызов к сигнатуре SDK (скорее всего — позиционные аргументы `(texts)` или `(texts, model)` без `input=`). |
| Нужно ли трогать RAG/ChromaDB/чтение файлов? | Нет для исправления текущей ошибки; при желании — только телеметрия ChromaDB. |

После исправления вызова эмбеддингов индексация PDF и DOCX в базу знаний должна заработать при тех же сценариях, что и в тестах.
