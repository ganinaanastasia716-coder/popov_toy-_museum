import os, io, json, base64, sqlite3, secrets, mimetypes
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
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 with conn() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS toys(id INTEGER PRIMARY KEY AUTOINCREMENT,inventory_number TEXT UNIQUE,name TEXT NOT NULL DEFAULT '',series TEXT DEFAULT '',brand TEXT DEFAULT '',author TEXT DEFAULT '',rarity TEXT DEFAULT '',height TEXT DEFAULT '',release_year INTEGER,material TEXT DEFAULT '',production_country TEXT DEFAULT '',condition TEXT DEFAULT '',market_price REAL,purchase_price REAL,currency TEXT DEFAULT 'USD',country TEXT DEFAULT 'Thailand',city TEXT DEFAULT '',museum TEXT DEFAULT 'Popov Toy Museum',building TEXT DEFAULT '',hall TEXT DEFAULT '',rack TEXT DEFAULT '',display_case TEXT DEFAULT '',shelf TEXT DEFAULT '',slot TEXT DEFAULT '',description TEXT DEFAULT '',image_path TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
  for col in ["name","brand","series","inventory_number"]: c.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON toys({col})")
def next_num(c):
 n=c.execute("SELECT COUNT(*) FROM toys").fetchone()[0]+1
 while c.execute("SELECT 1 FROM toys WHERE inventory_number=?",(f"PM-TOY-{n:05d}",)).fetchone(): n+=1
 return f"PM-TOY-{n:05d}"
def as_toy(r):
 d=dict(r); d["location"]=" · ".join(str(d[k]) for k in ["country","city","museum","building","hall","rack","display_case","shelf","slot"] if d.get(k)) or "Место не назначено"; return d
def admin_only(fn):
 from functools import wraps
 @wraps(fn)
 def w(*a,**kw):
  if not session.get("admin"): return redirect(url_for("login",next=request.path))
  return fn(*a,**kw)
 return w
def features(raw):
 im=ImageOps.fit(Image.open(io.BytesIO(raw)).convert("RGB"),(12,12))
 vals=[v/255 for p in im.getdata() for v in p]
 ed=im.convert("L").filter(ImageFilter.FIND_EDGES)
 vals += [v/255 for v in ed.getdata()]
 n=sum(x*x for x in vals)**.5 or 1
 return [x/n for x in vals]
def scan_local(raw):
 try:q=features(raw)
 except Exception:return []
 out=[]
 with conn() as c: rows=c.execute("SELECT * FROM toys WHERE image_path!=''").fetchall()
 for t in rows:
  p=PHOTOS/t["image_path"]
  if not p.is_file(): continue
  try:
   f=features(p.read_bytes()); score=sum(a*b for a,b in zip(q,f)); out.append({"toy":as_toy(t),"score":round(score,4)})
  except Exception: pass
 return sorted(out,key=lambda x:x["score"],reverse=True)[:6]
def online_dossier(raw,filename):
 if not GEMINI_API_KEY: raise RuntimeError("Онлайн-поиск не настроен: добавьте GEMINI_API_KEY.")
 prompt="""Identify this designer collectible toy. Use Google Search to verify public information. Return JSON fields name, series, brand, author, rarity, height, release_year, material, production_country, market_price, currency, description, confidence, search_summary. Do not invent facts; use empty values if unknown. Explain uncertainty. This is a proposed dossier, not an official catalog record."""
 mime=mimetypes.guess_type(filename)[0] or "image/jpeg"
 url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
 body={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":mime,"data":base64.b64encode(raw).decode()}}]}],"tools":[{"google_search":{}}],"generationConfig":{"responseMimeType":"application/json"}}
 r=requests.post(url,json=body,timeout=75); r.raise_for_status(); payload=r.json()
 text="".join(p.get("text","") for p in payload.get("candidates",[{}])[0].get("content",{}).get("parts",[]))
 try:data=json.loads(text)
 except Exception:
  a,b=text.find("{"),text.rfind("}"); data=json.loads(text[a:b+1])
 sources=[]
 for cand in payload.get("candidates",[]):
  for chunk in cand.get("groundingMetadata",{}).get("groundingChunks",[]):
   w=chunk.get("web",{})
   if w.get("uri"): sources.append({"title":w.get("title",w["uri"]),"url":w["uri"]})
 data["sources"]=sources; return data
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
 if not f:return jsonify(error="Сделайте фото или выберите его из галереи."),400
 raw=f.read(); matches=scan_local(raw)
 if matches and matches[0]["score"]>=float(os.getenv("PHOTO_MATCH_THRESHOLD","0.90")): return jsonify(mode="database",matches=matches,message="Похожие экспонаты найдены в базе.")
 return jsonify(mode="not_found",matches=matches,message="В музейной коллекции не найдено уверенного совпадения. Онлайн-поиск доступен только администратору при добавлении экспоната.")
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

    with conn() as c:
        for f in files:
            if not f or not f.filename:
                continue

            try:
                raw = f.read()
                if not raw:
                    errors.append(f"{f.filename}: пустой файл")
                    continue

                # Читаем HEIC/HEIF и другие поддерживаемые форматы.
                image = Image.open(io.BytesIO(raw))
                image = ImageOps.exif_transpose(image).convert("RGB")

                # Сохраняем все фотографии в едином формате JPEG.
                output = io.BytesIO()
                image.save(
                    output,
                    format="JPEG",
                    quality=92,
                    optimize=True
                )
                jpeg_data = output.getvalue()

            except Exception as e:
                errors.append(
                    f"{f.filename}: формат не поддерживается "
                    f"или файл повреждён ({type(e).__name__})"
                )
                continue

            number = next_num(c)
            folder = PHOTOS / number
            folder.mkdir(parents=True, exist_ok=True)

            name = "main.jpg"
            (folder / name).write_bytes(jpeg_data)

            title = (
                Path(f.filename).stem
                .replace("_", " ")
                .replace("-", " ")
            )

            try:
                c.execute(
                    """INSERT INTO toys
                    (inventory_number, name, country, museum, image_path)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        number,
                        title,
                        "Thailand",
                        "Popov Toy Museum",
                        f"{number}/{name}"
                    )
                )
                count += 1
            except Exception:
                (folder / name).unlink(missing_ok=True)
                raise

    flash(f"Добавлено экспонатов: {count}. Заполните паспорта.")

    for error in errors[:5]:
        flash(error)

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
