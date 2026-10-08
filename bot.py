# Telegram webhook is handled by app.py on the same Render Web Service.
# Run this script manually only if you want to re-register the webhook.
import os, requests
token=os.getenv("BOT_TOKEN"); base=os.getenv("WEBAPP_URL","").rstrip("/")
if not token or not base: raise SystemExit("Set BOT_TOKEN and WEBAPP_URL first.")
r=requests.post(f"https://api.telegram.org/bot{token}/setWebhook",json={"url":base+"/telegram/webhook"},timeout=20)
r.raise_for_status()
print(r.json())
