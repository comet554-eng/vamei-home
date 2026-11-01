"""一轮「理解 → 知识库调用 → 生成 → 校验」。每一步都记进 trace，页面上能看到数据怎么流动、
哪一步用了模型、出错时怎么退回。"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import rules
import templates
from kb import FILLER_IDS, find_terms, has_term
from llm import LLMError

LANGS = {"en": "English", "es": "Spanish", "zh": "Chinese", "pt": "Portuguese", "ru": "Russian"}
REPLY_LANGS = ("en", "es")  # 校验词表只覆盖英语和西语
INTENTS = ["price", "moq", "certificates", "registration", "samples", "exclusivity", "shipping", "indication"]
BUYER_TYPES = ["distributor", "clinic", "individual", "unknown"]
CHANNELS = {
    "alibaba": "Alibaba.com RFQ/chat reply: concise, under 180 words, short bullet list of specs, "
               "end with one question that moves the deal forward.",
    "email": "Formal B2B email: first line 'Subject: ...', then greeting and structured paragraphs, under 300 words.",
}
FIELD_LABELS = {"indication": "适应症", "areas": "适用部位", "volumes": "规格", "needle": "针头",
                "duration": "维持时间", "particle_size": "颗粒大小", "intended_use": "用途",
                "concentration": "浓度", "shelf_life": "有效期"}
FIELD_LABELS_EN = {"indication": "Indication", "areas": "Treatment areas", "volumes": "Sizes", "needle": "Needle",
                   "duration": "Duration", "particle_size": "Particle size", "intended_use": "Intended use",
                   "concentration": "Concentration", "shelf_life": "Shelf life"}
STEPS_EN = {"理解": "Understand", "知识库调用": "Knowledge base", "生成": "Generate", "校验": "Check"}
NO_SUMMARY_EN = "(Identified by keyword rules; no summary)"
REUSE_EN = "Reused the previous round's understanding"

UNDERSTAND_SYS = """You analyse B2B inquiries received by a Chinese manufacturer of hyaluronic acid dermal fillers.
Return ONLY a JSON object with these keys:
- "language": ISO 639-1 code of the inquiry language
- "country": ISO 3166-1 alpha-2 code of the buyer's country, or null if not stated
- "buyer_type": one of "distributor", "clinic", "individual", "unknown"
- "intents": subset of ["price","moq","certificates","registration","samples","exclusivity","shipping","indication"]
- "products": ids from CATALOG the buyer asks about (map described uses to products); [] if unclear
- "asked_uses": uses or body areas the buyer mentions, in English
- "quantity": quantity mentioned, or null
- "summary_zh": one-sentence summary in Simplified Chinese for the salesperson
- "summary_en": the same summary in English"""

GENERATE_SYS = """You are the export sales assistant of Zhejiang Jingjia Medical (brand HAFILLER).
Write a reply to the buyer, plus a faithful Simplified Chinese translation for the salesperson.
Rules:
1. Reply language: {lang}. Channel style: {style}
2. State only facts found in KB_CONTEXT, MARKET and POLICY. Never invent clinical data, certificates, prices or contact details.
3. A field whose "st" is "conflict", "suspect" or "image" is not confirmed: leave it out or say it is to be confirmed.
4. KB has no prices: write the placeholder [PRICE] (Spanish: [PRECIO]) unless the salesperson gives a price.
5. If the buyer asks about price, include incoterm, currency, MOQ, payment terms and quote validity from POLICY.
6. MARKET status "unknown": say registration with the regulator is to be confirmed; never promise customs clearance or legal sale.
   MARKET status "not_registered": say the product is not approved by that regulator and cannot be supplied to that market for now.
7. Exclusive distribution, price protection or registration guarantees need manager approval: say so instead of agreeing.
8. If the buyer is an individual or wants to self-inject, decline politely: we only supply licensed distributors and clinics.
   Breast, buttock or other body augmentation is never offered: say our fillers are not used for it (do not write "to be confirmed").
9. End with the signature from POLICY in the reply language.
Return ONLY a JSON object: {{"reply": "...", "reply_zh": "..."}}"""


def _step(name, mode, t0, note, note_en, error=None):
    """note_en 必填，页面切到英文时用；error 是原始报错，不翻译。"""
    return {"step": name, "step_en": STEPS_EN[name], "mode": mode, "ms": round((time.perf_counter() - t0) * 1000),
            "note": note, "note_en": note_en, "error": error}


def _note(step, zh, en):
    """给已有步骤的说明追加一句，中英各一份。"""
    step["note"] += zh
    step["note_en"] += en


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def heuristic_understanding(kb, text):
    """关键词规则识别。没配置模型、模型出错时用它；模型结果也拿它来补漏。"""
    H = kb.rules["heuristics"]
    if re.search(r"[一-鿿]", text):
        lang = "zh"
    elif re.search(r"[Ѐ-ӿ]", text):
        lang = "ru"
    else:
        es, pt = len(find_terms(text, H["lang_es"])), len(find_terms(text, H["lang_pt"]))
        lang = "pt" if pt > es else ("es" if es >= 2 else "en")
    if has_term(text, kb.rules["C3_inquiry"]):
        buyer = "individual"
    elif has_term(text, H["buyer_distributor"]):
        buyer = "distributor"
    elif has_term(text, H["buyer_clinic"]):
        buyer = "clinic"
    else:
        buyer = "unknown"
    return {
        "language": lang,
        "country": kb.detect_country(text),
        "buyer_type": buyer,
        "intents": sorted(k for k, terms in H["intents"].items() if has_term(text, terms)),
        "products": list(dict.fromkeys(pid for _, _, pid in kb.product_mentions(text))),
        "asked_uses": list(dict.fromkeys(t.lower() for _, _, t in find_terms(text, kb.rules["C1_body"]))),
        "quantity": None,
        "summary_zh": "（关键词规则识别，没有摘要）",
        "summary_en": NO_SUMMARY_EN,
    }


def normalize(raw, base, kb):
    """校正模型或页面传来的理解结果：枚举值不对就用规则结果，意图、型号取两者并集。"""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(base)
    lang = str(raw.get("language") or "").lower()[:2]
    if lang in LANGS:
        out["language"] = lang
    country = str(raw.get("country") or "").upper()
    if re.fullmatch(r"[A-Z]{2}", country):
        out["country"] = country
    if raw.get("buyer_type") in BUYER_TYPES and raw["buyer_type"] != "unknown":
        out["buyer_type"] = raw["buyer_type"]
    if base.get("buyer_type") == "individual":
        out["buyer_type"] = "individual"  # 规则命中「自用」时不让模型改回去
    intents = [i for i in raw.get("intents") or [] if i in INTENTS]
    out["intents"] = sorted(set(base["intents"]) | set(intents))
    prods = [p for p in raw.get("products") or [] if p in kb.products]
    out["products"] = list(dict.fromkeys(base["products"] + prods))
    uses = [str(x)[:60] for x in raw.get("asked_uses") or [] if isinstance(x, str)]
    out["asked_uses"] = list(dict.fromkeys(base["asked_uses"] + uses))[:8]
    if isinstance(raw.get("quantity"), (str, int, float)):
        out["quantity"] = str(raw["quantity"])[:60]
    if isinstance(raw.get("summary_zh"), str) and raw["summary_zh"].strip():
        out["summary_zh"] = raw["summary_zh"].strip()[:200]
    en = raw.get("summary_en")
    if isinstance(en, str) and en.strip() and not re.search(r"[一-鿿]", en):  # 模型偶尔填成中文，就不用
        out["summary_en"] = en.strip()[:300]
    if raw.get("reply_lang") in REPLY_LANGS:
        out["reply_lang"] = raw["reply_lang"]
    return out


def catalog(kb):
    """给理解步骤用的型号清单。眼科产品没有 indication，用 intended_use。"""
    out = []
    for p in kb.products.values():
        f = p.get("indication") or p.get("intended_use") or {"v": ""}
        out.append({"id": p["id"], "name": p["name"], "indication": f["v"],
                    "also_described_as": [a["v"] for a in f.get("alt", [])]})
    return out


def understand(kb, llm, inquiry):
    t0 = time.perf_counter()
    base = heuristic_understanding(kb, inquiry)
    if not llm.enabled:
        return base, _step("理解", "rules", t0, "未配置模型，用关键词规则识别",
                           "No model configured; identified by keyword rules")
    try:
        raw = llm.chat_json(UNDERSTAND_SYS, f"CATALOG:\n{_j(catalog(kb))}\n\nINQUIRY:\n{inquiry}", max_tokens=600)
        return normalize(raw, base, kb), _step("理解", "llm", t0, f"{llm.model} 识别，规则结果补漏",
                                               f"Identified by {llm.model}; keyword rules fill the gaps")
    except LLMError as e:
        return base, _step("理解", "rules", t0, "模型调用失败，退回关键词规则",
                           "Model call failed; fell back to keyword rules", str(e))


def _field(f):
    out = {"v": f["v"], "st": f["st"]}
    if f.get("alt"):
        out["alt"] = [a["v"] for a in f["alt"]]
    return out


def retrieve(kb, u):
    """按识别出的型号和国家取知识库片段。返回给模型的上下文，以及给页面看的引用清单。"""
    t0 = time.perf_counter()
    pids = [p for p in u.get("products", []) if p in kb.products] or FILLER_IDS
    items, refs = [], []
    for pid in pids:
        p = kb.products[pid]
        item = {"id": pid, "name": p["name"], "type": p["type"]}
        for key, label in FIELD_LABELS.items():
            if key in p:
                item[key] = _field(p[key])
                v = p[key]["v"]
                refs.append({"product": p["name"], "field": label, "field_en": FIELD_LABELS_EN[key],
                             "value": v if isinstance(v, str) else " / ".join(map(str, v)),
                             "st": p[key]["st"], "d": p[key].get("d"), "src": p[key].get("src", [])})
        items.append(item)
    common = kb.filler_common
    ctx = {
        "company": {"name": kb.company["name"]["v"], "founded": kb.company["founded"]["v"],
                    "milestones": kb.company["timeline"]["v"], "contacts": "unconfirmed, do not quote"},
        "filler_common": {"generic_name": common["generic_name"]["v"], "concentration": common["concentration"]["v"],
                          "technology": common["technology"]["v"]},
        "products": items,
    }
    code = u.get("country")
    market = dict(kb.markets[code], code=code) if code in kb.markets else (
        {"code": code, "status": "unknown", "note": "not in KB"} if code else None)
    if market:
        market.pop("aliases", None)
    policy = {k: v for k, v in kb.policy.items() if k != "meta"}
    flagged = sum(1 for r in refs if r["st"] in ("conflict", "suspect"))
    note = f"取 {len(items)} 个型号、{len(refs)} 个字段，其中 {flagged} 个有矛盾或可疑"
    note += f"；市场 {code}：{market['status']}" if market else "；未识别国家"
    note_en = (f"Retrieved {len(items)} product{'s' * (len(items) != 1)} and {len(refs)} fields, "
               f"{flagged} conflicting or suspect")
    note_en += f"; market {code}: {market['status']}" if market else "; country not identified"
    return {"kb": ctx, "market": market, "policy": policy, "refs": refs}, _step("知识库调用", "kb", t0, note, note_en)


def reply_lang(u):
    if u.get("reply_lang") in REPLY_LANGS:
        return u["reply_lang"]
    return u["language"] if u.get("language") in REPLY_LANGS else "en"


def generate(kb, llm, u, ctx, channel, inquiry, previous=None, instruction=""):
    t0 = time.perf_counter()
    lang = reply_lang(u)
    if llm.enabled:
        system = GENERATE_SYS.format(lang=LANGS[lang], style=CHANNELS[channel])
        parts = [f"INQUIRY:\n{inquiry}", f"UNDERSTANDING:\n{_j(u)}", f"KB_CONTEXT:\n{_j(ctx['kb'])}",
                 f"MARKET:\n{_j(ctx['market'])}", f"POLICY:\n{_j(ctx['policy'])}"]
        if previous:
            parts += [f"PREVIOUS_REPLY:\n{previous}",
                      f"SALESPERSON_INSTRUCTION (Chinese):\n{instruction or '按校验结果修改'}",
                      "TASK: revise PREVIOUS_REPLY following the instruction; keep everything else unchanged."]
        try:
            out = llm.chat_json(system, "\n\n".join(parts), max_tokens=2000)
            reply = str(out.get("reply") or "").strip()
            if reply:
                return reply, str(out.get("reply_zh") or "").strip(), _step(
                    "生成", "llm", t0, f"{llm.model} 生成{'修改稿' if previous else '初稿'}（{LANGS[lang]}）",
                    f"{llm.model} wrote the {'revision' if previous else 'first draft'} ({LANGS[lang]})")
            error = "模型返回的 reply 为空"
        except LLMError as e:
            error = str(e)
        note, note_en = "模型调用失败，退回离线模板", "Model call failed; fell back to the offline template"
    else:
        error = None
        note, note_en = "未配置模型，使用离线模板", "No model configured; used the offline template"
    if previous:
        note += "；模板不理解修改指令，请直接改回复再点「重新校验」"
        note_en += "; the template cannot follow revision instructions, so edit the reply directly and click \"Re-check\""
    reply = templates.render(kb, u, lang, channel)
    reply_zh = templates.render(kb, u, "zh", channel)
    return reply, reply_zh, _step("生成", "template", t0, note, note_en, error)


def check_step(kb, reply, u, inquiry):
    t0 = time.perf_counter()
    findings, level = rules.check(reply, u, kb, inquiry)
    reds = sum(f["level"] == "red" for f in findings)
    note = f"跑 {len(rules.CHECKS)} 条规则：红 {reds}，黄 {len(findings) - reds}"
    note_en = f"Ran {len(rules.CHECKS)} rules: {reds} red, {len(findings) - reds} yellow"
    return findings, level, _step("校验", "rules", t0, note, note_en)


# 理解一步放到后台线程，和生成同时跑。模型调用都是等网络，线程够用；32 足够几个人同时演示
_POOL = ThreadPoolExecutor(max_workers=32, thread_name_prefix="understand")
PLAN_KEYS = ("country", "buyer_type", "reply_lang", "products")


def _with_lang(u, lang_choice):
    if lang_choice in REPLY_LANGS:
        u["reply_lang"] = lang_choice
    u["reply_lang"] = reply_lang(u)
    return u


def _plan(u):
    """决定回复怎么写的字段：国家、买家类型、回复语言、型号。意图不算，生成时模型能看到询盘原文。"""
    return tuple(tuple(sorted(u.get(k) or [])) if k == "products" else u.get(k) for k in PLAN_KEYS)


def _first_round_parallel(kb, llm, inquiry, channel, lang_choice):
    """第一轮：模型理解在后台跑，同时用关键词规则的预判直接生成。理解结果出来后，
    如果国家、买家类型、语言、型号和预判一样，预判稿就是正式稿，省掉理解的时间；不一样就按模型理解重写。"""
    job = _POOL.submit(understand, kb, llm, inquiry)
    guess = _with_lang(heuristic_understanding(kb, inquiry), lang_choice)
    ctx, s_kb = retrieve(kb, guess)
    reply, reply_zh, s_gen = generate(kb, llm, guess, ctx, channel, inquiry)
    u, s_u = job.result()
    u = _with_lang(u, lang_choice)
    _note(s_u, "（与生成并行）", " (in parallel with Generate)")
    if _plan(u) == _plan(guess):
        _note(s_gen, "；用关键词预判同时起草，模型理解一致，直接采用",
              "; drafted in parallel from the keyword guess; the model's understanding matched, so the draft was kept")
        return u, ctx, reply, reply_zh, [s_u, s_kb, s_gen]
    diff = [k for k, a, b in zip(PLAN_KEYS, _plan(u), _plan(guess)) if a != b]
    wasted = s_gen["ms"]
    ctx, s_kb = retrieve(kb, u)
    reply, reply_zh, s_gen = generate(kb, llm, u, ctx, channel, inquiry)
    _note(s_gen, f"；模型理解和预判不同（{'、'.join(diff)}），预判稿作废（白跑 {wasted} ms）后重写",
          f"; the model's understanding differed from the guess ({', '.join(diff)}), so the guess draft was "
          f"discarded ({wasted} ms wasted) and rewritten")
    return u, ctx, reply, reply_zh, [s_u, s_kb, s_gen]


def run_round(kb, llm, inquiry, channel="alibaba", prev=None, instruction="", lang_choice="auto"):
    """prev 是上一轮的 {understanding, reply}；没有就是第一轮。"""
    t_round = time.perf_counter()
    channel = channel if channel in CHANNELS else "alibaba"
    previous = (prev or {}).get("reply") or None
    if prev and isinstance(prev.get("understanding"), dict):
        t0 = time.perf_counter()
        u = _with_lang(normalize(prev["understanding"], heuristic_understanding(kb, inquiry), kb), lang_choice)
        trace = [_step("理解", "reuse", t0, "沿用上一轮的理解结果", REUSE_EN)]
        ctx, s = retrieve(kb, u)
        trace.append(s)
        reply, reply_zh, s = generate(kb, llm, u, ctx, channel, inquiry, previous, instruction)
        trace.append(s)
    elif llm.enabled:
        u, ctx, reply, reply_zh, trace = _first_round_parallel(kb, llm, inquiry, channel, lang_choice)
    else:
        u, s = understand(kb, llm, inquiry)
        u = _with_lang(u, lang_choice)
        trace = [s]
        ctx, s = retrieve(kb, u)
        trace.append(s)
        reply, reply_zh, s = generate(kb, llm, u, ctx, channel, inquiry)
        trace.append(s)
    findings, level, s = check_step(kb, reply, u, inquiry)
    trace.append(s)
    return {"kind": "revise" if previous else "first", "instruction": instruction, "understanding": u,
            "refs": ctx["refs"], "market": ctx["market"], "reply": reply, "reply_zh": reply_zh,
            "findings": findings, "level": level, "trace": trace,
            "wall_ms": round((time.perf_counter() - t_round) * 1000)}


def check_only(kb, inquiry, understanding, reply):
    """业务员手改回复后重新校验，不调用模型。"""
    t0 = time.perf_counter()
    u = normalize(understanding, heuristic_understanding(kb, inquiry), kb)
    trace = [_step("理解", "reuse", t0, "沿用上一轮的理解结果", REUSE_EN)]
    ctx, s = retrieve(kb, u)
    trace.append(s)
    trace.append(_step("生成", "manual", time.perf_counter(), "业务员手动修改，未调用模型",
                       "Edited by the salesperson; no model call"))
    findings, level, s = check_step(kb, reply, u, inquiry)
    trace.append(s)
    return {"kind": "manual", "instruction": "", "understanding": u, "refs": ctx["refs"], "market": ctx["market"],
            "reply": reply, "reply_zh": "", "findings": findings, "level": level, "trace": trace}
