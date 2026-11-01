"""校验规则引擎。只用词表和知识库做确定性判断，不调用模型，同样的输入每次结果一样。
规则编号和等级对应 README 里的校验规则表；词表在 kb/rules.json。"""
import re

from kb import find_terms, has_term

ORDER = {"red": 0, "yellow": 1}
VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*ml\b", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\[[A-ZÁÉÍÓÚÑ0-9 _/]{3,}\]")
PERCENT_RE = re.compile(r"\d+(?:[.,]\d+)?\s?%")
CASES_RE = re.compile(r"\b\d{2,}\s+(?:cases|patients|casos|pacientes)\b", re.IGNORECASE)
CERT_NEAR = re.compile(r"(CE|ISO|NMPA|MDSAP)[\s-]*$")


END_RE = r"(?<!\b[A-Z])[.!?]"  # 「U.S.」这种单个大写字母后的句点不算断句
CJK_END = r"[。！？；\n;]"       # 中文句号后面通常不跟空格，所以单独算


def sentence_at(text, i):
    """i 所在句子的 (起, 止)。句号后紧跟数字（如 1.5ml）不算断句。"""
    start = 0
    for m in re.finditer(END_RE + r"(?=\s)|" + CJK_END, text[:i]):
        start = m.end()
    m = re.search(END_RE + r"(?=\s|$)|" + CJK_END, text[i:])
    end = i + m.end() if m else len(text)
    return start, end


def declines(reply, R):
    """回复是不是在婉拒供货。固定短语加正则，能匹配「unable to supply them」这类中间插词的说法。"""
    if has_term(reply, R["decline"]):
        return True
    return any(re.search(p, reply, re.IGNORECASE) for p in R.get("decline_patterns", []))


def window(text, s, e, before=60, after=40):
    """词语前后一段文字，不跨句。"""
    a, b = sentence_at(text, s)
    return text[max(a, s - before):min(b, e + after)]


def negated(text, s, e, R):
    return has_term(window(text, s, e), R["negation"])


def mask(text, phrases):
    """把例外短语换成等长空格，其他位置的下标不变。"""
    for s, e, _ in find_terms(text, phrases):
        text = text[:s] + " " * (e - s) + text[e:]
    return text


def finding(rule, level, title, message, suggestion, title_en, message_en, suggestion_en, spans=()):
    """英文三项必填，页面切到英文时用。"""
    return {"rule": rule, "level": level, "title": title, "message": message, "suggestion": suggestion,
            "title_en": title_en, "message_en": message_en, "suggestion_en": suggestion_en,
            "spans": [[s, e] for s, e in sorted(spans)]}


def words_of(reply, spans, sep="、"):
    return sep.join(dict.fromkeys(reply[s:e] for s, e in sorted(spans)))


def words_en(reply, spans):
    return words_of(reply, spans, ", ")


def c1_body(reply, u, kb, R):
    spans = [(s, e) for s, e, _ in find_terms(reply, R["C1_body"]) if not negated(reply, s, e, R)]
    if not spans:
        return []
    return [finding("C1", "red", "推荐了身体部位填充",
                    f"回复把产品用于「{words_of(reply, spans)}」。产品库里隆胸、隆臀的适应症互相矛盾（D02、D03），也没有任何国家批准这一用途的记录。",
                    "删掉身体部位用途，只介绍面部适应症；如果买家问到，明确说明不用于隆胸、隆臀。",
                    "Body-area filling recommended",
                    f"The reply uses the product for \"{words_en(reply, spans)}\". The sources contradict each other on "
                    "breast and buttock indications (D02, D03), and no country has approved this use.",
                    "Remove body-area uses and describe facial indications only; if the buyer asks, state clearly "
                    "that the product is not for breast or buttock augmentation.", spans)]


def c2_registration(reply, u, kb, R):
    code = u.get("country")
    m = kb.markets.get(code) if code else None
    if code == "US":
        return []  # 美国由 C4 处理
    if code and not m:
        return [finding("C2", "yellow", f"产品库没有 {code} 的市场数据",
                        "不知道该国的监管机构和注册状态。", "向注册专员确认后补进 kb/markets.json。",
                        f"No market data for {code} in the knowledge base",
                        "The regulator and registration status for this country are unknown.",
                        "Confirm with the registration specialist, then add it to kb/markets.json.")]
    if not m:
        return [finding("C2", "yellow", "没识别出买家国家",
                        "不知道买家在哪个国家，就没法判断能不能卖、要什么注册。", "先问清买家所在国家，再承诺供货。",
                        "Buyer country not identified",
                        "Without the buyer's country we cannot tell whether the product may be sold there "
                        "or what registration it needs.",
                        "Ask which country the buyer is in before committing to supply.")]
    name = m.get("name") or code
    out = []
    if m["status"] != "registered":
        spans = []
        hits = [(s, e) for s, e, _ in find_terms(reply, R["C2_claims"])]
        hits += [x.span() for p in R.get("C2_patterns", []) for x in re.finditer(p, reply)]  # 「已在哥伦比亚注册」
        for s, e in hits:
            if CERT_NEAR.search(reply[max(0, s - 12):s]) or re.search(r"CE|ISO|NMPA|MDSAP", reply[s:e]):
                continue  # 「CE approved」「已获得 CE 证书」说的是 CE，不是当地注册
            a, b = sentence_at(reply, s)
            if negated(reply, s, e, R) or has_term(reply[a:b], R["pending"]):
                continue  # 「待确认」常放在句末，所以按整句查
            spans.append((s, e))
        if spans:
            out.append(finding("C2", "red", f"声称已在{m['name_zh']}注册或可清关",
                               f"回复里有「{words_of(reply, spans)}」，但产品库里{m['name_zh']}（{m['regulator']}）的注册状态是「"
                               f"{m['status']}」。",
                               f"改成「{m['regulator']} 注册情况待确认」，不承诺清关。",
                               f"Claims registration or customs clearance in {name}",
                               f"The reply says \"{words_en(reply, spans)}\", but the knowledge base lists the "
                               f"registration status in {name} ({m['regulator']}) as \"{m['status']}\".",
                               f"Change it to \"{m['regulator']} registration to be confirmed\" and do not promise "
                               "customs clearance.", spans))
    if declines(reply, R):
        return out
    if m["status"] == "unknown":
        out.append(finding("C2", "yellow", f"{m['name_zh']}注册状态未知",
                           f"产品库没有 {m['regulator']} 的注册记录，发送前需要注册专员确认。",
                           "向注册专员确认后再更新 kb/markets.json。",
                           f"Registration status in {name} unknown",
                           f"The knowledge base has no {m['regulator']} registration record; the registration "
                           "specialist must confirm before sending.",
                           "Confirm with the registration specialist, then update kb/markets.json."))
    elif m["status"] == "not_registered":
        out.append(finding("C2", "yellow", f"{m['name_zh']}未注册",
                           f"产品在 {m['regulator']} 没有注册，只能谈注册合作，不能直接供货。", "说明需要先完成当地注册。",
                           f"Not registered in {name}",
                           f"The product is not registered with {m['regulator']}; we can only discuss a registration "
                           "partnership, not supply directly.",
                           "Explain that local registration must be completed first."))
    return out


def c3_individual(reply, u, kb, R):
    inquiry = u.get("_inquiry", "")
    if u.get("buyer_type") != "individual" and not has_term(inquiry, R["C3_inquiry"]):
        return []
    if has_term(reply, R["C3_decline"]) or declines(reply, R):
        return []
    return [finding("C3", "red", "买家可能是个人或要自行注射",
                    "注射填充剂是三类医疗器械，只能卖给有资质的经销商和医疗机构，由执业医生注射。",
                    "改成婉拒，说明只向有资质的经销商和诊所供货。",
                    "Buyer may be an individual or plans to self-inject",
                    "Injectable fillers are Class III medical devices. They may only be sold to licensed distributors "
                    "and medical institutions, and injected by licensed physicians.",
                    "Decline politely and explain that we only supply licensed distributors and clinics.")]


def c4_us(reply, u, kb, R):
    if u.get("country") != "US":
        return []
    fda = find_terms(reply, ["FDA"])
    claims = [(s, e) for s, e, _ in fda if not negated(reply, s, e, R)]
    if claims and len(claims) < len(fda) and declines(reply, R):
        claims = []  # 已明确否认并婉拒，「Regarding FDA approval:」这类标题不算声称
    if claims:
        return [finding("C4", "red", "对美国买家提到 FDA 但没有否认",
                        "三份资料都没有 FDA 批准，回复不能暗示产品可以在美国销售。",
                        "明确写出产品未获 FDA 批准，不能供应美国市场。",
                        "FDA mentioned to a US buyer without a denial",
                        "None of the three sources shows FDA approval; the reply must not imply the product "
                        "can be sold in the US.",
                        "State clearly that the product is not FDA approved and cannot be supplied to the US market.",
                        claims)]
    if not fda:
        return [finding("C4", "red", "美国买家，但回复没说明未获 FDA 批准",
                        "资料里只有 CE、MDSAP、NMPA，没有 FDA 批准。", "加一句：产品未获 FDA 批准，目前不能供应美国市场。",
                        "US buyer, but the reply does not say the product is not FDA approved",
                        "The sources only list CE, MDSAP and NMPA; there is no FDA approval.",
                        "Add: the product is not FDA approved and cannot be supplied to the US market for now.")]
    return []


def c5_absolute(reply, u, kb, R):
    spans = [(s, e) for s, e, _ in find_terms(reply, R["C5_terms"])]
    spans += [(s, e) for s, e, _ in find_terms(reply, R["C5_negatable"]) if not negated(reply, s, e, R)]
    if not spans:
        return []
    return [finding("C5", "yellow", "绝对化的安全或功效说法",
                    f"「{words_of(reply, spans)}」属于高风险用语，资料里也没有支持它的证据。",
                    "删掉这类说法，或换成有出处的客观描述。",
                    "Absolute safety or efficacy claim",
                    f"\"{words_en(reply, spans)}\" is high-risk wording, and the sources have no evidence for it.",
                    "Remove these claims or replace them with objective, sourced statements.", spans)]


def c6_unsourced(reply, u, kb, R):
    spans = []
    for m in list(PERCENT_RE.finditer(reply)) + list(CASES_RE.finditer(reply)):
        a, b = sentence_at(reply, m.start())
        sent = reply[a:b]
        if m.re is PERCENT_RE and not has_term(sent, R["C6_context"]):
            continue  # 「30% 定金」这类不是临床数据
        if has_term(sent, R["C6_source"]):
            continue
        spans.append((m.start(), m.end()))
    if not spans:
        return []
    return [finding("C6", "yellow", "临床数据没有出处",
                    f"「{words_of(reply, spans)}」来自画册，但画册没写研究名称、时间和机构。",
                    "附上研究出处，或者删掉具体数字。",
                    "Clinical data without a source",
                    f"\"{words_en(reply, spans)}\" comes from the brochure, which gives no study name, date or institution.",
                    "Cite the study, or remove the specific figures.", spans)]


def p1_superlative(reply, u, kb, R):
    masked = mask(reply, R["P1_exceptions"])
    spans = [(s, e) for s, e, _ in find_terms(masked, R["P1_terms"])]
    if not spans:
        return []
    return [finding("P1", "yellow", "绝对化或夸大用语",
                    f"「{words_of(reply, spans)}」在平台和广告规则里都属于风险用语，也拿不出依据。",
                    "删掉最高级和排名说法，改用具体参数。",
                    "Superlative or exaggerated wording",
                    f"\"{words_en(reply, spans)}\" is risky under platform and advertising rules, and we cannot back it up.",
                    "Remove superlatives and ranking claims; use specific parameters instead.", spans)]


def p2_competitor(reply, u, kb, R):
    spans = [(s, e) for s, e, _ in find_terms(reply, R["P2_terms"])]
    if not spans:
        return []
    return [finding("P2", "yellow", "点名了竞品或别的品牌",
                    f"提到「{words_of(reply, spans)}」，有商标和比较广告风险；Aquaderm 是资料里混进来的别家品牌（D09）。",
                    "不提竞品名称，只讲自家参数。",
                    "Competitor or other brand named",
                    f"Mentioning \"{words_en(reply, spans)}\" carries trademark and comparative-advertising risk; "
                    "Aquaderm is another company's brand that slipped into the sources (D09).",
                    "Do not name competitors; describe our own parameters only.", spans)]


def k1_quote(reply, u, kb, R):
    if not {"price", "moq"} & set(u.get("intents", [])) or declines(reply, R):
        return []
    missing = [k for k, terms in R["K1_required"].items() if not has_term(reply, terms)]
    placeholders = [(m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(reply)]
    out = []
    if missing:
        out.append(finding("K1", "yellow", "报价要素不全",
                           f"买家问了价格，回复缺少：{'、'.join(R['K1_labels'][k] for k in missing)}。",
                           "按 kb/policy.json 补齐报价要素。",
                           "Quote is incomplete",
                           f"The buyer asked for a price, but the reply is missing: "
                           f"{', '.join(R['K1_labels_en'][k] for k in missing)}.",
                           "Add the missing quote elements from kb/policy.json."))
    if placeholders:
        out.append(finding("K1", "yellow", "有占位符要手填",
                           f"「{words_of(reply, placeholders)}」需要业务员填入实际内容，产品库里没有价格。",
                           "发送前把方括号里的内容换成实际价格。",
                           "Placeholders to fill in by hand",
                           f"The salesperson must replace \"{words_en(reply, placeholders)}\" with real content; "
                           "the knowledge base has no prices.",
                           "Replace the bracketed text with the actual price before sending.", placeholders))
    return out


def k2_overcommit(reply, u, kb, R):
    spans = []
    for s, e, _ in find_terms(reply, R["K2_terms"]):
        a, b = sentence_at(reply, s)
        sent = reply[a:b]
        if has_term(sent, R["deferral"]) or has_term(sent, R["negation"]):
            continue
        spans.append((s, e))
    if not spans:
        return []
    return [finding("K2", "red", "超出权限的承诺",
                    f"「{words_of(reply, spans)}」需要经理审批（kb/policy.json 的 needs_manager_approval），业务员不能直接答应。",
                    "改成：独家代理需经理审批，先了解买家的销售能力和年度计划。",
                    "Commitment beyond the salesperson's authority",
                    f"\"{words_en(reply, spans)}\" needs manager approval (needs_manager_approval in kb/policy.json); "
                    "the salesperson cannot agree to it directly.",
                    "Change it to: exclusive distribution requires manager approval; first learn about the buyer's "
                    "sales capacity and annual plan.", spans)]


def k3_specs(reply, u, kb, R):
    """回复里每个「x ml」挂到同一行里它前面最近的型号上，再和产品库比。"""
    mentions = kb.product_mentions(reply)
    unknown, contested = [], []
    for m in VOLUME_RE.finditer(reply):
        line_start = reply.rfind("\n", 0, m.start()) + 1
        owner = [pid for s, e, pid in mentions if line_start <= s < m.start()]
        if not owner:
            continue
        pid = owner[-1]
        val = float(m.group(1).replace(",", "."))
        sets, ranges = kb.volume_sources(pid)
        if not sets and not ranges:
            continue
        in_all = all(val in s for s in sets) if sets else False
        in_any = any(val in s for s in sets) or any(lo <= val <= hi for lo, hi in ranges)
        name = kb.products[pid]["name"]
        if not in_any:
            unknown.append((m.start(), m.end(), name))
            continue
        if in_all or kb.products[pid]["volumes"].get("st") != "conflict":
            continue
        line_end = reply.find("\n", m.end())
        rest = reply[m.start():line_end if line_end >= 0 else len(reply)]
        if has_term(rest, R["pending"]):
            continue
        contested.append((m.start(), m.end(), name))
    def listed(items, sep):
        return sep.join(f"{n} {reply[s:e]}" for s, e, n in items)

    out = []
    if unknown:
        out.append(finding("K3", "yellow", "规格不在产品库里",
                           listed(unknown, "、") + " 在三份资料里都没有。",
                           "按产品库改成现有规格。",
                           "Size not in the product knowledge base",
                           listed(unknown, ", ") + " does not appear in any of the three sources.",
                           "Change it to a size listed in the knowledge base.", [(s, e) for s, e, _ in unknown]))
    if contested:
        out.append(finding("K3", "yellow", "规格在资料里有矛盾",
                           listed(contested, "、") + " 只出现在部分资料里（见 conflicts.md D01、D05）。",
                           "向朋友确认后再报这个规格，或先标「待确认」。",
                           "Size conflicts between sources",
                           listed(contested, ", ") + " appears in only some of the sources (see conflicts.md D01, D05).",
                           "Confirm with the factory contact before quoting this size, or mark it \"to be confirmed\".",
                           [(s, e) for s, e, _ in contested]))
    return out


CHECKS = [c1_body, c2_registration, c3_individual, c4_us, c5_absolute, c6_unsourced,
          p1_superlative, p2_competitor, k1_quote, k2_overcommit, k3_specs]


def check(reply, understanding, kb, inquiry=""):
    """对一段回复跑全部规则。返回 (findings, level)，level 是 red / yellow / green。"""
    u = dict(understanding, _inquiry=inquiry)
    out = []
    for fn in CHECKS:
        out.extend(fn(reply, u, kb, kb.rules))
    out.sort(key=lambda f: (ORDER[f["level"]], f["rule"]))
    level = out[0]["level"] if out else "green"
    return out, level
