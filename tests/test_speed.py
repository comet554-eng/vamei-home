"""第一轮「理解与生成并行」的测试。用假模型模拟网络延迟，不调用真模型。
运行：python -m unittest discover -s tests"""
import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"

import pipeline  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLMError  # noqa: E402

KBASE = KB()
SAMPLES = json.loads((ROOT / "samples" / "inquiries.json").read_text(encoding="utf-8"))
DELAY = 0.3  # 假模型每次调用的耗时


class FakeLLM:
    """按系统提示词区分是理解还是生成；记录每次调用的线程，用来确认真的并行了。"""
    enabled = True
    model = "fake"

    def __init__(self, understanding=None, fail_understand=False):
        self.understanding = understanding or {}
        self.fail_understand = fail_understand
        self.calls = []
        self.lock = threading.Lock()

    def chat_json(self, system, user, max_tokens=2000):
        kind = "understand" if system == pipeline.UNDERSTAND_SYS else "generate"
        with self.lock:
            self.calls.append((kind, threading.current_thread().name))
        time.sleep(DELAY)
        if kind == "understand":
            if self.fail_understand:
                raise LLMError("HTTP 529: overloaded")
            return dict(self.understanding)
        return {"reply": "Estimado cliente: el registro ante INVIMA está por confirmar.", "reply_zh": "INVIMA 注册待确认。"}


def colombia():
    return SAMPLES[0]


class ParallelFirstRound(unittest.TestCase):
    def test_same_plan_keeps_draft_and_saves_time(self):
        s = colombia()
        llm = FakeLLM({"language": "es", "country": "CO", "buyer_type": "distributor", "products": ["HF-SS", "HF-DP"]})
        t0 = time.perf_counter()
        r = pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"])
        wall = time.perf_counter() - t0
        self.assertEqual([k for k, _ in llm.calls].count("generate"), 1)
        threads = {k: t for k, t in llm.calls}
        self.assertNotEqual(threads["understand"], threads["generate"])
        self.assertLess(wall, DELAY * 2 - 0.1, "理解和生成应该同时跑")
        self.assertEqual([t["step"] for t in r["trace"]], ["理解", "知识库调用", "生成", "校验"])
        self.assertIn("直接采用", r["trace"][2]["note"])
        self.assertGreaterEqual(r["wall_ms"], DELAY * 1000)

    def test_different_plan_rewrites(self):
        s = colombia()
        llm = FakeLLM({"language": "es", "country": "MX", "buyer_type": "distributor"})
        r = pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"])
        self.assertEqual([k for k, _ in llm.calls].count("generate"), 2)
        self.assertEqual(r["market"]["code"], "MX")
        self.assertIn("country", r["trace"][2]["note"])
        self.assertIn("重写", r["trace"][2]["note"])

    def test_understand_failure_falls_back_to_keywords(self):
        s = colombia()
        llm = FakeLLM(fail_understand=True)
        r = pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"])
        self.assertEqual(r["trace"][0]["mode"], "rules")
        self.assertIn("529", r["trace"][0]["error"])
        self.assertEqual([k for k, _ in llm.calls].count("generate"), 1)
        self.assertEqual(r["understanding"]["country"], "CO")

    def test_revise_round_unchanged(self):
        s = colombia()
        llm = FakeLLM()
        prev = {"understanding": {"country": "CO", "buyer_type": "distributor"}, "reply": "Hola"}
        r = pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"], prev, "语气正式点")
        self.assertEqual([k for k, _ in llm.calls], ["generate"])
        self.assertEqual(r["trace"][0]["mode"], "reuse")


if __name__ == "__main__":
    unittest.main()
