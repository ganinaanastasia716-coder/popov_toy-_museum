import os, sqlite3, base64, mimetypes, json
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
from PIL import Image
import numpy as np
import requests
BASE=os.path.dirname(os.path.abspath(__file__)); DB=os.path.join(BASE,'museum.db'); PHOTOS=os.path.join(BASE,'photos')
app=Flask(__name__); app.secret_key=os.getenv('FLASK_SECRET','change-me')

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
 os.makedirs(PHOTOS,exist_ok=True); c=db(); c.execute('''CREATE TABLE IF NOT EXISTS toys(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,inventory_num TEXT,brand TEXT,author TEXT,format TEXT,height_cm TEXT,material TEXT,year TEXT,production_country TEXT,country TEXT,city TEXT,museum TEXT,building TEXT,hall TEXT,rack TEXT,display_case TEXT,shelf TEXT,slot TEXT,location TEXT,description TEXT,photo_path TEXT)'''); c.commit(); c.close()

def toy_rows(): return [dict(x) for x in db().execute('SELECT * FROM toys ORDER BY id DESC').fetchall()]

def score(a,b):
 a=np.asarray(a.resize((64,64)).convert('RGB'),dtype=np.float32)/255; b=np.asarray(b.resize((64,64)).convert('RGB'),dtype=np.float32)/255
 return float(1/(1+np.mean((a-b)**2)))

def search_bytes(data,k=6):
 try: q=Image.open(__import__('io').BytesIO(data)).convert('RGB')
 except: return []
 out=[]; c=db(); rows=c.execute('SELECT * FROM toys').fetchall(); c.close()
 for r in rows:
  p=r['photo_path'] or ''
  if not os.path.exists(p): continue
  try: s=score(q,Image.open(p).convert('RGB')); out.append((s,dict(r)))
  except: pass
 out.sort(key=lambda x:x[0],reverse=True); return [x[1] | {'similarity':round(x[0]*100,1)} for x in out[:k]]

@app.route('/health')
def health():
 return jsonify({'ok':True,'service':'TOY MUSEUM'})

@app.route('/')
def home(): return render_template('index.html',toys=toy_rows()[:6])
@app.route('/search')
def search():
 q=request.args.get('q','').strip().lower(); field=request.args.get('field','title'); rows=toy_rows()
 if q: rows=[x for x in rows if q in str(x.get(field,'')).lower() or q in str(x.get('title','')).lower() or q in str(x.get('brand','')).lower()]
 return render_template('results.html',toys=rows,q=q)
@app.route('/collection')
def collection(): return render_template('collection.html',toys=toy_rows())
@app.route('/scan')
def scan(): return render_template('scan.html')
@app.route('/api/search-photo',methods=['POST'])
def api_photo():
 f=request.files.get('photo');
 if not f: return jsonify({'ok':False,'error':'Фото не получено'}),400
 return jsonify({'ok':True,'results':search_bytes(f.read(),6)})
@app.route('/toy/<int:tid>')
def toy(tid):
 c=db(); r=c.execute('SELECT * FROM toys WHERE id=?',(tid,)).fetchone(); c.close()
 if not r:return 'Not found',404
 return render_template('toy.html',toy=dict(r))
@app.route('/photos/<path:name>')
def photos(name): return send_from_directory(PHOTOS,name)
@app.route('/admin')
def admin(): return render_template('admin.html',toys=toy_rows())
@app.route('/admin/upload',methods=['POST'])
def upload():
 files=request.files.getlist('photos'); c=db()
 for f in files:
  if not f.filename: continue
  safe=os.path.basename(f.filename); path=os.path.join(PHOTOS,safe); f.save(path)
  if not c.execute('SELECT 1 FROM toys WHERE photo_path=?',(path,)).fetchone():
   n=c.execute('SELECT COUNT(*) FROM toys').fetchone()[0]+1; title=os.path.splitext(safe)[0].replace('_',' ').title(); c.execute('INSERT INTO toys(title,inventory_num,country,location,photo_path) VALUES(?,?,?,?,?)',(title,f'INV-{n:05d}','Таиланд','Коридор',path))
 c.commit(); return redirect(url_for('admin'))
@app.route('/admin/toy/<int:tid>',methods=['POST'])
def edit(tid):
 c=db(); fields=['title','inventory_num','brand','author','format','height_cm','material','year','production_country','country','city','museum','building','hall','rack','display_case','shelf','slot','location','description']; vals=[request.form.get(x,'').strip() for x in fields]; c.execute('UPDATE toys SET '+','.join(f'{x}=?' for x in fields)+' WHERE id=?',vals+[tid]); c.commit(); return redirect(url_for('admin'))
@app.route('/admin/toy/<int:tid>/research',methods=['POST'])
def research(tid):
 key=os.getenv('GEMINI_API_KEY',''); c=db(); r=c.execute('SELECT * FROM toys WHERE id=?',(tid,)).fetchone(); c.close()
 if not key or not r:return jsonify({'ok':False,'error':'GEMINI_API_KEY не настроен или экспонат не найден'}),400
 p=r['photo_path'];
 if not p or not os.path.exists(p): return jsonify({'ok':False,'error':'Нет фото'}),400
 data=base64.b64encode(open(p,'rb').read()).decode(); mime=mimetypes.guess_type(p)[0] or 'image/jpeg'
 model=os.getenv('GEMINI_MODEL','gemini-3.6-flash'); url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
 prompt='Определи дизайнерскую игрушку по фото. Используй Google Search. Не выдумывай. Верни JSON с title, brand, collection, series, character, universe, format, height_cm, material, author, production_country, year, collaboration, condition, value_usd, description. Неизвестное оставь пустым.'
 payload={'contents':[{'parts':[{'text':prompt},{'inline_data':{'mime_type':mime,'data':data}}]}],'tools':[{'google_search':{}}],'generationConfig':{'responseMimeType':'application/json'}}
 try:
  rr=requests.post(url,json=payload,timeout=90); rr.raise_for_status(); j=rr.json(); text=''.join(p.get('text','') for p in j.get('candidates',[{}])[0].get('content',{}).get('parts',[]) if 'text' in p); return jsonify({'ok':True,'data':json.loads(text) if text else {},'sources':[]})
 except Exception as e:return jsonify({'ok':False,'error':str(e)}),500
@app.route('/telegram/webhook',methods=['POST'])
def webhook():
 token=os.getenv('BOT_TOKEN','').strip(); web=os.getenv('WEBAPP_URL','').strip().rstrip('/')
 if not token or not web:return 'ok'
 u=request.get_json(silent=True) or {}; m=u.get('message',{}); chat=m.get('chat',{}).get('id')
 if not chat:return 'ok'
 kb={'inline_keyboard':[[{'text':'🏛 Открыть TOY MUSEUM','web_app':{'url':web}}]]}
 text='Добро пожаловать в TOY MUSEUM.\n\nНайдите экспонат по фото, номеру, названию или месту хранения.'
 if m.get('photo'):
  kb={'inline_keyboard':[[{'text':'📷 Открыть фотосканер','web_app':{'url':web+'/scan'}}]]}
  text='Фото получено. Откройте фотосканер — он сравнит снимок с эталонами коллекции.'
 elif (m.get('text') or '').strip().lower() in ('/search','/find','/scan'):
  kb={'inline_keyboard':[[{'text':'📷 Открыть поиск','web_app':{'url':web+'/scan'}}]]}
  text='Откройте поиск TOY MUSEUM: фото, камера, номер, название, город, музей или страна.'
 try:
  requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':text,'reply_markup':kb},timeout=15)
 except requests.RequestException:
  pass
 return 'ok'

def register_telegram_webhook():
 token=os.getenv('BOT_TOKEN','').strip(); web=os.getenv('WEBAPP_URL','').strip().rstrip('/')
 if not token or not web:return
 try:
  requests.post(f'https://api.telegram.org/bot{token}/setWebhook',json={'url':web+'/telegram/webhook','drop_pending_updates':True},timeout=15)
 except requests.RequestException:
  pass

init()
register_telegram_webhook()
