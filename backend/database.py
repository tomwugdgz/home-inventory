# -*- coding: utf-8 -*-
"""
家物志 · 数据库层（SQLite，零依赖）
==================================
用 Python 标准库 sqlite3，无需安装任何包。
数据库文件：backend/data/jiawuzhi.db
表结构：locations / items / categories / uses / member / nfc_bindings / token_ledger
"""
import sqlite3
import json
import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "jiawuzhi.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """建表 + 灌入默认数据（幂等，可重复调用）"""
    conn = connect()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS locations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        parent_id TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(parent_id) REFERENCES locations(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        icon TEXT DEFAULT '',
        is_default INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS uses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        is_default INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT,
        color TEXT,
        use_scene TEXT,
        location_id TEXT,
        image_path TEXT,
        nfc_uid TEXT,
        tags TEXT DEFAULT '[]',
        source TEXT DEFAULT 'manual',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY(location_id) REFERENCES locations(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_items_loc ON items(location_id);
    CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

    CREATE TABLE IF NOT EXISTS member (
        id INTEGER PRIMARY KEY CHECK(id=1),
        level TEXT DEFAULT 'free',
        tokens_left INTEGER DEFAULT 10,
        tokens_total INTEGER DEFAULT 10,
        nfc_tags INTEGER DEFAULT 0,
        month_key TEXT DEFAULT '',
        updated_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS nfc_bindings (
        uid TEXT PRIMARY KEY,
        bind_type TEXT NOT NULL,
        bind_id TEXT NOT NULL,
        qr_fallback TEXT,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS token_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        amount INTEGER NOT NULL,
        balance_after INTEGER NOT NULL,
        note TEXT,
        created_at INTEGER NOT NULL
    );
    """)

    # 默认分类
    default_cats = [
        ('衣物','👕'),('工具','🔧'),('食品','🍫'),('日用','🧴'),
        ('数码','🔌'),('书籍','📚'),('其他','📦'),
    ]
    for name, icon in default_cats:
        c.execute("INSERT OR IGNORE INTO categories(name,icon,is_default) VALUES(?,?,1)", (name, icon))

    # 默认用途
    default_uses = ['日常穿着','换季收纳','居家备用','维修工具','充电数码','纪念收藏','清洁日用','其他']
    for name in default_uses:
        c.execute("INSERT OR IGNORE INTO uses(name,is_default) VALUES(?,1)", (name,))

    # 默认位置树（房间→子位置）
    import time
    now = int(time.time() * 1000)
    default_locs = [
        ('r1','主卧',None),('r1a','衣柜·上层','r1'),('r1b','床头柜抽屉','r1'),
        ('r2','客厅',None),('r2a','电视柜','r2'),('r2b','储物箱','r2'),
        ('r3','书房',None),('r3a','书柜第二层','r3'),
    ]
    for lid, name, parent in default_locs:
        c.execute("INSERT OR IGNORE INTO locations(id,name,parent_id,created_at) VALUES(?,?,?,?)",
                  (lid, name, parent, now))

    # 默认物品（演示数据）
    default_items = [
        ('i1','冬季羽绒服','衣物','黑','换季收纳','r1a',None,'[]','manual'),
        ('i2','螺丝刀套装','工具','红','维修工具','r2b',None,'["维修"]','manual'),
        ('i3','备用毛巾','日用','米','居家备用','r1a',None,'[]','manual'),
        ('i4','数据线收纳盒','数码','黑','充电数码','r3a',None,'["充电"]','manual'),
        ('i5','儿童相册','书籍','粉','纪念收藏','r3a',None,'["纪念"]','manual'),
        ('i6','生日蜡烛','日用','黄','其他','r2a',None,'["聚会"]','manual'),
    ]
    for iid, name, cat, color, use, loc, img, tags, source in default_items:
        c.execute("""INSERT OR IGNORE INTO items
            (id,name,category,color,use_scene,location_id,image_path,tags,source,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (iid, name, cat, color, use, loc, img, tags, source, now-3600000, now-3600000))

    # 会员账户（单例）
    c.execute("INSERT OR IGNORE INTO member(id,level,tokens_left,tokens_total,nfc_tags,updated_at) VALUES(1,'free',10,10,0,?)", (now,))

    conn.commit()
    conn.close()
    return DB_PATH


def row_to_dict(row):
    return dict(row) if row else None


# ---------- 位置 ----------
def list_locations():
    conn = connect()
    rows = conn.execute("SELECT * FROM locations ORDER BY created_at").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def add_location(name, parent_id=None, lid=None):
    import time
    conn = connect()
    lid = lid or ('r' + str(int(time.time()*1000)))
    conn.execute("INSERT INTO locations(id,name,parent_id,created_at) VALUES(?,?,?,?)",
                 (lid, name, parent_id, int(time.time()*1000)))
    conn.commit(); conn.close()
    return lid

def update_location(lid, name, parent_id):
    conn = connect()
    # 防止把父级设成自己的后代
    if parent_id:
        cur = parent_id
        while cur:
            r = conn.execute("SELECT parent_id FROM locations WHERE id=?", (cur,)).fetchone()
            if not r: break
            if r['parent_id'] == lid:
                conn.close(); raise ValueError("不能把上级设成自己的子位置")
            cur = r['parent_id']
    conn.execute("UPDATE locations SET name=?,parent_id=? WHERE id=?", (name, parent_id, lid))
    conn.commit(); conn.close()

def delete_location(lid):
    conn = connect()
    conn.execute("UPDATE items SET location_id=NULL WHERE location_id=?", (lid,))
    conn.execute("UPDATE locations SET parent_id=NULL WHERE parent_id=?", (lid,))
    conn.execute("DELETE FROM locations WHERE id=?", (lid,))
    conn.commit(); conn.close()


# ---------- 物品 ----------
def list_items():
    conn = connect()
    rows = conn.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
    conn.close()
    out=[]
    for r in rows:
        d=row_to_dict(r)
        d['tags']=json.loads(d.get('tags') or '[]')
        out.append(d)
    return out

def add_item(data):
    import time
    conn = connect()
    iid = data.get('id') or ('i' + str(int(time.time()*1000)))
    now = int(time.time()*1000)
    conn.execute("""INSERT INTO items
        (id,name,category,color,use_scene,location_id,image_path,nfc_uid,tags,source,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (iid, data['name'], data.get('category'), data.get('color'), data.get('use_scene'),
         data.get('location_id'), data.get('image_path'), data.get('nfc_uid'),
         json.dumps(data.get('tags',[]),ensure_ascii=False), data.get('source','manual'), now, now))
    conn.commit(); conn.close()
    return iid

def update_item(iid, data):
    conn = connect()
    fields=[]; vals=[]
    for k in ('name','category','color','use_scene','location_id','image_path','nfc_uid'):
        if k in data: fields.append(f"{k}=?"); vals.append(data[k])
    if 'tags' in data: fields.append("tags=?"); vals.append(json.dumps(data['tags'],ensure_ascii=False))
    import time
    fields.append("updated_at=?"); vals.append(int(time.time()*1000))
    vals.append(iid)
    conn.execute(f"UPDATE items SET {','.join(fields)} WHERE id=?", vals)
    conn.commit(); conn.close()

def delete_item(iid):
    conn = connect()
    conn.execute("DELETE FROM items WHERE id=?", (iid,))
    conn.commit(); conn.close()


# ---------- 分类 / 用途 ----------
def list_categories():
    conn=connect(); rows=conn.execute("SELECT name,icon FROM categories ORDER BY id").fetchall(); conn.close()
    return [{'name':r['name'],'icon':r['icon']} for r in rows]

def list_uses():
    conn=connect(); rows=conn.execute("SELECT name FROM uses ORDER BY id").fetchall(); conn.close()
    return [r['name'] for r in rows]

def add_taxonomy(kind, name):
    conn=connect()
    table='categories' if kind=='cat' else 'uses'
    try:
        if kind=='cat': conn.execute("INSERT INTO categories(name,icon) VALUES(?,?)", (name,'🏷️'))
        else: conn.execute("INSERT INTO uses(name) VALUES(?)", (name,))
        conn.commit(); ok=True
    except sqlite3.IntegrityError:
        ok=False
    conn.close(); return ok

def delete_taxonomy(kind, name):
    conn=connect()
    table='categories' if kind=='cat' else 'uses'
    conn.execute(f"DELETE FROM {table} WHERE name=?", (name,))
    conn.commit(); conn.close()


# ---------- 会员 / Token ----------
def get_member():
    conn=connect(); r=conn.execute("SELECT * FROM member WHERE id=1").fetchone(); conn.close()
    return row_to_dict(r)

def update_member(data):
    conn=connect()
    fields=[]; vals=[]
    for k in ('level','tokens_left','tokens_total','nfc_tags'):
        if k in data: fields.append(f"{k}=?"); vals.append(data[k])
    import time
    fields.append("updated_at=?"); vals.append(int(time.time()*1000))
    conn.execute(f"UPDATE member SET {','.join(fields)} WHERE id=1", vals)
    conn.commit(); conn.close()

def consume_token(note='AI识别'):
    """消耗 1 个 Token（会员不扣），返回是否成功"""
    m=get_member()
    if m['level']=='vip':
        _log_token('识别', 0, m['tokens_left'], note+' (会员免费)')
        return True
    if m['tokens_left']<=0: return False
    conn=connect()
    conn.execute("UPDATE member SET tokens_left=tokens_left-1 WHERE id=1")
    conn.commit(); conn.close()
    m2=get_member()
    _log_token('识别', -1, m2['tokens_left'], note)
    return True

def _log_token(action, amount, balance, note):
    import time
    conn=connect()
    conn.execute("INSERT INTO token_ledger(action,amount,balance_after,note,created_at) VALUES(?,?,?,?,?)",
                 (action, amount, balance, note, int(time.time()*1000)))
    conn.commit(); conn.close()

def list_ledger(limit=50):
    conn=connect()
    rows=conn.execute("SELECT * FROM token_ledger ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close(); return [row_to_dict(r) for r in rows]


# ---------- NFC 绑定 ----------
def bind_nfc(uid, bind_type, bind_id, qr_fallback=''):
    import time
    conn=connect()
    conn.execute("""INSERT INTO nfc_bindings(uid,bind_type,bind_id,qr_fallback,created_at)
        VALUES(?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET bind_type=excluded.bind_type,
        bind_id=excluded.bind_id,qr_fallback=excluded.qr_fallback""",
        (uid,bind_type,bind_id,qr_fallback,int(time.time()*1000)))
    conn.commit(); conn.close()

def resolve_nfc(uid):
    conn=connect()
    r=conn.execute("SELECT * FROM nfc_bindings WHERE uid=?", (uid,)).fetchone()
    conn.close(); return row_to_dict(r)


# ---------- 全量导出（给小程序首屏一次拉取）----------
def export_all():
    return {
        'locations': list_locations(),
        'items': list_items(),
        'categories': list_categories(),
        'uses': list_uses(),
        'member': get_member(),
    }


if __name__ == '__main__':
    p = init_db()
    print("数据库已初始化:", p)
    print("物品数:", len(list_items()), "| 位置数:", len(list_locations()))
