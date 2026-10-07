import os, sqlite3, base64, mimetypes, json, io, hashlib
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session, abort
from PIL import Image
import numpy as np
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "museum.db")
PHOTOS = os.path.join(BASE, "photos")
PLACEHOLDER = os.path.join(BASE, "static", "toy-placeholder.svg")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

FIELDS = [
    "title", "inventory_num", "brand", "collection", "series", "character", "universe", "format",
    "height_cm", "material", "author", "year", "collaboration", "condition", "value_usd",
    "production_country", "country", "city", "museum", "building", "hall", "rack", "display_case",
    "shelf", "slot", "location", "description", "notes", "photo_path"
]

EDIT_FIELDS = [x for x in FIELDS if x not in ("photo_path", "inventory_num")]


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    os.makedirs(PHOTOS, exist_ok=True)
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS toys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, inventory_num TEXT, brand TEXT, collection TEXT, series TEXT,
        character TEXT, universe TEXT, format TEXT, height_cm TEXT, material TEXT,
        author TEXT, year TEXT, collaboration TEXT, condition TEXT, value_usd TEXT,
        production_country TEXT, country TEXT, city TEXT, museum TEXT, building TEXT,
        hall TEXT, rack TEXT, display_case TEXT, shelf TEXT, slot TEXT, location TEXT,
        description TEXT, notes TEXT, photo_path TEXT
    )""")
    existing = {r[1] for r in c.execute("PRAGMA table_info(toys)").fetchall()}
    for field in FIELDS:
        if field not in existing:
            c.execute(f"ALTER TABLE toys ADD COLUMN {field} TEXT")
    c.commit()
    c.close()


def toy_rows():
    c = db()
    rows = [dict(x) for x in c.execute("SELECT * FROM toys ORDER BY id DESC").fetchall()]
    c.close()
    return rows


def photo_filename(value):
    if not value:
        return ""
    return os.path.basename(str(value).replace("\\", "/"))


def photo_exists(value):
    name = photo_filename(value)
    return bool(name and os.path.isfile(os.path.join(PHOTOS, name)))


def image_url(value):
    name = photo_filename(value)
    return url_for("photos", name=name) if name else url_for("placeholder")

app.jinja_env.globals["image_url"] = image_url


def normalize_image(im):
    im = im.convert("RGB").resize((64, 64))
    a = np.asarray(im, dtype=np.float32) / 255.0
    gray = a.mean(axis=2)
    return a, gray


def visual_vector(im):
    a, gray = normalize_image(im)
    small = gray[::4, ::4].flatten()
    hist = []
    for ch in range(3):
        hist.extend(np.histogram(a[:, :, ch], bins=16, range=(0, 1), density=True)[0])
    edge_x = np.diff(gray, axis=1).flatten()
    edge_y = np.diff(gray, axis=0).flatten()
    v = np.concatenate([small, np.array(hist, dtype=np.float32), edge_x[::4], edge_y[:,] [::4]])
    norm = np.linalg.norm(v)
    return v / norm if norm else v


def similarity(im1, im2):
    try:
        a = visual_vector(im1)
        b = visual_vector(im2)
        cosine = float(np.dot(a, b))
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))
    except Exception:
        return 0.0


def search_bytes(data, k=6):
    try:
        query = Image.open(io.BytesIO(data)).convert("RGB")
        qv = visual_vector(query)
    except Exception:
        return []
    c = db()
    rows = c.execute("SELECT * FROM toys ORDER BY id DESC").fetchall()
    c.close()
    out = []
    for row in rows:
        item = dict(row)
        name = photo_filename(item.get("photo_path"))
        path = os.path.join(PHOTOS, name)
        if not name or not os.path.isfile(path):
            continue
        try:
            iv = visual_vector(Image.open(path).convert("RGB"))
            cosine = float(np.dot(qv, iv))
            score = max(0.0, min(1.0, (cosine + 1.0) / 2.0))
            item["similarity"] = round(score * 100, 1)
            out.append(item)
        except Exception:
            continue
    out.sort(key=lambda x: x["similarity"], reverse=True)
    return out[:k]


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "TOY MUSEUM"})


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip().lower()
    field = request.args.get("field", "title")
    allowed = set(FIELDS)
    if field not in allowed:
        field = "title"
    rows = toy_rows()
    if q:
        rows = [x for x in rows if q in str(x.get(field, "") or "").lower()
                or q in str(x.get("title", "") or "").lower()
                or q in str(x.get("brand", "") or "").lower()
                or q in str(x.get("character", "") or "").lower()
                or q in str(x.get("inventory_num", "") or "").lower()]
    return render_template("results.html", toys=rows, q=q)


@app.route("/collection")
def collection():
    # The catalogue lives in SQLite; it is not rendered on the home screen.
    return render_template("collection.html", toys=toy_rows())


@app.route("/scan")
def scan():
    return render_template("scan.html")


@app.route("/api/search-photo", methods=["POST"])
def api_photo():
    f = request.files.get("photo")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Фото не получено"}), 400
    results = search_bytes(f.read(), 6)
    return jsonify({"ok": True, "results": results, "count": len(results)})


@app.route("/toy/<int:tid>")
def toy(tid):
    c = db()
    r = c.execute("SELECT * FROM toys WHERE id=?", (tid,)).fetchone()
    c.close()
    if not r:
        return "Not found", 404
    return render_template("toy.html", toy=dict(r))


@app.route("/photos/<path:name>")
def photos(name):
    safe = os.path.basename(name)
    path = os.path.join(PHOTOS, safe)
    if not os.path.isfile(path):
        return send_from_directory(os.path.dirname(PLACEHOLDER), os.path.basename(PLACEHOLDER), mimetype="image/svg+xml")
    return send_from_directory(PHOTOS, safe)


@app.route("/placeholder.svg")
def placeholder():
    return send_from_directory(os.path.dirname(PLACEHOLDER), os.path.basename(PLACEHOLDER), mimetype="image/svg+xml")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        key = request.form.get("key", "")
        expected = os.getenv("ADMIN_KEY", "admin")
        if key == expected:
            session["admin"] = True
            return redirect(request.args.get("next") or url_for("admin"))
        return render_template("admin_login.html", error="Неверный пароль")
    return render_template("admin_login.html", error="")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", toys=toy_rows())


@app.route("/admin/upload", methods=["POST"])
@admin_required
def upload():
    files = request.files.getlist("photos")
    c = db()
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        raw_name = os.path.basename(f.filename)
        stem, extension = os.path.splitext(raw_name)
        digest = hashlib.sha1((raw_name + str(os.urandom(8))).encode()).hexdigest()[:8]
        safe = f"{stem[:60]}-{digest}{extension.lower()}"
        path = os.path.join(PHOTOS, safe)
        f.save(path)
        n = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM toys").fetchone()[0]
        c.execute("""INSERT INTO toys(title,inventory_num,country,location,photo_path)
                     VALUES(?,?,?,?,?)""", (stem.replace("_", " ").replace("-", " ").strip(), f"INV-{n:05d}", "", "", safe))
    c.commit()
    c.close()
    return redirect(url_for("admin"))


@app.route("/admin/toy/<int:tid>", methods=["POST"])
@admin_required
def edit(tid):
    vals = [request.form.get(x, "").strip() for x in EDIT_FIELDS]
    c = db()
    c.execute("UPDATE toys SET " + ",".join(f"{x}=?" for x in EDIT_FIELDS) + " WHERE id=?", vals + [tid])
    c.commit()
    c.close()
    return redirect(url_for("admin"))


@app.route("/admin/toy/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_toy(tid):
    c = db()
    r = c.execute("SELECT photo_path FROM toys WHERE id=?", (tid,)).fetchone()
    c.execute("DELETE FROM toys WHERE id=?", (tid,))
    c.commit()
    c.close()
    if r and r["photo_path"]:
        path = os.path.join(PHOTOS, photo_filename(r["photo_path"]))
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return redirect(url_for("admin"))


RESEARCH_FIELDS = [
    "title", "brand", "collection", "series", "character", "universe", "format", "height_cm",
    "material", "author", "production_country", "year", "collaboration", "condition", "value_usd", "description"
]


@app.route("/admin/toy/<int:tid>/research", methods=["POST"])
@admin_required
def research(tid):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    c = db()
    r = c.execute("SELECT * FROM toys WHERE id=?", (tid,)).fetchone()
    c.close()
    if not key or not r:
        return jsonify({"ok": False, "error": "GEMINI_API_KEY не настроен или экспонат не найден"}), 400
    name = photo_filename(r["photo_path"])
    path = os.path.join(PHOTOS, name)
    if not name or not os.path.exists(path):
        return jsonify({"ok": False, "error": "У экспоната нет фотографии"}), 400
    raw = open(path, "rb").read()
    data = base64.b64encode(raw).decode()
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    prompt = ("Определи дизайнерскую игрушку по фотографии. Используй Google Search только для проверки. "
              "Не выдумывай. Верни только JSON с полями: " + ", ".join(RESEARCH_FIELDS) + ". "
              "Если поле неизвестно, оставь пустую строку. Это предложение для хранителя, не финальная запись.")
    payload = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": data}}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    try:
        rr = requests.post(url, json=payload, timeout=90)
        rr.raise_for_status()
        j = rr.json()
        parts = j.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if p.get("text"))
        proposal = json.loads(text) if text else {}
        return jsonify({"ok": True, "data": {k: proposal.get(k, "") for k in RESEARCH_FIELDS}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/admin/toy/<int:tid>/apply-research", methods=["POST"])
@admin_required
def apply_research(tid):
    payload = request.get_json(silent=True) or {}
    selected = payload.get("fields", {})
    c = db()
    row = c.execute("SELECT * FROM toys WHERE id=?", (tid,)).fetchone()
    if not row:
        c.close()
        return jsonify({"ok": False, "error": "Экспонат не найден"}), 404
    allowed = set(RESEARCH_FIELDS)
    for key, val in selected.items():
        if key in allowed and not row[key] and str(val).strip():
            c.execute(f"UPDATE toys SET {key}=? WHERE id=?", (str(val).strip(), tid))
    c.commit()
    c.close()
    return jsonify({"ok": True})


@app.route("/telegram/webhook", methods=["POST"])
def webhook():
    token = os.getenv("BOT_TOKEN", "").strip()
    web = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    if not token or not web:
        return "ok"
    update = request.get_json(silent=True) or {}
    message = update.get("message", {})
    chat = message.get("chat", {}).get("id")
    if not chat:
        return "ok"
    if message.get("photo"):
        text = "Фото получено. Откройте фотосканер — он покажет несколько похожих экспонатов."
        url = web + "/scan"
        label = "📷 Открыть фотосканер"
    else:
        text = "Добро пожаловать в TOY MUSEUM. Найдите экспонат по фото, номеру, названию или месту хранения."
        url = web
        label = "🏛 Открыть TOY MUSEUM"
    kb = {"inline_keyboard": [[{"text": label, "web_app": {"url": url}}]]}
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text, "reply_markup": kb}, timeout=15)
    except requests.RequestException:
        pass
    return "ok"


def register_telegram_webhook():
    token = os.getenv("BOT_TOKEN", "").strip()
    web = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    if not token or not web:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/setWebhook", json={"url": web + "/telegram/webhook", "drop_pending_updates": True}, timeout=15)
    except requests.RequestException:
        pass


init()
register_telegram_webhook()
