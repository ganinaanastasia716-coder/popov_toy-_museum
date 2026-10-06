import os
import telebot
from telebot import types

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL')

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is not set. Add BOT_TOKEN in Railway Variables.')
if not WEB_APP_URL:
    raise RuntimeError('WEB_APP_URL is not set. Add WEB_APP_URL in Railway Variables.')

bot = telebot.TeleBot(BOT_TOKEN)


def main_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton('🔎 Найти игрушку', web_app=types.WebAppInfo(url=WEB_APP_URL)))
    return kb


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        '🏛️ <b>Музей игрушек</b>\n\nОткройте Mini App, чтобы найти экспонат по фотографии, названию, инвентарному номеру, стране, городу или музею.',
        parse_mode='HTML',
        reply_markup=main_keyboard(),
    )


@bot.message_handler(commands=['find', 'search'])
def find(message):
    bot.send_message(
        message.chat.id,
        '🔎 Откройте каталог и найдите нужную игрушку:',
        reply_markup=main_keyboard(),
    )


@bot.message_handler(content_types=['photo'])
def photo_hint(message):
    bot.send_message(
        message.chat.id,
        '📷 Для распознавания фотографии откройте Mini App — там используется визуальный поиск по базе музея.',
        reply_markup=main_keyboard(),
    )


print('🚀 Museum bot started')
bot.infinity_polling(skip_pending=True)
