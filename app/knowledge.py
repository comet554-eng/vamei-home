"""管理员导入的产品资料（工作台设置 → 产品资料导入）。
队友的 Next.js 版存在 Cloudflare D1；这里存成一个 JSON 文件，校验规则照搬队友的 db/product-knowledge.ts：
每次 1–200 条，名称 ≤120 字、资料 ≤8000 字、来源 ≤300 字，不收膝关节和眼科产品，名称不分大小写，同名更新，总数最多 200 款。"""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "product_knowledge.json"
MAX_ROWS = 200
OUT_OF_SCOPE = re.compile(r"hairont|膝关节|眼科|ophthalmo", re.IGNORECASE)


def validate(value):
    """返回清洗后的 [{name, content, source}]；不合格抛 ValueError，错误信息和队友版一致。"""
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ROWS:
        raise ValueError("每次请导入 1–200 条产品资料")
    names, rows = set(), []
    for i, item in enumerate(value, 1):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("content"), str) \
                or ("source" in item and item["source"] is not None and not isinstance(item["source"], str)):
            raise ValueError(f"第 {i} 行字段格式不正确")
        row = {"name": item["name"].strip(), "content": item["content"].strip(), "source": (item.get("source") or "").strip()}
        if not row["name"] or len(row["name"]) > 120 or not row["content"] or len(row["content"]) > 8000 or len(row["source"]) > 300:
            raise ValueError(f"第 {i} 行：名称需为 1–120 字，资料需为 1–8000 字，来源最多 300 字")
        if OUT_OF_SCOPE.search(row["name"]):
            raise ValueError(f"第 {i} 行产品不在当前客服范围内")
        key = row["name"].lower()
        if key in names:
            raise ValueError(f"第 {i} 行产品名称重复：{row['name']}")
        names.add(key)
        rows.append(row)
    return rows


class KnowledgeStore:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data.get("products", []) if isinstance(data, dict) else []

    def all(self):
        """按名称排序（不分大小写），和队友版 ORDER BY name COLLATE NOCASE 一样。"""
        with self._lock:
            rows = self._read()
        return sorted(({"name": r["name"], "content": r["content"], "source": r.get("source", "")} for r in rows),
                      key=lambda r: r["name"].lower())

    def save(self, rows):
        """同名（不分大小写）覆盖，其余保留。超过 200 款抛 ValueError，不写入。返回本次保存条数。"""
        with self._lock:
            current = {r["name"].lower(): r for r in self._read()}
            for r in rows:
                current[r["name"].lower()] = r
            if len(current) > MAX_ROWS:
                raise ValueError("数据库最多保存 200 款产品，请合并同名资料后重试")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".knowledge-", suffix=".json")
            try:  # 先写临时文件再替换，写到一半断电也不会留下坏文件
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"products": list(current.values())}, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        return len(rows)
