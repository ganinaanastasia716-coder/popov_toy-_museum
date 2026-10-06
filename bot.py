import os
import telebot
from telebot import types

# ============================================================
# TOY MUSEUM — Telegram bot
# Bot's job:
# 1. Welcome the visitor.
# 2. Open the TOY MUSEUM Mini App.
# 3. Send every search request (text/photo) into the Mini App.
#
# IMPORTANT:
# - Put the real Telegram token into Render Environment Variables:
#   BOT_TOKEN
# - Do NOT write the token into this file.
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://popov-toy-museum.onrender.com"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def app_button():
    """Button that opens the TOY MUSEUM Mini App."""
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "🏛 Открыть TOY MUSEUM",
            web_app=types.WebAppInfo(url=WEBAPP_URL)
        )
    )
    return markup


def search_button():
    """Reply button for starting a search in the Mini App."""
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True
    )
    markup.row(types.KeyboardButton("🔎 Найти игрушку"))
    return markup


WELCOME_TEXT = """🏛 <b>TOY MUSEUM</b>

Цифровой музей дизайнерских игрушек.

Здесь можно найти экспонат:
📷 по фотографии
🔢 по инвентарному номеру
🔤 по названию
🏛 по музею
📍 по городу
🌍 по стране

Нажмите кнопку ниже — откроется наше приложение."""


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        WELCOME_TEXT,
        reply_markup=app_button()
    )
    bot.send_message(
        message.chat.id,
        "Или нажмите «🔎 Найти игрушку», чтобы открыть поиск.",
        reply_markup=search_button()
    )


@bot.message_handler(commands=["search", "find"])
def search_command(message):
    bot.send_message(
        message.chat.id,
        "🔎 Открываю поиск игрушки в TOY MUSEUM.",
        reply_markup=app_button()
    )


@bot.message_handler(
    func=lambda message: bool(message.text)
)
def text_search(message):
    # Any ordinary text is treated as a search request.
    query = message.text.strip()

    if query == "🔎 Найти игрушку":
        bot.send_message(
            message.chat.id,
            "🔎 Открываю поиск игрушки.",
            reply_markup=app_button()
        )
        return

    bot.send_message(
        message.chat.id,
        f"🔎 Ищем «{query}» в TOY MUSEUM.\n\n"
        "Откройте приложение — там можно искать по названию, "
        "номеру, городу, музею и другим параметрам.",
        reply_markup=app_button()
    )


@bot.message_handler(content_types=["photo"])
def photo_search(message):
    # The bot does NOT save the user's photo as a museum exhibit.
    # The actual photo search is performed inside the Mini App.
    bot.send_message(
        message.chat.id,
        "📷 Для поиска по фотографии откройте сканер TOY MUSEUM.\n\n"
        "Там можно сделать снимок камерой или выбрать фотографию "
        "из галереи. Приложение покажет похожие экспонаты.",
        reply_markup=app_button()
    )


@bot.message_handler(content_types=["document"])
def document_search(message):
    bot.send_message(
        message.chat.id,
        "📷 Если это фотография игрушки, откройте сканер TOY MUSEUM "
        "и выберите изображение из галереи.",
        reply_markup=app_button()
    )


if __name__ == "__main__":
    print("TOY MUSEUM Telegram bot started")
    print(f"Mini App: {WEBAPP_URL}")
    bot.infinity_polling(
        skip_pending=True,
        allowed_updates=["message"]
    )
