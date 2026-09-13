#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 CHANGELOG.md 顶部追加一条同步记录。

用法：python3 scripts/log_update.py "2026-09-14 新增热点推荐 8 条（含 2 条超表面相关）"
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "CHANGELOG.md"
msg = " ".join(sys.argv[1:]).strip() or "同步更新"
line = f"- {date.today().isoformat()}：{msg}\n"

HEADER = "# 同步记录\n\n本文件由每日热点任务自动追加，记录每次仓库同步的内容。\n\n"
if LOG.exists():
    text = LOG.read_text(encoding="utf-8")
    if not text.startswith("# "):
        text = HEADER + text
else:
    text = HEADER

lines = text.splitlines(keepends=True)
# 在头部说明之后插入新记录
idx = 4 if len(lines) > 4 else len(lines)
lines.insert(idx, line)
LOG.write_text("".join(lines), encoding="utf-8")
print(f"已追加记录：{line.strip()}")
