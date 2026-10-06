import os
import sqlite3
import numpy as np
import telebot
from PIL import Image
from sentence_transformers import SentenceTransformer
import faiss

# Включаем поддержку HEIC-формата файлов от iPhone (если библиотека установлена)
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# ==========================================
# 1. НАСТРОЙКИ И ИНИЦИАЛИЗАЦИЯ
# ==========================================
TELEGRAM_BOT_TOKEN = "8851782447:AAExmUaQB1dKjXLHFVq7tBI4xeP5K6VQlyo"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

print("⏳ Загрузка локальной нейросети CLIP (бесплатно)...")
model = SentenceTransformer('clip-ViT-B-32')

# Создаем векторную базу данных FAISS (размерность 512 для CLIP)
dimension = 512
index = faiss.IndexFlatIP(dimension)

# Карта соответствия: индекс вектора FAISS -> ID экспоната в SQLite
toy_ids_map = []

# ==========================================
# 2. ИНДЕКСАЦИЯ ФОТО ИЗ BAZY SQLite
# ==========================================
def index_existing_photos():
    global index, toy_ids_map
    
    if not os.path.exists('museum.db'):
        print("❌ Файл museum.db не найден! Сначала запустите python fill_db.py")
        return

    conn = sqlite3.connect('museum.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, photo_path FROM toys")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("⚠️ База данных пуста. Сначала запустите fill_db.py")
        return

    embeddings = []
    toy_ids_map = []

    print(f"🔄 Создаем векторы для {len(rows)} фотографий из папки photos...")
    for toy_id, title, photo_path in rows:
        if os.path.exists(photo_path):
            try:
                img = Image.open(photo_path).convert('RGB')
                vec = model.encode(img, normalize_embeddings=True)
                embeddings.append(vec)
                toy_ids_map.append(toy_id)
                print(f"  • Векторизовано: {title} ({photo_path})")
            except Exception as e:
                print(f"  ❌ Ошибка чтения файла {photo_path}: {e}")
        else:
            print(f"  ⚠️ Файл не найден по пути: {photo_path}")

    if embeddings:
        embeddings_np = np.array(embeddings).astype('float32')
        index.reset()
        index.add(embeddings_np)
        print(f"✅ Успешно заиндексировано объектов в FAISS: {index.ntotal}\n")

# ==========================================
# 3. ЛОГИКА ОБРАБОТКИ СООБЩЕНИЙ В TELEGRAM
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 **Привет! Я музейный ИИ-ассистент.**\n\n"
        "Отправь мне фотографию любой игрушки, и я сверю её с нашей базой данных!"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if index.ntotal == 0:
        bot.reply_to(message, "⚠️ База данных пуста или не проиндексирована!")
        return

    bot.reply_to(message, "🔍 Сканирую фото и ищу векторные совпадения...")

    # Скачиваем присланное фото во временный файл
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    temp_path = "temp_user_photo.jpg"
    
    with open(temp_path, 'wb') as f:
        f.write(downloaded_file)

    try:
        # 1. Превращаем фото пользователя в вектор
        user_img = Image.open(temp_path).convert('RGB')
        user_vec = model.encode(user_img, normalize_embeddings=True)
        user_vec_np = np.array([user_vec]).astype('float32')

        # 2. Мгновенный векторный поиск ближайшего совпадения
        D, I = index.search(user_vec_np, k=1)
        
        confidence = float(D[0][0])  # Оценка сходства (от 0.0 до 1.0)
        matched_idx = I[0][0]

        # 3. Проверка порога уверенности (65%)
        if confidence >= 0.65:
            matched_toy_id = toy_ids_map[matched_idx]
            
            # Забираем текстовые данные из SQLite
            conn = sqlite3.connect('museum.db')
            cursor = conn.cursor()
            cursor.execute("SELECT title, inventory_num, location, description FROM toys WHERE id = ?", (matched_toy_id,))
            toy = cursor.fetchone()
            conn.close()

            response = (
                f"🎉 **ЭКСПОНАТ НАЙДЕН!**\n"
                f"🎯 Точность совпадения: `{confidence*100:.1f}%`\n\n"
                f"🧸 **Название:** {toy[0]}\n"
                f"🏷 **Инвентарный №:** `{toy[1]}`\n"
                f"📍 **Локация:** {toy[2]}\n"
                f"📝 **Информация:** {toy[3]}"
            )
        else:
            response = (
                f"❓ **Игрушка в базе музея не найдена.**\n"
                f"Наибольшее сходство: `{confidence*100:.1f}%` (ниже порога 65%).\n"
                f"Попробуйте сделать фото ближе или при другом освещении."
            )

        bot.reply_to(message, response, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"❌ Произошла ошибка при обработке: {e}")
    
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    index_existing_photos()
    print("🚀 Бот запущен! Напишите ему в Telegram...")
    bot.polling(none_stop=True)