"""Telegram webhook helper.
The bot is handled by app.py on the existing Render Web Service.
No separate Worker is required.
"""
import os
import requests

TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")

if TOKEN and WEBAPP_URL:
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(
        url,
        json={"url": WEBAPP_URL + "/telegram/webhook", "drop_pending_updates": True},
        timeout=20,
    )
    response.raise_for_status()
    print("Telegram webhook:", WEBAPP_URL + "/telegram/webhook")
else:
    print("Set BOT_TOKEN and WEBAPP_URL to register Telegram webhook.")
