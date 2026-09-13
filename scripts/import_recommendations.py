#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把某日整理好的推荐清单（JSON 数组）转成 data/recommendations.jsonl（追加去重）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "recommendations_raw.json"
DAY = sys.argv[2] if len(sys.argv) > 2 else None
OUT = ROOT / "data" / "recommendations.jsonl"

recs = json.loads(SRC.read_text(encoding="utf-8"))
seen = set()
if OUT.exists():
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            seen.add(json.loads(line)["url"].strip())

new = 0
with OUT.open("a", encoding="utf-8") as f:
    for r in recs:
        url = r["url"].strip()
        if url in seen:
            continue
        seen.add(url)
        f.write(json.dumps({
            "url": url,
            "stars": r.get("stars"),
            "desc": r.get("desc", ""),
            "date": DAY or r.get("date", ""),
        }, ensure_ascii=False) + "\n")
        new += 1
print(f"追加 {new} 条到 {OUT.relative_to(ROOT)}（总计去重后 {len(seen)} 条）")
