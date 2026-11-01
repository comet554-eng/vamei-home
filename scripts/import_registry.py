"""把四国注册清单 xlsx 转成 kb/registry.json，供 /api/registry 和网站「注册清单」页使用。
中文全部取自 xlsx；英文取自 kb/registry_en.json，按编号合并。缺译文直接报错，不生成半成品。
运行：python scripts/import_registry.py [输出路径]   默认写 kb/registry.json；重跑结果一字不差。"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "kb" / "sources" / "医疗器械四国注册清单_工作初稿.xlsx"
EN = ROOT / "kb" / "registry_en.json"
OUT = ROOT / "kb" / "registry.json"

MARKET_CODE = {"共用": "ALL", "沙特": "SA", "巴西": "BR", "德国": "DE", "土耳其": "TR"}
DIMENSIONS = {"当地分类": "classification", "主要准入路径": "pathway", "本地主体": "local_entity",
              "重点材料/门槛": "key_documents", "上市前核查": "premarket_checks"}
# 状态和适用性用代码值存，界面按语言显示；xlsx 里只出现「待确认」「未开始」，其余是页面上可选的值
CODES = {
    "market": {"ALL": {"zh": "共用", "en": "Shared"}, "SA": {"zh": "沙特", "en": "Saudi Arabia"},
               "BR": {"zh": "巴西", "en": "Brazil"}, "DE": {"zh": "德国", "en": "Germany"},
               "TR": {"zh": "土耳其", "en": "Türkiye"}},
    "applicability": {"tbd": {"zh": "待确认", "en": "To be confirmed"}, "yes": {"zh": "适用", "en": "Applicable"},
                      "no": {"zh": "不适用", "en": "Not applicable"}},
    "status": {"todo": {"zh": "未开始", "en": "Not started"}, "doing": {"zh": "进行中", "en": "In progress"},
               "done": {"zh": "已完成", "en": "Done"}, "blocked": {"zh": "受阻", "en": "Blocked"}},
}


def fail(msg):
    raise SystemExit(f"导入失败：{msg}")


def rows(ws):
    """每行去掉首尾空白，空单元格为空串；整行为空的跳过。"""
    out = []
    for r in ws.iter_rows(values_only=True):
        cells = ["" if v is None else v.strip() if isinstance(v, str) else v for v in r]
        if any(c != "" for c in cells):
            out.append(cells)
    return out


def text(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.strftime("%Y-%m-%d")
    return "" if v is None else str(v).strip()


def pair(zh, en, where):
    if not en or not str(en).strip():
        fail(f"{where} 缺英文译文（kb/registry_en.json）")
    return {"zh": zh, "en": en}


def header_at(table, first):
    for i, r in enumerate(table):
        if r and r[0] == first:
            return i
    fail(f"找不到以「{first}」开头的表头")


def starting(table, prefix):
    hits = [r[0] for r in table if isinstance(r[0], str) and r[0].startswith(prefix)]
    if len(hits) != 1:
        fail(f"以「{prefix}」开头的说明应正好 1 条，实际 {len(hits)} 条")
    return hits[0]


def expand_refs(s):
    """"SA1 / BR1"、"DE1-DE4" → 编号列表。"""
    out = []
    for part in re.split(r"\s*/\s*", s):
        m = re.fullmatch(r"([A-Z]+)(\d+)-\1(\d+)", part)
        if m:
            out += [f"{m[1]}{n}" for n in range(int(m[2]), int(m[3]) + 1)]
        elif re.fullmatch(r"[A-Z]+\d+", part):
            out.append(part)
        else:
            fail(f"看不懂的依据编号「{part}」")
    return out


def code_of(table, value, where):
    for code, label in CODES[table].items():
        if label["zh"] == value:
            return code
    fail(f"{where}：未知的{table}取值「{value}」")


def build(src=SRC):
    en = json.loads(EN.read_text(encoding="utf-8"))
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    names = wb.sheetnames
    if names[:3] != ["四国注册对照", "材料与任务", "官方核查入口"]:
        fail(f"工作表不是预期的三张：{names}")
    overview, tasks_ws, sources_ws = (rows(wb[n]) for n in names[:3])
    em = en["meta"]

    # 四国注册对照：标题、两条说明、对照表、末尾两条
    h = header_at(overview, "市场")
    dims = []
    for col in overview[h][1:]:
        if col not in DIMENSIONS:
            fail(f"对照表多了未知列「{col}」")
        dims.append(DIMENSIONS[col])
    markets = []
    for r in overview[h + 1:]:
        if r[0] not in MARKET_CODE or r[0] == "共用":
            continue
        code = MARKET_CODE[r[0]]
        e = en["markets"].get(code, {})
        m = {"code": code, "name_zh": r[0], "name_en": pair(r[0], e.get("name"), f"市场 {code}")["en"]}
        for key, value in zip(dims, r[1:]):
            m[key] = pair(text(value), e.get(key), f"市场 {code}.{key}")
        markets.append(m)
    if [m["code"] for m in markets] != ["SA", "BR", "DE", "TR"]:
        fail(f"对照表应为沙特、巴西、德国、土耳其四行，实际 {[m['code'] for m in markets]}")

    # 官方核查入口：说明一句 + 来源表
    sh = header_at(sources_ws, "编号")
    sources = []
    for r in sources_ws[sh + 1:]:
        sid, market, org, url, topic = (text(v) for v in r[:5])
        e = en["sources"].get(sid, {})
        code = MARKET_CODE.get(market.split("/")[0]) or fail(f"来源 {sid} 的市场「{market}」无法识别")
        if not url.startswith("https://"):
            fail(f"来源 {sid} 的链接不是 https：{url}")
        sources.append({"id": sid, "market": code, "market_label": pair(market, e.get("market"), f"来源 {sid}.market"),
                        "org": pair(org, e.get("org"), f"来源 {sid}.org"), "url": url,
                        "topic": pair(topic, e.get("topic"), f"来源 {sid}.topic")})
    source_ids = {s["id"] for s in sources}

    # 材料与任务：说明一句 + 任务表
    th = header_at(tasks_ws, "编号")
    cols = tasks_ws[th]
    expect = ["编号", "市场", "阶段", "材料/任务", "适用说明", "依据编号", "适用性", "责任人", "计划日期", "状态", "证据/文件位置"]
    if list(cols[:len(expect)]) != expect:
        fail(f"任务表表头和预期不一致：{cols}")
    tasks = []
    for r in tasks_ws[th + 1:]:
        tid = text(r[0])
        e = en["tasks"].get(tid, {})
        market = MARKET_CODE.get(text(r[1])) or fail(f"任务 {tid} 的市场「{r[1]}」无法识别")
        refs = expand_refs(text(r[5]))
        missing = [x for x in refs if x not in source_ids]
        if missing:
            fail(f"任务 {tid} 引用了来源表里没有的编号 {missing}")
        stage = text(r[2])
        tasks.append({"id": tid, "market": market,
                      "stage": pair(stage, en["stages"].get(stage), f"阶段「{stage}」"),
                      "task": pair(text(r[3]), e.get("task"), f"任务 {tid}.task"),
                      "note": pair(text(r[4]), e.get("note"), f"任务 {tid}.note"),
                      "refs": refs,
                      "applicability": code_of("applicability", text(r[6]), f"任务 {tid}"),
                      "owner": text(r[7]), "due": text(r[8]),
                      "status": code_of("status", text(r[9]), f"任务 {tid}"),
                      "evidence": text(r[10])})

    meta = {
        "source_file": Path(src).name,
        "title": pair(overview[0][0], em.get("title"), "标题"),
        "assumption": pair(starting(overview, "适用假设"), em.get("assumption"), "适用假设"),
        "disclaimer": pair(starting(overview, "工作初稿"), em.get("disclaimer"), "初稿声明"),
        "pending": pair(starting(overview, "待补充"), em.get("pending"), "待补充"),
        "no_fees": pair(starting(overview, "不预填"), em.get("no_fees"), "不预填费用周期"),
        "tasks_title": pair(tasks_ws[0][0], em.get("tasks_title"), "任务表标题"),
        "progress_note": pair(tasks_ws[1][0], em.get("progress_note"), "进度说明"),
        "sources_title": pair(sources_ws[0][0], em.get("sources_title"), "来源表标题"),
        "sources_note": pair(sources_ws[1][0], em.get("sources_note"), "来源表说明"),
    }
    dimensions = [dict(key=k, **pair(zh, en["dimensions"].get(k), f"维度 {k}"))
                  for zh, k in DIMENSIONS.items() if k in dims]
    return {"meta": meta, "codes": CODES, "dimensions": dimensions, "markets": markets,
            "tasks": tasks, "sources": sources}


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", nargs="?", default=str(OUT))
    ap.add_argument("--src", default=str(SRC))
    a = ap.parse_args()
    data = build(Path(a.src))
    Path(a.out).write_bytes(dump(data).encode("utf-8"))  # 写字节，Windows 上也是 \n 换行
    print(f"已生成 {a.out}：{len(data['markets'])} 国、{len(data['tasks'])} 项任务、{len(data['sources'])} 个来源")


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    main()
