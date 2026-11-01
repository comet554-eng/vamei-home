"""服务路由测试：网站在 /，工作台在 /lab/，API 只对本机来源开跨域。不调用模型。"""
import http.client
import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"  # 环境变量优先于 .env，测试不调用模型

import server  # noqa: E402


class Routing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, method, path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, headers=headers or {})
        r = c.getresponse()
        body = r.read().decode("utf-8", "replace")
        c.close()
        return r, body

    def test_site_and_lab(self):
        r, body = self.req("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn('id="view-inquiry"', body)
        r, body = self.req("GET", "/lab/")
        self.assertEqual(r.status, 200)
        self.assertIn("工作流 A", body)
        self.assertEqual(self.req("GET", "/lab")[0].status, 301)
        for path in ("/inquiry.js", "/inquiry.css", "/app.js", "/styles.css", "/lab/app.js", "/lab/style.css"):
            self.assertEqual(self.req("GET", path)[0].status, 200, path)

    def test_no_path_escape(self):
        for path in ("/../kb/products.json", "/lab/../../.env", "/%2e%2e/.env"):
            self.assertEqual(self.req("GET", path)[0].status, 404, path)

    def test_cors_only_for_local_origins(self):
        r, _ = self.req("OPTIONS", "/api/round", {"Origin": "http://localhost:4173"})
        self.assertEqual(r.status, 204)
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), "http://localhost:4173")
        r, _ = self.req("GET", "/api/status", {"Origin": "http://127.0.0.1:4173"})
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), "http://127.0.0.1:4173")
        r, _ = self.req("GET", "/api/status", {"Origin": "http://evil.example"})
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_widget_endpoints(self):
        self.assertEqual(self.req("GET", "/widget/hafiller-widget.js")[0].status, 200)
        r, body = self.req("GET", "/api/product-knowledge")
        self.assertEqual(r.status, 200)
        self.assertIsInstance(json.loads(body)["products"], list)  # 内容取决于 data/ 里导入过什么
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", "/api/hafiller-chat", body='{"messages":[{"role":"user","content":"hi"}]}',
                  headers={"Content-Type": "application/json"})
        r = c.getresponse()
        self.assertEqual(r.status, 503)  # 测试里是 mock 模式，挂件会提示切回规则库
        c.close()


if __name__ == "__main__":
    unittest.main()
