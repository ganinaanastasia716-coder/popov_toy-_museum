import io
import os
import re
import sqlite3
import json
import base64
import requests
from pathlib import Path

import numpy as np
from PIL import Image
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

BASE = Path(__file__).resolve().parent
DB = BASE / "museum.db"
PHOTOS = BASE / "photos"
PHOTOS.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-me-in-render")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

_clip_model = None
_faiss_index = None
_toy_ids_map = []

TOY_FIELDS = [
    "title", "inventory_num", "brand", "collection", "series", "character",
    "universe", "format", "height_cm", "material", "country", "production_country",
    "city", "museum", "building", "hall", "rack", "display_case", "shelf", "slot",
    "location", "author", "year", "collaboration", "condition", "value_usd",
    "insurance_usd", "coa", "hologram", "original_box", "description", "notes"
]

SCHEMA_COLUMNS = {
    "title": "TEXT NOT NULL DEFAULT ''",
    "inventory_num": "TEXT",
    "brand": "TEXT",
    "collection": "TEXT",
    "series": "TEXT",
    "character": "TEXT",
    "universe": "TEXT",
    "format": "TEXT",
    "height_cm": "TEXT",
    "material": "TEXT",
    "country": "TEXT",
    "production_country": "TEXT",
    "city": "TEXT",
    "museum": "TEXT",
    "building": "TEXT",
    "hall": "TEXT",
    "rack": "TEXT",
    "display_case": "TEXT",
    "shelf": "TEXT",
    "slot": "TEXT",
    "location": "TEXT",
    "author": "TEXT",
    "year": "TEXT",
    "collaboration": "TEXT",
    "condition": "TEXT",
    "value_usd": "TEXT",
    "insurance_usd": "TEXT",
    "coa": "TEXT",
    "hologram": "TEXT",
    "original_box": "TEXT",
    "description": "TEXT",
    "notes": "TEXT",
    "photo_path": "TEXT",
}


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("CREATE TABLE IF NOT EXISTS toys (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(toys)").fetchall()}
    for column, definition in SCHEMA_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE toys ADD COLUMN {column} {definition}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT ''
        )
    """)
    # Безопасные стартовые значения для старых карточек: пустые поля не перезаписываем.
    conn.execute("UPDATE toys SET country='Таиланд' WHERE country IS NULL OR country=''")
    conn.execute("UPDATE toys SET location='Коридор' WHERE location IS NULL OR location=''")
    conn.commit()
    conn.close()


def invalidate_faiss():
    global _faiss_index, _toy_ids_map
    _faiss_index = None
    _toy_ids_map = []


def get_clip():
    global _clip_model
    if _clip_model is None:
        from sentence_transformers import SentenceTransformer
        _clip_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32")
    return _clip_model


def rebuild_faiss():
    global _faiss_index, _toy_ids_map
    import faiss

    model = get_clip()
    conn = db()
    rows = conn.execute("SELECT id, photo_path FROM toys WHERE photo_path IS NOT NULL AND photo_path != ''").fetchall()
    conn.close()

    vectors, ids = [], []
    for row in rows:
        path = BASE / row["photo_path"]
        if not path.exists():
            continue
        try:
            with Image.open(path).convert("RGB") as img:
                vec = model.encode(img, normalize_embeddings=True)
            vectors.append(np.asarray(vec, dtype="float32"))
            ids.append(row["id"])
        except Exception:
            continue

    _faiss_index = faiss.IndexFlatIP(512)
    if vectors:
        _faiss_index.add(np.vstack(vectors).astype("float32"))
    _toy_ids_map = ids
    return _faiss_index.ntotal


def search_photo_bytes(data, limit=5):
    global _faiss_index, _toy_ids_map
    model = get_clip()
    if _faiss_index is None:
        rebuild_faiss()
    if _faiss_index is None or _faiss_index.ntotal == 0:
        return []

    with Image.open(io.BytesIO(data)).convert("RGB") as img:
        vec = model.encode(img, normalize_embeddings=True)
    query = np.asarray([vec], dtype="float32")
    k = min(limit, _faiss_index.ntotal)
    scores, indexes = _faiss_index.search(query, k)

    ids = [int(_toy_ids_map[int(i)]) for i in indexes[0] if 0 <= int(i) < len(_toy_ids_map)]
    if not ids:
        return []
    conn = db()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM toys WHERE id IN ({placeholders})", ids).fetchall()
    conn.close()
    by_id = {row["id"]: row for row in rows}
    result = []
    for score, idx in zip(scores[0], indexes[0]):
        idx = int(idx)
        if idx < 0 or idx >= len(_toy_ids_map):
            continue
        toy_id = _toy_ids_map[idx]
        row = by_id.get(toy_id)
        if row:
            result.append((row, float(score)))
    return result


def next_inventory(conn):
    rows = conn.execute("SELECT inventory_num FROM toys WHERE inventory_num LIKE 'INV-%'").fetchall()
    nums = []
    for row in rows:
        match = re.search(r"(\d+)$", row["inventory_num"] or "")
        if match:
            nums.append(int(match.group(1)))
    return f"INV-{(max(nums) + 1 if nums else 1):05d}"


def safe_photo_name(filename):
    filename = os.path.basename(filename)
    stem = re.sub(r"[^\w\-. ]+", "_", Path(filename).stem).strip() or "toy"
    ext = Path(filename).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    return stem, ext



RESEARCH_FIELDS = [
    "title", "brand", "collection", "series", "character", "universe",
    "format", "height_cm", "material", "author", "production_country",
    "year", "collaboration", "condition", "value_usd", "description"
]


def _extract_json_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def google_dossier(image_bytes, filename="toy.jpg"):
    if not GEMINI_API_KEY:
        raise RuntimeError("Не задан GEMINI_API_KEY в Render → Environment.")

    encoded = base64.b64encode(image_bytes).decode("ascii")
    suffix = Path(filename).suffix.lower()
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".heic": "image/heic"
    }.get(suffix, "image/jpeg")

    prompt = """
Ты — музейный исследователь дизайнерских игрушек.
Определи модель/персонажа по фотографии и, используя Google Search,
найди подтверждаемую информацию о конкретном экспонате.

Верни ТОЛЬКО JSON-объект с ключами:
title, brand, collection, series, character, universe, format,
height_cm, material, author, production_country, year, collaboration,
condition, value_usd, description, confidence, search_summary.

Правила:
- Не выдумывай. Если точных данных нет — ставь пустую строку.
- height_cm указывай только если источник подтверждает размер.
- value_usd только если есть разумная подтверждённая оценка/цена; иначе пусто.
- confidence: число от 0 до 1.
- search_summary: коротко объясни, почему предложенная модель похожа.
- description: краткое музейное описание без выдуманных фактов.
- Это ПРЕДЛОЖЕНИЕ для хранителя, не окончательная запись в музейную базу.
"""

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": encoded}}
            ]
        }],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    response = requests.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    text = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]
    result = _extract_json_text(text)
    if not isinstance(result, dict):
        raise ValueError("Google вернул неожиданный формат.")
    sources = []
    gm = data.get("candidates", [{}])[0].get("groundingMetadata", {})
    for chunk in gm.get("groundingChunks", []):
        web = chunk.get("web", {})
        if web.get("uri"):
            sources.append({"title": web.get("title") or web["uri"], "url": web["uri"]})
    result["sources"] = sources[:8]
    return result


@app.route("/admin/research", methods=["POST"])
def admin_research():
    gate = require_admin_view()
    if gate:
        return gate
    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Фото не получено"}), 400
    try:
        result = google_dossier(file.read(), file.filename)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/admin/toy/<int:toy_id>/research", methods=["POST"])
def research_existing_toy(toy_id):
    gate = require_admin_view()
    if gate:
        return gate
    conn = db()
    row = conn.execute("SELECT * FROM toys WHERE id=?", (toy_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "Экспонат не найден"}), 404
    photo_path = BASE / (row["photo_path"] or "")
    if not photo_path.exists():
        return jsonify({"ok": False, "error": "У экспоната нет фотографии"}), 400
    try:
        result = google_dossier(photo_path.read_bytes(), photo_path.name)
        return jsonify({"ok": True, "result": result, "toy_id": toy_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/admin/toy/<int:toy_id>/apply-research", methods=["POST"])
def apply_research(toy_id):
    gate = require_admin_view()
    if gate:
        return jsonify({"ok": False, "error": "Нет доступа"}), 403
    data = request.get_json(silent=True) or {}
    conn = db()
    row = conn.execute("SELECT * FROM toys WHERE id=?", (toy_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Экспонат не найден"}), 404

    updates = {}
    for field in RESEARCH_FIELDS:
        value = str(data.get(field, "") or "").strip()
        # Никогда не перезаписываем уже заполненное поле предложением.
        if value and not (row[field] or "").strip():
            updates[field] = value

    if updates:
        assignments = ", ".join(f"{f}=?" for f in updates)
        conn.execute(
            f"UPDATE toys SET {assignments} WHERE id=?",
            tuple(updates.values()) + (toy_id,)
        )
        conn.commit()
    conn.close()
    return jsonify({"ok": True, "updated": list(updates.keys())})


def admin_required():
    if not ADMIN_KEY:
        return True
    return bool(session.get("admin_ok"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not ADMIN_KEY:
        return redirect(url_for("admin"))
    if request.method == "POST":
        if request.form.get("key", "") == ADMIN_KEY:
            session["admin_ok"] = True
            return redirect(url_for("admin"))
        return render_template("admin_login.html", error="Неверный ключ")
    return render_template("admin_login.html", error=None)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_ok", None)
    return redirect(url_for("home"))


def require_admin_view():
    if not admin_required():
        return redirect(url_for("admin_login"))
    return None


@app.route("/")
def home():
    conn = db()
    count = conn.execute("SELECT COUNT(*) AS c FROM toys").fetchone()["c"]
    brand_rows = conn.execute("SELECT brand, COUNT(*) c FROM toys WHERE brand IS NOT NULL AND brand != '' GROUP BY brand ORDER BY c DESC LIMIT 8").fetchall()
    conn.close()
    return render_template("index.html", count=count, brands=brand_rows)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    field = request.args.get("field", "all")
    brand = request.args.get("brand", "").strip()
    condition = request.args.get("condition", "").strip()
    fmt = request.args.get("format", "").strip()
    conn = db()
    clauses, params = [], []

    if q:
        allowed = {
            "title": "title", "inventory": "inventory_num", "brand": "brand", "character": "character",
            "city": "city", "museum": "museum", "country": "country", "author": "author",
            "hall": "hall", "rack": "rack", "shelf": "shelf", "slot": "slot"
        }
        if field in allowed:
            clauses.append(f"{allowed[field]} LIKE ?")
            params.append(f"%{q}%")
        else:
            clauses.append("(" + " OR ".join([f"{c} LIKE ?" for c in ["title","inventory_num","brand","collection","series","character","universe","country","city","museum","author","hall","rack","shelf","slot"]]) + ")")
            params.extend([f"%{q}%"] * 15)
    if brand:
        clauses.append("brand = ?"); params.append(brand)
    if condition:
        clauses.append("condition = ?"); params.append(condition)
    if fmt:
        clauses.append("format = ?"); params.append(fmt)

    if clauses:
        rows = conn.execute("SELECT * FROM toys WHERE " + " AND ".join(clauses) + " ORDER BY id DESC LIMIT 100", params).fetchall()
    else:
        rows = conn.execute("SELECT * FROM toys ORDER BY id DESC LIMIT 100").fetchall()
    brands = conn.execute("SELECT DISTINCT brand FROM toys WHERE brand IS NOT NULL AND brand != '' ORDER BY brand").fetchall()
    conn.close()
    return render_template("results.html", rows=rows, q=q, field=field, brand=brand, condition=condition, fmt=fmt, brands=brands)


@app.route("/collection")
def collection():
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM toys").fetchone()["c"]
    value = conn.execute("SELECT SUM(CAST(REPLACE(value_usd, ',', '') AS REAL)) v FROM toys WHERE value_usd != ''").fetchone()["v"] or 0
    brands = conn.execute("SELECT COALESCE(NULLIF(brand,''),'Без бренда') name, COUNT(*) value FROM toys GROUP BY brand ORDER BY value DESC").fetchall()
    halls = conn.execute("SELECT COALESCE(NULLIF(hall,''),'Без зала') name, COUNT(*) value FROM toys GROUP BY hall ORDER BY value DESC").fetchall()
    conditions = conn.execute("SELECT COALESCE(NULLIF(condition,''),'Не указано') name, COUNT(*) value FROM toys GROUP BY condition ORDER BY value DESC").fetchall()
    conn.close()
    return render_template("collection.html", total=total, value=value, brands=brands, halls=halls, conditions=conditions)


@app.route("/quest")
def quest():
    conn = db()
    rows = conn.execute("SELECT * FROM toys WHERE title != '' ORDER BY RANDOM() LIMIT 3").fetchall()
    conn.close()
    return render_template("quest.html", rows=rows)


@app.route("/scan")
def scan_page():
    return render_template("scan.html")


@app.route("/api/search-photo", methods=["POST"])
def api_search_photo():
    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Фото не получено"}), 400
    try:
        matches = search_photo_bytes(file.read(), limit=5)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Ошибка сканера: {exc}"}), 500

    payload = []
    for row, score in matches:
        payload.append({
            "id": row["id"], "title": row["title"], "inventory_num": row["inventory_num"],
            "brand": row["brand"], "character": row["character"], "hall": row["hall"],
            "rack": row["rack"], "shelf": row["shelf"], "slot": row["slot"],
            "format": row["format"], "height_cm": row["height_cm"],
            "photo": url_for("photos", name=Path(row["photo_path"]).name) if row["photo_path"] else "",
            "score": round(score, 4), "url": url_for("toy", toy_id=row["id"])
        })
    return jsonify({"ok": True, "matches": payload, "threshold": 0.65})


@app.route("/toy/<int:toy_id>")
def toy(toy_id):
    conn = db()
    row = conn.execute("SELECT * FROM toys WHERE id=?", (toy_id,)).fetchone()
    conn.close()
    if not row:
        return "Экспонат не найден", 404
    return render_template("toy.html", toy=row)


@app.route("/shelf/<int:toy_id>")
def shelf(toy_id):
    conn = db()
    toy_row = conn.execute("SELECT * FROM toys WHERE id=?", (toy_id,)).fetchone()
    if not toy_row:
        conn.close(); return "Экспонат не найден", 404
    hall = toy_row["hall"] or "Зал"
    rack = toy_row["rack"] or "Стеллаж"
    rows = conn.execute("SELECT * FROM toys WHERE hall=? AND rack=? ORDER BY shelf, slot, id", (hall, rack)).fetchall()
    conn.close()
    return render_template("shelf.html", toy=toy_row, rows=rows)


@app.route("/photos/<path:name>")
def photos(name):
    return send_from_directory(PHOTOS, name)


@app.route("/admin")
def admin():
    gate = require_admin_view()
    if gate: return gate
    conn = db()
    rows = conn.execute("SELECT * FROM toys ORDER BY id DESC").fetchall()
    count = conn.execute("SELECT COUNT(*) c FROM toys").fetchone()["c"]
    value = conn.execute("SELECT SUM(CAST(REPLACE(value_usd, ',', '') AS REAL)) v FROM toys WHERE value_usd != ''").fetchone()["v"] or 0
    brands = conn.execute("SELECT COALESCE(NULLIF(brand,''),'Без бренда') brand, COUNT(*) c FROM toys GROUP BY brand ORDER BY c DESC LIMIT 12").fetchall()
    halls = conn.execute("SELECT COALESCE(NULLIF(hall,''),'Без зала') hall, COUNT(*) c FROM toys GROUP BY hall ORDER BY c DESC").fetchall()
    conn.close()
    return render_template("admin.html", rows=rows, count=count, value=value, brands=brands, halls=halls, admin_key_enabled=bool(ADMIN_KEY))


@app.route("/admin/upload", methods=["POST"])
def upload():
    gate = require_admin_view()
    if gate: return gate
    files = request.files.getlist("photos")
    common = {k: request.form.get(k, "").strip() for k in SCHEMA_COLUMNS if k not in {"title","inventory_num","photo_path","description","notes"}}
    conn = db()
    for file in files:
        if not file or not file.filename:
            continue
        stem, ext = safe_photo_name(file.filename)
        if ext not in {".jpg", ".png", ".webp", ".heic"}:
            continue
        target = PHOTOS / f"{stem}{ext}"
        n = 1
        while target.exists():
            target = PHOTOS / f"{stem}_{n}{ext}"; n += 1
        file.save(target)
        inv = next_inventory(conn)
        conn.execute("""
            INSERT INTO toys (title, inventory_num, brand, collection, series, character, universe, format, height_cm,
            material, country, production_country, city, museum, building, hall, rack, display_case, shelf, slot,
            location, author, year, collaboration, condition, value_usd, insurance_usd, coa, hologram, original_box,
            description, notes, photo_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            stem, inv, common.get("brand",""), common.get("collection",""), common.get("series",""),
            common.get("character",""), common.get("universe",""), common.get("format",""), common.get("height_cm",""),
            common.get("material",""), common.get("country","Таиланд"), common.get("production_country",""),
            common.get("city",""), common.get("museum",""), common.get("building",""), common.get("hall",""),
            common.get("rack",""), common.get("display_case",""), common.get("shelf",""), common.get("slot",""),
            common.get("location","Коридор"), common.get("author",""), common.get("year",""), common.get("collaboration",""),
            common.get("condition",""), common.get("value_usd",""), common.get("insurance_usd",""), common.get("coa",""),
            common.get("hologram",""), common.get("original_box",""), "", "", str(target.relative_to(BASE))
        ))
    conn.commit(); conn.close(); invalidate_faiss()
    return redirect(url_for("admin"))


@app.route("/admin/toy/<int:toy_id>", methods=["POST"])
def edit_toy(toy_id):
    gate = require_admin_view()
    if gate: return gate
    values = {field: request.form.get(field, "").strip() for field in TOY_FIELDS}
    conn = db()
    assignments = ", ".join(f"{f}=?" for f in TOY_FIELDS)
    conn.execute(f"UPDATE toys SET {assignments} WHERE id=?", tuple(values[f] for f in TOY_FIELDS) + (toy_id,))
    conn.commit(); conn.close(); invalidate_faiss()
    return redirect(url_for("admin"))


@app.route("/admin/toy/<int:toy_id>/delete", methods=["POST"])
def delete_toy(toy_id):
    gate = require_admin_view()
    if gate: return gate
    conn = db(); row = conn.execute("SELECT photo_path FROM toys WHERE id=?", (toy_id,)).fetchone()
    if row:
        photo = BASE / (row["photo_path"] or "")
        if photo.exists():
            try: photo.unlink()
            except OSError: pass
        conn.execute("DELETE FROM toys WHERE id=?", (toy_id,)); conn.commit()
    conn.close(); invalidate_faiss()
    return redirect(url_for("admin"))


@app.route("/api/stats")
def stats():
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM toys").fetchone()["c"]
    value = conn.execute("SELECT SUM(CAST(REPLACE(value_usd, ',', '') AS REAL)) v FROM toys WHERE value_usd != ''").fetchone()["v"] or 0
    brands = [dict(r) for r in conn.execute("SELECT COALESCE(NULLIF(brand,''),'Без бренда') name, COUNT(*) value FROM toys GROUP BY brand ORDER BY value DESC LIMIT 10")]
    conn.close()
    return jsonify({"total": total, "value_usd": value, "brands": brands})



@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return jsonify({"ok": False, "error": "BOT_TOKEN не настроен"}), 503

    update = request.get_json(silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return jsonify({"ok": True})

    text_message = message.get("text", "")
    webapp_url = os.getenv("WEBAPP_URL", request.host_url.rstrip("/"))
    reply_markup = {
        "inline_keyboard": [[
            {"text": "🏛 Открыть TOY MUSEUM",
             "web_app": {"url": webapp_url}}
        ]]
    }

    if text_message.startswith("/start") or text_message in {"/search", "/find"}:
        text = (
            "Добро пожаловать в TOY MUSEUM.\n\n"
            "Цифровой паспорт коллекции: найдите экспонат по фото, "
            "номеру, бренду, персонажу или месту хранения."
        )
    elif message.get("photo"):
        reply_markup = {
            "inline_keyboard": [[
                {"text": "📷 Открыть фотосканер",
                 "web_app": {"url": webapp_url + "/scan"}}
            ]]
        }
        text = "Фото получено. Откройте фотосканер — найдём похожие экспонаты в коллекции."
    else:
        text = "Откройте TOY MUSEUM и выберите способ поиска."

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "reply_markup": reply_markup},
            timeout=15,
        )
    except requests.RequestException:
        pass
    return jsonify({"ok": True})


def register_telegram_webhook():
    token = os.getenv("BOT_TOKEN", "")
    webapp_url = os.getenv("WEBAPP_URL", "").rstrip("/")
    if not token or not webapp_url:
        return
    webhook_url = webapp_url + "/telegram/webhook"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "drop_pending_updates": True},
            timeout=20,
        )
        print("Telegram webhook:", response.status_code, webhook_url)
    except requests.RequestException as exc:
        print("Telegram webhook registration skipped:", exc)


init_db()
register_telegram_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
