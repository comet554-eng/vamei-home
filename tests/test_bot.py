"""网页机器人 AI 模式：回复过规则校验、红灯改写、保守兜底，以及中文词表。用假模型，不调用真实接口。"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"

import bot  # noqa: E402
import rules  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLMError  # noqa: E402

KBASE = KB()


class FakeLLM:
    """按顺序吐出预设回复；遇到 LLMError 实例就抛出。"""
    def __init__(self, *replies, enabled=True):
        self.replies, self.enabled, self.calls = list(replies), enabled, []

    def chat(self, system, user, max_tokens=2000):
        self.calls.append(user)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def ask(text):
    return [{"role": "user", "content": text}]


class ChatFlow(unittest.TestCase):
    def test_clean_reply_passes_through(self):
        llm = FakeLLM("Derm 浓度 20 mg/ml，规格 1.0 / 2.0 ml。价格需销售核实，您在哪个国家？")
        code, body = bot.chat_reply(KBASE, llm, ask("Derm 的参数是什么"))
        self.assertEqual(code, 200)
        self.assertFalse(body["check"]["revised"] or body["check"]["fallback"])
        self.assertEqual(len(llm.calls), 1)

    def test_red_reply_is_revised(self):
        llm = FakeLLM("Sub Skin 很适合隆臀，效果很好。", "本系列不用于隆臀等身体部位填充。面部用途需按注册文件核实。")
        code, body = bot.chat_reply(KBASE, llm, ask("Sub Skin 能做隆臀吗"))
        self.assertEqual(code, 200)
        self.assertTrue(body["check"]["revised"])
        self.assertFalse(body["check"]["fallback"])
        self.assertIn("不用于隆臀", body["reply"])
        self.assertIn("C1", llm.calls[1])  # 改写时带上了校验意见

    def test_still_red_falls_back(self):
        llm = FakeLLM("我们已在哥伦比亚注册，可以清关。", "已经在哥伦比亚 INVIMA 注册，放心。")
        code, body = bot.chat_reply(KBASE, llm, ask("你们在哥伦比亚注册了吗"))
        self.assertEqual(code, 200)
        self.assertTrue(body["check"]["fallback"])
        self.assertEqual(body["reply"], bot.SAFE_REPLY["zh"])
        self.assertNotIn("red", [body["check"]["level"]])

    def test_us_buyer_needs_fda_disclaimer(self):
        llm = FakeLLM("Derm 规格 1.0 / 2.0 ml。", "产品未获 FDA 批准，目前不能供应美国市场。")
        code, body = bot.chat_reply(KBASE, llm, ask("我们是美国迈阿密的诊所，想采购 Derm"))
        self.assertTrue(body["check"]["revised"])
        self.assertIn("FDA", body["reply"])

    def test_not_configured_and_errors(self):
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM(enabled=False), ask("hi"))[0], 503)
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM(LLMError("HTTP 502")), ask("hi"))[0], 502)
        for bad in (None, [], [{"role": "system", "content": "x"}], [{"role": "user", "content": "x" * 6001}],
                    ask("a") * 13, [{"role": "assistant", "content": "hi"}]):
            self.assertEqual(bot.chat_reply(KBASE, FakeLLM("x"), bad)[0], 400, bad)

    def test_prompt_keeps_teammate_rules(self):
        p = bot.system_prompt()
        self.assertTrue(p.startswith("你是 HAFILLER 外贸询盘客服"))
        self.assertIn("补充规则", p)
        self.assertNotIn("app/bot.py", p)


def hits(reply, country=None, inquiry=""):
    u = {"country": country, "buyer_type": "unknown", "intents": [], "products": []}
    return {(f["rule"], f["level"]) for f in rules.check(reply, u, KBASE, inquiry)[0]}


class ChineseRules(unittest.TestCase):
    def test_body_use(self):
        self.assertIn(("C1", "red"), hits("Sub Skin 适合隆臀和丰胸。", "CO"))
        self.assertNotIn(("C1", "red"), hits("本系列不用于隆臀。", "CO"))

    def test_negation_does_not_leak_across_sentences(self):
        self.assertIn(("C1", "red"), hits("价格不能在这里确认。Sub Skin 适合隆臀。", "CO"))

    def test_registration_claims(self):
        self.assertIn(("C2", "red"), hits("我们已在哥伦比亚注册。", "CO"))
        self.assertNotIn(("C2", "red"), hits("哥伦比亚的注册情况待核实。", "CO"))
        self.assertNotIn(("C2", "red"), hits("公司已获得 CE 证书。", "CO"))

    def test_individual_and_superlatives(self):
        self.assertIn(("C3", "red"), hits("可以，发货到伦敦。", "GB", "我想买来自己打"))
        self.assertNotIn(("C3", "red"), hits("我们只向有资质的经销商和医疗机构供货。", "GB", "我想买来自己打"))
        self.assertIn(("P1", "yellow"), hits("HAFILLER 是全球第一的填充剂。", "CO"))
        self.assertIn(("C5", "yellow"), hits("零风险，无副作用。", "CO"))
        self.assertNotIn(("C5", "yellow"), hits("不能承诺零风险。", "CO"))


if __name__ == "__main__":
    unittest.main()
