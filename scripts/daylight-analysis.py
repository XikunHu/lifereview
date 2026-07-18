#!/usr/bin/env python3
"""daylight-analysis.py v2 20260718 — 日照×入睡 n-of-1 分析 + 观察规则触发
晨报调用入口。读 canonical.daylight_min（由 health-extract.py v10+ 写入）。

用法:
  python3 daylight-analysis.py 2026-07-17   # 单日：触发观察规则，输出提醒话术
  python3 daylight-analysis.py               # 多日：日照 vs 入睡相关性

规则（见 lifereview-daily SKILL.md「观察规则：日照×入睡晚」）：
  满足≥2 条即提醒：① daylight_min<20  ② sleep_start≥01:00  ③（Looki 22点后脑力活动，需另查）
"""
import json, os, sys, statistics, math
from datetime import datetime, timedelta

CANON = os.path.expanduser("~/.life-log/daily-canonical.jsonl")

def load_canon():
    """读 canonical，返回 {date: {daylight_min, asleep_axis, asleep_str, sleep_h, hrv}}"""
    out = {}
    if not os.path.exists(CANON): return out
    for line in open(CANON):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except: continue
        d = r.get("date")
        if not d: continue
        rec = {"daylight_min": float(r["daylight_min"]) if r.get("daylight_min") else None}
        ss = r.get("sleep_start")
        if ss:
            try:
                dt = datetime.fromisoformat(ss)
                h = dt.hour + dt.minute/60
                rec["asleep_axis"] = h+24 if h<12 else h
                rec["asleep_str"] = dt.strftime("%H:%M")
            except: pass
        try: rec["sleep_h"] = float(r["sleep"]) if r.get("sleep") else None
        except: pass
        try: rec["hrv"] = float(r["hrv"]) if r.get("hrv") else None
        except: pass
        out[d] = rec
    return out

def fmt(h):
    h = h % 24
    return f"{int(h):02d}:{int((h%1)*60):02d}"

def _next_day(d):
    try:
        return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    except: return None

def single_day(target, canon):
    """单日模式：触发观察规则。
    日照在 canon[target]，当晚入睡在 canon[target+1]（睡眠按醒来日归属）。"""
    rec = canon.get(target)
    if not rec or rec.get("daylight_min") is None:
        return f"⚠️ {target} 无日照数据（HAE 未导出/手表未采集）"

    dl = rec["daylight_min"]
    hist = sorted(v["daylight_min"] for v in canon.values() if v.get("daylight_min") is not None)
    pct = sum(1 for v in hist if v <= dl) / len(hist) * 100 if hist else 0

    lines = [f"☀️ {target} 日照 {dl:.0f} 分钟（历史 P{pct:.0f}，中位 {statistics.median(hist):.0f}min）" if hist else f"☀️ {target} 日照 {dl:.0f} 分钟"]

    # 当晚入睡 = canon[target+1].sleep_start（睡眠按醒来日归属）
    nd = _next_day(target)
    asleep_rec = canon.get(nd) if nd else None
    asleep_axis = asleep_rec["asleep_axis"] if asleep_rec and asleep_rec.get("asleep_axis") is not None else None
    asleep_str = asleep_rec["asleep_str"] if asleep_rec else None
    sleep_h = asleep_rec.get("sleep_h") if asleep_rec else None

    asleep_late = asleep_axis is not None and asleep_axis >= 25
    if asleep_str:
        lines.append(f"   当晚入睡: {asleep_str}  睡眠 {sleep_h or '?'}h")
    else:
        lines.append("   ⚠️ 次日睡眠数据未就绪，无法判断当晚入睡")

    if dl < 20 and asleep_late:
        lines.append("")
        lines.append("🔔 触发日照×入睡晚观察规则：")
        lines.append(f"   「☀️ {target} 日照仅 {dl:.0f}min（P{pct:.0f}），当晚入睡 {asleep_str}。")
        lines.append("    日照不足推迟昼夜相位，建议今天上午出门走 15 分钟补晨光。」")
        lines.append("   ⚠️ 补查 Looki 22:00 后是否有工作/会议/录制场景——若有，叠加睡前脑力激活，建议今晚 23 点前停止高强度脑力")
    elif dl < 20:
        lines.append("   ⚠️ 日照偏低（建议补晨光）；入睡是否受影响看次日数据")
    elif asleep_late:
        lines.append("   ⚠️ 入睡晚但日照尚可，主因可能是睡前脑力活动（补查 Looki）")
    else:
        lines.append("   ✅ 日照与入睡均在正常范围")
    return "\n".join(lines)

def multi_day(canon):
    """多日模式：日照 vs 当晚入睡相关性。
    配对：canon[date].daylight_min ↔ canon[date+1].sleep_start（睡眠按醒来日归属）。"""
    pairs = []
    for d, v in canon.items():
        if v.get("daylight_min") is None: continue
        nd = _next_day(d)
        if not nd or nd not in canon: continue
        nv = canon[nd]
        if nv.get("asleep_axis") is None: continue
        pairs.append((d, v["daylight_min"], nv["asleep_axis"]))
    pairs.sort()
    if len(pairs) < 3:
        return f"配对数据不足（{len(pairs)} 天），需累积更多"

    lines = [f"=== 日照 vs 入睡 最近 {len(pairs)} 天 ==="]
    for d, dl, ax in pairs[-14:]:
        flag = "🔴低" if dl < 20 else ("🟡偏少" if dl < 40 else "🟢")
        lines.append(f"  {d}  日照 {dl:>5.0f}min {flag}  入睡 {fmt(ax)}")

    if len(pairs) >= 5:
        xs = [p[1] for p in pairs]; ys = [p[2] for p in pairs]
        n = len(pairs)
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((p[1]-mx)*(p[2]-my) for p in pairs)/n
        sx = math.sqrt(sum((p[1]-mx)**2 for p in pairs)/n)
        sy = math.sqrt(sum((p[2]-my)**2 for p in pairs)/n)
        r = cov/(sx*sy) if sx*sy > 0 else 0
        strength = "强" if abs(r)>=0.5 else ("中" if abs(r)>=0.3 else "弱/无")
        lines.append(f"\nPearson r = {r:.2f}（{strength}相关，{'日照越多入睡越早' if r<-0.2 else '日照越多入睡越晚' if r>0.2 else '无明显关系'}）")
        low = [p[2] for p in pairs if p[1] < 30]
        high = [p[2] for p in pairs if p[1] >= 30]
        if low and high:
            lines.append(f"日照<30min 天（n={len(low)}）入睡均值 {fmt(statistics.mean(low))}")
            lines.append(f"日照≥30min 天（n={len(high)}）入睡均值 {fmt(statistics.mean(high))}")
        lines.append(f"\n注意：只有日总量，无晨光时段。n-of-1 结论需累积 ≥30 天 + 晨光分时段数据。")
    return "\n".join(lines)

if __name__ == "__main__":
    canon = load_canon()
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        print(single_day(target, canon))
    else:
        print(multi_day(canon))
