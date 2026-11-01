"""知识库加载与词语匹配。所有数据都在 kb/ 目录的 JSON 里，代码只负责读和查。"""
import json
import re
from functools import lru_cache
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
FILLER_IDS = ["HF-FL", "HF-DERM", "HF-DD", "HF-DP", "HF-SS"]


def _load(name):
    with open(KB_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _bounded(ch):
    """字母数字需要词边界；中文没有空格分词，不加。"""
    return ch.isalnum() and not ("一" <= ch <= "鿿")


@lru_cache(maxsize=4096)
def term_pattern(term):
    """单词边界只加在词首尾是字母数字的一侧，这样 $、#1、No.1 也能匹配。
    全大写且不超过 4 个字母的词（US、FDA、MOQ）区分大小写，避免把英语的 us 当成美国。"""
    body = re.escape(term).replace("\\ ", "\\s+")
    left = "(?<!\\w)" if _bounded(term[0]) else ""
    right = "(?!\\w)" if _bounded(term[-1]) else ""
    letters = re.sub("[^A-Za-z]", "", term)
    case_sensitive = letters.isupper() and len(letters) <= 4
    return re.compile(left + body + right, 0 if case_sensitive else re.IGNORECASE)


def find_terms(text, terms):
    """返回 [(start, end, matched_text)]，按位置排序，重叠的只保留较长的。"""
    hits = []
    for t in terms:
        for m in term_pattern(t).finditer(text):
            hits.append((m.start(), m.end(), m.group(0)))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out = []
    for h in hits:
        if out and h[0] < out[-1][1]:
            continue
        out.append(h)
    return out


def has_term(text, terms):
    return any(term_pattern(t).search(text) for t in terms)


class KB:
    def __init__(self):
        p = _load("products.json")
        self.meta = p["meta"]
        self.company = p["company"]
        self.filler_common = p["filler_common"]
        self.products = {x["id"]: x for x in p["products"]}
        self.evidence = p["evidence"]
        self.markets = _load("markets.json")["markets"]
        self.policy = _load("policy.json")
        self.rules = _load("rules.json")

    def product_mentions(self, text):
        """在文本里找型号名，返回 [(start, end, product_id)]。长名字优先，所以 Derm Deep 不会被当成 Derm。"""
        names = []
        for pid, aliases in self.rules["product_aliases"].items():
            for a in aliases:
                names.append((a, pid))
        names.sort(key=lambda x: -len(x[0]))
        taken, out = [], []
        for name, pid in names:
            for m in term_pattern(name).finditer(text):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                out.append((m.start(), m.end(), pid))
        return sorted(out)

    def detect_country(self, text):
        """按国家别名在文本里第一次出现的位置选国家。找不到返回 None。"""
        best = None
        for code, m in self.markets.items():
            hits = find_terms(text, m.get("aliases", []) + [m["name"]])
            zh = m.get("name_zh")
            if zh:  # 中文没有词边界：「南美国家」里的「美国」不算
                hits += [(x.start(), x.end(), zh) for x in re.finditer(re.escape(zh), text)
                         if not (x.start() and text[x.start() - 1] in "南北中")]
                hits.sort()
            if not hits:
                continue
            if best is None or hits[0][0] < best[0]:
                best = (hits[0][0], code)
        return best[1] if best else None

    def volume_sources(self, pid):
        """该型号每个来源列出的规格。返回 (每个来源一个 ml 数值集合, 区间列表 [(低, 高)])。"""
        field = self.products.get(pid, {}).get("volumes")
        if not field:
            return [], []
        sets, ranges = [], []
        for v in [field["v"]] + [a["v"] for a in field.get("alt", [])]:
            items = v if isinstance(v, list) else [v]
            nums = set()
            for item in items:
                found = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", item)]
                if "~" in item and len(found) == 2:
                    ranges.append((found[0], found[1]))
                    continue
                nums.update(found)
            if nums:
                sets.append(nums)
        return sets, ranges
