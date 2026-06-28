#!/usr/bin/env python3
"""score.py — 双维度评分引擎 v3
身体恢复度（生理） + 行为持续性（Looki）

用法: score.py（从 tmp/looki.json 和 tmp/cal.json 读取）

⚠️ 使用前替换 <YOUR_HEALTH_EXPORT_PATH> → HAE JSON 所在目录
"""
import json, re
from datetime import datetime
from pathlib import Path

tmpd = Path(__file__).parent

# ═══ 加载 Health 数据（用于身体恢复度评分） ═══
health_data = {}
he_found = False
# try /tmp first
if Path("/tmp/health_data.json").exists():
    health_data = json.loads(Path("/tmp/health_data.json").read_text())
    he_found = True
# then HAE 新自动化流程 (latest date file)
if not he_found:
    hae_dir = Path.home() / "<YOUR_HEALTH_EXPORT_PATH>/新自动化流程"
    # fallback: try common iCloud paths
    if not hae_dir.exists():
        import os
        hae_dir = Path(os.path.expanduser("<YOUR_HEALTH_EXPORT_PATH>/新自动化流程"))
    if hae_dir.exists():
        files = sorted(hae_dir.glob("HealthAutoExport-*.json"))
        if files:
            health_data = json.loads(files[-1].read_text())
            he_found = True

looki_data = json.loads((tmpd / "looki.json").read_text())
cal_data = json.loads((tmpd / "cal.json").read_text())

looki_moments = looki_data.get("data", [])
events = cal_data if isinstance(cal_data, list) else cal_data.get("data", [])

lc = len(looki_moments)

# ─── 从 Looki 描述中提取可观察行为 ──────────────────────

all_desc = " ".join([m.get("description", "") for m in looki_moments])
all_titles = " ".join([m.get("title", "") for m in looki_moments])
all_text = all_desc + " " + all_titles

def has_sig(text, keywords):
    return any(kw in text for kw in keywords)

# ═══ 精力信号 ═══
energy_pos = {
    "敲击键盘": "键盘操作",
    "飞速": "快速打字",
    "站立": "站立活动",
    "活跃": "活跃状态",
    "快步": "快步移动",
    "讨论": "主动交流",
}
energy_neg = {
    "昏暗": "昏暗环境中活动",
    "托腮": "托腮（可能疲劳）",
    "仰头": "仰头沉思（可能走神）",
    "床上": "床上活动",
    "躺": "躺卧",
    "打哈欠": "打哈欠",
    "哈欠": "打哈欠",
}

energy_evidence = []
for kw, label in energy_pos.items():
    if kw in all_text:
        energy_evidence.append(f"+ {label}")
for kw, label in energy_neg.items():
    if kw in all_text:
        energy_evidence.append(f"- {label}")

# 起床时间——以 Apple Watch sleepEnd 为准，不用 Looki 第一条
awake_h = None
sleep_start_str = ""
sleep_end_str = ""
if health_data:
    mm = {m['name']: m for m in health_data.get('data', {}).get('metrics', [])}
    sa = mm.get('sleep_analysis') or health_data.get('sleep_analysis')
    if sa:
        sa_data = sa.get('data', []) if isinstance(sa, dict) else ([sa] if isinstance(sa, dict) else [])
        for p in sa_data:
            end_str = p.get('sleepEnd', p.get('end', ''))
            start_str = p.get('sleepStart', p.get('start', ''))
            if end_str and end_str != '?':
                try:
                    awake_h = datetime.fromisoformat(end_str).hour
                    sleep_end_str = end_str
                    sleep_start_str = start_str
                except: pass
                break
if awake_h is None and lc > 0:
    try:
        awake_h = datetime.fromisoformat(looki_moments[0]["start_time"]).hour
    except: pass

if awake_h is not None:
    if awake_h < 7:
        energy_evidence.append(f"- 早起（{awake_h}:00 前醒）")
    elif awake_h < 9:
        energy_evidence.append(f"~ 正常起床（{awake_h}:00 档）")

# Looki 时间跨度（排除夜间睡眠误判）
sleep_env_kw = ["睡", "卧室", "床上", "床边", "熄灯", "黑暗中", "入睡", "就寝", "躺下休息", "睡着"]
screen_kw = ["屏幕", "电脑", "手机屏", "荧光", "微光"]

def is_sleep_false_active(m):
    d = m.get("description", "")
    try:
        h = datetime.fromisoformat(m["start_time"]).hour
    except Exception:
        h = 12
    night = (h >= 23 or h <= 6)
    return night and has_sig(d, sleep_env_kw) and has_sig(d, screen_kw)

awake_moments = [m for m in looki_moments if not is_sleep_false_active(m)]
sleep_false_count = len(looki_moments) - len(awake_moments)

looki_span = 0.0
if len(awake_moments) >= 2:
    try:
        first_t = datetime.fromisoformat(awake_moments[0]["start_time"])
        last_t = datetime.fromisoformat(awake_moments[-1]["end_time"])
        looki_span = (last_t - first_t).total_seconds() / 3600
    except Exception:
        pass
if looki_span > 14:
    energy_evidence.append(f"- 超长活动跨度 ({looki_span:.0f}h)")
if sleep_false_count > 0:
    energy_evidence.append(f"~ 已排除 {sleep_false_count} 段夜间屏幕误开（按睡眠处理）")

# ═══ 专注信号 ═══
focus_evidence = []

phone_booth = len(re.findall(r"电话亭", all_text))
if phone_booth >= 2:
    focus_evidence.append(f"+ 主动进电话亭 {phone_booth} 次（强专注信号）")
elif phone_booth == 1:
    focus_evidence.append("+ 主动进电话亭 1 次")

deep_blocks = 0
deep_mins = 0
for m in looki_moments:
    desc = m.get("description", "")
    if has_sig(desc, ["电话亭", "深度", "全神贯注", "专注", "键盘", "代码"]):
        try:
            s = datetime.fromisoformat(m["start_time"])
            e = datetime.fromisoformat(m["end_time"])
            dur = (e - s).total_seconds() / 60
            dur = min(dur, 90)
            if dur >= 30:
                deep_blocks += 1
                deep_mins += dur
        except Exception:
            pass

if deep_blocks >= 2:
    focus_evidence.append(f"+ {deep_blocks} 个深度工作块，共 {int(deep_mins)}min")

focus_neg_signals = {
    "看手机": "看手机",
    "查看手机": "查看手机",
    "切换": "场景切换",
    "转场": "场景转场",
    "打断": "被打断",
}
for kw, label in focus_neg_signals.items():
    if kw in all_text:
        focus_evidence.append(f"- {label}")

context_switches = len(re.findall(r"切换|转场|进入.*电话亭|走出.*电话亭", all_text))
if context_switches >= 3:
    focus_evidence.append(f"- 场景切换 {context_switches} 次（上下文切换成本）")

# ═══ 压力信号 ═══
stress_evidence = []

stress_pos = {
    "匆匆": "匆忙移动", "赶": "赶时间", "紧张": "紧张表现",
    "皱眉": "皱眉", "叹气": "叹气", "激烈": "激烈讨论", "快速移动": "快速移动",
}
stress_neg = {
    "舒缓": "舒缓状态", "平和": "心态平和", "休息": "主动休息", "放松": "放松状态",
}

for kw, label in stress_pos.items():
    if kw in all_text:
        stress_evidence.append(f"+ {label}")
for kw, label in stress_neg.items():
    if kw in all_text:
        stress_evidence.append(f"- {label}")

has_commute = has_sig(all_text, ["电梯", "通勤", "街头", "步入", "穿过", "十字路口", "人行道", "办公楼", "大厅"])
if has_commute:
    stress_evidence.append("~ 通勤")

last_moment_h = 0
if lc > 0:
    try:
        last_moment_h = datetime.fromisoformat(looki_moments[-1]["end_time"]).hour
    except Exception:
        pass

# ═══ 状态信号 ═══
state_signals = []

rescue_kw = {
    "刷视频": "刷视频", "短视频": "刷短视频", "刷手机": "刷手机",
    "刷社交": "刷社交媒体", "社交媒体": "刷社交媒体", "刷刷": "无意识刷手机",
    "看视频": "看视频", "浏览": "随意浏览", "低头操作手机": "长时间低头玩手机",
    "发呆": "发呆", "放空": "放空", "走神": "走神", "刷新闻": "刷新闻",
}
rescue_hits = set()
for kw, label in rescue_kw.items():
    if kw in all_text:
        rescue_hits.add(label)

phone_long = re.search(r'(始终|一直|不停|持续|长达|长时间|一路|反复).{0,10}(手机|刷)', all_text)
short_video = ("短视频" in all_text or "刷视频" in all_text or "刷社交" in all_text)
if phone_long or short_video:
    rescue_hits.discard("刷手机")
    rescue_hits.discard("随意浏览")
    rescue_hits.add("⚡长时间看手机/刷短视频【明确求救】")

for label in rescue_hits:
    state_signals.append(("rescue", label))

indulge_kw = {
    "可乐": "喝可乐", "奶茶": "喝奶茶", "咖啡": "喝咖啡", "零食": "吃零食",
    "甜": "吃甜食", "巧克力": "吃巧克力", "薯片": "吃薯片", "饮料": "喝饮料",
    "茶歇": "茶歇加餐", "拿取零食": "拿零食",
}
indulge_hits = set()
for kw, label in indulge_kw.items():
    if kw in all_text:
        indulge_hits.add(label)
for label in indulge_hits:
    state_signals.append(("indulge", label))

recover_kw = {
    "眯": "眯一会", "打盹": "打盹", "小睡": "小睡", "午睡": "午睡",
    "小憩": "小憩", "闭眼": "闭眼休息", "趴": "趴着休息", "靠着": "靠着歇",
    "靠在": "靠着歇", "躺": "躺下", "稍作休息": "稍作休息", "片刻": "片刻停留",
}
recover_hits = set()
for kw, label in recover_kw.items():
    if kw in all_text:
        recover_hits.add(label)
for label in recover_hits:
    state_signals.append(("recover", label))

# ─── 日历数据 ───
n_cal = len(events)
cal_min = 0.0
b2b = 0
prev = None
first_mtg_h = 99.0
last_mtg_h = 0.0
max_gap = 0.0

for e in events:
    s = datetime.fromisoformat(e["start_time"]["datetime"])
    en = datetime.fromisoformat(e["end_time"]["datetime"])
    cal_min += (en - s).total_seconds() / 60
    sh = s.hour + s.minute / 60
    eh = en.hour + en.minute / 60
    if sh < first_mtg_h:
        first_mtg_h = sh
    if eh > last_mtg_h:
        last_mtg_h = eh
    if prev is not None:
        gap = (s - prev).total_seconds() / 60
        if gap > max_gap:
            max_gap = gap
        if gap <= 15 and gap >= -30:
            b2b += 1
    prev = en

cal_h = cal_min / 60

# ═══ 行为评分 ═══
if lc <= 2:
    confidence = "low"
    energy = 7
    if first_mtg_h < 10: energy -= 2
    if cal_h > 4: energy -= 1
    if cal_h > 6: energy -= 2
    if last_mtg_h > 19: energy -= 1
    energy = max(1, min(10, energy))

    focus = 7
    if max_gap > 60: focus += 1
    if b2b >= 3: focus -= 2
    if cal_h > 4: focus -= 1
    focus = max(1, min(10, focus))

    stress = 3
    if cal_h > 4: stress += 2
    if cal_h > 6: stress += 3
    if b2b >= 3: stress += 2
    if last_mtg_h > 19: stress += 1
    stress = max(1, min(10, stress))

    score_note = "⚠️ Looki 未开启（今日仅 {} 个 moments），评分根据日历负载估算，**非行为观察**，准确度有限".format(lc)
else:
    confidence = "high" if lc >= 5 else "medium"

    pos_e = 0
    neg_e = 0
    for e in energy_evidence:
        if e.startswith("+ 键盘") or e.startswith("+ 快速打字"):
            pos_e += 0
        elif e.startswith("+"):
            pos_e += 1
        elif "床上" in e or "躺" in e:
            neg_e += 2
        elif "跨度" in e and "超长" in e:
            span_h = float(re.search(r'(\d+)h', e).group(1)) if re.search(r'(\d+)h', e) else 14
            if span_h > 16: neg_e += 2
            elif span_h > 14: neg_e += 1
        elif e.startswith("-"):
            neg_e += 1
    energy = 7 + pos_e - neg_e
    energy = max(1, min(10, energy))

    pos_f = min(phone_booth, 2) + (1 if deep_blocks >= 2 else 0)
    neg_f = 1 if context_switches >= 4 else 0
    focus = 7 + pos_f - neg_f
    focus = max(1, min(10, focus))

    pos_s = len([e for e in stress_evidence if e.startswith("+")])
    neg_s = len([e for e in stress_evidence if e.startswith("-")])
    stress = 4 + pos_s - neg_s
    stress = max(1, min(10, stress))

    score_note = "评分基于 Looki 实际捕捉到的 {} 个 moments 中的行为信号".format(lc)

# ═══ 身体恢复度 ═══
recovery = None
recovery_note = ""
if health_data:
    date_str = looki_moments[0].get("date", "") if looki_moments else ""
    if not date_str:
        date_str = events[0].get("start_time", {}).get("datetime", "")[:10] if events else ""

    def get_health_val(data, metric, date_str):
        if metric not in data: return None
        for s in data[metric]:
            if s.get("date") == date_str:
                return s.get("value")
        return None

    rhr_val = get_health_val(health_data, "restingHeartRate", date_str)
    hrv_val = get_health_val(health_data, "heartRateVariability", date_str)
    sleep_val = get_health_val(health_data, "sleepTime", date_str)

    rec = 5
    details = []
    if rhr_val is not None:
        if rhr_val < 47: rec += 2; details.append(f"RHR {rhr_val:.0f} (极佳)")
        elif rhr_val < 50: rec += 1; details.append(f"RHR {rhr_val:.0f} (良好)")
        elif rhr_val < 55: rec += 0; details.append(f"RHR {rhr_val:.0f}")
        else: rec -= 1; details.append(f"RHR {rhr_val:.0f} (偏高)")
    if hrv_val is not None:
        if hrv_val > 70: rec += 2; details.append(f"HRV {hrv_val:.0f} (极佳)")
        elif hrv_val > 60: rec += 1; details.append(f"HRV {hrv_val:.0f} (良好)")
        elif hrv_val > 50: rec += 0; details.append(f"HRV {hrv_val:.0f}")
        else: rec -= 1; details.append(f"HRV {hrv_val:.0f} (偏低)")
    if sleep_val is not None and sleep_val > 0:
        sh = sleep_val / 60
        if sh >= 7.5: rec += 2; details.append(f"睡眠 {sh:.1f}h (充足)")
        elif sh >= 7: rec += 1; details.append(f"睡眠 {sh:.1f}h (OK)")
        elif sh >= 6: rec += 0; details.append(f"睡眠 {sh:.1f}h (偏少)")
        else: rec -= 2; details.append(f"睡眠 {sh:.1f}h (不足)")

    if details:
        recovery = max(1, min(10, rec))
        recovery_note = " | ".join(details)

# ─── 日程负载 ───
schedule_load = ""
if n_cal > 0:
    schedule_load = "{} 个会议 / {:.1f}h".format(n_cal, cal_h)
    if b2b >= 3:
        schedule_load += " / 背靠背 ≥{} 连".format(b2b)
    if last_mtg_h > 20:
        schedule_load += " / 晚间会议延至 {}:00".format(int(last_mtg_h))

# ─── 风险 ───
risks = []
if last_mtg_h > 20:
    risks.append("晚间日程延至 {} 点后，可能压缩恢复时间".format(int(last_mtg_h)))
if b2b >= 3 and cal_h > 5:
    risks.append("下午会议连排，中间无有效喘息窗口")
if lc <= 2:
    risks.append("今日 Looki 数据稀疏，评分不可用——可能设备关闭或未佩戴")

# ─── 行为标签 ───
tags = []
if has_sig(all_text, ["思考", "沉思", "念叨", "自我对话"]):
    tags.append("晨间思考")
if phone_booth >= 2:
    tags.append("电话亭深度 x{}".format(phone_booth))
elif phone_booth == 1:
    tags.append("电话亭深度工作")
if has_sig(all_text, ["讨论", "交流", "协作", "团队", "伙伴", "围坐"]):
    tags.append("团队协作")
if has_commute:
    tags.append("通勤")
if has_sig(all_text, ["静谧", "平和", "舒缓", "休息", "安宁", "安静"]):
    tags.append("恢复时段")

# ─── 状态信号分组 ───
sig_grouped = {"rescue": [], "indulge": [], "recover": []}
for cat, label in state_signals:
    if label not in sig_grouped[cat]:
        sig_grouped[cat].append(label)

print(json.dumps({
    "total_min": int(cal_min),
    "total_h": round(cal_h, 1),
    "back_to_back": b2b,
    "first_mtg_h": round(first_mtg_h, 1) if first_mtg_h < 99 else 99,
    "last_mtg_h": round(last_mtg_h, 1),
    "max_gap": int(max_gap),
    "energy": energy if energy is not None else "?",
    "focus": focus if focus is not None else "?",
    "stress": stress if stress is not None else "?",
    "recovery": recovery,
    "recovery_note": recovery_note,
    "confidence": confidence,
    "score_note": score_note,
    "energy_evidence": energy_evidence,
    "focus_evidence": focus_evidence,
    "stress_evidence": stress_evidence,
    "state_rescue": sig_grouped["rescue"],
    "state_indulge": sig_grouped["indulge"],
    "state_recover": sig_grouped["recover"],
    "risks": risks,
    "tags": tags,
    "looki_count": lc,
    "phone_booth": phone_booth,
    "deep_mins": int(deep_mins),
    "deep_blocks": deep_blocks,
    "looki_span": round(looki_span, 1),
    "schedule_load": schedule_load,
}))
