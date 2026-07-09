# Деплой parser-bot на сервер (Ubuntu/Debian, 24/7 через systemd)

Ниже — полная инструкция, как поднять парсер на VPS, чтобы он работал
автономно и сам перезапускался после сбоя/перезагрузки.

В командах замени плейсхолдеры:
- `USER` — твой пользователь на сервере (напр. `root` или `ubuntu`)
- `SERVER_IP` — ip-адрес сервера
- `GHUSER` — твой логин на GitHub
- `REPO` — имя репозитория (напр. `AI_Foundation`)

---

## 0. Подключиться к серверу

```bash
ssh USER@SERVER_IP
```

## 1. Установить системные пакеты

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 2. Склонировать приватный репозиторий

Для приватного репо нужен доступ. Самый простой способ — Personal Access Token.
На GitHub: Settings → Developer settings → Personal access tokens →
Fine-grained tokens → создать токен с доступом «Contents: Read» к нужному репо.

```bash
cd ~
git clone https://GHUSER:ВСТАВЬ_ТОКЕН@github.com/GHUSER/REPO.git
```

(Токен в URL сохранится в `~/REPO/.git/config`. Это ок для личного сервера.
Альтернатива — deploy-ключ по SSH, см. раздел в конце.)

## 3. Создать виртуальное окружение и поставить зависимости

`.venv` с Mac НЕ копируем — он несовместим. Создаём свежий на сервере:

```bash
cd ~/REPO
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r parser-bot/requirements.txt
```

## 4. Создать .env на сервере (его нет в гите)

```bash
nano ~/REPO/parser-bot/.env
```

Вставь (со своими значениями) и сохрани (Ctrl+O, Enter, Ctrl+X):

```
TELEGRAM_API_ID=31783014
TELEGRAM_API_HASH=9ff92a26d38497b54c1985a6b7b06bbb
TELEGRAM_SESSION_NAME=parser_session
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=ТВОЙ_ТОКЕН_БОТА
OUTPUT_CHAT_ID=-1003998202575
FORWARD_TO_GROUP=true
FILTER_ENABLED=true
```

## 5. Перенести файл сессии Telegram с Mac на сервер

Без этого бот на сервере попросит код входа (в безголовом режиме это неудобно).
Файл сессии = твоя авторизация, копируем его.

**На Mac** (в обычном терминале, не на сервере) выполни:

```bash
scp /Users/mishapushka/AI_Foundation/parser-bot/parser_session.session USER@SERVER_IP:~/REPO/parser-bot/
```

(Если рядом есть файл `parser_session.session-journal` — скопируй и его тем же способом.)

> Telegram может прислать уведомление о новом входе с сервера — это нормально,
> сессия продолжит работать. Никому не передавай этот файл: он даёт полный
> доступ к аккаунту.

## 6. Проверить ручной запуск

```bash
cd ~/REPO/parser-bot
../.venv/bin/python main.py
```

Должны появиться строки `Авторизован как…`, `Пересылка в группу включена`,
`Правила фильтрации загружены`, `Слушаю N каналов`. Если всё ок — останови
（Ctrl+C) и переходи к автозапуску.

## 7. Настроить автозапуск через systemd

Создай unit-файл:

```bash
sudo nano /etc/systemd/system/parserbot.service
```

Вставь (поправь USER и пути, если клонировал не в домашнюю папку):

```ini
[Unit]
Description=Telegram Parser Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=USER
WorkingDirectory=/home/USER/REPO/parser-bot
ExecStart=/home/USER/REPO/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> Если пользователь `root`, путь будет `/root/REPO/...` вместо `/home/USER/REPO/...`.

Включи и запусти:

```bash
sudo systemctl daemon-reload
sudo systemctl enable parserbot
sudo systemctl start parserbot
```

## 8. Проверка и управление

```bash
sudo systemctl status parserbot      # статус (работает / упал)
journalctl -u parserbot -f           # живой просмотр логов
sudo systemctl restart parserbot     # перезапустить
sudo systemctl stop parserbot        # остановить
```

Теперь бот работает 24/7, поднимается при загрузке сервера и сам
перезапускается при сбое (Restart=always).

---

## Обновление кода после изменений

Когда правишь код или `filters.json` на Mac и пушишь в гит:

```bash
cd ~/REPO
git pull
sudo systemctl restart parserbot
```

(Файлы `.env` и `.session` при этом не трогаются — они не в гите.)

---

## Альтернатива: доступ к приватному репо по SSH-ключу

Вместо токена в URL можно создать deploy-ключ:

```bash
ssh-keygen -t ed25519 -C "server-deploy" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Скопируй вывод и добавь на GitHub: репо → Settings → Deploy keys → Add deploy key.
Потом клонируй по SSH:

```bash
git clone git@github.com:GHUSER/REPO.git
```
