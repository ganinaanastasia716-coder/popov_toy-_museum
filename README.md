# TOY MUSEUM v3 — Render-ready

Премиальный мобильный интерфейс TOY MUSEUM сохранён: главная без сетки всех экспонатов, поиск, фото-сканер, цифровой паспорт, навигатор полки, коллекция, квест и отдельная админка.

## Что исправлено
- Python зафиксирован на 3.13.11 через `.python-version` и `PYTHON_VERSION`.
- Совместимый набор NumPy / PyTorch / torchvision / FAISS / sentence-transformers.
- Убран `pillow-heif`, который ранее ломал сборку на Render.
- Веб-приложение и Telegram worker используют отдельные наборы зависимостей.
- Flask-шаблоны находятся в `templates/`, CSS — в `static/`.
- Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`.
- Токены и секреты не хранятся в коде.

## Render Environment Variables
Для Web Service:
- `BOT_TOKEN`
- `WEBAPP_URL`
- `ADMIN_KEY`
- `FLASK_SECRET`

Для Bot Worker:
- `BOT_TOKEN`
- `WEBAPP_URL`

`WEBAPP_URL` должен указывать на адрес Web Service, например `https://your-service.onrender.com`.

## Важно при замене файлов
Если в текущем репозитории уже есть `museum.db` и папка `photos` с вашими 15 игрушками, сохраните их. Код автоматически обновит структуру старой БД и не требует пересоздания карточек.

## Запуск
Web Service:
`pip install -r requirements.txt`

Bot Worker:
`pip install -r requirements-bot.txt`

Web start:
`gunicorn --bind 0.0.0.0:$PORT app:app`

Bot start:
`python bot.py`
