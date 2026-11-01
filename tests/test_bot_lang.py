"""网页机器人 AI 模式错误提示的语言：按客户最后一条消息选中文或英文。用假模型，不调用真实接口。"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"

import bot  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLMError  # noqa: E402

KBASE = KB()


class FakeLLM:
    """同 test_bot.py：按顺序吐出预设回复；遇到 LLMError 实例就抛出。"""
    def __init__(self, *replies, enabled=True):
        self.replies, self.enabled = list(replies), enabled

    def chat(self, system, user, max_tokens=2000):
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def ask(text):
    return [{"role": "user", "content": text}]


class ErrorLanguage(unittest.TestCase):
    def test_english_errors(self):
        msg = ask("Selected products: Derm\nWhat is the price?")
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM(enabled=False), msg), (503, {"error": bot.NOT_CONFIGURED["en"]}))
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM(LLMError("HTTP 502")), msg), (502, {"error": bot.UNAVAILABLE["en"]}))
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM("x"), ask("x" * 6001)), (400, {"error": bot.INVALID["en"]}))
        self.assertNotRegex(bot.NOT_CONFIGURED["en"] + bot.UNAVAILABLE["en"] + bot.INVALID["en"], r"[一-鿿]")

    def test_chinese_errors(self):
        msg = ask("当前勾选产品：Derm\n价格多少")
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM(enabled=False), msg)[1]["error"], bot.NOT_CONFIGURED["zh"])
        self.assertEqual(bot.chat_reply(KBASE, FakeLLM(LLMError("HTTP 502")), msg)[1]["error"], bot.UNAVAILABLE["zh"])

    def test_unreadable_messages_use_chinese(self):
        for bad in (None, [], "hello", [{"role": "system", "content": "hello"}], [{"role": "user", "content": 1}]):
            self.assertEqual(bot.chat_reply(KBASE, FakeLLM("x"), bad), (400, {"error": bot.INVALID["zh"]}), bad)

    def test_language_follows_last_customer_message(self):
        msgs = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "您好"},
                {"role": "user", "content": "Selected products: Derm\nprice?"}]
        self.assertEqual(bot.error_lang(msgs), "en")
        self.assertEqual(bot.error_lang(msgs[:2]), "zh")


if __name__ == "__main__":
    unittest.main()
