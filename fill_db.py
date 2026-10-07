import os, sqlite3
PHOTOS='photos'; DB='museum.db'
EXT=('.jpg','.jpeg','.png','.webp')
conn=sqlite3.connect(DB); c=conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS toys(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,inventory_num TEXT,brand TEXT,author TEXT,format TEXT,height_cm TEXT,material TEXT,year TEXT,production_country TEXT,country TEXT,city TEXT,museum TEXT,building TEXT,hall TEXT,rack TEXT,display_case TEXT,shelf TEXT,slot TEXT,location TEXT,description TEXT,photo_path TEXT)''')
cols={r[1] for r in c.execute('PRAGMA table_info(toys)')}
for col in ['brand','author','format','height_cm','material','year','production_country','rack','slot']:
    if col not in cols: c.execute(f'ALTER TABLE toys ADD COLUMN {col} TEXT')
files=sorted(f for f in os.listdir(PHOTOS) if f.lower().endswith(EXT)) if os.path.isdir(PHOTOS) else []
for f in files:
    path=os.path.join(PHOTOS,f)
    if c.execute('SELECT 1 FROM toys WHERE photo_path=?',(path,)).fetchone(): continue
    n=c.execute('SELECT COUNT(*) FROM toys').fetchone()[0]+1
    title=os.path.splitext(f)[0].replace('_',' ').replace('-',' ').strip().title()
    c.execute('INSERT INTO toys(title,inventory_num,country,location,description,photo_path) VALUES(?,?,?,?,?,?)',(title,f'INV-{n:05d}','Таиланд','Коридор',f'Экспонат из файла {f}',path))
conn.commit(); print(f'Готово. Найдено фото: {len(files)}. База: {DB}')
