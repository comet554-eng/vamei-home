"""产品资料导入：存储校验、导入接口的同源限制和大小限制、机器人只带相关资料。用临时目录，不碰 data/。"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"

import bot  # noqa: E402
import knowledge  # noqa: E402
import server  # noqa: E402
from kb import KB  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "产品资料导入示例.json").read_text(encoding="utf-8"))


def row(name, content="浓度 20 mg/ml", source=""):
    return {"name": name, "content": content, "source": source}


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = knowledge.KnowledgeStore(Path(self.tmp.name) / "k.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_matches_teammate_rules(self):
        cases = [([], "1–200"), ([row("a")] * 201, "1–200"), ([{"name": 1, "content": "x"}], "字段格式"),
                 ([row("")], "1–120"), ([row("a", "x" * 8001)], "8000"), ([row("a", source="s" * 301)], "300"),
                 ([row("Hairont 膝关节")], "范围"), ([row("Derm"), row("derm")], "重复")]
        for value, msg in cases:
            with self.subTest(msg):
                with self.assertRaisesRegex(ValueError, msg):
                    knowledge.validate(value)
        self.assertEqual(knowledge.validate([{"name": " Derm ", "content": " x "}]), [row("Derm", "x")])

    def test_upsert_case_insensitive_and_sorted(self):
        self.assertEqual(self.store.all(), [])
        self.store.save(knowledge.validate(SAMPLE))
        self.store.save([row("derm", "新资料")])
        names = [r["name"] for r in self.store.all()]
        self.assertEqual(names, ["derm", "Fine Lines"])
        self.assertEqual(self.store.all()[0]["content"], "新资料")
        self.assertEqual(knowledge.KnowledgeStore(self.store.path).all(), self.store.all())  # 写到了文件
        self.assertEqual([p.name for p in self.store.path.parent.iterdir()], ["k.json"])  # 没留下临时文件

    def test_total_cap_does_not_write(self):
        self.store.save([row(f"P{i}") for i in range(200)])
        with self.assertRaisesRegex(ValueError, "200"):
            self.store.save([row("one more")])
        self.assertEqual(len(self.store.all()), 200)


class ImportEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved, server.KNOWLEDGE = server.KNOWLEDGE, knowledge.KnowledgeStore(Path(cls.tmp.name) / "k.json")
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        server.KNOWLEDGE = cls.saved
        cls.tmp.cleanup()

    def post(self, body, origin=None, host=None, ctype="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": ctype, "Origin": origin or f"http://127.0.0.1:{self.port}"}
        if host:
            headers["Host"] = host
        c.request("POST", "/api/product-knowledge", body=data, headers=headers)
        r = c.getresponse()
        out = (r.status, json.loads(r.read().decode("utf-8")))
        c.close()
        return out

    def get(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/api/product-knowledge")
        r = c.getresponse()
        out = (r.status, json.loads(r.read().decode("utf-8")))
        c.close()
        return out

    def test_import_then_list(self):
        self.assertEqual(self.post({"products": SAMPLE}), (200, {"saved": 2}))
        status, body = self.get()
        self.assertEqual(status, 200)
        self.assertEqual([p["name"] for p in body["products"]], ["Derm", "Fine Lines"])

    def test_only_same_local_origin(self):
        self.assertEqual(self.post({"products": SAMPLE}, origin="http://localhost:4173")[0], 403)  # 本机别的端口
        self.assertEqual(self.post({"products": SAMPLE}, origin="http://evil.example")[0], 403)
        self.assertEqual(self.post({"products": SAMPLE}, origin="http://evil.example", host="evil.example")[0], 403)  # DNS 重绑定
        self.assertEqual(self.post({"products": SAMPLE}, ctype="text/plain")[0], 403)

    def test_bad_input(self):
        self.assertEqual(self.post(b"{not json"), (400, {"error": "资料格式无效"}))
        self.assertEqual(self.post({"products": [row("眼科粘弹剂")]})[0], 400)
        self.assertEqual(self.post({"products": [row("x", "资" * 400000)]})[0], 413)  # 中文 UTF-8 每字 3 字节，约 1.2 MB


class BotUsesImports(unittest.TestCase):
    def test_only_mentioned_products_are_sent(self):
        class LLM:
            enabled, calls = True, []

            def chat(self, system, user, max_tokens=0):
                self.calls.append(user)
                return "Derm 规格 1.0 / 2.0 ml，其余待销售核实。"

        imported = knowledge.validate(SAMPLE)
        llm = LLM()
        bot.chat_reply(KB(), llm, [{"role": "user", "content": "当前勾选产品：Derm\nDerm 有哪些规格"}], imported)
        self.assertIn("IMPORTED", llm.calls[-1])
        self.assertIn("外销交联产品参数", llm.calls[-1])
        self.assertNotIn("Fine Lines（", llm.calls[-1])
        bot.chat_reply(KB(), llm, [{"role": "user", "content": "你们有哪些认证"}], imported)
        self.assertNotIn("IMPORTED", llm.calls[-1])


if __name__ == "__main__":
    unittest.main()
