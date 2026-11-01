"""校验意见和数据流说明的英文字段：每条规则每个分支都有英文，trace 每一步都有英文。
用假模型，不调用真实接口。运行：python -m unittest discover -s tests"""
import copy
import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"

import pipeline  # noqa: E402
import rules  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLM, LLMError  # noqa: E402

KBASE = KB()
SAMPLES = json.loads((ROOT / "samples" / "inquiries.json").read_text(encoding="utf-8"))
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")  # 汉字和全角标点

CO = {"country": "CO", "buyer_type": "distributor", "intents": ["price"], "products": []}
US = {"country": "US", "buyer_type": "clinic", "intents": [], "products": []}
GB_PERSON = {"country": "GB", "buyer_type": "individual", "intents": ["price"], "products": []}

# (回复, 理解, 询盘, 应命中的规则, 应命中的中文标题片段)；覆盖每条规则的每个分支
CASES = [
    ("Sub Skin is ideal for buttock augmentation.", CO, "", "C1", "身体部位"),
    ("Ideal para aumento de glúteos y senos.", CO, "", "C1", "身体部位"),
    ("Hello.", {"country": "ZZ", "intents": []}, "", "C2", "市场数据"),
    ("Hello.", {"intents": []}, "", "C2", "没识别出"),
    ("The product is already registered with INVIMA.", CO, "", "C2", "声称已在"),
    ("El producto ya está registrado ante INVIMA y pasa la aduana.", CO, "", "C2", "声称已在"),
    ("Registration with INVIMA is to be confirmed.", CO, "", "C2", "注册状态未知"),
    ("Derm is $25 per box.", GB_PERSON, "", "C3", "个人"),
    ("Sure, we can ship.", {"country": "GB", "buyer_type": "unknown", "intents": []},
     "I will inject myself at home", "C3", "个人"),
    ("Yes, it is FDA approved.", US, "", "C4", "没有否认"),
    ("Price is [PRICE].", US, "", "C4", "没说明"),
    ("No side effects and permanent results.", CO, "", "C5", "绝对化"),
    ("Sin efectos secundarios, 100% seguro.", CO, "", "C5", "绝对化"),
    ("Clinical trials show 98.2% satisfaction in 500 patients.", CO, "", "C6", "出处"),
    ("This is the best filler, No.1 in the world.", CO, "", "P1", "夸大"),
    ("Es mejor que Restylane y Juvederm.", CO, "", "P2", "竞品"),
    ("Price is 20 per box.", CO, "", "K1", "要素不全"),
    ("Precio: [PRECIO] USD por caja, FOB Shanghai. MOQ: 100. Pago: 30% T/T. Válida por 30 días.", CO, "", "K1", "占位符"),
    ("We offer you exclusive distribution in Colombia.", CO, "", "K2", "超出权限"),
    ("Le ofrecemos distribución exclusiva y protección de precios.", CO, "", "K2", "超出权限"),
    ("- Derm Deep: 5ml", CO, "", "K3", "不在产品库"),
    ("- Derm Deep: 0.5ml / 1.0ml", CO, "", "K3", "有矛盾"),
]


def kb_with_unregistered():
    """真实数据里只有美国是 not_registered，而美国走 C4。加一个假市场来覆盖 C2 的「未注册」分支。"""
    kb = copy.copy(KBASE)
    kb.markets = dict(KBASE.markets, ZZ={"name": "Testland", "name_zh": "测试国", "regulator": "TRA",
                                          "status": "not_registered", "aliases": []})
    return kb


class FakeLLM:
    """按系统提示词区分理解和生成；不等待，不联网。"""
    enabled = True
    model = "fake"

    def __init__(self, understanding=None, fail=()):
        self.understanding = understanding or {}
        self.fail = set(fail)

    def chat_json(self, system, user, max_tokens=2000):
        kind = "understand" if system == pipeline.UNDERSTAND_SYS else "generate"
        if kind in self.fail:
            raise LLMError("HTTP 529: overloaded")
        if kind == "understand":
            return dict(self.understanding)
        return {"reply": "Registration with INVIMA is to be confirmed.", "reply_zh": "INVIMA 注册待确认。"}


class FindingsEnglish(unittest.TestCase):
    def assert_english(self, findings):
        for f in findings:
            for k in ("title_en", "message_en", "suggestion_en"):
                with self.subTest(rule=f["rule"], title=f["title"], field=k):
                    self.assertTrue(f.get(k, "").strip(), f)
                    self.assertIsNone(CJK.search(f[k]), f[k])

    def test_every_branch(self):
        seen = set()
        for reply, u, inquiry, rule, title in CASES:
            findings = rules.check(reply, u, KBASE, inquiry)[0]
            with self.subTest(reply=reply):
                self.assertTrue(any(f["rule"] == rule and title in f["title"] for f in findings),
                                [f["title"] for f in findings])
            self.assert_english(findings)
            seen |= {f["rule"] for f in findings}
        findings = rules.check("We can supply.", {"country": "ZZ", "intents": []}, kb_with_unregistered())[0]
        self.assertTrue(any(f["rule"] == "C2" and "未注册" in f["title"] for f in findings))
        self.assert_english(findings)
        self.assertEqual(seen, {"C1", "C2", "C3", "C4", "C5", "C6", "P1", "P2", "K1", "K2", "K3"})

    def test_risky_edits(self):
        llm = LLM()
        for s in SAMPLES:
            with self.subTest(s["id"]):
                u = pipeline.understand(KBASE, llm, s["inquiry"])[0]
                findings = rules.check(s["risky_edit"], u, KBASE, s["inquiry"])[0]
                self.assertTrue(findings)
                self.assert_english(findings)

    def test_quotes_reply_and_market_names(self):
        f = [x for x in rules.check("El producto ya está registrado ante INVIMA.", CO, KBASE)[0] if x["level"] == "red"][0]
        self.assertIn("registrado", f["message_en"])
        self.assertIn("Colombia", f["title_en"])
        self.assertIn("INVIMA", f["message_en"])
        k1 = [x for x in rules.check("Price is 20 per box.", CO, KBASE)[0] if x["rule"] == "K1"][0]
        self.assertIn("Incoterm", k1["message_en"])

    def test_chinese_unchanged(self):
        f = rules.check("Price is 20 per box.", CO, KBASE)[0]
        k1 = [x for x in f if x["rule"] == "K1"][0]
        self.assertEqual(k1["message"], "买家问了价格，回复缺少：贸易术语、币种、MOQ、报价有效期、付款方式。")


class TraceEnglish(unittest.TestCase):
    def assert_round(self, r):
        for s in r["trace"]:
            for k in ("step_en", "note_en"):
                with self.subTest(step=s["step"], field=k, note=s["note"]):
                    self.assertTrue(s.get(k, "").strip(), s)
                    self.assertIsNone(CJK.search(s[k]), s[k])
        self.assertEqual([s["step_en"] for s in r["trace"]], ["Understand", "Knowledge base", "Generate", "Check"])
        self.assertTrue(r["understanding"].get("summary_en"))
        self.assertIsNone(CJK.search(r["understanding"]["summary_en"]))
        self.assertTrue(r["refs"])
        for ref in r["refs"]:
            self.assertTrue(ref.get("field_en"), ref)
            self.assertIsNone(CJK.search(ref["field_en"]))

    def test_mock_rounds_and_check_only(self):
        llm = LLM()
        self.assertFalse(llm.enabled)
        for s in SAMPLES:
            with self.subTest(s["id"]):
                r = pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"])
                self.assert_round(r)
                self.assert_round(pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"], r, "语气正式点"))
                bad = pipeline.check_only(KBASE, s["inquiry"], r["understanding"], s["risky_edit"])
                self.assert_round(bad)
                self.assertEqual(bad["trace"][2]["mode"], "manual")

    def test_numbers_in_english_notes(self):
        r = pipeline.run_round(KBASE, LLM(), SAMPLES[0]["inquiry"], SAMPLES[0]["channel"])
        reds = sum(f["level"] == "red" for f in r["findings"])
        self.assertIn(f"{reds} red, {len(r['findings']) - reds} yellow", r["trace"][3]["note_en"])
        self.assertIn(f"{len(r['refs'])} fields", r["trace"][1]["note_en"])
        self.assertIn("market CO: unknown", r["trace"][1]["note_en"])

    def test_parallel_and_fallback_notes(self):
        s = SAMPLES[0]
        same = {"language": "es", "country": "CO", "buyer_type": "distributor", "products": ["HF-SS", "HF-DP"],
                "summary_zh": "哥伦比亚经销商询价。", "summary_en": "Colombian distributor asks for prices."}
        r = pipeline.run_round(KBASE, FakeLLM(same), s["inquiry"], s["channel"])
        self.assert_round(r)
        self.assertIn("in parallel with Generate", r["trace"][0]["note_en"])
        self.assertIn("draft was kept", r["trace"][2]["note_en"])
        self.assertEqual(r["understanding"]["summary_en"], "Colombian distributor asks for prices.")

        r = pipeline.run_round(KBASE, FakeLLM({"country": "MX"}), s["inquiry"], s["channel"])
        self.assert_round(r)
        self.assertIn("(country)", r["trace"][2]["note_en"])
        self.assertRegex(r["trace"][2]["note_en"], r"\d+ ms wasted")

        r = pipeline.run_round(KBASE, FakeLLM(fail={"understand", "generate"}), s["inquiry"], s["channel"])
        self.assert_round(r)
        self.assertIn("fell back to keyword rules", r["trace"][0]["note_en"])
        self.assertIn("fell back to the offline template", r["trace"][2]["note_en"])

        prev = {"understanding": r["understanding"], "reply": r["reply"]}
        r = pipeline.run_round(KBASE, FakeLLM(fail={"generate"}), s["inquiry"], s["channel"], prev, "改短一点")
        self.assert_round(r)
        self.assertIn("Re-check", r["trace"][2]["note_en"])

    def test_summary_en_normalized(self):
        base = pipeline.heuristic_understanding(KBASE, SAMPLES[0]["inquiry"])
        self.assertEqual(base["summary_en"], pipeline.NO_SUMMARY_EN)
        self.assertEqual(pipeline.normalize({"summary_en": "这是中文"}, base, KBASE)["summary_en"], pipeline.NO_SUMMARY_EN)
        long = pipeline.normalize({"summary_en": "  " + "x" * 500}, base, KBASE)["summary_en"]
        self.assertEqual(long, "x" * 300)


if __name__ == "__main__":
    unittest.main()
