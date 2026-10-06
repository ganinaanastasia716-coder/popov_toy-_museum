import os
import sqlite3

# ============================================================
# НАСТРОЙКИ
# ============================================================

PHOTOS_DIR = "photos"
DB_FILE = "museum.db"

# Сейчас в коллекции: только JPG.
# Каждый JPG = ОДНА отдельная игрушка.
VALID_EXTENSIONS = (".jpg",)


def fill_database_auto():
    # --------------------------------------------------------
    # 1. Проверяем папку с фотографиями
    # --------------------------------------------------------
    if not os.path.isdir(PHOTOS_DIR):
        print(f"❌ Ошибка: папка '{PHOTOS_DIR}' не найдена.")
        print("Создайте папку photos и положите туда JPG-фотографии игрушек.")
        return

    # Берём ТОЛЬКО JPG
    image_files = sorted(
        filename
        for filename in os.listdir(PHOTOS_DIR)
        if filename.lower().endswith(VALID_EXTENSIONS)
    )

    if not image_files:
        print(f"⚠️ В папке '{PHOTOS_DIR}' не найдено JPG-фотографий.")
        return

    print(f"📸 Найдено JPG-фотографий: {len(image_files)}")

    if len(image_files) != 15:
        print("⚠️ Внимание: ожидалось 15 JPG.")
        print("   Это не ошибка — скрипт всё равно импортирует найденные JPG.")
    else:
        print("✅ Все 15 фотографий найдены.")

    # --------------------------------------------------------
    # 2. Создаём/обновляем базу
    # --------------------------------------------------------
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Для текущего этапа используем одну запись = одна игрушка.
    # Позже, когда появятся дополнительные фотографии одной игрушки,
    # структуру можно будет расширить.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS toys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            inventory_num TEXT,
            country TEXT,
            city TEXT,
            museum TEXT,
            building TEXT,
            hall TEXT,
            display_case TEXT,
            shelf TEXT,
            location TEXT,
            description TEXT,
            photo_path TEXT
        )
    """)

    # Если база была создана старой версией программы,
    # добавляем отсутствующие поля.
    existing_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(toys)").fetchall()
    }

    new_columns = {
        "country": "TEXT",
        "city": "TEXT",
        "museum": "TEXT",
        "building": "TEXT",
        "hall": "TEXT",
        "display_case": "TEXT",
        "shelf": "TEXT",
    }

    for column, column_type in new_columns.items():
        if column not in existing_columns:
            cursor.execute(
                f"ALTER TABLE toys ADD COLUMN {column} {column_type}"
            )

    # На этом этапе база строится заново из текущих 15 JPG.
    # Старые записи от HEIC/PNG/WEBP и предыдущих импортов исчезнут.
    cursor.execute("DELETE FROM toys")

    # --------------------------------------------------------
    # 3. Создаём 1 запись на каждый JPG
    # --------------------------------------------------------
    items = []

    for index, filename in enumerate(image_files, start=1):
        name_without_ext = os.path.splitext(filename)[0]

        # Название берём из имени файла.
        # Например:
        # 01_bear.jpg -> 01 Bear
        clean_title = (
            name_without_ext
            .replace("_", " ")
            .replace("-", " ")
            .strip()
            .title()
        )

        inventory_num = f"INV-{index:03d}"
        photo_path = os.path.join(PHOTOS_DIR, filename)

        # Пока эти поля пустые — их можно будет заполнить
        # через мини-приложение/админку.
        country = ""
        city = ""
        museum = ""
        building = ""
        hall = ""
        display_case = ""
        shelf = ""

        # Сохраняем также старое поле location для совместимости
        # с текущим Telegram-ботом.
        location = ""

        description = f"Экспонат из файла {filename}"

        items.append((
            clean_title,
            inventory_num,
            country,
            city,
            museum,
            building,
            hall,
            display_case,
            shelf,
            location,
            description,
            photo_path,
        ))

    cursor.executemany("""
        INSERT INTO toys (
            title,
            inventory_num,
            country,
            city,
            museum,
            building,
            hall,
            display_case,
            shelf,
            location,
            description,
            photo_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, items)

    conn.commit()

    # --------------------------------------------------------
    # 4. Проверка результата
    # --------------------------------------------------------
    cursor.execute("SELECT COUNT(*) FROM toys")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT id, title, inventory_num, photo_path
        FROM toys
        ORDER BY id
    """)
    rows = cursor.fetchall()

    conn.close()

    print()
    print("=" * 70)
    print(f"✅ БАЗА ГОТОВА: {total} игрушек")
    print("=" * 70)

    for toy_id, title, inventory_num, photo_path in rows:
        print(f"{inventory_num} | {title} | {photo_path}")

    print()
    print("Теперь в базе:")
    print(f"  • JPG-фотографий: {len(image_files)}")
    print(f"  • игрушек:         {total}")
    print()
    print("Если здесь написано 15 игрушек — импорт выполнен правильно.")


if __name__ == "__main__":
    fill_database_auto()
