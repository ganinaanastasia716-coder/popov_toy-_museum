# TOY MUSEUM — exact-style functional build

## Render
One Web Service. No paid Worker.

Start command:
`gunicorn --workers 1 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT app:app`

Environment variables:
- `BOT_TOKEN` — Telegram bot token (create/rotate it in BotFather; never commit it)
- `WEBAPP_URL` — `https://popov-toy-museum.onrender.com`
- `ADMIN_KEY` — admin password
- `FLASK_SECRET` — long random secret
- `GEMINI_API_KEY` — optional, for “Найти досье”
- `GEMINI_MODEL` — optional, defaults to `gemini-2.5-flash`

## Admin
Open `/admin/login`, enter `ADMIN_KEY`, upload one or multiple toy photos. Each upload creates one row in `museum.db` with a generated inventory number. Unknown metadata stays empty.

## Photo scanner
`/scan` accepts a real camera capture on supported mobile browsers and a gallery image. The uploaded search image is used only for matching; it is not saved as a museum item. Results are the best six matches from the museum database.

## Images
All museum photos are served from `/photos/<filename>`. Missing files return a museum placeholder instead of a broken-image question mark.

## Catalogue
The complete exhibit list is stored in SQLite and is not shown on the home screen. `/collection` is the catalogue page.
