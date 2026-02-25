# GigaBot 🤖

AI-агент на базе **GigaChat** для управления проектами и документами через Telegram.

## Возможности

| # | Функция | Описание |
|---|---------|----------|
| 1 | **Папки проектов** | Создание структурированных папок (Договоры, Документация, Сметы, Фото, Переписка) |
| 2 | **Работа с файлами** | Чтение и создание DOCX, XLSX, PDF, TXT |
| 3 | **OCR** | Распознавание текста с фотографий (Tesseract) |
| 4 | **Анализ фото** | Описание содержимого изображений через GigaChat Vision |
| 5 | **Файловый менеджер** | Перемещение файлов из Telegram в папки проектов |
| 6 | **Голосовые запросы** | Распознавание голоса через SaluteSpeech |
| 7 | **RAG** | База знаний (ChromaDB + GigaChat Embeddings, модель EmbeddingsGigaR, пакетная индексация) |
| 8 | **Генерация изображений** | Создание картинок через Kandinsky |
| 9 | **Имена файлов** | Сохранение оригинальных имён файлов из Telegram |
| 10 | **Поиск в интернете** | Brave Search API |
| 11 | **Задачи** | Управление задачами с дедлайнами и напоминаниями |
| 12 | **Голосовые заметки** | Синтез речи через SaluteSpeech TTS |
| 13 | **Создание документов** | Генерация DOCX, XLSX по запросу |

## Стек технологий

- **LLM**: GigaChat-2-Max (только GigaChat, без других моделей)
- **SDK**: [gigachat](https://pypi.org/project/gigachat/) — прямая интеграция
- **RAG**: ChromaDB + GigaChat Embeddings
- **Голос**: SaluteSpeech (STT + TTS)
- **OCR**: Tesseract
- **Генерация**: Kandinsky (через GigaChat)
- **Канал**: Telegram (python-telegram-bot)

## Быстрый старт

### 1. Установка

```bash
# Клонировать
git clone https://github.com/SoapMaker101/gigabot.git
cd gigabot

# Создать виртуальное окружение
python3.11 -m venv .venv
source .venv/bin/activate

# Установить
pip install -e .

# Системные зависимости (Ubuntu)
sudo apt install -y tesseract-ocr tesseract-ocr-rus
```

### 2. Настройка

```bash
gigabot onboard
```

Редактировать `~/.gigabot/config.json`:

```json
{
  "gigachat": {
    "credentials": "ВСТАВЬ_СЮДА_BASE64_CREDENTIALS",
    "scope": "GIGACHAT_API_PERS",
    "model": "GigaChat-2-Max"
  },
  "saluteSpeech": {
    "credentials": "ВСТАВЬ_BASE64_ОТ_SALUTESPEECH"
  },
  "telegram": {
    "enabled": true,
    "token": "ВСТАВЬ_ТОКЕН_БОТА",
    "allowFrom": ["ТВОЙ_TELEGRAM_ID"]
  },
  "tools": {
    "web": {
      "apiKey": "ВСТАВЬ_BRAVE_API_KEY"
    }
  }
}
```

### 3. Запуск

```bash
# Telegram-бот (основной режим)
gigabot gateway

# Или CLI-режим
gigabot agent -m "Привет!"

# Интерактивный режим
gigabot agent
```

## Установка на сервер (Ubuntu 24.04)

```bash
# Системные зависимости
sudo apt update && sudo apt install -y python3.11 python3.11-venv tesseract-ocr tesseract-ocr-rus

# Установка
sudo mkdir -p /opt/gigabot
sudo python3.11 -m venv /opt/gigabot/venv
source /opt/gigabot/venv/bin/activate
git clone https://github.com/SoapMaker101/gigabot.git /opt/gigabot/source
pip install -e /opt/gigabot/source

# Настройка
gigabot onboard
# Отредактировать ~/.gigabot/config.json

# Systemd сервис
sudo tee /etc/systemd/system/gigabot.service > /dev/null << 'EOF'
[Unit]
Description=GigaBot AI Agent
After=network.target

[Service]
Type=simple
User=gigabot
ExecStart=/opt/gigabot/venv/bin/gigabot gateway
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gigabot
sudo systemctl start gigabot
```

## Структура проекта

```
gigabot/
├── gigabot/
│   ├── agent/              # Ядро агента
│   │   ├── loop.py         # Главный цикл
│   │   ├── context.py      # Сборка промпта
│   │   ├── memory.py       # Долгосрочная память
│   │   ├── skills.py       # Система навыков
│   │   ├── subagent.py     # Фоновые подагенты
│   │   └── tools/          # Инструменты
│   │       ├── filesystem.py   # Файлы + проекты
│   │       ├── rag.py          # RAG (ChromaDB)
│   │       ├── ocr.py          # OCR (Tesseract)
│   │       ├── kandinsky.py    # Генерация изображений
│   │       ├── tasks.py        # Управление задачами
│   │       ├── salute_speech.py # TTS (голосовые заметки)
│   │       ├── web.py          # Поиск в интернете
│   │       ├── shell.py        # Выполнение команд
│   │       ├── message.py      # Отправка сообщений
│   │       ├── spawn.py        # Подагенты
│   │       └── cron.py         # Планировщик
│   ├── channels/
│   │   └── telegram.py     # Telegram-бот
│   ├── providers/
│   │   └── gigachat_provider.py  # GigaChat SDK
│   ├── config/             # Конфигурация
│   ├── bus/                # Шина сообщений
│   ├── session/            # Сессии
│   ├── cron/               # Cron-сервис
│   └── cli/                # CLI-интерфейс
├── pyproject.toml
└── README.md
```

## Данные

```
~/.gigabot/
├── config.json         # Конфигурация
├── workspace/
│   ├── projects/       # Папки проектов
│   ├── sessions/       # История разговоров
│   ├── memory/         # MEMORY.md + HISTORY.md
│   └── skills/         # Пользовательские навыки
├── media/              # Файлы из Telegram
├── rag_db/             # ChromaDB
├── tasks/              # Задачи (tasks.json)
├── voice_notes/        # Голосовые заметки
└── cron/               # Расписание (jobs.json)
```

## Команды CLI

| Команда | Описание |
|---------|----------|
| `gigabot onboard` | Инициализация конфига и workspace |
| `gigabot gateway` | Запуск Telegram-бота |
| `gigabot agent -m "..."` | Одно сообщение в CLI |
| `gigabot agent` | Интерактивный режим |
| `gigabot status` | Статус системы |
| `gigabot cron list` | Список задач по расписанию |
| `gigabot cron add` | Добавить задачу |
| `gigabot channels status` | Статус каналов |

## Получение ключей

### GigaChat
1. Зарегистрируйтесь на [developers.sber.ru](https://developers.sber.ru)
2. Создайте проект с GigaChat API
3. Получите Client ID и Client Secret
4. Закодируйте в base64: `echo -n "CLIENT_ID:CLIENT_SECRET" | base64`

### SaluteSpeech
1. На [developers.sber.ru](https://developers.sber.ru) создайте проект SaluteSpeech
2. Получите Client ID и Client Secret
3. Закодируйте: `echo -n "CLIENT_ID:CLIENT_SECRET" | base64`

### Telegram Bot
1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Получите токен

### Brave Search
1. Зарегистрируйтесь на [brave.com/search/api](https://brave.com/search/api/)
2. Получите API key

## Обновление на сервере

```bash
cd ~/gigabot
git pull origin main
pip install -e .
sudo systemctl restart gigabot
```

> **Если исходники в `/opt/gigabot/source`, а сервис запускается из другого venv** (например `/home/gigabot/gigabot/.venv`) — устанавливать нужно в тот venv: `source /path/to/that/.venv/bin/activate` и `pip install -e /opt/gigabot/source`. Подробно: [docs/SERVER-INSTALL.md](docs/SERVER-INSTALL.md) (раздел «Важно: откуда сервис берёт код»).

Проверка:

```bash
sudo systemctl status gigabot
sudo journalctl -u gigabot -n 50 --no-pager
```

## Важные особенности GigaChat API

- **Результаты функций** должны быть валидным JSON. GigaBot автоматически оборачивает текстовые результаты в `{"result": "..."}`.
- **`functions_state_id`** — GigaChat возвращает идентификатор состояния при вызове функций. GigaBot сохраняет и передаёт его для корректной работы цепочек вызовов.
- **`function_call: "auto"`** — передаётся автоматически когда доступны функции.
- **Telegram ID** в `allowFrom` должен быть строкой: `"allowFrom": ["744902182"]`, не числом.

## Лицензия

MIT
