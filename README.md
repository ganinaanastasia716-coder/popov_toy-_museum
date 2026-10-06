# 🏛️ Museum Toy Finder — Telegram Bot + Mini App

Это единый проект музея игрушек:

Telegram-бот открывает Mini App, а Mini App ищет игрушки в SQLite по названию, инвентарному номеру, стране, городу, музею и фотографии.

## Структура

```text
museum_project/
├── bot.py                 # Telegram-бот, открывающий Mini App
├── app.py                 # Flask backend Mini App
├── museum.db              # SQLite, 15 записей игрушек
├── fill_db.py             # заполнение БД по JPG
├── requirements.txt
├── photos/                # сюда положить 15 JPG
├── templates/index.html
└── static/style.css
```

## Важно про фотографии

В этой сборке есть готовая `museum.db` с 15 записями, но сами 15 JPG не были доступны среди файлов текущего чата, поэтому в ZIP оставлена папка `photos/` с инструкцией. Положите туда ваши оригинальные JPG.

## Railway

Рекомендуемый вариант — два Railway Service из одного GitHub-репозитория.

### Service 1 — Mini App

Start command:

```bash
python app.py
```

После публикации получите URL Mini App, например:

```text
https://your-museum-app.up.railway.app
```

### Service 2 — Telegram Bot

Start command:

```bash
python bot.py
```

Variables:

```text
BOT_TOKEN=токен_из_BotFather
WEB_APP_URL=https://your-museum-app.up.railway.app
```

Токен Telegram нельзя помещать в GitHub или код.

## Локальный запуск Mini App

```bash
pip install -r requirements.txt
python app.py
```

## Пересоздание базы из фотографий

Если хотите заново создать записи из JPG:

```bash
python fill_db.py
```

Скрипт создаёт одну запись `toys` на каждый `.jpg`.
