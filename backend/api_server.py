# -*- coding: utf-8 -*-
"""
家物志 · 后端 API 服务器（零依赖，Python 标准库）
==================================================
功能：
1. REST API —— 物品/位置/分类/用途/会员/NFC 的增删改查，数据存 SQLite
2. /api/vision —— AI 拍照识别代理（Key 藏服务端）
3. 静态文件托管 —— H5 Demo（可选）
局域网手机/微信小程序访问同一份数据库，数据实时共享。

启动：python backend/api_server.py
端口：8892（与 H5 Demo 的 8891 分开）
"""
import os, json, sys, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

# ============ 配置 ============
PORT = int(os.environ.get("API_PORT", 8892))
AI_BASE = os.environ.get("AI_BASE", "http://127.0.0.1:31415/v1")
def _load_key():
    k = os.environ.get("AI_KEY", "").strip()
    if k: return k
    for envp in [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')]:
        if os.path.exists(envp):
            for line in open(envp, encoding='utf-8').read().splitlines():
                if line.strip().startswith('AI_KEY='):
                    return line.split('=',1)[1].strip().strip('"').strip("'")
    return ""
AI_KEY = _load_key()
AI_MODEL = "sensenova-6.8-flash-lite"
TIMEOUT = 90

db.init_db()


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type,Authorization')
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get('Content-Length', 0))
        if not n: return {}
        return json.loads(self.rfile.read(n).decode('utf-8'))

    def do_OPTIONS(self):
        self._json({})

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        q = parse_qs(u.query)

        try:
            if p == '/api/health':
                return self._json({'ok':True,'service':'家物志API','db':str(db.DB_PATH),'ai_model':AI_MODEL})

            if p == '/api/bootstrap':
                return self._json(db.export_all())

            if p == '/api/locations':
                return self._json({'locations': db.list_locations()})
            if p == '/api/items':
                return self._json({'items': db.list_items()})
            if p == '/api/categories':
                return self._json({'categories': db.list_categories()})
            if p == '/api/uses':
                return self._json({'uses': db.list_uses()})
            if p == '/api/member':
                return self._json(db.get_member())
            if p == '/api/ledger':
                return self._json({'ledger': db.list_ledger(int(q.get('limit',[50])[0]))})

            if p == '/api/nfc/resolve':
                uid = q.get('uid',[''])[0]
                if not uid: return self._json({'error':'缺少 uid'},400)
                b = db.resolve_nfc(uid)
                if not b: return self._json({'found':False})
                # 带出绑定对象信息
                extra = None
                if b['bind_type']=='item':
                    extra = next((i for i in db.list_items() if i['id']==b['bind_id']), None)
                return self._json({'found':True,'binding':b,'item':extra})

            return self._json({'error':'not found'}, 404)
        except Exception as e:
            return self._json({'error':str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path); p = u.path
        try:
            b = self._body()

            if p == '/api/locations':
                lid = db.add_location(b['name'], b.get('parent_id'))
                return self._json({'ok':True,'id':lid})

            if p == '/api/items':
                iid = db.add_item(b)
                return self._json({'ok':True,'id':iid})

            if p == '/api/taxonomy':
                ok = db.add_taxonomy(b['kind'], b['name'])
                return self._json({'ok':ok, 'error': None if ok else '已存在'})

            if p == '/api/nfc/bind':
                db.bind_nfc(b['uid'], b.get('bind_type','location'), b['bind_id'], b.get('qr_fallback',''))
                return self._json({'ok':True})

            if p == '/api/member/token/consume':
                ok = db.consume_token(b.get('note','AI识别'))
                return self._json({'ok':ok, 'member':db.get_member()})

            if p == '/api/member/upgrade':
                db.update_member({'level':'vip','tokens_left':999999,'tokens_total':999999})
                return self._json({'ok':True,'member':db.get_member()})

            if p == '/api/member/downgrade':
                db.update_member({'level':'free','tokens_left':10,'tokens_total':10})
                return self._json({'ok':True,'member':db.get_member()})

            if p == '/api/vision':
                return self._vision(b)

            return self._json({'error':'not found'},404)
        except Exception as e:
            return self._json({'error':str(e)},500)

    def do_PUT(self):
        u = urlparse(self.path); p = u.path
        try:
            b = self._body()
            if p.startswith('/api/locations/'):
                lid = p.split('/')[-1]
                db.update_location(lid, b['name'], b.get('parent_id'))
                return self._json({'ok':True})
            if p.startswith('/api/items/'):
                iid = p.split('/')[-1]
                db.update_item(iid, b)
                return self._json({'ok':True})
            if p == '/api/member':
                db.update_member(b)
                return self._json({'ok':True,'member':db.get_member()})
            return self._json({'error':'not found'},404)
        except ValueError as e:
            return self._json({'error':str(e)},400)
        except Exception as e:
            return self._json({'error':str(e)},500)

    def do_DELETE(self):
        u = urlparse(self.path); p = u.path
        try:
            if p.startswith('/api/locations/'):
                db.delete_location(p.split('/')[-1]); return self._json({'ok':True})
            if p.startswith('/api/items/'):
                db.delete_item(p.split('/')[-1]); return self._json({'ok':True})
            if p.startswith('/api/taxonomy/'):
                parts = p.split('/')  # /api/taxonomy/{kind}/{name}
                kind = parts[3] if len(parts)>3 else 'cat'
                name = '/'.join(parts[4:])
                db.delete_taxonomy(kind, name); return self._json({'ok':True})
            return self._json({'error':'not found'},404)
        except Exception as e:
            return self._json({'error':str(e)},500)

    def _vision(self, b):
        """AI 拍照识别代理：注入用户自定义分类，Key 不上浏览器"""
        image_url = b.get('image_url','')
        user_cats = b.get('cats',[]) or db.list_categories()
        user_uses = b.get('uses',[]) or db.list_uses()
        if not image_url: return self._json({'error':'缺少 image_url'},400)
        if not AI_KEY: return self._json({'error':'服务端未配置 AI_KEY'},500)

        cat_hint = '、'.join([c['name'] if isinstance(c,dict) else c for c in user_cats])
        use_hint = '、'.join(user_uses)
        prompt_text = (
            '你是家庭收纳助手。识别图片物品，只输出 JSON，不要解释：\n'
            '{"name":"物品名","cat":"类别，从这组选一个：'+cat_hint+'",'
            '"color":"颜色，从这组选：黑/白/灰/红/蓝/绿/黄/米/粉/棕",'
            '"use":"用途，从这组选一个：'+use_hint+'","confidence":0到1小数}\n'
            '类别和用途必须严格从给定列表选，不要自造词。无法辨认时 name 填 未识别物品。'
        )
        payload = {
            'model': AI_MODEL,
            'messages':[{'role':'user','content':[
                {'type':'text','text':prompt_text},
                {'type':'image_url','image_url':{'url':image_url}},
            ]}],
            'max_tokens':200,'temperature':0.2,
        }
        try:
            req = urllib.request.Request(AI_BASE+'/chat/completions',
                data=json.dumps(payload).encode('utf-8'),
                headers={'Authorization':'Bearer '+AI_KEY,'Content-Type':'application/json'},
                method='POST')
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                result = json.loads(r.read().decode('utf-8'))
            content = result['choices'][0]['message']['content']
            parsed = _extract_json(content)
            # 扣 Token（会员不扣）
            db.consume_token('拍照识别:'+parsed.get('name','?'))
            return self._json({'ok':True,'model':result.get('model',AI_MODEL),'result':parsed,
                               'member':db.get_member(),'raw':content})
        except urllib.error.HTTPError as e:
            return self._json({'error':'AI服务返回 %s'%e.code,'detail':e.read().decode('utf-8','ignore')[:300]},502)
        except Exception as e:
            return self._json({'error':str(e)},500)


def _extract_json(text):
    import re
    if not isinstance(text,str): text=str(text)
    candidates=[]; depth=0; start=-1; in_str=False; esc=False
    for i,ch in enumerate(text):
        if in_str:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch=='"': in_str=False
            continue
        if ch=='"': in_str=True
        elif ch=='{':
            if depth==0: start=i
            depth+=1
        elif ch=='}':
            if depth>0:
                depth-=1
                if depth==0 and start>=0: candidates.append(text[start:i+1]); start=-1
    for block in reversed(candidates):
        try:
            obj=json.loads(block)
            if isinstance(obj,dict) and 'name' in obj: return obj
        except: pass
    m=re.search(r'"name"\s*:\s*"([^"]+)"',text)
    if m:
        return {'name':m.group(1),
                'cat':(re.search(r'"cat"\s*:\s*"([^"]+)"',text) or [None,'其他'])[1],
                'color':(re.search(r'"color"\s*:\s*"([^"]+)"',text) or [None,'米'])[1],
                'use':(re.search(r'"use"\s*:\s*"([^"]+)"',text) or [None,'其他'])[1],
                'confidence':0.85}
    return {'name':'未识别物品','cat':'其他','color':'米','use':'其他','confidence':0.3}


if __name__ == '__main__':
    import socket
    try:
        ips = sorted({s[4][0] for s in socket.getaddrinfo(socket.gethostname(),None)
                      if s[0]==socket.AF_INET and not s[4][0].startswith('127.')})
    except: ips=[]
    print("="*56)
    print("  家物志 · 后端 API 服务器")
    print("="*56)
    print("  健康检查: http://127.0.0.1:%d/api/health" % PORT)
    for ip in ips:
        print("  局域网/小程序: http://%s:%d/api/bootstrap" % (ip,PORT))
    print("  数据库:", db.DB_PATH)
    print("  AI 模型:", AI_MODEL, "| Key:", "已配置" if AI_KEY else "未配置")
    print("="*56)
    HTTPServer(('0.0.0.0',PORT), APIHandler).serve_forever()
