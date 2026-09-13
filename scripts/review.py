#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按分类打印 repos.json 全量清单，用于人工校对。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data = json.loads((ROOT / "data" / "repos.json").read_text(encoding="utf-8"))
repos = data["repos"]
cat_filter = sys.argv[1] if len(sys.argv) > 1 else None

order, buckets = [], {}
for r in repos:
    c = r["category"]
    if c not in buckets:
        order.append(c)
        buckets[c] = []
    buckets[c].append(r)

for c in order:
    if cat_filter and cat_filter != c:
        continue
    print(f"\n########## {c} ({len(buckets[c])}) ##########")
    for r in buckets[c]:
        src = {"star": "⭐", "hot": "🔥"}.get(r.get("source"), "?")
        print(f"  {src} {r['full_name']} | ★{r.get('stars', 0)} | {(r.get('description') or '')[:70]}")
