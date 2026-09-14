# GithubStar

个人 GitHub 项目雷达 —— 把「已 star 的项目」和「每日热点检索推荐的项目」分类归档，便于检索与回顾。

- 数据更新时间：**2026-09-15**
- 收录总数：**283** 个仓库（⭐ 已 star 142 个、🔥 热点推荐 141 个）
- 数据源：[`data/repos.json`](data/repos.json)（单一事实源）；每日热点推荐记录在 [`data/recommendations.jsonl`](data/recommendations.jsonl)
- 维护方式：Hermes Agent 每日热点任务自动同步（GitHub search → 分类归档 → 提交推送）

## 分类导航

| 分类 | 数量 | 说明 |
| --- | ---: | --- |
| [飞控与无人机](categories/01-飞控与无人机.md) | 29 | PX4 / ArduPilot / 飞控板卡 / 无人机导航与仿真 |
| [电磁仿真与超表面](categories/02-电磁仿真与超表面.md) | 30 | FDTD / CST / 超表面与电磁材料设计 |
| [嵌入式与单片机](categories/03-嵌入式与单片机.md) | 67 | RTOS、MCU 生态、LVGL、MicroPython、调试与仿真工具 |
| [硬件设计与 EDA](categories/04-硬件设计与EDA.md) | 24 | KiCad / EDA / CAD / PCB / FPGA 设计流程 |
| [无线通信与感知](categories/05-无线通信与感知.md) | 22 | WiFi CSI、无线链路、IMU、GNSS 等感知与通信 |
| [AI Agent 与 LLM 工具链](categories/06-AIAgent与LLM工具链.md) | 50 | 编码 Agent、Skills、MCP、浏览器与自动化 |
| [知识管理与笔记](categories/07-知识管理与笔记.md) | 16 | Obsidian、知识图谱、RAG、教程与书籍 |
| [AI 模型与视觉](categories/08-AI模型与视觉.md) | 17 | 语音、视觉、模型训练 / 压缩 / 推理 |
| [开发工具与系统资源](categories/09-开发工具与系统资源.md) | 28 | 系统工具、字体、容器、资源清单等 |

## 目录结构

```
GithubStar/
├── README.md                  # 本文件（总览 + 分类导航）
├── categories/                # 各分类明细页
├── data/
│   ├── repos.json             # 单一事实源：所有项目 + 分类 + 来源 + 收录日期
│   ├── recommendations.jsonl  # 每日热点推荐流水（含日期）
│   └── stars_raw.json         # gh api 抓取的 star 原始数据
├── scripts/
│   ├── sync.py                # 合并 star + 推荐，自动归类 → repos.json
│   ├── import_recommendations.py  # 把某日推荐清单追加进 recommendations.jsonl
│   ├── build_index.py         # repos.json → README.md + categories/*.md
│   └── review.py              # 按分类打印清单，人工校对用
└── CHANGELOG.md               # 同步记录
```

## 本地使用

```bash
# 1) 抓取最新 star 列表（需 gh 已登录）
gh api --paginate "user/starred?per_page=100" \
  --jq '.[] | {full_name, description, language, topics, stars: .stargazers_count, pushed_at, archived, html_url, starred_at}' \
  > data/stars_raw.json

# 2) 追加当日热点推荐后合并归类、生成页面
python3 scripts/import_recommendations.py <当日推荐.json> <日期>
python3 scripts/sync.py --report
python3 scripts/build_index.py
```

## 标记说明

- ⭐ 已 star：本人 GitHub 收藏的项目（新增 star 会在下次同步时自动并入）
- 🔥 热点推荐：每日热点检索推送中推荐的项目，同日归档到本仓库
- 每个条目记录收录日期；重复推荐只更新来源日期，不重复收录

---

*由 Hermes Agent 自动维护；分类规则见 [`scripts/sync.py`](scripts/sync.py)。*
