# Popov Toy Museum

## Запуск в VS Code (Windows)
1. Распакуйте архив и откройте папку `Popov_Toy_Museum` в VS Code.
2. В терминале:
```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ADMIN_PASSWORD="change-me"
$env:FLASK_SECRET="local-secret-change-me"
python app.py
```
3. Откройте http://127.0.0.1:5000
4. Панель администратора: http://127.0.0.1:5000/admin/login

## Telegram / Render
Задайте в Render переменные `BOT_TOKEN`, `WEBAPP_URL` (публичный HTTPS URL), `ADMIN_PASSWORD`, `FLASK_SECRET`. Для онлайн-досье также задайте `GEMINI_API_KEY`. Webhook работает внутри того же Flask-сервиса; отдельный Worker не нужен.

## Что есть
Главная в тёмном музейном стиле, коллекция с пагинацией, карточка экспоната на светлом фоне, загрузка фото, поиск похожих изображений, админ-панель и опциональное онлайн-досье Gemini. Поиск по фото — лёгкое визуальное сравнение, поэтому похожесть не гарантирует точную идентификацию.

`museum.db` создаётся автоматически. Архив не содержит ваших настоящих фотографий. Для Render продумайте постоянное хранилище/резервное копирование: локальная файловая система сервиса может быть временной. Никогда не добавляйте токены и пароли в GitHub.
