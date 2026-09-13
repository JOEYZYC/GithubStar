#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/repos.json 生成 README.md 与 categories/*.md。

用法：python3 scripts/build_index.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CAT_DIR = ROOT / "categories"

BADGE = {"star": "⭐ 已 star", "hot": "🔥 热点推荐"}


def fmt_stars(n: int | None) -> str:
    return f"★{n:,}" if n else "★—"


def load() -> tuple[list[dict], str]:
    data = json.loads((DATA / "repos.json").read_text(encoding="utf-8"))
    return data["repos"], data.get("updated_at", date.today().isoformat())


def entry_md(r: dict) -> str:
    badge = BADGE.get(r.get("source"), "⭐ 已 star")
    if r.get("sources") and len(r["sources"]) > 1:
        badge = "⭐🔥 已 star + 热点推荐"
    meta = " · ".join(x for x in [fmt_stars(r.get("stars")), r.get("language") or "", badge] if x)
    lines = [f"#### [{r['full_name']}]({r['url']})", f"`{meta}`"]
    if r.get("description"):
        lines.append(r["description"].replace("\n", " ").strip())
    if r.get("note"):
        lines.append(f"> 📝 {r['note']}")
    if r.get("hot_dates"):
        lines.append(f"> 热点推荐于 {', '.join(r['hot_dates'])}")
    lines.append(f"> 收录日期：{r.get('added_at', '—')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    repos, updated = load()
    order: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for r in repos:
        c = r["category"]
        if c not in buckets:
            order.append(c)
            buckets[c] = []
        buckets[c].append(r)

    CAT_DIR.mkdir(exist_ok=True)
    # 分类页面
    files: dict[str, Path] = {}
    for i, c in enumerate(order, 1):
        slug = f"{i:02d}-{c.replace(' ', '')}"
        path = CAT_DIR / f"{slug}.md"
        body = [
            f"# {c}",
            "",
            f"> 共 {len(buckets[c])} 个项目 · 数据更新时间 {updated} · [返回总览](../README.md)",
            "",
            "---",
            "",
        ]
        for r in buckets[c]:
            body.append(entry_md(r))
            body.append("---")
            body.append("")
        path.write_text("\n".join(body), encoding="utf-8")
        files[c] = path

    # README
    total = len(repos)
    n_star = sum(1 for r in repos if r.get("source") == "star")
    n_hot = total - n_star
    readme = [
        "# GithubStar",
        "",
        "个人 GitHub 项目雷达 —— 把「已 star 的项目」和「每日热点检索推荐的项目」分类归档，便于检索与回顾。",
        "",
        f"- 数据更新时间：**{updated}**",
        f"- 收录总数：**{total}** 个仓库（⭐ 已 star {n_star} 个、🔥 热点推荐 {n_hot} 个）",
        "- 数据源：[`data/repos.json`](data/repos.json)（单一事实源）；每日热点推荐记录在 [`data/recommendations.jsonl`](data/recommendations.jsonl)",
        "- 维护方式：Hermes Agent 每日热点任务自动同步（GitHub search → 分类归档 → 提交推送）",
        "",
        "## 分类导航",
        "",
        "| 分类 | 数量 | 说明 |",
        "| --- | ---: | --- |",
    ]
    descs = {
        "飞控与无人机": "PX4 / ArduPilot / 飞控板卡 / 无人机导航与仿真",
        "嵌入式与单片机": "RTOS、MCU 生态、LVGL、MicroPython、调试与仿真工具",
        "硬件设计与 EDA": "KiCad / EDA / CAD / PCB / FPGA 设计流程",
        "无线通信与感知": "WiFi CSI、无线链路、IMU、GNSS 等感知与通信",
        "电磁仿真与超表面": "FDTD / CST / 超表面与电磁材料设计",
        "AI Agent 与 LLM 工具链": "编码 Agent、Skills、MCP、浏览器与自动化",
        "知识管理与笔记": "Obsidian、知识图谱、RAG、教程与书籍",
        "AI 模型与视觉": "语音、视觉、模型训练 / 压缩 / 推理",
        "开发工具与系统资源": "系统工具、字体、容器、资源清单等",
        "待归类": "尚未归入上述分类的项目",
    }
    for c in order:
        rel = files[c].relative_to(ROOT).as_posix()
        readme.append(f"| [{c}]({rel}) | {len(buckets[c])} | {descs.get(c, '')} |")
    readme += [
        "",
        "## 目录结构",
        "",
        "```",
        "GithubStar/",
        "├── README.md                  # 本文件（总览 + 分类导航）",
        "├── categories/                # 各分类明细页",
        "├── data/",
        "│   ├── repos.json             # 单一事实源：所有项目 + 分类 + 来源 + 收录日期",
        "│   ├── recommendations.jsonl  # 每日热点推荐流水（含日期）",
        "│   └── stars_raw.json         # gh api 抓取的 star 原始数据",
        "├── scripts/",
        "│   ├── sync.py                # 合并 star + 推荐，自动归类 → repos.json",
        "│   ├── import_recommendations.py  # 把某日推荐清单追加进 recommendations.jsonl",
        "│   ├── build_index.py         # repos.json → README.md + categories/*.md",
        "│   └── review.py              # 按分类打印清单，人工校对用",
        "└── CHANGELOG.md               # 同步记录",
        "```",
        "",
        "## 本地使用",
        "",
        "```bash",
        "# 1) 抓取最新 star 列表（需 gh 已登录）",
        "gh api --paginate \"user/starred?per_page=100\" \\",
        "  --jq '.[] | {full_name, description, language, topics, stars: .stargazers_count, pushed_at, archived, html_url, starred_at}' \\",
        "  > data/stars_raw.json",
        "",
        "# 2) 追加当日热点推荐后合并归类、生成页面",
        "python3 scripts/import_recommendations.py <当日推荐.json> <日期>",
        "python3 scripts/sync.py --report",
        "python3 scripts/build_index.py",
        "```",
        "",
        "## 标记说明",
        "",
        "- ⭐ 已 star：本人 GitHub 收藏的项目（新增 star 会在下次同步时自动并入）",
        "- 🔥 热点推荐：每日热点检索推送中推荐的项目，同日归档到本仓库",
        "- 每个条目记录收录日期；重复推荐只更新来源日期，不重复收录",
        "",
        "---",
        "",
        "*由 Hermes Agent 自动维护；分类规则见 [`scripts/sync.py`](scripts/sync.py)。*",
        "",
    ]
    (ROOT / "README.md").write_text("\n".join(readme), encoding="utf-8")
    print(f"生成 README.md（{total} 个项目 / {len(order)} 个分类）与 {len(order)} 个分类页")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
