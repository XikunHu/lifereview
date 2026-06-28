#!/bin/bash
# morning-brief.sh v2 — 完整晨间简报（Shell 版，供参考）
# 新版本推荐使用 morning-brief.py
# 用法: ./morning-brief.sh
#
# ⚠️ 使用前替换：
#   - <YOUR_FEISHU_CHAT_ID> → 飞书接收消息的 chat_id
#   - <YOUR_HEALTH_EXPORT_PATH> → HAE JSON 所在目录
#   - <YOUR_NAME> → 你的飞书显示名（日历过滤用）

set -euo pipefail

YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$HOME/.life-log/$YESTERDAY.md"
TARGET_USER="<YOUR_FEISHU_CHAT_ID>"

# ─── 昨日完整回顾 ──────────────────────────────────────
YESTERDAY_SUMMARY=""
if [ -f "$LOG_FILE" ]; then
  ENERGY=$(grep -oE '精力.*\| *([0-9]+)/10' "$LOG_FILE" | grep -oE '[0-9]+' | head -1 || echo "?")
  FOCUS=$(grep -oE '专注.*\| *([0-9]+)/10' "$LOG_FILE" | grep -oE '[0-9]+' | head -1 || echo "?")
  STRESS=$(grep -oE '压力.*\| *([0-9]+)/10' "$LOG_FILE" | grep -oE '[0-9]+' | head -1 || echo "?")

  TAGS=$(grep '| 精力 |' "$LOG_FILE" | head -1 | awk -F'|' '{print $4}' | xargs 2>/dev/null || echo "")

  SCENES=$(grep -E '^[0-9]+\. \*\*' "$LOG_FILE" | sed 's/^[0-9]*\. \*\*//' | sed 's/\*\*//' || echo "")
  FIRST_SCENE=$(echo "$SCENES" | head -1)
  LAST_SCENE=$(echo "$SCENES" | tail -1)
  SCENE_COUNT=$(echo "$SCENES" | grep -c . || echo 0)

  RISKS=$(grep '⚠️' "$LOG_FILE" | sed 's/⚠️ /• /g' | head -3 || echo "")

  if [ "$ENERGY" = "?" ]; then
    YESTERDAY_SUMMARY="**${YESTERDAY}** · Looki 未记录（休息日或设备关闭）"
  else
    YESTERDAY_SUMMARY="**${YESTERDAY}** · 精力 ${ENERGY} | 专注 ${FOCUS} | 压力 ${STRESS}"
    [ -n "$TAGS" ] && YESTERDAY_SUMMARY="${YESTERDAY_SUMMARY}
行为: ${TAGS}"
    if [ "$SCENE_COUNT" -gt 0 ] && [ -n "$FIRST_SCENE" ]; then
      YESTERDAY_SUMMARY="${YESTERDAY_SUMMARY}
场景: ${FIRST_SCENE} → ${LAST_SCENE}（共${SCENE_COUNT}段）"
    fi
    [ -n "$RISKS" ] && YESTERDAY_SUMMARY="${YESTERDAY_SUMMARY}

${RISKS}"
  fi
else
  YESTERDAY_SUMMARY="昨日日志未生成"
fi

# ─── 今日状态预判（基于昨日生理数据）─────────────────
STATE_PREDICTION=""
HEALTH_JSON=""
HAE_DIR="<YOUR_HEALTH_EXPORT_PATH>/新自动化流程"
HAE_DIR2="<YOUR_HEALTH_EXPORT_PATH>/iCloud for Proma"
TODAY_FILE="$HAE_DIR/HealthAutoExport-${TODAY}.json"
YESTERDAY_FILE="$HAE_DIR/HealthAutoExport-${YESTERDAY}.json"
TODAY_FILE2="$HAE_DIR2/HealthAutoExport-${TODAY}.json"
YESTERDAY_FILE2="$HAE_DIR2/HealthAutoExport-${YESTERDAY}.json"
if [ -f "$TODAY_FILE" ]; then
  HEALTH_JSON="$TODAY_FILE"
elif [ -f "$YESTERDAY_FILE" ]; then
  HEALTH_JSON="$YESTERDAY_FILE"
elif [ -f "$TODAY_FILE2" ]; then
  HEALTH_JSON="$TODAY_FILE2"
elif [ -f "$YESTERDAY_FILE2" ]; then
  HEALTH_JSON="$YESTERDAY_FILE2"
else
  LATEST_FILE=$(ls -t "$HAE_DIR"/HealthAutoExport-*.json "$HAE_DIR2"/HealthAutoExport-*.json 2>/dev/null | head -1)
  if [ -f "$LATEST_FILE" ]; then
    HEALTH_JSON="$LATEST_FILE"
  fi
fi
if [ -f "$HEALTH_JSON" ]; then
  HE_DATE=$(basename "$HEALTH_JSON" | sed 's/HealthAutoExport-//' | sed 's/.json//' | cut -c1-10)
  if [ "$HE_DATE" = "$TODAY" ] || [ "$HE_DATE" = "$YESTERDAY" ]; then
    HEALTH_FRESH=true
  else
    HEALTH_FRESH=false
    STATE_PREDICTION="（HAE数据来自${HE_DATE}，暂未更新。昨晚睡眠和生理指标暂无）"
  fi
  if [ "$HEALTH_FRESH" = true ]; then
  STATE_PREDICTION=$(python3 "$HOME/.life-log/tmp/health-extract.py" "$HEALTH_JSON" "$YESTERDAY" 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
lines = []
rhr = float(d.get('rhr', 0) or 0)
hrv = float(d.get('hrv', 0) or 0)
sleep = float(d.get('sleep', 0) or 0)

if rhr > 0:
    if rhr < 47: lines.append(f'💪 静息HR {rhr:.0f}（极佳·深度恢复）')
    elif rhr < 50: lines.append(f'✅ 静息HR {rhr:.0f}（良好）')
    elif rhr < 53: lines.append(f'⚠️ 静息HR {rhr:.0f}（略高·基线+{rhr-47:.0f}）→ 昨晚有饮酒/聚餐吗？')
    else: lines.append(f'🔴 静息HR {rhr:.0f}（偏高·基线+{rhr-47:.0f}）→ 酒精/社交/恢复不足')
if hrv > 0:
    if hrv > 70: lines.append(f'💪 昨晚睡眠HRV {hrv:.0f}（极佳）')
    elif hrv > 60: lines.append(f'✅ 昨晚睡眠HRV {hrv:.0f}（良好）')
    else: lines.append(f'⚠️ 昨晚睡眠HRV {hrv:.0f}（偏低·恢复不充分）')
if sleep > 0:
    if sleep >= 7.5: lines.append(f'😴 昨晚睡眠 {sleep:.1f}h（充足）')
    elif sleep >= 7: lines.append(f'😴 昨晚睡眠 {sleep:.1f}h（OK）')
    elif sleep >= 6: lines.append(f'⚠️ 昨晚睡眠 {sleep:.1f}h（偏少）')
    else: lines.append(f'🔴 昨晚睡眠 {sleep:.1f}h（不足·今晚优先补觉）')

if rhr >= 51 and rhr < 55:
    lines.append('🍺 RHR偏高时通常与饮酒/深夜社交相关（与会多无关）')
elif rhr >= 55:
    lines.append('🔴 RHR显著偏高——身体应激状态，今天优先保护恢复时间')

if lines:
    print(' | '.join(lines))
" 2>/dev/null)
  fi
fi

# ─── 今日日程 + 负载分析 ──────────────────────────────
TODAY_BLOCK=""
if command -v lark-cli &>/dev/null; then
  CAL=$(lark-cli calendar +agenda --start "$TODAY" --end "$TODAY" --as user 2>/dev/null || echo '{"data":[]}')

  # ⚠️ 替换 <YOUR_NAME> 为你的飞书显示名
  ACCEPTED=$(echo "$CAL" | jq -r '
    [.data[] | select(.self_rsvp_status == "accept" and (.summary | test("打开 Proma") | not))]
    | sort_by(.start_time.datetime)
    | .[] | "`\(.start_time.datetime[11:16])` \(.summary)"
  ' 2>/dev/null || echo "")

  LOAD=$(echo "$CAL" | python3 "$HOME/.life-log/tmp/schedule-analyzer.py" 2>/dev/null || echo "")

  if [ -n "$ACCEPTED" ]; then
    TODAY_BLOCK="${ACCEPTED}

${LOAD}"
  else
    TODAY_BLOCK="今日暂无已接受日程"
  fi
fi

# ─── 昨日叙事 ──────────────────────────────────────────
HLTH_JSON=""
if [ -f "$YESTERDAY_FILE" ]; then HLTH_JSON="$YESTERDAY_FILE"
elif [ -f "$TODAY_FILE" ]; then HLTH_JSON="$TODAY_FILE"
elif [ -f "$YESTERDAY_FILE2" ]; then HLTH_JSON="$YESTERDAY_FILE2"
elif [ -f "$TODAY_FILE2" ]; then HLTH_JSON="$TODAY_FILE2"
else
  LATEST_FILE=$(ls -t "$HAE_DIR"/HealthAutoExport-*.json "$HAE_DIR2"/HealthAutoExport-*.json 2>/dev/null | head -1)
  if [ -f "$LATEST_FILE" ]; then HLTH_JSON="$LATEST_FILE"
  fi
fi
NARR_JSON="$HOME/.life-log/$YESTERDAY.md"
YESTERDAY_NARR=""
YESTERDAY_HEALTH=""
YESTERDAY_PERSP=""
if [ -f "$HLTH_JSON" ] && [ -f "$NARR_JSON" ]; then
  NARR_INFO=$(python3 "$HOME/.life-log/tmp/daily-narrative.py" "$HLTH_JSON" "$NARR_JSON" "$YESTERDAY" 2>/dev/null)
  YESTERDAY_NARR=$(echo "$NARR_INFO" | jq -r '.narrative // ""')
  YESTERDAY_HEALTH=$(echo "$NARR_INFO" | jq -r '.body_line // ""')
  YESTERDAY_PERSP=$(echo "$NARR_INFO" | jq -r '.perspective // ""')
fi

# ─── 专注力预判 ─────────────────────────────────────────
FOCUS_PREDICTION=""
if [ -f "$HEALTH_JSON" ] && [ "$HEALTH_FRESH" = true ]; then
  FOCUS_PREDICTION=$(python3 "$HOME/.life-log/tmp/focus-predict.py" "$HEALTH_JSON" "$LOG_FILE" 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d: sys.exit(0)
print(f'🧠 今日专注力预判: {d[\"score\"]}/10 — {d[\"label\"]}')
for f in d.get('factors', []):
    print(f'  {f}')
for r in d.get('recommendations', []):
    print(f'  → {r}')
" 2>/dev/null)
fi

# ─── 发送 ─────────────────────────────────────────────
MSG=$(cat <<ENDMSG
🌅 **晨间简报 · ${TODAY}**

━━━ 今天身体怎么样 ━━━

${STATE_PREDICTION}

━━━ 今天专注力预判 ━━━

${FOCUS_PREDICTION}

━━━ 昨天发生了什么 ━━━

${YESTERDAY_NARR}

${YESTERDAY_HEALTH}

${YESTERDAY_PERSP}

━━━ 今天日程 ━━━

${TODAY_BLOCK}

━━━━━━━━━━━
有偏差就告诉我
ENDMSG
)

# ─── 发送前自检 ──────────────────────────────────────────
ISSUES=""
if [ -z "${YESTERDAY_NARR:-}" ]; then
  ISSUES="${ISSUES}• 叙事为空"
fi
if [ -z "${STATE_PREDICTION:-}" ] && [ "$HEALTH_FRESH" = true ]; then
  ISSUES="${ISSUES}• 状态预测缺失（健康数据存在但未生成）"
fi
if [ -z "${TODAY_BLOCK:-}" ] || echo "$TODAY_BLOCK" | grep -q "今日暂无"; then
  ISSUES="${ISSUES}• 今日日程未拉到（可能网络/DNS）"
fi
if echo "${MSG:-}" | grep -q "0 会\|0会"; then
  ISSUES="${ISSUES}• 会议数为0，确认是否真的无会"
fi
if [ -n "$ISSUES" ]; then
  echo "[SELF-CHECK] ⚠️ 发送前发现问题:" >&2
  echo "$ISSUES" >&2
  echo "[SELF-CHECK] 将发送但内容可能不完整" >&2
fi

echo "=== Sending morning brief ==="
echo "$MSG" | python3 "$HOME/.life-log/tmp/proma-send.py"

echo "=== Done ==="
