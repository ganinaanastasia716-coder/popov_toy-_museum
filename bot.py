"""Telegram bot helper for TOY MUSEUM.

The bot is intentionally NOT a separate Render Worker.
The existing Flask Web Service handles Telegram webhook requests at /telegram/webhook.
Run this file locally only if you want to set/update the webhook manually.
"""
import os
import requests

TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")


def telegram(method, payload=None):
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    r = requests.post(url, json=payload or {}, timeout=20)
    r.raise_for_status()
    return r.json()


def set_webhook():
    if not TOKEN or not WEBAPP_URL:
        raise RuntimeError("BOT_TOKEN and WEBAPP_URL are required")
    webhook_url = f"{WEBAPP_URL}/telegram/webhook"
    return telegram("setWebhook", {"url": webhook_url, "drop_pending_updates": True})


def webhook_info():
    return telegram("getWebhookInfo")


if __name__ == "__main__":
    result = set_webhook()
    print(result)
    print(f"Webhook: {WEBAPP_URL}/telegram/webhook")
