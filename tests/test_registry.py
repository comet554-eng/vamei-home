"""四国注册清单：数据完整、英文齐全、重跑导入一致、接口可读；沙特和土耳其能识别。不调用模型。"""
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"

import server  # noqa: E402
from kb import KB  # noqa: E402

REGISTRY = ROOT / "kb" / "registry.json"
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")


def pairs(node, path="$"):
    """找出所有 {zh, en} 和 name_zh/name_en 对。"""
    if isinstance(node, dict):
        if "zh" in node:
            yield path, node.get("zh"), node.get("en")
        if "name_zh" in node:
            yield path + ".name", node.get("name_zh"), node.get("name_en")
        for k, v in node.items():
            yield from pairs(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from pairs(v, f"{path}[{i}]")


class Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_counts(self):
        self.assertEqual([m["code"] for m in self.d["markets"]], ["SA", "BR", "DE", "TR"])
        self.assertEqual(len(self.d["tasks"]), 40)
        self.assertEqual(len(self.d["sources"]), 9)
        self.assertEqual(len(self.d["dimensions"]), 5)

    def test_refs_and_codes(self):
        ids = {s["id"] for s in self.d["sources"]}
        for t in self.d["tasks"]:
            self.assertTrue(t["refs"], t["id"])
            self.assertLessEqual(set(t["refs"]), ids, t["id"])
            self.assertIn(t["market"], self.d["codes"]["market"])
            self.assertIn(t["applicability"], self.d["codes"]["applicability"])
            self.assertIn(t["status"], self.d["codes"]["status"])
        self.assertEqual(next(t for t in self.d["tasks"] if t["id"] == "25")["refs"], ["DE1", "DE2", "DE3", "DE4"])
        for s in self.d["sources"]:
            self.assertTrue(s["url"].startswith("https://"), s["id"])

    def test_every_zh_has_en(self):
        found = list(pairs(self.d))
        self.assertGreater(len(found), 150)
        for path, zh, en in found:
            self.assertTrue(isinstance(zh, str) and zh.strip(), path)
            self.assertTrue(isinstance(en, str) and en.strip(), f"{path} 缺英文")
            self.assertIsNone(CJK.search(en), f"{path} 英文里有中文：{en}")

    def test_reimport_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "registry.json"
            subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "import_registry.py"), str(out)],
                           check=True, capture_output=True)
            self.assertEqual(out.read_bytes(), REGISTRY.read_bytes(), "重跑导入结果和 kb/registry.json 不一致")


class Endpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_get_registry(self):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        c.request("GET", "/api/registry")
        r = c.getresponse()
        body = r.read().decode("utf-8")
        c.close()
        self.assertEqual(r.status, 200)
        self.assertTrue(r.getheader("Content-Type").startswith("application/json"))
        self.assertEqual(len(json.loads(body)["tasks"]), 40)


class Countries(unittest.TestCase):
    def test_new_markets(self):
        kb = KB()
        for text, code in [("我们在利雅得", "SA"), ("沙特客户要报价", "SA"), ("We are a clinic in Jeddah, KSA", "SA"),
                           ("Somos distribuidores en Arabia Saudita", "SA"), ("a distributor in Istanbul", "TR"),
                           ("土耳其经销商", "TR"), ("Türkiye importer", "TR"), ("伊斯坦布尔的诊所", "TR")]:
            self.assertEqual(kb.detect_country(text), code, text)

    def test_existing_markets_unchanged(self):
        kb = KB()
        for text, code in [("Distribuidor en Bogotá", "CO"), ("clinic in São Paulo", "BR"), ("we are in Berlin", "DE"),
                           ("importer from Miami", "US"), ("哥伦比亚客户", "CO"), ("Madrid clinic", "ES")]:
            self.assertEqual(kb.detect_country(text), code, text)
        self.assertIsNone(kb.detect_country("please send us your catalogue"))  # 「us」不是美国，「sa」不是沙特


if __name__ == "__main__":
    unittest.main()
