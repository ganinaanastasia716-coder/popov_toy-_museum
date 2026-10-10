import os, io, json, base64, sqlite3, secrets, mimetypes
os.environ.setdefault("HF_HOME", "/data/hf-cache")
import hashlib
import threading
import numpy as np
import torch
from transformers import CLIPModel, CLIPProcessor
from pathlib import Path
from datetime import datetime, timezone
from functools import wraps
import requests
from PIL import Image, ImageOps, ImageFilter
from pillow_heif import register_heif_opener
register_heif_opener()
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory

ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv("DATABASE_PATH",ROOT/"museum.db"))
PHOTOS=Path(os.getenv("PHOTO_DIR",ROOT/"photos")); PHOTOS.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv("FLASK_SECRET","local-dev-change-this")
ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD","change-me")
BOT_TOKEN=os.getenv("BOT_TOKEN",""); WEBAPP_URL=os.getenv("WEBAPP_URL","")
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY",""); GEMINI_MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
FIELDS=[("inventory_number","Инвентарный номер"),("name","Название"),("series","Серия"),("brand","Бренд"),("author","Автор"),("rarity","Редкость"),("height","Размер / высота"),("release_year","Год выпуска"),("material","Материал"),("production_country","Страна производства"),("condition","Состояние"),("market_price","Рыночная цена"),("purchase_price","Цена покупки"),("currency","Валюта"),("country","Страна хранения"),("city","Город"),("museum","Музей"),("building","Корпус"),("hall","Зал"),("rack","Стеллаж"),("display_case","Витрина"),("shelf","Полка"),("slot","Место"),("description","Описание"),("image_path","Путь к фото")]
def photo_sha256(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 with conn() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS toys(id INTEGER PRIMARY KEY AUTOINCREMENT,inventory_number TEXT UNIQUE,name TEXT NOT NULL DEFAULT '',series TEXT DEFAULT '',brand TEXT DEFAULT '',author TEXT DEFAULT '',rarity TEXT DEFAULT '',height TEXT DEFAULT '',release_year INTEGER,material TEXT DEFAULT '',production_country TEXT DEFAULT '',condition TEXT DEFAULT '',market_price REAL,purchase_price REAL,currency TEXT DEFAULT 'USD',country TEXT DEFAULT 'Thailand',city TEXT DEFAULT '',museum TEXT DEFAULT 'Popov Toy Museum',building TEXT DEFAULT '',hall TEXT DEFAULT '',rack TEXT DEFAULT '',display_case TEXT DEFAULT '',shelf TEXT DEFAULT '',slot TEXT DEFAULT '',description TEXT DEFAULT '',image_path TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
  for col in ["name","brand","series","inventory_number"]: c.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON toys({col})")
  columns = {row["name"] for row in c.execute("PRAGMA table_info(toys)").fetchall()}
  if "photo_hash" not in columns: c.execute("ALTER TABLE toys ADD COLUMN photo_hash TEXT")
  if "clip_embedding" not in columns: c.execute("ALTER TABLE toys ADD COLUMN clip_embedding BLOB")
def next_num(c):
 n=c.execute("SELECT COUNT(*) FROM toys").fetchone()[0]+1
 while c.execute("SELECT 1 FROM toys WHERE inventory_number=?",(f"PM-TOY-{n:05d}",)).fetchone(): n+=1
 return f"PM-TOY-{n:05d}"
def as_toy(r):
 d=dict(r); d.pop("clip_embedding",None); d["location"]=" · ".join(str(d[k]) for k in ["country","city","museum","building","hall","rack","display_case","shelf","slot"] if d.get(k)) or "Место не назначено"; return d
def admin_only(fn):
 from functools import wraps
 @wraps(fn)
 def w(*a,**kw):
  if not session.get("admin"): return redirect(url_for("login",next=request.path))
  return fn(*a,**kw)
 return w
# CLIP model is loaded only when photo search/upload needs it.
# On Render, the model runs on CPU and its embeddings are cached in SQLite.
CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")
_clip_model = None
_clip_processor = None
_clip_lock = threading.Lock()


def get_clip():
    global _clip_model, _clip_processor
    if _clip_model is None or _clip_processor is None:
        with _clip_lock:
            if _clip_model is None or _clip_processor is None:
                processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
                model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
                model.eval()
                model.to("cpu")
                _clip_processor = processor
                _clip_model = model
    return _clip_model, _clip_processor


def clip_embedding(raw):
    """Create a normalized CLIP image vector, stored as float32 bytes."""
    model, processor = get_clip()
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    with torch.inference_mode():
        vector = model.get_image_features(**inputs)
        if not isinstance(vector, torch.Tensor):
            vector = vector.pooler_output
        vector = torch.nn.functional.normalize(vector, p=2, dim=-1)
    return vector[0].cpu().numpy().astype(np.float32).tobytes()


def embedding_similarity(a, b):
    try:
        va = np.frombuffer(a, dtype=np.float32)
        vb = np.frombuffer(b, dtype=np.float32)
        if va.size == 0 or va.shape != vb.shape:
            return -1.0
        return float(np.dot(va, vb))
    except (TypeError, ValueError):
        return -1.0


def _get_or_create_embedding(toy_id, image_path, cached_embedding, connection=None):
    """Return the cached embedding or compute and store it.

    If `connection` is given, the embedding is written on it and the caller is
    responsible for committing; otherwise a short-lived connection is used.
    """
    if cached_embedding:
        return cached_embedding
    path = PHOTOS / image_path
    if not path.is_file():
        return None
    embedding = clip_embedding(path.read_bytes())
    if connection is not None:
        connection.execute("UPDATE toys SET clip_embedding=? WHERE id=?", (embedding, toy_id))
    else:
        with conn() as c:
            c.execute("UPDATE toys SET clip_embedding=? WHERE id=?", (embedding, toy_id))
    return embedding


def scan_local(raw):
    """Search every catalog image with CLIP and return the closest candidates."""
    query_embedding = clip_embedding(raw)
    out = []
    c = conn()
    try:
        rows = c.execute(
            "SELECT * FROM toys WHERE image_path IS NOT NULL AND image_path != ''"
        ).fetchall()
        for row in rows:
            try:
                embedding = _get_or_create_embedding(
                    row["id"], row["image_path"], row["clip_embedding"], connection=c
                )
                if not embedding:
                    continue
                score = embedding_similarity(query_embedding, embedding)
                out.append({"toy": as_toy(row), "score": round(score, 4)})
            except Exception:
                app.logger.exception("CLIP failed for catalog item id=%s", row["id"])
        c.commit()
    finally:
        c.close()
    return sorted(out, key=lambda item: item["score"], reverse=True)[:6]

def online_dossier(raw, filename):
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Не настроен GEMINI_API_KEY. Добавьте ключ Gemini "
            "в переменные окружения Render."
        )

    prompt = """
You are an expert researcher identifying designer collectible toys
for a museum catalog.

Carefully examine the uploaded photo. Look for character, shape,
colors, logos, labels, packaging, and distinctive visual details.

Use Google Search to verify the likely identification. Prefer official
manufacturer, artist, and brand websites, reputable retailers,
auction records, and established collector databases.

Return ONE valid JSON object only, without Markdown or explanations
outside the JSON. Include these fields:
name, series, brand, author, rarity, height, release_year, material,
production_country, market_price, currency, description, confidence,
search_summary.

Use strings for all fields except confidence, which must be a number
from 0 to 1. If a fact cannot be verified, return an empty string.
Never invent dimensions, prices, release years, authors, or countries.

In description, describe the visible toy and distinguish visual
observations from verified product information.
In search_summary, briefly explain what was verified and what remains
uncertain. Do not claim certainty without evidence.
"""

    mime = mimetypes.guess_type(filename)[0] or "image/jpeg"

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": base64.b64encode(raw).decode("utf-8"),
                        },
                    },
                ],
            },
        ],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2},
    }

    response = requests.post(
        url,
        params={"key": GEMINI_API_KEY},
        json=body,
        timeout=90,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not response.ok:
        error_info = payload.get("error", {})
        message = error_info.get("message") or (
            f"Google Gemini вернул HTTP {response.status_code}."
        )
        raise RuntimeError(
            f"Ошибка Gemini API (HTTP {response.status_code}): {message}"
        )

    candidates = payload.get("candidates") or []

    if not candidates:
        feedback = payload.get("promptFeedback") or {}
        reason = feedback.get("blockReason")

        if reason:
            raise RuntimeError(
                f"Gemini не обработал фотографию: {reason}."
            )

        raise RuntimeError(
            "Gemini вернул пустой ответ. Попробуйте другое фото."
        )

    parts = (candidates[0].get("content") or {}).get("parts") or []
    answer = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict)
    ).strip()

    if not answer:
        raise RuntimeError(
            "Gemini не вернул текст с результатом поиска."
        )

    # Убираем Markdown-обрамление, если модель его добавила.
    if answer.startswith("```"):
        answer = answer.split("\n", 1)[-1].strip()
        if answer.endswith("```"):
            answer = answer[:-3].strip()

    try:
        data = json.loads(answer)
    except json.JSONDecodeError:
        # Иногда модель добавляет текст вокруг JSON.
        start = answer.find("{")
        end = answer.rfind("}")

        if start == -1 or end <= start:
            raise RuntimeError(
                "Gemini вернул результат в неподходящем формате. "
                "Попробуйте ещё раз."
            )

        try:
            data = json.loads(answer[start:end + 1])
        except json.JSONDecodeError:
            raise RuntimeError(
                "Не удалось прочитать ответ Gemini. Попробуйте ещё раз."
            )

    if not isinstance(data, dict):
        raise RuntimeError("Gemini вернул неожиданный формат данных.")

    # Сохраняем ссылки, найденные Google Search, если они есть.
    sources = []

    for candidate in candidates:
        metadata = candidate.get("groundingMetadata") or {}

        for chunk in metadata.get("groundingChunks", []):
            web_source = chunk.get("web") or {}
            source_url = web_source.get("uri")

            if source_url:
                source = {
                    "title": web_source.get("title") or source_url,
                    "url": source_url,
                }

                if source not in sources:
                    sources.append(source)

    data["sources"] = sources

    return data
@app.get("/")
def home():
 q=request.args.get("q","").strip(); toys=[]
 brand_defs={"POP MART":["POP MART","POP MART"],"ROBBi":["ROBBi","ROBBI"],"KAWS":["KAWS"],"BE@RBRICK":["BE@RBRICK","BEARBRICK","BEAR BRICK"],"INSTINCTOY":["INSTINCTOY","INSTINCT TOY"],"STAR WARS":["STAR WARS","STARWARS"]}
 brand_toys={}; brand_counts={}
 with conn() as c:
  count=c.execute("SELECT COUNT(*) FROM toys").fetchone()[0]
  if q: toys=[as_toy(r) for r in c.execute("SELECT * FROM toys WHERE name LIKE ? OR inventory_number LIKE ? OR brand LIKE ? OR series LIKE ? ORDER BY name LIMIT 24",tuple([f"%{q}%"]*4)).fetchall()]
  for display,aliases in brand_defs.items():
   terms=[]
   for alias in aliases: terms.append("UPPER(brand) LIKE ?")
   params=[f"%{a.upper()}%" for a in aliases]
   brand_counts[display]=c.execute("SELECT COUNT(*) FROM toys WHERE "+" OR ".join(terms),params).fetchone()[0]
   row=c.execute("SELECT * FROM toys WHERE image_path!='' AND ("+" OR ".join(terms)+") ORDER BY CASE WHEN name!='' THEN 0 ELSE 1 END,id DESC LIMIT 1",params).fetchone()
   if row: brand_toys[display]=as_toy(row)
 return render_template("index.html",q=q,toys=toys,count=count,brand_toys=brand_toys,brand_counts=brand_counts)
@app.get("/collection")
def collection():
 page=max(1,int(request.args.get("page",1))); q=request.args.get("q","").strip(); brand=request.args.get("brand","").strip()
 clauses=[]; args=[]
 if q: clauses.append("(name LIKE ? OR inventory_number LIKE ? OR series LIKE ? OR brand LIKE ?)"); args += [f"%{q}%"]*4
 if brand: clauses.append("brand=?"); args.append(brand)
 where=(" WHERE "+" AND ".join(clauses)) if clauses else ""
 with conn() as c:
  total=c.execute("SELECT COUNT(*) FROM toys"+where,args).fetchone()[0]
  toys=[as_toy(r) for r in c.execute("SELECT * FROM toys"+where+" ORDER BY name LIMIT 24 OFFSET ?",args+[(page-1)*24]).fetchall()]
  brands=[r[0] for r in c.execute("SELECT DISTINCT brand FROM toys WHERE brand!='' ORDER BY brand")]
 return render_template("collection.html",toys=toys,q=q,brand=brand,brands=brands,page=page,pages=max(1,(total+23)//24),total=total)
@app.get("/toy/<int:toy_id>")
def detail(toy_id):
 with conn() as c:
  row=c.execute("SELECT * FROM toys WHERE id=?",(toy_id,)).fetchone()
  if not row:return render_template("404.html"),404
  toy=as_toy(row); similar=[as_toy(r) for r in c.execute("SELECT * FROM toys WHERE id!=? AND ((series!='' AND series=?) OR (brand!='' AND brand=?)) LIMIT 4",(toy_id,row["series"],row["brand"])).fetchall()]
 return render_template("toy.html",toy=toy,similar=similar)
@app.get("/scan")
def scan_page(): return render_template("scan.html")
@app.post("/api/scan")
def api_scan():
 f=request.files.get("photo")
 if not f: return jsonify(error="Сделайте фото или выберите его из галереи."),400
 raw=f.read()
 try:
  matches=scan_local(raw)
 except Exception:
  app.logger.exception("CLIP photo search failed")
  return jsonify(error="Не удалось запустить визуальный поиск. Проверьте журналы Render: возможно, модель CLIP ещё загружается или не хватает памяти."),503
 threshold=float(os.getenv("PHOTO_MATCH_THRESHOLD","0.82"))
 if matches and matches[0]["score"]>=threshold:
  return jsonify(mode="database",matches=matches,message="Похожие экспонаты найдены в базе.")
 return jsonify(mode="not_found",matches=matches,message="Уверенное совпадение в коллекции не найдено. Онлайн-поиск доступен только администратору при добавлении экспоната.")
@app.get("/admin/login")
def login():return render_template("admin_login.html",next=request.args.get("next","/admin"))
@app.post("/admin/login")
def login_post():
 if secrets.compare_digest(request.form.get("password",""),ADMIN_PASSWORD):session["admin"]=True;return redirect(request.args.get("next") or "/admin")
 flash("Неверный пароль.");return redirect(url_for("login"))
@app.get("/admin/logout")
def logout():session.clear();return redirect("/")
@app.get("/admin")
@admin_only
def admin():
 with conn() as c: toys=[as_toy(r) for r in c.execute("SELECT * FROM toys ORDER BY id DESC LIMIT 250").fetchall()]
 return render_template("admin.html",toys=toys,fields=FIELDS)

@app.post("/admin/upload")
@admin_only
def upload():
    files = request.files.getlist("photos")
    count = 0
    errors = []
    duplicate_threshold = float(os.getenv("CLIP_DUPLICATE_THRESHOLD", "0.965"))

    with conn() as c:
        columns = {row["name"] for row in c.execute("PRAGMA table_info(toys)").fetchall()}
        if "photo_hash" not in columns:
            c.execute("ALTER TABLE toys ADD COLUMN photo_hash TEXT")
        if "clip_embedding" not in columns:
            c.execute("ALTER TABLE toys ADD COLUMN clip_embedding BLOB")

        for f in files:
            if not f or not f.filename:
                continue
            try:
                raw = f.read()
                if not raw:
                    errors.append(f"{f.filename}: пустой файл")
                    continue
                image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=92, optimize=True)
                jpeg_data = output.getvalue()
                image_hash = photo_sha256(jpeg_data)
            except Exception as exc:
                errors.append(f"{f.filename}: фото повреждено или формат не поддерживается ({type(exc).__name__})")
                continue

            exact = c.execute(
                "SELECT inventory_number, name FROM toys WHERE photo_hash=? LIMIT 1",
                (image_hash,)
            ).fetchone()
            if exact:
                errors.append(f"Точное фото уже есть: {exact['inventory_number']} — {exact['name']}. Карточка не создана.")
                continue

            # Fail closed: do not create a card if CLIP cannot check for duplicates.
            try:
                new_embedding = clip_embedding(jpeg_data)
                candidates = c.execute(
                    "SELECT id, inventory_number, name, image_path, clip_embedding FROM toys WHERE image_path IS NOT NULL AND image_path != ''"
                ).fetchall()
                best = None
                best_score = -1.0
                for item in candidates:
                    try:
                        existing_embedding = _get_or_create_embedding(
                            item["id"], item["image_path"], item["clip_embedding"]
                        )
                        if not existing_embedding:
                            continue
                        score = embedding_similarity(new_embedding, existing_embedding)
                        if score > best_score:
                            best_score = score
                            best = item
                    except Exception:
                        app.logger.exception("Could not encode existing toy %s", item["inventory_number"])
                        continue

                if best is not None and best_score >= duplicate_threshold:
                    errors.append(
                        f"Возможный дубликат: {best['inventory_number']} — {best['name']} "
                        f"(CLIP {best_score:.3f}). Новая карточка не создана — проверьте найденный экспонат."
                    )
                    continue
            except Exception as exc:
                app.logger.exception("CLIP duplicate check failed during upload")
                errors.append(
                    f"{f.filename}: проверка CLIP не выполнена ({type(exc).__name__}); "
                    "карточка не создана, чтобы случайно не добавить дубликат. Проверьте логи Render."
                )
                continue

            number = next_num(c)
            folder = PHOTOS / number
            folder.mkdir(parents=True, exist_ok=True)
            photo_file = folder / "main.jpg"
            photo_file.write_bytes(jpeg_data)
            title = Path(f.filename).stem.replace("_", " ").replace("-", " ")
            try:
                c.execute(
                    """INSERT INTO toys
                    (inventory_number, name, country, museum, image_path, photo_hash, clip_embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (number, title, "Thailand", "Popov Toy Museum", f"{number}/main.jpg", image_hash, new_embedding)
                )
                count += 1
            except Exception:
                photo_file.unlink(missing_ok=True)
                try:
                    folder.rmdir()
                except OSError:
                    pass
                raise

    flash(f"Добавлено экспонатов: {count}.")
    for error in errors[:10]:
        flash(error)
    if len(errors) > 10:
        flash(f"Других пропущенных файлов: {len(errors) - 10}.")
    return redirect("/admin")

@app.post("/admin/toy/<int:toy_id>/save")
@admin_only
def save(toy_id):
 updates={}
 for key,_ in FIELDS:
  if key in {"image_path"}:continue
  v=request.form.get(key,"").strip()
  if key=="release_year":
   try:v=int(v) if v else None
   except ValueError:v=None
  if key in {"market_price","purchase_price"}:
   try:v=float(v) if v else None
   except ValueError:v=None
  updates[key]=v
 with conn() as c:
  row=c.execute("SELECT * FROM toys WHERE id=?",(toy_id,)).fetchone()
  if not row:flash("Экспонат не найден.");return redirect("/admin")
  if not updates.get("inventory_number"):updates["inventory_number"]=row["inventory_number"] or next_num(c)
  if c.execute("SELECT id FROM toys WHERE inventory_number=? AND id!=?",(updates["inventory_number"],toy_id)).fetchone():flash("Инвентарный номер уже существует.");return redirect("/admin")
  updates["updated_at"]=datetime.now(timezone.utc).isoformat()
  c.execute("UPDATE toys SET "+",".join(k+"=?" for k in updates)+" WHERE id=?",list(updates.values())+[toy_id])
 flash("Карточка сохранена.");return redirect("/admin")

@app.post("/admin/toy/<int:toy_id>/delete")
@admin_only
def delete_toy(toy_id):
    with conn() as c:
        row = c.execute(
            "SELECT image_path FROM toys WHERE id = ?",
            (toy_id,)
        ).fetchone()

        if row is None:
            flash("Экспонат не найден.")
            return redirect("/admin")

        image_path = row["image_path"] or ""

        # Удаляем карточку из базы данных.
        c.execute(
            "DELETE FROM toys WHERE id = ?",
            (toy_id,)
        )

        # Проверяем, используется ли фотография другой карточкой.
        still_used = None
        if image_path:
            still_used = c.execute(
                "SELECT 1 FROM toys WHERE image_path = ? LIMIT 1",
                (image_path,)
            ).fetchone()

    # Удаляем фотографию, только если её больше никто не использует.
    photo_deleted = True

    if image_path and not still_used:
        photos_root = PHOTOS.resolve()
        photo_file = (PHOTOS / image_path).resolve()

        if photos_root in photo_file.parents and photo_file.is_file():
            try:
                photo_file.unlink()

                if photo_file.parent != photos_root:
                    try:
                        photo_file.parent.rmdir()
                    except OSError:
                        pass

            except OSError:
                photo_deleted = False

    flash("Карточка удалена.")
    if not photo_deleted:
        flash("Фотографию не удалось удалить. Проверьте файлы на сервере.")

    return redirect("/admin")
@app.post("/admin/toy/<int:toy_id>/research")
@admin_only
def research(toy_id):
 with conn() as c:r=c.execute("SELECT * FROM toys WHERE id=?",(toy_id,)).fetchone()
 if not r:return jsonify(error="Экспонат не найден"),404
 p=PHOTOS/r["image_path"]
 if not p.is_file():return jsonify(error="Фотография не найдена"),404
 try:return jsonify(online_dossier(p.read_bytes(),p.name))
 except Exception as e:return jsonify(error=str(e)),502
@app.post("/admin/toy/<int:toy_id>/apply-research")
@admin_only
def apply_research(toy_id):
 data=request.get_json(silent=True) or {}; allowed={"name","series","brand","author","rarity","height","release_year","material","production_country","market_price","currency","description"}
 data={k:v for k,v in data.items() if k in allowed}
 with conn() as c:
  r=c.execute("SELECT * FROM toys WHERE id=?",(toy_id,)).fetchone()
  if not r:return jsonify(error="Экспонат не найден"),404
  data={k:v for k,v in data.items() if r[k] in (None,"")}
  if data:c.execute("UPDATE toys SET "+",".join(k+"=?" for k in data)+",updated_at=? WHERE id=?",list(data.values())+[datetime.now(timezone.utc).isoformat(),toy_id])
 return jsonify(message="Заполнены только пустые поля. Проверьте данные.",applied=list(data))
@app.get("/photos/<path:filename>")
def photo(filename):return send_from_directory(PHOTOS,filename)
@app.post("/telegram/webhook")
def webhook():
 if not BOT_TOKEN:return "Bot not configured",503
 upd=request.get_json(silent=True) or {}; m=upd.get("message") or upd.get("edited_message")
 if not m:return "ok"
 chat=m.get("chat",{}).get("id"); txt=(m.get("text") or "").strip(); isphoto=bool(m.get("photo"))
 if not chat:return "ok"
 base=(WEBAPP_URL or request.host_url.rstrip("/")).rstrip("/")
 url=base+("/scan" if isphoto or txt.split(" ")[0] in ("/scan","/camera") else "")
 label="📷 Открыть фотосканер" if url.endswith("/scan") else "🏛 Открыть Popov Toy Museum"
 reply="Сначала проверим фото по коллекции музея. Онлайн-поиск доступен только хранителю." if isphoto else "Добро пожаловать в Popov Toy Museum. Ищите экспонаты по фото, названию или инвентарному номеру."
 requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":reply,"reply_markup":{"inline_keyboard":[[{"text":label,"web_app":{"url":url}}]]}},timeout=15)
 return "ok"
def set_webhook():
 if BOT_TOKEN and WEBAPP_URL and os.getenv("REGISTER_TELEGRAM_WEBHOOK","true").lower()=="true":
  try:requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",json={"url":WEBAPP_URL.rstrip("/")+"/telegram/webhook"},timeout=15).raise_for_status()
  except Exception as e:print("Webhook registration failed:",e)
init_db();set_webhook()
if __name__=="__main__":app.run(host="127.0.0.1",port=int(os.getenv("PORT","5000")),debug=True)
