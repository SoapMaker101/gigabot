# Установка GigaBot на сервер

## Требования

- Ubuntu 22.04 / 24.04
- Python 3.11+
- 4 vCPU, 16 GB RAM (рекомендовано)
- Tesseract OCR

## Шаг 1. Системные зависимости

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv tesseract-ocr tesseract-ocr-rus git
```

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
