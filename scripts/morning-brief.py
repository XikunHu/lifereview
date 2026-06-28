#!/usr/bin/env python3
"""morning-brief.py v2 — 新格式晨间简报
融合裁决/审计/证伪/基线对比 + 保留叙事/新视角

⚠️ 使用前替换：
  - <YOUR_LOOKI_API_KEY> → Looki API 密钥
  - <YOUR_LOOKI_SERVER_IP> → Looki 服务器 IP（如 DNS 正常可用 open.looki.ai）
  - <YOUR_FEISHU_CHAT_ID> → 飞书接收消息的 chat_id
  - <YOUR_HEALTH_EXPORT_PATH> → HAE JSON 所在目录
  - <YOUR_NAME> → 你的飞书显示名（日历过滤用）
"""

import json, os, sys, statistics, subprocess
from datetime import datetime, timedelta

# ═══ 配置 — 替换为你的值 ═══
HAE_BASE = os.path.expanduser("<YOUR_HEALTH_EXPORT_PATH>/iCloud for Proma")
LOOKI_KEY = '<YOUR_LOOKI_API_KEY>'
LOOKI_HOST = 'open.looki.ai'  # 如 DNS 被劫持，改为直连 IP
CHAT_ID = '<YOUR_FEISHU_CHAT_ID>'
today = datetime.now().strftime('%Y-%m-%d')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

# ═══ 1. HAE 数据 ═══
def get_hae(date):
    fn = os.path.join(HAE_BASE, f"HealthAutoExport-{date}.json")
    if not os.path.exists(fn):
        return None
    data = json.load(open(fn))
    mm = {m['name']: m for m in data['data']['metrics']}
    out = {}
    # RHR
    if 'resting_heart_rate' in mm:
        vals = [p['qty'] for p in mm['resting_heart_rate']['data'] if p.get('qty')]
        if vals:
            out['rhr'] = int(statistics.median(vals))
    # HRV night
    if 'heart_rate_variability' in mm:
        pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['heart_rate_variability']['data'] if p.get('qty')]
        night = [v for h, v in pts if 0 <= h < 9]
        pool = night if night else [v for _, v in pts]
        if pool:
            m = statistics.median(pool)
            clean = [v for v in pool if v <= m * 2] or pool
            out['hrv'] = int(statistics.median(clean))
            out['hrv_n'] = len(night)
    # Sleep
    if 'sleep_analysis' in mm:
        for p in mm['sleep_analysis']['data']:
            ts = float(p.get('totalSleep', 0))
            if ts > 0:
                out['sleep'] = ts
                out['deep'] = float(p.get('deep', 0))
                out['rem'] = float(p.get('rem', 0))
                out['sleep_start'] = p.get('sleepStart', '')[:16]
                out['sleep_end'] = p.get('sleepEnd', '')[:16]
                break
    # Resp
    if 'respiratory_rate' in mm:
        pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['respiratory_rate']['data'] if p.get('qty')]
        night = [v for h, v in pts if 0 <= h < 9]
        if night: out['resp'] = round(statistics.median(night), 1)
    # Steps
    if 'step_count' in mm:
        out['steps'] = int(sum(p.get('qty', 0) or 0 for p in mm['step_count']['data']))
    # Active
    if 'active_energy' in mm:
        out['active'] = int(sum(p.get('qty', 0) or 0 for p in mm['active_energy']['data']))
    return out

# ═══ 2. Looki ═══
def get_looki(date):
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    # 如果 DNS 正常，不需要下面两行；如果被劫持才需要
    # ctx.check_hostname = False
    # ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(f'https://{LOOKI_HOST}/api/v1/moments?on_date={date}',
        headers={'Host': 'open.looki.ai', 'X-API-Key': LOOKI_KEY})
    try:
        r = json.loads(urllib.request.urlopen(req, context=ctx, timeout=20).read().decode())
        return r.get('data', [])
    except:
        return []

def get_realtime():
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    req = urllib.request.Request(f'https://{LOOKI_HOST}/api/v1/realtime/latest-event',
        headers={'Host': 'open.looki.ai', 'X-API-Key': LOOKI_KEY})
    try:
        r = json.loads(urllib.request.urlopen(req, context=ctx, timeout=10).read().decode())
        return r.get('data')
    except:
        return None

# ═══ 3. 日历 ═══
def get_calendar(date):
    try:
        raw = subprocess.run(['lark-cli', 'calendar', '+agenda', '--start', date, '--end', date, '--as', 'user'],
            capture_output=True, text=True, timeout=30)
        data = json.loads(raw.stdout)
        if not data.get('ok'):
            return []
    except:
        return []

    import re
    events = []
    for e in data.get('data', []):
        s = e.get('summary', '')
        org = (e.get('event_organizer') or {}).get('display_name', '') or ''
        rsvp = e.get('self_rsvp_status', '')
        st = e.get('start_time', {}).get('datetime', '')[:16]
        et = e.get('end_time', {}).get('datetime', '')[:16]
        # 三层漏斗
        excl = bool(re.search(r'打开 Proma|Looki 每日|Looki 周报|上传 Looki', s))
        excl2 = bool(re.search(r'交[租费水电燃气煤]$|交费|缴费|还款|转账|扣款|退款|领券|下单|Review.*持仓|预约|挂号|约[医检师傅]|报备|填[写表]|审批|盖章|签[字约]|确认.*订阅|确认.*续期|早餐在冰箱|带水果|拿行李|回办公室拿|修改时间$|简单心理|学费|退款|好评', s))
        incl = (rsvp == 'accept' or bool(re.search(r'<YOUR_NAME>', org)) or
                bool(re.search(r'[A-Z]{2,3}\d{3,4}|高铁|火车|动车|航班|起飞|航站楼|→|->|飞往|飞去|飞机', s)))
        if not excl and not excl2 and incl:
            sh, sm = int(st[11:13]), int(st[14:16])
            eh, em = int(et[11:13]), int(et[14:16])
            dur = (eh*60+em) - (sh*60+sm)
            events.append({'start': st[11:16], 'end': et[11:16], 'summary': s, 'dur': dur})
    return events

# ═══ 4. RHR 趋势 ═══
def get_rhr_trend(days=7):
    trend = []
    for i in range(days, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        fn = os.path.join(HAE_BASE, f"HealthAutoExport-{d}.json")
        if os.path.exists(fn):
            dd = json.load(open(fn))
            dmm = {m['name']: m for m in dd['data']['metrics']}
            if 'resting_heart_rate' in dmm:
                vals = [p['qty'] for p in dmm['resting_heart_rate']['data'] if p.get('qty')]
                if vals:
                    trend.append((d[-5:], int(statistics.median(vals))))
    return trend

# ═══ 5. 组装报告 ═══
hae_today = get_hae(today)
hae_yday = get_hae(yesterday)
looki_yday = get_looki(yesterday)
realtime = get_realtime()
cal_today = get_calendar(today)
rhr_trend = get_rhr_trend(7)

# 计算7d基线
rhr_vals = [v for _, v in rhr_trend[:-1]] if rhr_trend else []
rhr_7d = sum(rhr_vals) / len(rhr_vals) if rhr_vals else None

# 裁决
rhr = hae_today.get('rhr') or (hae_yday.get('rhr') if hae_yday else None)
hrv = hae_today.get('hrv')
sleep_h = hae_today.get('sleep')
deep_h = hae_today.get('deep', 0)
rem_h = hae_today.get('rem', 0)

issues = []
if rhr:
    if rhr < 47: pass  # 深度恢复
    elif rhr < 50: pass  # normal
    else: issues.append(f"RHR {rhr}")
if sleep_h:
    if sleep_h < 7: issues.append(f"睡眠 {sleep_h:.1f}h")
if deep_h:
    if deep_h < 0.7: issues.append(f"深睡 {deep_h:.1f}h")

if len(issues) >= 2:
    verdict = "🔴 红灯"
elif len(issues) == 1:
    verdict = "🟡 黄灯"
else:
    verdict = "🟢 绿灯"

# 审计
audit_parts = []
audit_parts.append("HAE " + ("✅" if hae_today else "❌"))
audit_parts.append("Looki " + (f"✅ {len(looki_yday)}段" if looki_yday else "❌"))
audit_parts.append("Realtime " + ("✅" if realtime else "❌"))
audit_parts.append("日历 " + ("✅" if cal_today else "❌"))

# 构建消息
msg = f"## {verdict} · {today}\n\n"
msg += f"**数据审计**：{' | '.join(audit_parts)}\n\n"

# 一句话裁决
if issues:
    msg += f"**{', '.join(issues)}**——"
    if rhr and rhr >= 50:
        msg += f"RHR 尚未回到深度恢复区间，今天优先保护恢复时间。"
    else:
        msg += "今天优先保护恢复时间。"
else:
    msg += "身体状态良好，今天可以正常发挥。"
msg += "\n\n---\n\n"

# 昨天 Looki
if looki_yday:
    msg += f"### 昨天 ({yesterday}) Looki 轨迹\n\n"
    for m in looki_yday:
        st = m['start_time'][11:16]
        et = m['end_time'][11:16]
        title = m['title']
        desc = m.get('description', '')[:100]
        msg += f"**{st}-{et}** | {title}\n  {desc}\n\n"
else:
    msg += f"### 昨天\n\nLooki 数据暂未生成（AI 处理中）\n\n"

# 生理基线
msg += "### 生理基线\n\n"
if hae_today:
    msg += "| 指标 | 数值 | 7d 基线 | 偏离 |\n"
    msg += "|------|------|---------|------|\n"
    if rhr:
        d = f"↑ {rhr - rhr_7d:.0f}" if rhr_7d and rhr > rhr_7d else (f"↓ {rhr_7d - rhr:.0f}" if rhr_7d else "—")
        msg += f"| RHR | {rhr} bpm | {rhr_7d:.0f} | {d} |\n"
    if hrv:
        msg += f"| HRV | {hrv} ms (n={hae_today.get('hrv_n','?')}) | — | — |\n"
    if sleep_h:
        msg += f"| 睡眠 | {sleep_h:.1f}h | — | — |\n"
    if deep_h is not None:
        msg += f"| 深睡 | {deep_h:.1f}h | — | — |\n"
    if rem_h is not None:
        msg += f"| REM | {rem_h:.1f}h | — | — |\n"
    if hae_today.get('resp'):
        msg += f"| 呼吸 | {hae_today['resp']}/min | — | — |\n"
    msg += "\n"

# 日程
if cal_today:
    total_h = sum(e['dur'] for e in cal_today) / 60
    msg += f"### 今日日程 ({len(cal_today)}会/{total_h:.1f}h)\n\n"
    for e in cal_today:
        msg += f"`{e['start']}` {e['summary'][:45]}\n"
    msg += "\n"

# RHR 趋势
if rhr_trend:
    msg += "### RHR 本周\n"
    msg += " → ".join([f"{v}" for _, v in rhr_trend]) + "\n\n"

msg += "---\n有偏差就告诉我。精力X 专注X 压力X，我来调整。"

# ═══ 6. 发送 ═══
log_file = os.path.expanduser(f"~/.life-log/{today}.md")
with open(log_file, 'w') as f:
    f.write(f"# {today} 晨间简报\n\n{msg}")

# Send via proma-send
cred_file = os.path.expanduser("~/.life-log/.proma-credentials.json")
if os.path.exists(cred_file):
    print(msg)
else:
    print("ERROR: credentials not found at ~/.life-log/.proma-credentials.json", file=sys.stderr)
    sys.exit(1)
