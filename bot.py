"""Telegram helper for TOY MUSEUM.
The bot itself is served by the same Render Web Service through app.py.
No separate paid Worker is required.
"""
import os
import requests


def set_webhook():
    token = os.getenv("BOT_TOKEN", "").strip()
    web = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    if not token or not web:
        raise RuntimeError("BOT_TOKEN and WEBAPP_URL must be set")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": web + "/telegram/webhook", "drop_pending_updates": True},
        timeout=20,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    set_webhook()
