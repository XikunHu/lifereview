#!/bin/bash
# daily-log-gen.sh v4 — 行为观察评分引擎
# 只基于 Looki 实际捕捉到的行为打分，不编造
# 用法: ./daily-log-gen.sh [date]
#
# ⚠️ 使用前替换：
#   - <YOUR_LOOKI_SERVER_IP> → Looki 服务器 IP（DNS 正常可用 open.looki.ai）
#   - <YOUR_NAME> → 你的飞书显示名（日历过滤用）
#   - <YOUR_HEALTH_EXPORT_PATH> → HAE JSON 所在目录

set -euo pipefail

DATE="${1:-$(date +%Y-%m-%d)}"
WEEKDAY=$(date -j -f "%Y-%m-%d" "$DATE" "+%A" 2>/dev/null || date -d "$DATE" "+%A")
case "$WEEKDAY" in
  Monday)  WDAY="周一" ;; Tuesday) WDAY="周二" ;; Wednesday) WDAY="周三" ;;
  Thursday) WDAY="周四" ;; Friday) WDAY="周五" ;; Saturday) WDAY="周六" ;; Sunday) WDAY="周日" ;;
esac

LOG_DIR="$HOME/.life-log"; LOG_FILE="$LOG_DIR/$DATE.md"
TMPD="$LOG_DIR/tmp"; mkdir -p "$LOG_DIR" "$TMPD"
CRED_FILE="$HOME/.config/looki/credentials.json"

# ─── 配置 ───
LOOKI_IP="<YOUR_LOOKI_SERVER_IP>"  # 替换为 Looki 服务器 IP
HAE_DIR="<YOUR_HEALTH_EXPORT_PATH>"  # 替换为你的 HAE 路径

# ─── Looki ──────────────────────────────────────────────────
LOOKI_MOMENTS=""; LOOKI_REALTIME=""; MOMENT_COUNT=0; MOMENTS_JSON='{"data":[]}'

if [ -f "$CRED_FILE" ]; then
  API_KEY=$(jq -r .api_key "$CRED_FILE")
  # v5: 用 Python 直连 Looki API（绕过可能的 VPN DNS+TLS SNI 拦截）
  MOMENTS_JSON=$(python3 -c "
import urllib.request, ssl, json, sys
API_KEY = '$API_KEY'
IP = '$LOOKI_IP'
ctx = ssl.create_default_context()
# 如果 DNS 正常，注释掉下面两行
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    req = urllib.request.Request('https://'+IP+'/api/v1/moments?on_date=$DATE',
        headers={'Host': 'open.looki.ai', 'X-API-Key': API_KEY})
    resp = urllib.request.urlopen(req, context=ctx, timeout=20)
    print(resp.read().decode())
except Exception as e:
    print(json.dumps({'data':[]}))
" 2>/dev/null || echo '{"data":[]}')
  REALTIME_JSON=$(python3 -c "
import urllib.request, ssl, json
API_KEY = '$API_KEY'
IP = '$LOOKI_IP'
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    req = urllib.request.Request('https://'+IP+'/api/v1/realtime/latest-event',
        headers={'Host': 'open.looki.ai', 'X-API-Key': API_KEY})
    resp = urllib.request.urlopen(req, context=ctx, timeout=10)
    print(resp.read().decode())
except Exception as e:
    print('{}')
" 2>/dev/null || echo '{}')
  MOMENT_COUNT=$(echo "$MOMENTS_JSON" | jq -r '(.data // []) | length')
  if [ "$MOMENT_COUNT" -gt 0 ]; then
    LOOKI_MOMENTS=$(echo "$MOMENTS_JSON" | jq -r '(.data // []) | to_entries | .[] | "\(.key + 1). **\(.value.title // "无标题")**\n   \(.value.start_time[0:16] // "") → \(.value.end_time[0:16] // "")\n   \(.value.description // "")\n"')
  else
    LOOKI_MOMENTS="（今日暂无 moments — Looki 可能关闭或未佩戴）"
  fi
  RD=$(echo "$REALTIME_JSON" | jq -r '.data.description // ""')
  [ -n "$RD" ] && [ "$RD" != "null" ] && LOOKI_REALTIME="$RD"
else
  LOOKI_MOMENTS="（Looki 凭据未配置）"
fi

# ─── 飞书日历（仅已接受）───────────────────────────────────
CALENDAR_SECTION=""; CAL_COUNT=0; EVENTS=""
ENERGY="?"; FOCUS="?"; STRESS="?"
ENERGY_BAR="N/A"; FOCUS_BAR="N/A"; STRESS_BAR="N/A"
ENERGY_EV=""; FOCUS_EV=""; STRESS_EV=""
SCORE_NOTE=""; SCHEDULE_LOAD=""; RISKS=""; TAGS=""
BACK_TO_BACK=0; TOTAL_H=0; TOTAL_MIN=0

if command -v lark-cli &>/dev/null; then
  CAL_RAW=$(lark-cli calendar +agenda --start "$DATE" --end "$DATE" --as user 2>/dev/null)
  CAL_OK=$(echo "$CAL_RAW" | jq -r '.ok // false')
  if [ "$CAL_OK" != "true" ]; then
    # API 失败，尝试从已有日志恢复日历数据
    if [ -f "$LOG_FILE" ]; then
      EXISTING_MEETINGS=$(grep -c '^| \d{2}:\d{2}' "$LOG_FILE" 2>/dev/null || echo 0)
      if [ "$EXISTING_MEETINGS" -gt 0 ]; then
        echo "[WARN] 日历API失败，保留已有 $(grep -c '^|' "$LOG_FILE" 2>/dev/null) 条日程数据" >&2
        CAL_JSON=$(python3 -c "
import json,re,sys
txt=open('$LOG_FILE').read()
mtgs=re.findall(r'\| (\d{2}:\d{2}) - (\d{2}:\d{2}) \| (.+?) \| (.+?) \|', txt)
data=[{'start_time':{'datetime':f'$DATE"T"{s}:00+08:00'},'end_time':{'datetime':f'$DATE"T"{e}:00+08:00'},'summary':t.strip(),'event_organizer':{'display_name':o.strip()},'self_rsvp_status':'accept'} for s,e,t,o in mtgs]
print(json.dumps({'data':data}))
" 2>/dev/null || echo '{"data":[]}')
      else
        echo "[WARN] 日历API失败，无已有数据可恢复" >&2
        CAL_JSON='{"data":[]}'
      fi
    else
      echo "[WARN] 日历API失败，无已有日志" >&2
      CAL_JSON='{"data":[]}'
    fi
  else
    # 参与规则（三选一即可）：① 点了「接受」② 自己创建的 ③ 标题含行程语义
    # ⚠️ 替换 <YOUR_NAME> 为你的飞书显示名
    CAL_JSON=$(echo "$CAL_RAW" | jq '(.data // []) | map(select(
      (
        .self_rsvp_status == "accept"
        or ((.event_organizer.display_name // "") | test("<YOUR_NAME>"))
        or (.summary | test("[A-Z]{2,3}\\d{3,4}|高铁|火车|动车|航班|起飞|航站楼|→|->|飞往|飞去|飞机"))
      )
      and (.summary | test("打开 Proma|Looki 每日|Looki 周报|上传 Looki") | not)
      and (.summary | test("交[租费水电燃气煤]$|交费|缴费|还款|转账|扣款|退款|领券|下单|Review.*持仓|预约|挂号|约[医检师傅]|报备|填[写表]|审批|盖章|签[字约]|确认.*订阅|确认.*续期|早餐在冰箱|带水果|拿行李|回办公室拿|修改时间$|简单心理|学费|退款|好评") | not)
    )) | {data: .}')
  fi
  CAL_COUNT=$(echo "$CAL_JSON" | jq -r '(.data // []) | length')

  if [ "$CAL_COUNT" -gt 0 ]; then
    EVENTS_JSON=$(echo "$CAL_JSON" | jq -c '(.data // []) | sort_by(.start_time.datetime)')
    EVENTS=$(echo "$EVENTS_JSON" | jq -r '.[] | "| \(.start_time.datetime[11:16]) - \(.end_time.datetime[11:16]) | \(.summary // "无标题") | \(.event_organizer.display_name // "") |"')

    echo "$MOMENTS_JSON" > "$TMPD/looki.json"
    echo "$EVENTS_JSON" > "$TMPD/cal.json"
    METRICS=$(python3 "$TMPD/score.py" 2>/dev/null || echo '{}')
  fi
fi

# ─── 解析评分 ──────────────────────────────────────────────
if [ -n "${METRICS:-}" ] && [ "${METRICS:-}" != "{}" ]; then
  TOTAL_MIN=$(echo "$METRICS" | jq -r '.total_min // 0')
  TOTAL_H=$(echo "$METRICS" | jq -r '.total_h // 0')
  BACK_TO_BACK=$(echo "$METRICS" | jq -r '.back_to_back // 0')
  ENERGY=$(echo "$METRICS" | jq -r '.energy // "?"')
  FOCUS=$(echo "$METRICS" | jq -r '.focus // "?"')
  STRESS=$(echo "$METRICS" | jq -r '.stress // "?"')
  SCORE_NOTE=$(echo "$METRICS" | jq -r '.score_note // ""')
  SCHEDULE_LOAD=$(echo "$METRICS" | jq -r '.schedule_load // ""')
  ENERGY_EV=$(echo "$METRICS" | jq -r '.energy_evidence | if length > 0 then join("\n") else "（未捕捉到显著精力信号）" end')
  FOCUS_EV=$(echo "$METRICS" | jq -r '.focus_evidence | if length > 0 then join("\n") else "（未捕捉到显著专注信号）" end')
  STRESS_EV=$(echo "$METRICS" | jq -r '.stress_evidence | if length > 0 then join("\n") else "（未捕捉到显著压力信号）" end')
  RISKS=$(echo "$METRICS" | jq -r '.risks | if length > 0 then "⚠️ " + join("\n⚠️ ") else "" end')
  TAGS=$(echo "$METRICS" | jq -r '.tags | join(" · ")')
  SIG_RESCUE=$(echo "$METRICS" | jq -r '.state_rescue | join("、")')
  SIG_INDULGE=$(echo "$METRICS" | jq -r '.state_indulge | join("、")')
  SIG_RECOVER=$(echo "$METRICS" | jq -r '.state_recover | join("、")')
  if [ "$ENERGY" != "?" ]; then
    ENERGY_BAR=$(python3 -c "n=int($ENERGY); print('█'*n + '░'*(10-n))" 2>/dev/null || echo "????")
    FOCUS_BAR=$(python3 -c "n=int($FOCUS); print('█'*n + '░'*(10-n))" 2>/dev/null || echo "????")
    STRESS_BAR=$(python3 -c "n=int($STRESS); print('█'*n + '░'*(10-n))" 2>/dev/null || echo "????")
  fi
fi

[ -n "$EVENTS" ] && CALENDAR_SECTION=$(cat <<CALENDAR
| 时间 | 会议 | 组织者 |
|------|------|--------|
$EVENTS

> 共 **$CAL_COUNT** 个会议 / 总时长约 ${TOTAL_H}h / 背靠背 ≥${BACK_TO_BACK} 连

CALENDAR
) || CALENDAR_SECTION="（今日无已接受日程）"

# ─── 状态信号区块 ───
STATE_BLOCK=""
SLEEP_LINE=""; RHR_LINE=""; HRV_LINE=""; STEPS_LINE=""
[ -n "${SIG_RESCUE:-}" ] && STATE_BLOCK="${STATE_BLOCK}- 🆘 **精力求救**（大脑累了找无意识娱乐）: ${SIG_RESCUE}
"
[ -n "${SIG_INDULGE:-}" ] && STATE_BLOCK="${STATE_BLOCK}- 🍬 **代偿/提神**（刺激物或零食补偿）: ${SIG_INDULGE}
"
[ -n "${SIG_RECOVER:-}" ] && STATE_BLOCK="${STATE_BLOCK}- 😴 **主动恢复**（小憩/休息）: ${SIG_RECOVER}
"
[ -z "$STATE_BLOCK" ] && STATE_BLOCK="（今日未捕捉到明显的求救/代偿/恢复信号）"

# ─── 生成 Markdown ──────────────────────────────────────────

cat > "$LOG_FILE" <<MARKDOWN
# $DATE $WDAY

## 场景轨迹 (Looki)

$LOOKI_MOMENTS

> 最新实时: ${LOOKI_REALTIME:-（无）}

## 日程负载 (飞书日历 · 仅已接受)

$CALENDAR_SECTION

## 行为观察

| 指标 | 评分 |  Looki 实际捕捉到的行为 |
|------|------|--------------------------|
| 精力 | ${ENERGY}/10 ${ENERGY_BAR} | $(echo "$ENERGY_EV" | head -1) |
$(echo "$ENERGY_EV" | tail -n +2 | while read line; do echo "| | | $line |"; done)
| 专注 | ${FOCUS}/10 ${FOCUS_BAR} | $(echo "$FOCUS_EV" | head -1) |
$(echo "$FOCUS_EV" | tail -n +2 | while read line; do echo "| | | $line |"; done)
| 压力 | ${STRESS}/10 ${STRESS_BAR} | $(echo "$STRESS_EV" | head -1) |
$(echo "$STRESS_EV" | tail -n +2 | while read line; do echo "| | | $line |"; done)

> ${SCORE_NOTE}

## 状态信号 (求救/代偿/恢复)

$STATE_BLOCK

${RISKS}

> 💡 如不符实际感受，回复「精力X 专注Y 压力Z」即可修正。

---

> 自动生成于 $(date '+%Y-%m-%d %H:%M:%S') · Looki 行为观察
MARKDOWN

echo "$LOG_FILE"
echo "MOMENT_COUNT=$MOMENT_COUNT CAL_COUNT=$CAL_COUNT BACK_TO_BACK=$BACK_TO_BACK"
echo "ENERGY=$ENERGY FOCUS=$FOCUS STRESS=$STRESS TAGS=$TAGS"
