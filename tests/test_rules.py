"""规则和流程的回归测试。运行：python -m unittest discover -s tests"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["HA_LLM_PROVIDER"] = "mock"  # 测试不调用模型

import pipeline  # noqa: E402
import rules  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLM  # noqa: E402

KBASE = KB()
CO = {"country": "CO", "buyer_type": "distributor", "intents": ["price", "exclusivity"], "products": []}
US = {"country": "US", "buyer_type": "clinic", "intents": [], "products": []}


def hits(reply, u, inquiry=""):
    findings, level = rules.check(reply, u, KBASE, inquiry)
    return {(f["rule"], f["level"]) for f in findings}, level


class BodyIndication(unittest.TestCase):
    def test_flags_body_use_en_es(self):
        self.assertIn(("C1", "red"), hits("Sub Skin is ideal for buttock augmentation.", CO)[0])
        self.assertIn(("C1", "red"), hits("Ideal para aumento de glúteos y senos.", CO)[0])

    def test_negated_body_use_passes(self):
        self.assertNotIn(("C1", "red"), hits("Sub Skin is not indicated for breast or buttock augmentation.", CO)[0])
        self.assertNotIn(("C1", "red"), hits("No se usan para aumento de glúteos ni de busto.", CO)[0])


class Registration(unittest.TestCase):
    def test_claim_in_unknown_market_is_red(self):
        self.assertIn(("C2", "red"), hits("The product is already registered with INVIMA.", CO)[0])

    def test_pending_wording_passes(self):
        found = hits("Registration with INVIMA is to be confirmed.", CO)[0]
        self.assertNotIn(("C2", "red"), found)
        self.assertIn(("C2", "yellow"), found)

    def test_pending_far_from_claim_word(self):
        uk = {"country": "GB", "buyer_type": "individual", "intents": []}
        reply = ("HAFILLER Derm's registration with the UK regulator, MHRA (UKCA/CE), is still to be confirmed, "
                 "so we cannot confirm supply to the UK at this time.")
        self.assertNotIn(("C2", "red"), hits(reply, uk)[0])

    def test_ce_approved_is_not_local_registration(self):
        self.assertNotIn(("C2", "red"), hits("The filler is CE approved.", CO)[0])

    def test_unknown_country(self):
        self.assertIn(("C2", "yellow"), hits("Hello.", {"intents": []})[0])


class IndividualAndUS(unittest.TestCase):
    def test_individual_needs_decline(self):
        u = {"country": "GB", "buyer_type": "individual", "intents": ["price"]}
        self.assertIn(("C3", "red"), hits("Derm is $25 per box.", u)[0])
        self.assertNotIn(("C3", "red"), hits("We only supply licensed distributors and clinics.", u)[0])

    def test_inquiry_wording_triggers_c3(self):
        u = {"country": "GB", "buyer_type": "unknown", "intents": []}
        self.assertIn(("C3", "red"), hits("Sure, we can ship.", u, "I will inject myself at home")[0])

    def test_us_fda(self):
        self.assertIn(("C4", "red"), hits("Yes, it is FDA approved.", US)[0])
        self.assertIn(("C4", "red"), hits("Price is [PRICE].", US)[0])
        self.assertEqual(hits("Our products are not FDA-approved, so we cannot supply the US market.", US),
                         (set(), "green"))


class WordingRules(unittest.TestCase):
    def test_absolute_claims(self):
        self.assertIn(("C5", "yellow"), hits("No side effects and permanent results.", CO)[0])
        self.assertNotIn(("C5", "yellow"), hits("Results are not permanent; duration is 9-18 months.", CO)[0])

    def test_unsourced_numbers_but_not_deposit(self):
        self.assertIn(("C6", "yellow"), hits("Clinical trials show 98.2% satisfaction.", CO)[0])
        self.assertNotIn(("C6", "yellow"), hits("Payment: 30% T/T deposit.", CO)[0])

    def test_superlative_but_not_signoff(self):
        self.assertIn(("P1", "yellow"), hits("This is the best filler.", CO)[0])
        self.assertNotIn(("P1", "yellow"), hits("Best regards,\nSales Team", CO)[0])

    def test_real_model_wordings(self):
        """2026-10-31 真实模型跑出来、曾被误判的三句话。"""
        uk = {"country": "GB", "buyer_type": "individual", "intents": ["price"]}
        self.assertEqual(hits("We are therefore unable to supply them for personal use.", uk), (set(), "green"))
        us_reply = ("Regarding FDA approval: HAFILLER Derm is not approved by the U.S. Food and Drug "
                    "Administration (FDA). For this reason, we cannot supply these products to the United States.")
        self.assertNotIn(("C4", "red"), hits(us_reply, US)[0])
        co = "La distribución exclusiva requiere la aprobación de nuestro gerente."
        self.assertNotIn(("K2", "red"), hits(co, CO)[0])
        gb = {"country": "GB", "buyer_type": "distributor", "intents": []}
        mhra = "HAFILLER Derm's registration with the UK regulator, MHRA (UKCA/CE), is still to be confirmed."
        self.assertNotIn(("C2", "red"), hits(mhra, gb)[0])

    def test_competitor(self):
        self.assertIn(("P2", "yellow"), hits("Smoother than Restylane.", CO)[0])


class CommercialRules(unittest.TestCase):
    def test_quote_elements(self):
        self.assertIn(("K1", "yellow"), hits("Price is 20 per box.", CO)[0])
        full = "Price: [PRICE] USD per box, FOB Shanghai. MOQ: 100 boxes. Payment: 30% T/T. Valid for 30 days."
        titles = {f["title"] for f in rules.check(full, CO, KBASE)[0] if f["rule"] == "K1"}
        self.assertEqual(titles, {"有占位符要手填"})

    def test_exclusivity(self):
        self.assertIn(("K2", "red"), hits("We offer you exclusive distribution in Colombia.", CO)[0])
        self.assertNotIn(("K2", "red"), hits("Exclusive distribution is subject to manager approval.", CO)[0])
        self.assertNotIn(("K2", "red"), hits("La distribución exclusiva requiere aprobación de la gerencia.", CO)[0])

    def test_specs_against_kb(self):
        found = rules.check("- Derm Deep: 0.5ml / 1.0ml / 5ml", CO, KBASE)[0]
        k3 = {f["title"] for f in found if f["rule"] == "K3"}
        self.assertEqual(k3, {"规格不在产品库里", "规格在资料里有矛盾"})
        self.assertFalse([f for f in rules.check("- Derm Deep: 0.5ml (to be confirmed)", CO, KBASE)[0] if f["rule"] == "K3"])
        self.assertFalse([f for f in rules.check("- Derm Plus: 1.5ml / 10ml / 20ml", CO, KBASE)[0] if f["rule"] == "K3"])


class Pipeline(unittest.TestCase):
    """离线模板必须自己通过校验：没有红灯。示例里的「风险话术」必须被抓出红灯。"""

    def test_samples(self):
        llm = LLM()
        self.assertFalse(llm.enabled)
        samples = json.loads((ROOT / "samples" / "inquiries.json").read_text(encoding="utf-8"))
        for s in samples:
            with self.subTest(s["id"]):
                r = pipeline.run_round(KBASE, llm, s["inquiry"], s["channel"])
                self.assertNotEqual(r["level"], "red", r["findings"])
                self.assertEqual([t["step"] for t in r["trace"]], ["理解", "知识库调用", "生成", "校验"])
                bad = pipeline.check_only(KBASE, s["inquiry"], r["understanding"], s["risky_edit"])
                self.assertEqual(bad["level"], "red")

    def test_catalog_covers_all_products(self):
        ids = [c["id"] for c in pipeline.catalog(KBASE)]
        self.assertEqual(ids, list(KBASE.products))
        self.assertTrue(all(c["indication"] for c in pipeline.catalog(KBASE)))

    def test_colombia_understanding(self):
        s = json.loads((ROOT / "samples" / "inquiries.json").read_text(encoding="utf-8"))[0]
        u = pipeline.heuristic_understanding(KBASE, s["inquiry"])
        self.assertEqual((u["language"], u["country"], u["buyer_type"]), ("es", "CO", "distributor"))
        self.assertEqual(set(u["products"]), {"HF-SS", "HF-DP"})
        self.assertTrue({"price", "exclusivity", "registration"} <= set(u["intents"]))


if __name__ == "__main__":
    unittest.main()
