#!/usr/bin/env bash
# GithubStar 每日同步：抓 star → 合并归类 → 生成页面 → 记录 → 提交推送
#
# 用法：scripts/daily_sync.sh "本次同步说明"
# 建议在跑之前先把当日热点推荐追加进 data/recommendations.jsonl
# （用 scripts/import_recommendations.py <推荐.json> <日期>）。
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/bin:$PATH"
MSG="${1:-每日同步}"
GH() { env -u GH_TOKEN -u GITHUB_TOKEN gh "$@"; }

echo "== 1/5 抓取 star 列表 =="
if GH api --paginate "user/starred?per_page=100" \
    --jq '.[] | {full_name, description, language, topics, stars: .stargazers_count, pushed_at, archived, html_url, starred_at}' \
    > data/stars_raw.json.tmp; then
    mv data/stars_raw.json.tmp data/stars_raw.json
    echo "   star 抓取完成：$(wc -l < data/stars_raw.json) 个"
else
    echo "   ⚠️ star 抓取失败，沿用上次数据" >&2
fi

echo "== 2/5 合并归类 =="
python3 scripts/sync.py || exit 1

echo "== 3/5 生成页面 =="
python3 scripts/build_index.py || exit 1

echo "== 4/5 记录变更 =="
python3 scripts/log_update.py "$MSG"

echo "== 5/5 提交推送 =="
git add -A
if git diff --cached --quiet; then
    echo "   无变更，跳过提交"
else
    git commit -q -m "$MSG"
    echo "   已提交：$(git log -1 --oneline)"
fi
if git remote get-url origin >/dev/null 2>&1; then
    # 先同步远程：网页端改过 README 等文件时，直接 push 会被拒（非快进）
    OB=$(git branch --show-current)
    if git fetch -q origin "$OB" 2>/dev/null; then
        if ! git rebase -q "origin/$OB" >/dev/null 2>&1; then
            git rebase --abort 2>/dev/null
            echo "   ⚠️ 远程有冲突改动，本次未推送；请手动处理后重跑" >&2
            exit 1
        fi
    fi
    if git push -q origin HEAD:"$OB" 2>&1; then
        echo "   ✅ 已推送到 origin"
    else
        echo "   ⚠️ 推送失败（本地提交已完成，稍后可重试 git push）" >&2
    fi
else
    echo "   ⚠️ 未配置 origin 远程仓库" >&2
fi
