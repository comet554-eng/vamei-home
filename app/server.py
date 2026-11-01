"""本地演示服务。只监听 127.0.0.1，只用标准库。
运行：python app/server.py
  http://127.0.0.1:8766/      队友的 MedBridge 网站（web/），左侧「询盘助手」页调用本服务的 API
  http://127.0.0.1:8766/lab/  原来的三栏询盘工作台（app/static/）"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bot  # noqa: E402
import knowledge  # noqa: E402
import pipeline  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLM  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
WEB = Path(__file__).resolve().parent.parent / "web"
SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "inquiries.json"
REGISTRY = Path(__file__).resolve().parent.parent / "kb" / "registry.json"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".md": "text/plain; charset=utf-8"}
# 队友用 python -m http.server 4173 单独起网站时，浏览器会跨端口调 API；只放行本机来源
LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")


def static_file(path):
    """/lab/... 取 app/static，其余取 web/。不允许跳出这两个目录。"""
    if path == "/lab":
        return None
    root, rest = (STATIC, path[len("/lab/"):]) if path.startswith("/lab/") else (WEB, path.lstrip("/"))
    f = (root / (rest or "index.html")).resolve()
    return f if root in f.parents and f.is_file() else None
MAX_BODY = 256 * 1024  # 机器人最多 12 条 × 6000 字，中文 UTF-8 约 216 KB
MAX_IMPORT = 1_000_000  # 产品资料导入，和队友页面的 1 MB 上限一致
LOCAL_HOSTS = ("localhost", "127.0.0.1")
MAX_TEXT = 5000

kb = KB()
llm = LLM()
KNOWLEDGE = knowledge.KnowledgeStore()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _cors(self):
        origin = self.headers.get("Origin") or ""
        if self.path.startswith("/api/") and LOCAL_ORIGIN.match(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            return self._send(200, llm.info())
        if path == "/api/samples":
            return self._send(200, SAMPLES.read_bytes(), TYPES[".json"])
        if path == "/api/product-knowledge":  # 网页机器人打开时、工作台设置的导入页都会读
            try:
                return self._send(200, {"products": KNOWLEDGE.all()})
            except (OSError, ValueError):
                return self._send(503, {"error": "产品数据库暂不可用，请稍后重试"})
        if path == "/api/registry":  # 网站「注册清单」页；数据由 scripts/import_registry.py 生成
            try:
                return self._send(200, json.loads(REGISTRY.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                return self._send(503, {"error": "注册清单数据暂不可用，请运行 python scripts/import_registry.py 重新生成"})
        if path == "/lab":
            self.send_response(301)
            self.send_header("Location", "/lab/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        f = static_file(path)
        if not f:
            return self._send(404, {"error": "not found"})
        return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

    def _same_local_origin(self):
        """导入只允许本机工作台页面提交：Host 必须是本机，Origin 必须和 Host 同源。
        单查 Host 挡不住 DNS 重绑定，单查 Origin 挡不住别的本机端口，所以两个都查。"""
        host = self.headers.get("Host") or ""
        if host.rsplit(":", 1)[0] not in LOCAL_HOSTS:
            return False
        return self.headers.get("Origin") == f"http://{host}"

    def _import_knowledge(self):
        def reject(code, body):
            # Read a small rejected request before replying. On Windows, closing a
            # socket with unread POST bytes can reset the connection before the
            # client receives the 403/413 response.
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= 2_000_000:
                self.rfile.read(n)
            else:
                self.close_connection = True
            return self._send(code, body)

        if not self._same_local_origin():
            return reject(403, {"error": "导入仅在本地工作台开放，请从工作台导入页面提交"})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return reject(403, {"error": "请从工作台导入页面提交"})
        if int(self.headers.get("Content-Length") or 0) > MAX_IMPORT:
            return reject(413, {"error": "文件过大，请拆分后导入（最多 1 MB）"})
        try:
            rows = knowledge.validate(self._payload(MAX_IMPORT).get("products"))
        except ValueError as e:  # JSON 解析、UTF-8 解码错误都是 ValueError 的子类，统一提示格式无效
            return self._send(400, {"error": str(e) if type(e) is ValueError else "资料格式无效"})
        try:
            return self._send(200, {"saved": KNOWLEDGE.save(rows)})
        except ValueError as e:
            return self._send(503, {"error": str(e)})
        except OSError:
            return self._send(503, {"error": "保存失败，请检查数据目录是否可写"})

    def _payload(self, limit=MAX_BODY):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            raise ValueError("请求体为空或过大")
        data = json.loads(self.rfile.read(n).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def do_POST(self):
        try:
            if self.path == "/api/product-knowledge":  # 工作台设置 → 产品资料导入
                return self._import_knowledge()
            p = self._payload()
            if self.path == "/api/hafiller-chat":  # 网页机器人挂件的 AI 模式
                try:
                    imported = KNOWLEDGE.all()
                except (OSError, ValueError):
                    imported = []  # 资料文件坏了也不影响聊天
                code, body = bot.chat_reply(kb, llm, p.get("messages"), imported)
                return self._send(code, body)
            inquiry = str(p.get("inquiry") or "").strip()[:MAX_TEXT]
            if not inquiry:
                return self._send(400, {"error": "询盘内容为空"})
            if self.path == "/api/round":
                prev = p.get("prev") if isinstance(p.get("prev"), dict) else None
                if prev:
                    prev = {"understanding": prev.get("understanding"),
                            "reply": str(prev.get("reply") or "")[:MAX_TEXT]}
                result = pipeline.run_round(kb, llm, inquiry, str(p.get("channel") or "alibaba"), prev,
                                            str(p.get("instruction") or "")[:1000], str(p.get("lang") or "auto"))
            elif self.path == "/api/check":
                reply = str(p.get("reply") or "").strip()[:MAX_TEXT]
                if not reply:
                    return self._send(400, {"error": "回复内容为空"})
                result = pipeline.check_only(kb, inquiry, p.get("understanding"), reply)
            else:
                return self._send(404, {"error": "not found"})
            return self._send(200, result)
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # 演示时不让页面卡死，错误写进日志
            self.log_error("处理失败: %r", e)
            return self._send(500, {"error": "服务内部错误，详见终端日志"})


def main():
    sys.stdout.reconfigure(errors="replace")  # 英文 Windows 控制台打印中文不崩
    port = int(os.environ.get("PORT", "8766"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"HAFILLER 询盘助手: http://127.0.0.1:{port}  模型: {llm.info()}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
