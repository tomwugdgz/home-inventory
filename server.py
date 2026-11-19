# -*- coding: utf-8 -*-
"""
家物志 · 本地服务器（零依赖，仅用 Python 标准库）
=================================================
作用：
1. 在 0.0.0.0:8891 托管 index.html —— 局域网手机可通过 http://电脑IP:8891 访问
2. 提供 /api/vision 代理 —— 把拍照识别请求转发到本地 AI 服务 127.0.0.1:31415
   （API Key 从环境变量/本地 .env 读取，绝不写进代码、绝不暴露给手机浏览器）

启动：
  1) 复制 config.example.env 为 .env，填入你的 AI_KEY
  2) python server.py
访问：电脑 http://localhost:8891  手机 http://192.168.3.167:8891
"""
import os
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# ============ 配置区（按需修改）============
PORT = int(os.environ.get("PORT", 8891))
AI_BASE = os.environ.get("AI_BASE", "http://127.0.0.1:31415/v1")

def _load_key():
    """按优先级读取 AI Key：环境变量 > 同目录 .env 文件 > 空（走演示模式）"""
    key = os.environ.get("AI_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("AI_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

AI_KEY = _load_key()
# 视觉模型：实测 sensenova-6.8-flash-lite 稳定返回纯 JSON（雨伞/蓝/居家备用），
# 而 auto 路由有时挑到带 thinking 的模型导致 JSON 被思维链污染。故固定此模型。
# 备用可切换：qwen2.5-vl-72b / qwen3-vl-235b-a22b-instruct / llava-1.5-7b（需该环境有 provider key）
AI_MODEL = "sensenova-6.8-flash-lite"
TIMEOUT = 90                                    # 视觉识别超时（秒）
# ==========================================

BASE_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    # 允许局域网访问时不打印过多日志
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))

    def do_GET(self):
        # 健康检查接口：手机连不上时可在浏览器打开确认服务活着
        if self.path == "/api/health":
            self._send_json({
                "ok": True,
                "service": "家物志本地服务器",
                "ai_endpoint": AI_BASE,
                "ai_model": AI_MODEL,
            })
            return
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/vision":
            self._handle_vision()
        else:
            self._send_json({"error": "not found"}, status=404)

    def _handle_vision(self):
        """拍照识别代理：接收手机上传的图片 base64，转发给本地 AI，返回识别结果"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            image_url = data.get("image_url", "")

            if not image_url:
                self._send_json({"error": "缺少 image_url"}, status=400)
                return

            # 构造给视觉模型的请求：强制 JSON 输出，抽取颜色/用途/物品名
            payload = {
                "model": AI_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "你是家庭收纳助手。请识别图片中的物品，只输出一个 JSON 对象，"
                                "不要任何解释文字。字段：\n"
                                '{"name":"物品名称","cat":"类别(衣物/工具/食品/日用/数码/书籍/其他)",'
                                '"color":"颜色(黑/白/灰/红/蓝/绿/黄/米/粉/棕)","use":"用途(日常穿着/换季收纳/'
                                '居家备用/维修工具/充电数码/纪念收藏/清洁日用/其他)","confidence":0到1的小数}\n'
                                "用途判断示例：雨伞/毛巾/纸巾→居家备用；螺丝刀/钳子→维修工具；充电器/数据线→充电数码；"
                                "相册/纪念品→纪念收藏；羽绒服→换季收纳；T恤→日常穿着。\n"
                                "如果无法辨认，name 填 未识别物品，其余字段给最合理猜测。"
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }],
                "max_tokens": 200,
                "temperature": 0.2,
            }

            req = urllib.request.Request(
                AI_BASE + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + AI_KEY,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            content = result["choices"][0]["message"]["content"]
            model_used = result.get("model", AI_MODEL)

            # 从 AI 回复里提取 JSON（容忍 Markdown 代码块包裹）
            parsed = _extract_json(content)
            self._send_json({
                "ok": True,
                "model": model_used,
                "raw": content,
                "result": parsed,
            })

        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:500]
            self._send_json({"error": "AI 服务返回 %s" % e.code, "detail": detail}, status=502)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def _extract_json(text):
    """从模型回复中提取 JSON 对象（抗思维链污染）"""
    import re
    if not isinstance(text, str):
        text = str(text)

    # 策略1：逐字符扫描，找所有平衡的 {...} 块，优先取含目标字段的那个
    candidates = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidates.append(text[start:i + 1])
                    start = -1

    # 从后往前优先（思维链在前，答案 JSON 通常在最后）
    for block in reversed(candidates):
        try:
            obj = json.loads(block)
            if isinstance(obj, dict) and "name" in obj:
                return obj
        except Exception:
            continue

    # 策略2：去掉 markdown 包裹后直接解析
    t = re.sub(r"```json?\s*", "", text, flags=re.I).replace("```", "").strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict) and "name" in obj:
            return obj
    except Exception:
        pass

    # 兜底：从文本里正则抠字段（应对模型只给了半截 JSON）
    name = re.search(r'"name"\s*:\s*"([^"]+)"', text)
    color = re.search(r'"color"\s*:\s*"([^"]+)"', text)
    if name:
        return {
            "name": name.group(1),
            "cat": (re.search(r'"cat"\s*:\s*"([^"]+)"', text) or [None, "其他"])[1],
            "color": color.group(1) if color else "米",
            "use": (re.search(r'"use"\s*:\s*"([^"]+)"', text) or [None, "其他"])[1],
            "confidence": 0.85,
        }
    return {"name": "未识别物品", "cat": "其他", "color": "米", "use": "其他", "confidence": 0.3}


if __name__ == "__main__":
    import socket
    try:
        hostname = socket.gethostname()
        local_ips = sorted({
            s[4][0] for s in socket.getaddrinfo(hostname, None)
            if s[0] == socket.AF_INET and not s[4][0].startswith("127.")
        })
    except Exception:
        local_ips = []

    print("=" * 58)
    print("  家物志 · 本地服务器已启动")
    print("=" * 58)
    print("  电脑访问:  http://localhost:%d" % PORT)
    for ip in local_ips:
        print("  手机访问:  http://%s:%d   (需连同一 WiFi)" % (ip, PORT))
    print("  AI 代理:   %s  (模型 %s)" % (AI_BASE, AI_MODEL))
    print("  API Key 仅存服务端，不暴露给浏览器")
    print("=" * 58)
    print("  按 Ctrl+C 停止")
    print("")

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
