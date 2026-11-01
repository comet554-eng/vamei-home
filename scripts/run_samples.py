"""用当前 .env 里的模型把 samples/inquiries.json 全部跑一遍：每条示例跑初稿和一轮修改。
各示例之间并行，示例内部按轮次顺序。结果写到 runs/ 下。
运行：python scripts/run_samples.py [--workers N]"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import pipeline  # noqa: E402
from kb import KB  # noqa: E402
from llm import LLM  # noqa: E402


def fix_instruction(findings):
    items = [f"- {f['rule']} {f['title']}：{f['suggestion']}" for f in findings]
    return "按校验意见修改：\n" + "\n".join(items) if items else "语气更正式一点，其余不变"


def run_one(kb, llm, s):
    t0 = time.perf_counter()
    r1 = pipeline.run_round(kb, llm, s["inquiry"], s["channel"])
    instruction = fix_instruction(r1["findings"])
    r2 = pipeline.run_round(kb, llm, s["inquiry"], s["channel"],
                            {"understanding": r1["understanding"], "reply": r1["reply"]}, instruction)
    risky = pipeline.check_only(kb, s["inquiry"], r1["understanding"], s["risky_edit"])
    return {"id": s["id"], "seconds": round(time.perf_counter() - t0, 1),
            "rounds": [r1, r2], "risky_level": risky["level"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=0, help="并发数，默认等于示例条数")
    args = ap.parse_args()
    kb, llm = KB(), LLM()
    samples = json.loads((ROOT / "samples" / "inquiries.json").read_text(encoding="utf-8"))
    print("模型:", llm.info())
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers or len(samples)) as pool:
        results = list(pool.map(lambda s: run_one(kb, llm, s), samples))
    wall = round(time.perf_counter() - t0, 1)

    for r in results:
        print(f"\n===== {r['id']}（{r['seconds']} s）")
        for i, rd in enumerate(r["rounds"], 1):
            steps = "；".join(f"{t['step']}:{t['mode']} {t['ms']}ms" + (f" 错误:{t['error'][:80]}" if t["error"] else "")
                             for t in rd["trace"])
            print(f"-- 第 {i} 轮 {rd['level']} | {steps}")
            for f in rd["findings"]:
                print(f"   {f['rule']} {f['level']} {f['title']}")
            print(rd["reply"])
        print(f"-- 风险话术校验: {r['risky_level']}")
    serial = round(sum(r["seconds"] for r in results), 1)
    print(f"\n总用时 {wall} s（各示例串行合计 {serial} s）")

    out = ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"llm": llm.info(), "wall_seconds": wall, "results": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("结果已保存:", out)


if __name__ == "__main__":
    main()
