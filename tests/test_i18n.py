"""网站中英文切换：web/i18n.js 的词典和模式要覆盖页面上会显示的所有中文；inquiry.js 的界面文字要中英成对。
不开浏览器，按 i18n.js 的规则在 Python 里复算一遍。"""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
HAN = re.compile(r"[㐀-鿿豈-﫿]")
# 和 i18n.js 的 CJK 一致：汉字加中文标点、全角符号
CJK = re.compile(r"[　-〿㐀-鿿豈-﫿＀-￯]")
SKIP_TAGS = {"script", "style", "svg", "textarea", "noscript"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
ATTRS = ("placeholder", "title", "aria-label")
# 不显示在页面上的中文：只用于逻辑判断的字、下载文件的内容和文件名
NOT_UI_EXACT = {"待"}
NOT_UI_PART = ("产品名称（请替换）", "产品资料导入模板.csv", "MedBridge 海外销售中心简报")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def between(src, start, end):
    a = src.index(start) + len(start)
    return src[a:src.index(end, a)]


def load_i18n():
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    words = json.loads(between(src, "/* I18N-DICT-START */", "/* I18N-DICT-END */"))
    pats = json.loads(between(src, "/* I18N-PATTERNS-START */", "/* I18N-PATTERNS-END */"))
    return words, pats


WORDS, PATS = load_i18n()
COMPILED = [(re.compile(p), r) for p, r in PATS]


def tr(s):
    """和 i18n.js 的 tr() 同样的规则：先查词典，再按顺序试模式；$1 原样代入，$t1 先翻译再代入。翻不了返回 None。"""
    if not CJK.search(s):
        return s
    if s in WORDS:
        return WORDS[s]
    for rx, rep in COMPILED:
        m = rx.search(s)
        if m:
            def sub(mm):
                g = m.group(int(mm.group(2))) or ""
                return (tr(g) or g) if mm.group(1) else g
            return re.sub(r"\$(t?)(\d)", sub, rep)
    return None


class _Texts(HTMLParser):
    """收集文本节点和 placeholder/title/aria-label；跳过 script、style、svg、textarea 和 [data-i18n-skip] 子树。"""

    def __init__(self):
        super().__init__()
        self.stack, self.buf, self.out = [], [], []

    @property
    def skipping(self):
        return bool(self.stack) and self.stack[-1][1]

    def flush(self):
        text = "".join(self.buf)
        self.buf = []
        if not self.skipping and CJK.search(text):
            self.out.append(norm(text))

    def handle_starttag(self, tag, attrs):
        self.flush()
        a = dict(attrs)
        skip = self.skipping or tag in SKIP_TAGS or "data-i18n-skip" in a
        if not skip:
            self.out += [norm(a[k]) for k in ATTRS if a.get(k) and CJK.search(a[k])]
            if tag == "meta" and a.get("name") == "description":
                self.out.append(norm(a.get("content", "")))
        if tag not in VOID:
            self.stack.append((tag, skip))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        self.flush()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.buf.append(data)

    def close(self):
        super().close()
        self.flush()


def html_texts(html):
    p = _Texts()
    p.feed(html)
    p.close()
    return p.out


def js_strings(src):
    """JS 源码里的字符串字面量 [(起点, 终点, 内容)]；模板字符串的 ${…} 换成 1，里面的字面量另算。跳过注释和正则字面量。"""
    out = []

    def scan(i, in_expr):
        prev, depth = "", 0
        while i < len(src):
            c = src[i]
            if in_expr and c == "}" and depth == 0:
                return i + 1
            if c.isspace():
                i += 1
            elif src.startswith("//", i):
                j = src.find("\n", i)
                i = len(src) if j < 0 else j
            elif src.startswith("/*", i):
                i = src.index("*/", i) + 2
            elif c in "\"'`":
                j, buf = i + 1, []
                while src[j] != c:
                    if src[j] == "\\":
                        buf.append(src[j:j + 2])
                        j += 2
                    elif c == "`" and src.startswith("${", j):
                        j = scan(j + 2, True)
                        buf.append("1")
                    else:
                        buf.append(src[j])
                        j += 1
                out.append((i, j + 1, "".join(buf)))
                i, prev = j + 1, "a"
            elif c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^"):
                j, in_class = i + 1, False
                while in_class or src[j] != "/":
                    if src[j] == "\\":
                        j += 1
                    elif src[j] in "[]":
                        in_class = src[j] == "["
                    j += 1
                i = j + 1
                while i < len(src) and src[i].isalpha():
                    i += 1
                prev = "a"
            else:
                depth += {"{": 1, "}": -1}.get(c, 0)
                prev = "a" if (c.isalnum() or c in "_$") else c
                i += 1
        return i

    scan(0, False)
    return out


def ui_texts_of_js(path):
    texts = []
    for _, _, s in js_strings(path.read_text(encoding="utf-8")):
        if not CJK.search(s) or s in NOT_UI_EXACT or any(p in s for p in NOT_UI_PART):
            continue
        texts += html_texts(s)  # 字面量里可能是一段 HTML，按文本节点拆开
    return texts


class Coverage(unittest.TestCase):
    def assert_covered(self, texts, where):
        missing = sorted({t for t in texts if t and (tr(t) is None or CJK.search(tr(t)))})
        self.assertFalse(missing, f"{where} 里这些中文没有英文：\n" + "\n".join(missing))

    def test_index_html(self):
        texts = html_texts((WEB / "index.html").read_text(encoding="utf-8"))
        self.assertGreater(len(texts), 200)
        self.assert_covered(texts, "web/index.html")

    def test_app_js(self):
        texts = ui_texts_of_js(WEB / "app.js")
        self.assertGreater(len(texts), 30)
        self.assert_covered(texts, "web/app.js")

    def test_product_import_js(self):
        texts = ui_texts_of_js(WEB / "product-import.js")
        self.assertGreater(len(texts), 20)
        self.assert_covered(texts, "web/product-import.js")

    def test_dynamic_sentences(self):
        """带数字、拼接的句子按模式翻译。"""
        cases = {
            "已保存 12 款": "12 saved",
            "第 3 条产品名称重复：Derm": "Item 3: duplicate product name: Derm",
            "已保存 2 条资料。请收起并重新打开客服，加载最新资料。 列表刷新失败，请刷新页面查看。":
                "Saved 2 items. Close and reopen the support chat to load the latest data. "
                "The list failed to refresh; reload the page to see it.",
            "VitaCare 已加入客户资产": "VitaCare added to customers",
        }
        for zh, en in cases.items():
            self.assertEqual(tr(zh), en)

    def test_english_has_no_chinese(self):
        bad = [k for k, v in WORDS.items() if not v.strip() or CJK.search(v)]
        bad += [p for p, r in PATS if CJK.search(r)]
        self.assertFalse(bad, bad)
        self.assertTrue(all(k == norm(k) and CJK.search(k) for k in WORDS), "词典的键要是去掉多余空白的中文")

    def test_terms(self):
        terms = {"询盘助手": "Inquiry Assistant", "注册清单": "Registration Checklist", "工作台设置": "Workspace Settings",
                 "产品资料导入": "Product Data Import", "通知中心": "Notifications", "上新素材库": "Content Studio",
                 "合规资料库": "Compliance Documents", "采购与库存": "Procurement & Inventory",
                 "业务总览": "Overview", "客户与回访": "Customers & Follow-ups", "林晓": "Lin Xiao", "周宁": "Zhou Ning"}
        for zh, en in terms.items():
            self.assertEqual(WORDS.get(zh), en)


class InquiryPage(unittest.TestCase):
    def test_ui_text_has_english(self):
        """询盘页的动态界面文字由全站词典翻译，逐条检查覆盖率。"""
        texts = ui_texts_of_js(WEB / "inquiry.js")
        self.assertGreater(len(texts), 50)
        bad = sorted({s for s in texts if s and (tr(s) is None or CJK.search(tr(s)))})
        self.assertFalse(bad, "这些中文没有英文：\n" + "\n".join(bad))

    def test_backend_english_fields(self):
        src = (WEB / "inquiry.js").read_text(encoding="utf-8")
        for field in ("title_en", "message_en", "suggestion_en", "step_en", "note_en", "summary_en", "field_en", "mb:langchange"):
            self.assertIn(field, src)

    def test_samples_have_english_labels(self):
        samples = json.loads((ROOT / "samples" / "inquiries.json").read_text(encoding="utf-8"))
        for s in samples:
            self.assertTrue(s.get("label_en") and not CJK.search(s["label_en"]), s["id"])


if __name__ == "__main__":
    unittest.main()
