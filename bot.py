import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_URL is not set")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏛 Открыть TOY MUSEUM", web_app=WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(
        message.chat.id,
        "Добро пожаловать в TOY MUSEUM.\n\n"
        "Цифровой паспорт коллекции: найдите экспонат по фото, номеру, бренду, персонажу или месту хранения.",
        reply_markup=kb,
    )

@bot.message_handler(content_types=["photo"])
def photo_in_chat(message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📷 Открыть фотосканер", web_app=WebAppInfo(url=WEBAPP_URL + "/scan")))
    bot.send_message(message.chat.id, "Откройте фотосканер — фото будет сопоставлено с эталонными экспонатами музея.", reply_markup=kb)

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
