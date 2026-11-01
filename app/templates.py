"""离线模板：没配置模型或模型调用失败时用。只用产品库里各来源一致的事实，所以默认是合规的。"""
from kb import has_term

TEXT = {
    "en": {
        "hi": "Dear {buyer},",
        "thanks": "Thank you for your inquiry about HAFILLER {products}. Please find the key specifications below:",
        "spec": "- {name}: {vols}; needle {needle}; expected duration {dur}; HA {conc}",
        "tbc": "other sizes to be confirmed",
        "months": "months", "or": "or",
        "quote": "Price: [PRICE] {cur} per box, {inc}. MOQ: {moq}. Payment: {pay}. This quote is valid for {days} days.",
        "cert": "Our company obtained the EU CE certificate in 2008 and holds BSI MDSAP certification.",
        "reg": "Registration with {reg} is to be confirmed; we will check with our regulatory team.",
        "samples": "{samples}.",
        "excl": "Exclusive distribution is subject to manager approval. Could you share your sales channels and annual volume plan?",
        "body": "Please note: our dermal fillers are for facial use; they are not used for breast or buttock augmentation.",
        "us": "Thank you for your interest. Our products are not FDA-approved, so we cannot supply the US market at this time. We would be glad to help if you have needs in other markets.",
        "indiv": "Thank you for your message. We only supply licensed distributors and medical clinics, and our fillers must be injected by a qualified medical professional, so we cannot sell for personal use.",
        "close": "Could you tell us your company name and whether you hold a medical device import license? We will then prepare a formal quotation.",
        "bye": "Best regards,",
    },
    "es": {
        "hi": "Estimado/a {buyer}:",
        "thanks": "Gracias por su consulta sobre HAFILLER {products}. Estas son las especificaciones principales:",
        "spec": "- {name}: {vols}; aguja {needle}; duración esperada {dur}; AH {conc}",
        "tbc": "otras presentaciones por confirmar",
        "months": "meses", "or": "o",
        "quote": "Precio: [PRECIO] {cur} por caja, {inc}. MOQ: {moq}. Pago: {pay}. Cotización válida por {days} días.",
        "cert": "Nuestra empresa obtuvo el certificado CE de la UE en 2008 y cuenta con la certificación MDSAP de BSI.",
        "reg": "El registro ante {reg} está por confirmar; lo verificaremos con nuestro equipo regulatorio.",
        "samples": "{samples}.",
        "excl": "La distribución exclusiva requiere aprobación de la gerencia. ¿Podría compartir sus canales de venta y su plan de volumen anual?",
        "body": "Tenga en cuenta: nuestros rellenos dérmicos son de uso facial; no se usan para aumento de glúteos ni de busto.",
        "us": "Gracias por su interés. Nuestros productos no cuentan con aprobación de la FDA, por lo que no podemos suministrar al mercado de EE.UU. por ahora.",
        "indiv": "Gracias por su mensaje. Solo vendemos a distribuidores y clínicas con licencia, y la inyección debe realizarla un profesional médico, por lo que no podemos vender para uso personal.",
        "close": "¿Podría indicarnos el nombre de su empresa y si cuenta con licencia de importación de dispositivos médicos? Así prepararemos una cotización formal.",
        "bye": "Saludos cordiales,",
    },
    "zh": {
        "hi": "{buyer}，您好：",
        "thanks": "感谢您咨询 HAFILLER {products}。主要规格如下：",
        "spec": "- {name}：{vols}；针头 {needle}；预期维持 {dur}；浓度 {conc}",
        "tbc": "其他规格待确认",
        "months": "个月", "or": "或",
        "quote": "价格：[价格] {cur}/盒，{inc}。MOQ：{moq}。付款方式：{pay}。报价有效期 {days} 天。",
        "cert": "公司 2008 年获得欧盟 CE 证书，并通过 BSI 的 MDSAP 认证。",
        "reg": "{reg} 注册情况待确认，我们会和注册部门核实。",
        "samples": "{samples}。",
        "excl": "独家代理需经理审批。能否介绍一下贵司的销售渠道和年度采购计划？",
        "body": "请注意：我们的填充剂用于面部，不用于隆胸或隆臀。",
        "us": "感谢关注。我们的产品未获 FDA 批准，目前不能供应美国市场。",
        "indiv": "感谢来信。我们只向有资质的经销商和医疗机构供货，产品必须由执业医生注射，不能卖给个人自用。",
        "close": "能否告知贵司名称，以及是否持有医疗器械进口资质？我们再出正式报价。",
        "bye": "此致",
    },
}

BUYER = {"en": "Customer", "es": "cliente", "zh": "客户"}


def _vols(kb, pid, T):
    """只报各来源都有的规格；有矛盾就加「其他规格待确认」。"""
    sets, _ = kb.volume_sources(pid)
    if not sets:
        return ""
    agreed = sorted(set.intersection(*sets))
    text = " / ".join(f"{v:.1f}ml" if v < 10 else f"{v:g}ml" for v in agreed)
    if len(sets) > 1 and set.union(*sets) != set(agreed):
        text += f" ({T['tbc']})"
    return text


SUBJECT = {"en": "Subject: HAFILLER dermal fillers – your inquiry",
           "es": "Asunto: Rellenos dérmicos HAFILLER – su consulta",
           "zh": "主题：HAFILLER 填充剂询价回复"}


def render(kb, u, lang, channel="alibaba"):
    T = TEXT.get(lang, TEXT["en"])
    L = lang if lang in TEXT else "en"
    P = kb.policy
    m = kb.markets.get(u.get("country") or "")
    intents = set(u.get("intents", []))
    lines = [SUBJECT[L], ""] if channel == "email" else []
    lines += [T["hi"].format(buyer=BUYER[L]), ""]
    sign = ["", T["bye"], P["signature"][L]]

    if u.get("buyer_type") == "individual":
        return "\n".join(lines + [T["indiv"]] + sign)
    if u.get("country") == "US":
        return "\n".join(lines + [T["us"]] + sign)

    pids = [p for p in u.get("products", []) if p in kb.products] or ["HF-FL", "HF-DERM", "HF-DD", "HF-DP", "HF-SS"]
    names = [kb.products[p]["name"].replace("HAFILLER ", "") for p in pids]
    lines.append(T["thanks"].format(products=" / ".join(names)))
    for pid in pids:
        p = kb.products[pid]
        if p["type"] != "filler":
            lines.append(f"- {p['name']}")
            continue
        dur = p["duration"]["v"].replace("months", T["months"])
        lines.append(T["spec"].format(name=p["name"], vols=_vols(kb, pid, T),
                                      needle=p["needle"]["v"].replace(" or ", f" {T['or']} "),
                                      dur=dur, conc=kb.filler_common["concentration"]["v"]))
    lines.append("")
    if intents & {"price", "moq"}:
        lines.append(T["quote"].format(cur=P["currency"], inc=P["incoterm"], moq=P["moq"][L],
                                       pay=P["payment"][L], days=P["quote_validity_days"]))
    if intents & {"certificates", "registration"}:
        lines.append(T["cert"])
    if m and m["status"] != "registered" and intents & {"certificates", "registration", "price"}:
        lines.append(T["reg"].format(reg=m["regulator"]))
    if "samples" in intents:
        lines.append(T["samples"].format(samples=P["samples"][L]))
    if "exclusivity" in intents:
        lines.append(T["excl"])
    if set(pids) & {"HF-DP", "HF-SS"} or has_term(" ".join(u.get("asked_uses", [])), kb.rules["C1_body"]):
        lines.append(T["body"])
    lines += ["", T["close"]]
    return "\n".join(lines + sign)
