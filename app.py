import os
import sqlite3
import threading
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image

DB_PATH = os.getenv("MUSEUM_DB", "museum.db")
PHOTOS_DIR = Path(os.getenv("PHOTOS_DIR", "photos"))
MODEL_NAME = os.getenv("CLIP_MODEL", "clip-ViT-B-32")
PORT = int(os.getenv("PORT", "8080"))

app = Flask(__name__)
model = None
index = None
toy_ids_map = []
index_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
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
    existing = {r["name"] for r in cur.execute("PRAGMA table_info(toys)").fetchall()}
    for name in ["inventory_num", "country", "city", "museum", "building", "hall", "display_case", "shelf", "location", "description", "photo_path"]:
        if name not in existing:
            cur.execute(f"ALTER TABLE toys ADD COLUMN {name} TEXT")
    conn.commit()
    conn.close()


def resolve_photo_path(photo_path):
    if not photo_path:
        return None
    candidates = [Path(photo_path), Path(str(photo_path).replace("\\", "/")), PHOTOS_DIR / Path(photo_path).name]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def photo_url(photo_path):
    p = resolve_photo_path(photo_path)
    return f"/photos/{p.name}" if p else None


def toy_to_dict(row):
    d = dict(row)
    if not d.get("location"):
        d["location"] = ", ".join(str(d.get(k)) for k in ["building", "hall", "display_case", "shelf"] if d.get(k))
    d["photo_url"] = photo_url(d.get("photo_path"))
    return d


def load_model_and_index():
    global model, index, toy_ids_map
    try:
        from sentence_transformers import SentenceTransformer
        import faiss
    except ImportError as e:
        print("CLIP/FAISS unavailable:", e)
        return

    print("Loading CLIP model...")
    model = SentenceTransformer(MODEL_NAME)
    conn = get_db()
    rows = conn.execute("SELECT id, title, photo_path FROM toys ORDER BY id").fetchall()
    conn.close()

    embeddings, ids = [], []
    for row in rows:
        p = resolve_photo_path(row["photo_path"])
        if not p:
            continue
        try:
            vec = model.encode(Image.open(p).convert("RGB"), normalize_embeddings=True)
            embeddings.append(np.asarray(vec, dtype="float32"))
            ids.append(int(row["id"]))
        except Exception as e:
            print("Index error:", p, e)

    with index_lock:
        index = faiss.IndexFlatIP(512)
        toy_ids_map = ids
        if embeddings:
            index.add(np.vstack(embeddings).astype("float32"))
    print(f"FAISS indexed: {len(ids)} photos")


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/photos/<path:filename>")
def photos(filename):
    return send_from_directory(PHOTOS_DIR, filename)


@app.get("/api/stats")
def stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM toys").fetchone()[0]
    countries = conn.execute("SELECT COUNT(DISTINCT country) FROM toys WHERE country IS NOT NULL AND country <> ''").fetchone()[0]
    cities = conn.execute("SELECT COUNT(DISTINCT city) FROM toys WHERE city IS NOT NULL AND city <> ''").fetchone()[0]
    museums = conn.execute("SELECT COUNT(DISTINCT museum) FROM toys WHERE museum IS NOT NULL AND museum <> ''").fetchone()[0]
    conn.close()
    return jsonify({"total": total, "countries": countries, "cities": cities, "museums": museums, "indexed": int(index.ntotal) if index is not None else 0})


@app.get("/api/locations")
def locations():
    conn = get_db()
    def vals(col):
        return [r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM toys WHERE {col} IS NOT NULL AND {col} <> '' ORDER BY {col} COLLATE NOCASE").fetchall()]
    data = {"countries": vals("country"), "cities": vals("city"), "museums": vals("museum")}
    conn.close()
    return jsonify(data)


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "").strip()
    country = request.args.get("country", "").strip()
    museum = request.args.get("museum", "").strip()
    limit = min(max(int(request.args.get("limit", "100")), 1), 200)

    conn = get_db()
    sql = "SELECT * FROM toys WHERE 1=1"
    params = []
    if q:
        like = f"%{q}%"
        sql += " AND (title LIKE ? OR inventory_num LIKE ? OR description LIKE ? OR country LIKE ? OR city LIKE ? OR museum LIKE ? OR building LIKE ? OR hall LIKE ? OR display_case LIKE ? OR shelf LIKE ? OR location LIKE ?)"
        params.extend([like] * 11)
    if city:
        sql += " AND city LIKE ?"; params.append(f"%{city}%")
    if country:
        sql += " AND country LIKE ?"; params.append(f"%{country}%")
    if museum:
        sql += " AND museum LIKE ?"; params.append(f"%{museum}%")
    sql += " ORDER BY title COLLATE NOCASE, id LIMIT ?"; params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify([toy_to_dict(r) for r in rows])


@app.get("/api/toys/<int:toy_id>")
def toy(toy_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM toys WHERE id = ?", (toy_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(toy_to_dict(row))


@app.post("/api/scan")
def scan():
    global model, index, toy_ids_map
    if model is None or index is None or index.ntotal == 0:
        return jsonify({"error": "Индекс CLIP ещё не готов. Запусти приложение и подожди загрузку модели."}), 503
    if "image" not in request.files:
        return jsonify({"error": "Фото не передано"}), 400
    try:
        image = Image.open(request.files["image"].stream).convert("RGB")
        vec = model.encode(image, normalize_embeddings=True).astype("float32").reshape(1, -1)
        scores, positions = index.search(vec, min(5, index.ntotal))
        ids = [toy_ids_map[int(p)] for p in positions[0] if int(p) >= 0]
        if not ids:
            return jsonify({"matches": []})
        conn = get_db()
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(f"SELECT * FROM toys WHERE id IN ({placeholders})", ids).fetchall()
        conn.close()
        by_id = {int(r["id"]): toy_to_dict(r) for r in rows}
        matches = []
        for toy_id, score in zip(ids, scores[0][:len(ids)]):
            if toy_id in by_id:
                item = by_id[toy_id]
                item["score"] = round(float(score), 4)
                item["confidence"] = round(max(0, min(100, float(score) * 100)), 1)
                matches.append(item)
        return jsonify({"matches": matches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    ensure_schema()
    threading.Thread(target=load_model_and_index, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
