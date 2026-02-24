# Установка GigaBot на сервер

## Требования

- Ubuntu 22.04 / 24.04
- Python 3.11+
- 4 vCPU, 16 GB RAM (рекомендовано)
- Tesseract OCR

## Шаг 1. Системные зависимости

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev libffi-dev tesseract-ocr tesseract-ocr-rus git
```

> **Важно:** `libffi-dev` и `python3.11-dev` необходимы для пакета `cffi`, от которого зависит `cryptography` → `pdfminer.six` → `pdfplumber` (чтение PDF). Без них `import pdfplumber` упадёт с `ModuleNotFoundError: No module named '_cffi_backend'`.

## Шаг 2. Создать пользователя (опционально)

```bash
sudo useradd -m -s /bin/bash gigabot
sudo su - gigabot
```

## Шаг 3. Клонировать и установить

```bash
git clone https://github.com/SoapMaker101/gigabot.git ~/gigabot
cd ~/gigabot
python3.11 -m venv .venv
source .venv/bin/activate
pip install hatchling
pip install -e .
```

## Шаг 4. Настроить

```bash
gigabot onboard
nano ~/.gigabot/config.json
```

Заполнить: GigaChat credentials, Telegram token, SaluteSpeech keys, Brave API key.

## Шаг 5. Проверить

```bash
gigabot agent -m "Привет! Кто ты?"
```

## Шаг 6. Systemd сервис

```bash
sudo tee /etc/systemd/system/gigabot.service > /dev/null << 'EOF'
[Unit]
Description=GigaBot AI Agent
After=network.target

[Service]
Type=simple
User=gigabot
WorkingDirectory=/home/gigabot/gigabot
ExecStart=/home/gigabot/gigabot/.venv/bin/gigabot gateway
Restart=always
RestartSec=5
Environment=HOME=/home/gigabot

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gigabot
sudo systemctl start gigabot
```

## Шаг 7. Проверить

```bash
sudo systemctl status gigabot
sudo journalctl -u gigabot -f
```

## Обновление

```bash
cd ~/gigabot
source .venv/bin/activate
git pull origin main
pip install -e .
sudo systemctl restart gigabot
```

## Логи

```bash
# Последние 50 строк
sudo journalctl -u gigabot -n 50 --no-pager

# В реальном времени
sudo journalctl -u gigabot -f

# Перезапуск
sudo systemctl restart gigabot
```

## Решение проблем

### PDF не читается: `ModuleNotFoundError: No module named '_cffi_backend'`

Проблема: pdfplumber установлен, но import падает из-за сломанного cffi.

```bash
# Проверить
source ~/gigabot/.venv/bin/activate
python -c "import pdfplumber; print(pdfplumber.__version__)"

# Исправить
sudo apt install -y libffi-dev python3.11-dev
pip install --force-reinstall cffi
sudo systemctl restart gigabot
```

### Проверка всех ключевых зависимостей

```bash
source ~/gigabot/.venv/bin/activate
python -c "import pdfplumber; print('pdfplumber', pdfplumber.__version__)"
python -c "from readability import Document; print('readability OK')"
python -c "import chromadb; print('chromadb', chromadb.__version__)"
python -c "import pytesseract; print('pytesseract', pytesseract.__version__)"
```
