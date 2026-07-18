#!/usr/bin/env python3
"""health-extract.py 20260707 — 从 HAE 自动化 JSON 提取指定日期的生理指标
v4: 修复步数/活跃能量按小时汇总、Walking HR 改用均值
v5: 新增碎步比（hourly阈值版）
v6: 碎步升级为 bout 检测（参考 JeffenCheung/personal-health-dashboard）
v7: 追加写入 daily-canonical.jsonl（参考 duanyu119/open-health-database）
v9: RHR交叉验证(夜间raw HR最低值) + 日间心率-活动耦合指标
20260704: HRV 中位数改均值 + 离群过滤基准同步切换（用户反馈：V 型分布时均值更诚实）
20260704: 步数合理性校验——孤立高值标记(frag_step_suspect) + 手表离线标记(steps_watch_off)
20260704: 睡眠夜晚归属校验——强制sleepStart日期检查 + --expected-sleep-night CLI (exit 2 on mismatch)
20260707: #21 非佩戴检测(non_wear_detected/wear_compliance) + #20 HRV口径标注(SDNN, 非RMSSD)"""
import json, sys, statistics, os
from datetime import datetime, timedelta

data = json.load(open(sys.argv[1]))
date = sys.argv[2]

# v10: --expected-sleep-night 校验（方案①+⑧）
# 用法: python3 health-extract.py file.json 2026-07-04 --expected-sleep-night 2026-07-03
# 校验提取出的 sleepStart 是否属于预期夜晚，不匹配则标记 sleep_night_mismatch 并 exit 2
expected_sleep_night = None
for i, arg in enumerate(sys.argv):
    if arg == '--expected-sleep-night' and i + 1 < len(sys.argv):
        expected_sleep_night = sys.argv[i + 1]

out = {}

mm = {m['name']: m for m in data['data']['metrics']}

# RHR — 取中位数（静息心率一般稳定，但仍防离群）
if 'resting_heart_rate' in mm:
    vals = [p['qty'] for p in mm['resting_heart_rate']['data'] if p.get('qty')]
    if vals:
        out['rhr'] = f"{statistics.median(vals):.0f}"
# v9: RHR 交叉验证——当 RHR 只有单日汇总时，用夜间 raw heart_rate 最低值验证
# Apple Watch 的 resting_heart_rate 可能只有 1 条/天，raw heart_rate 有 24 条小时 Avg
if 'heart_rate' in mm:
    hr_pts = [(int(p['date'].split()[1][:2]), p) for p in mm['heart_rate']['data']]
    night_hr = [(h, p['Avg'], p.get('Min', p['Avg'])) for h, p in hr_pts if 0 <= h < 6]
    day_hr = [(h, p['Avg'], p.get('Min', p['Avg'])) for h, p in hr_pts if 8 <= h < 22]
    if night_hr:
        night_avgs = [a for _, a, _ in night_hr]
        night_mins = [m for _, _, m in night_hr if m]
        out['night_hr_lowest'] = f"{min(night_avgs):.0f}"  # 夜间最低平均心率
        out['night_hr_median'] = f"{statistics.median(night_avgs):.0f}"
    # v8: 日间心率-活动耦合——看心率是否跟步数/energy同步变化
    # 高耦合 = 心脏对活动响应灵敏（健康）；低耦合 = 可能疲劳/过度训练/自主神经迟钝
    if day_hr and 'step_count' in mm:
        step_hourly = [p.get('qty', 0) or 0 for p in mm['step_count']['data']]
        pairs = []
        for h, avg_hr, min_hr in day_hr:
            if h < len(step_hourly) and step_hourly[h] > 0:
                pairs.append((step_hourly[h], avg_hr))
        if len(pairs) >= 4:
            # Pearson r between steps and HR
            n = len(pairs)
            sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
            sxx = sum(p[0]**2 for p in pairs); syy = sum(p[1]**2 for p in pairs)
            sxy = sum(p[0]*p[1] for p in pairs)
            denom = ((n*sxx - sx**2) * (n*syy - sy**2)) ** 0.5
            if denom > 0:
                r = (n*sxy - sx*sy) / denom
                out['hr_activity_coupling'] = f"{r:.2f}"
                if r > 0.6:
                    out['hr_activity_label'] = '高耦合——心脏对活动响应灵敏'
                elif r > 0.3:
                    out['hr_activity_label'] = '中耦合——正常范围'
                elif r > 0:
                    out['hr_activity_label'] = '弱耦合——可能疲劳或自主神经迟钝'
                else:
                    out['hr_activity_label'] = '解耦——生理状态需关注'
    # #21: 非佩戴检测——清醒时段连续 >3h 无心率读数 = 手表离身
    # HAE 心率是小时级，所以 >3h 缺失基本就是摘表（洗澡/充电/忘戴）
    # 只对"已完成的一天"判定：分析日 < 今天，或分析日 == 今天但当前已过 22:00
    _now = datetime.now()
    _is_today_complete = (date == _now.strftime('%Y-%m-%d') and _now.hour >= 22) or (date < _now.strftime('%Y-%m-%d'))
    if 'heart_rate' in mm and _is_today_complete:
        hr_hours = sorted(set(int(p['date'].split()[1][:2]) for p in mm['heart_rate']['data']))
        awake_hours = [h for h in range(8, 22)]  # 08:00-22:00 清醒时段
        missing_awake = [h for h in awake_hours if h not in hr_hours]
        if len(missing_awake) >= 6:  # 14h 清醒时段缺 6h+ = 严重非佩戴
            out['non_wear_detected'] = 'true'
            out['wear_compliance'] = f"{(14 - len(missing_awake)) / 14 * 100:.0f}"
            # 连续缺失段
            gaps = []
            gap_start = None
            for h in awake_hours:
                if h in missing_awake:
                    if gap_start is None: gap_start = h
                else:
                    if gap_start is not None:
                        gaps.append(f"{gap_start:02d}-{h:02d}")
                        gap_start = None
            if gap_start is not None:
                gaps.append(f"{gap_start:02d}-22")
            if gaps:
                out['non_wear_gaps'] = '; '.join(gaps[:3])

# HRV 口径标注（#20 调整版）
# Apple Watch HRV = SDNN（HKQuantityTypeIdentifierHeartRateVariabilitySDNN）
# 不是 RMSSD。要切 RMSSD 需要从 RR 间期算，但 HAE 默认不导出 heartbeat series
if 'heart_rate_variability' in mm:
    out['hrv_metric_type'] = 'SDNN'  # 明确标注口径
    out['hrv_metric_note'] = 'Apple Watch SDNN, 需 HAE heartbeat 导出后切 RMSSD'
if 'rhr' not in out:
    base_dir = os.path.dirname(sys.argv[1])
    parent = os.path.dirname(base_dir)
    for offset in [0, 1, -1, -2]:
        target = (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=offset)).strftime('%Y-%m-%d')
        for sub in [base_dir, f"{parent}/iCloud for Proma", f"{parent}/新自动化流程"]:
            t_file = f"{sub}/HealthAutoExport-{target}.json"
            if os.path.exists(t_file):
                try:
                    td = json.load(open(t_file)); tm = {m['name']: m for m in td['data']['metrics']}
                    if 'resting_heart_rate' in tm:
                        tv = [p['qty'] for p in tm['resting_heart_rate']['data'] if p.get('qty')]
                        if tv:
                            out['rhr'] = f"{round(sum(tv)/len(tv))}"
                            out['rhr_fallback'] = 'true'
                            break
                except: pass
        if 'rhr' in out: break

# HRV — 夜间窗口中位数（睡眠 HRV 是恢复评估的黄金标准）
# 白天 HRV 受运动/说话/压力干扰，不能准确反映自主神经恢复状态
# 与 Apple Health 显示的全天值口径不同，报告中标注为「睡眠 HRV」
# v9: 增加样本数/范围 + 早晨恢复读数 + 标记小样本风险
# v9.1: 改用均值替代中位数——用户反馈中位数在 V 型分布（如 [71,41,42,39,71]）
#   会丢弃极值信息（中位数=42 vs 均值=53），均值更能反映整晚 HRV 的平均水平
if 'heart_rate_variability' in mm:
    pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['heart_rate_variability']['data'] if p.get('qty')]
    night = [(h, v) for h, v in pts if 0 <= h < 9]
    pool = [v for _, v in night] if night else [v for _, v in pts]
    if pool:
        # 排除 >2 倍均值的极端离群值（如单次 135 拉偏 6 次采样的均值）
        avg = sum(pool) / len(pool)
        clean = [v for v in pool if v <= avg * 2] or pool
        out['hrv'] = f"{sum(clean) / len(clean):.0f}"
        out['hrv_n'] = str(len(pool))
        out['hrv_range'] = f"{min(pool):.0f}-{max(pool):.0f}"
        if len(pool) < 3:  # Apple Watch 夜间正常 4-6 次，<3 才算稀疏 (20260705 修正: 原阈值 5 太激进)
            out['hrv_sparse'] = 'true'  # 小样本警告
        # 早晨恢复读数：取 6-9 点最后一个读数，反映醒来时的 HRV 恢复状态
        morning = sorted([(h, v) for h, v in night if 6 <= h < 9], key=lambda x: x[0])
        if morning:
            out['hrv_morning'] = f"{morning[-1][1]:.0f}"

# v9: 7 日滚动 HRV 均值——从 daily-canonical.jsonl 读最近 7 天，避免单夜采样误导
canonical_file_hrv = os.path.expanduser("~/.life-log/daily-canonical.jsonl")
try:
    hrv_7d = []
    target_dt = datetime.strptime(date, '%Y-%m-%d')
    if os.path.exists(canonical_file_hrv):
        with open(canonical_file_hrv) as cf:
            for line in cf:
                line = line.strip()
                if not line: continue
                try:
                    rec = json.loads(line)
                    d = rec.get('date', '')
                    if d and 'hrv' in rec:
                        dd = datetime.strptime(d, '%Y-%m-%d')
                        if (target_dt - dd).days >= 1 and (target_dt - dd).days <= 7:
                            hrv_7d.append(float(rec['hrv']))
                except: pass
    # 加上当日自己的 HRV
    if 'hrv' in out:
        hrv_7d.append(float(out['hrv']))
    if len(hrv_7d) >= 3:
        out['hrv_7d_avg'] = f"{sum(hrv_7d)/len(hrv_7d):.0f}"
        out['hrv_7d_n'] = str(len(hrv_7d))
except Exception:
    pass  # 静默失败

# Steps — 日总和（HAE 按小时分条，需汇总）
# v6: 碎步指标升级为 bout 检测——合并相邻活跃小时识别步行段落
# 参考 JeffenCheung/personal-health-dashboard 的 bout 合并思路（5分钟阈值），
# 适配 HAE 小时级数据：相邻活跃小时 = 一个 bout，孤立的低步数小时 = 碎片
if 'step_count' in mm:
    total_steps = sum(p.get('qty', 0) or 0 for p in mm['step_count']['data'])
    if total_steps > 0:
        out['steps'] = f"{total_steps:.0f}"
    hourly = [p.get('qty', 0) or 0 for p in mm['step_count']['data']]

    # 20260704: 步数合理性校验——段誉式显式标记，不静默丢弃
    # (1) 单小时 >3000 步且相邻小时均为 0 → 疑似误计（手机放桌上/手表晃动）
    for i, s in enumerate(hourly):
        if s > 3000:
            prev_zero = i == 0 or hourly[i-1] == 0
            next_zero = i >= len(hourly)-1 or hourly[i+1] == 0
            if prev_zero and next_zero:
                out['frag_step_suspect'] = 'true'
                out['frag_step_suspect_hour'] = str(i)
                break
    # (2) 日总和 <100 步 → 手表未佩戴日
    if total_steps < 100:
        out['steps_watch_off'] = 'true'

    # ── bout 检测（小时级） ──
    # 连续活跃小时（步数>0）合并为一个 bout
    bouts = []
    current_bout_steps = 0
    current_bout_hours = 0
    for s in hourly:
        if s > 0:
            current_bout_steps += s
            current_bout_hours += 1
        else:
            if current_bout_hours > 0:
                bouts.append({'steps': current_bout_steps, 'hours': current_bout_hours})
                current_bout_steps = 0
                current_bout_hours = 0
    if current_bout_hours > 0:
        bouts.append({'steps': current_bout_steps, 'hours': current_bout_hours})

    if bouts:
        total_bouts = len(bouts)
        # 短 bout：单小时且 <500 步（孤立碎片，典型逛街/办公室来回）
        short_bouts = [b for b in bouts if b['hours'] == 1 and b['steps'] < 500]
        # 长 bout：≥2 小时连续或单小时 ≥2000 步（持续步行/跑步）
        long_bouts = [b for b in bouts if b['hours'] >= 2 or b['steps'] >= 2000]

        # 碎步指数（0-100）：短 bout 比例(40%) + bout 频率(30%) + 平均时长倒数(30%)
        short_ratio = len(short_bouts) / total_bouts
        freq_score = min(total_bouts / 12, 1.0)  # 12 bouts/天 = 满分频率
        avg_hours = sum(b['hours'] for b in bouts) / total_bouts
        gap_score = max(0, 1.0 - avg_hours / 3.0)  # 平均3h/bout → 0分

        frag_index = round((short_ratio * 40 + freq_score * 30 + gap_score * 30))
        out['frag_index'] = str(frag_index)
        out['frag_bouts'] = str(total_bouts)
        out['frag_short_bouts'] = str(len(short_bouts))
        out['frag_long_bouts'] = str(len(long_bouts))
        out['frag_avg_bout_h'] = f"{avg_hours:.1f}"

        # 等级（参考 Jeffen 的 A-E 但翻转：A=低碎片=健康）
        if frag_index <= 20:
            out['frag_grade'] = 'A'
            out['frag_label'] = 'A级·持续型——大步流星，能耗经济'
        elif frag_index <= 40:
            out['frag_grade'] = 'B'
            out['frag_label'] = 'B级·偏持续——偶有碎片但整体连贯'
        elif frag_index <= 60:
            out['frag_grade'] = 'C'
            out['frag_label'] = 'C级·混合型——碎片与持续各半'
        elif frag_index <= 80:
            out['frag_grade'] = 'D'
            out['frag_label'] = 'D级·碎片型——间歇模式耗能大，逛街型'
        else:
            out['frag_grade'] = 'E'
            out['frag_label'] = 'E级·高碎片型——频繁启停，一脚油门一脚刹车'

        # 步数集中度：Top 2 小时占总步数比例
        sorted_hours = sorted(hourly, reverse=True)
        top2 = sum(sorted_hours[:2])
        if total_steps > 0:
            out['step_concentration'] = f"{top2 / total_steps * 100:.0f}"
        out['frag_step_active_h'] = str(sum(1 for h in hourly if h > 0))
        out['frag_step_peak'] = str(max(hourly))

# v6: 步态指标（HAE 已含，简单提取）
for metric, key in [
    ('walking_speed', 'walk_speed'),
    ('walking_step_length', 'walk_step_len'),
    ('walking_asymmetry_percentage', 'walk_asymmetry'),
    ('walking_double_support_percentage', 'walk_double_support'),
]:
    if metric in mm:
        vals = [p.get('qty', 0) or 0 for p in mm[metric]['data'] if p.get('qty')]
        if vals:
            out[key] = f"{statistics.mean(vals):.1f}"

# Sleep — 用 totalSleep 和 sleepStart/sleepEnd（Apple Watch 原生字段）
if 'sleep_analysis' in mm:
    for p in mm['sleep_analysis']['data']:
        ts = float(p.get('totalSleep', 0))
        core = float(p.get('core', 0))
        deep = float(p.get('deep', 0))
        rem = float(p.get('rem', 0))
        sleep_start = p.get('sleepStart', '')
        sleep_end = p.get('sleepEnd', '')
        if ts > 0:
            out['sleep'] = f"{ts:.1f}"
            out['sleep_deep'] = f"{deep:.1f}"
            out['sleep_rem'] = f"{rem:.1f}"
            out['sleep_start'] = sleep_start
            out['sleep_end'] = sleep_end
            break
        elif core + deep + rem > 0:
            out['sleep'] = f"{core+deep+rem:.1f}"
            out['sleep_deep'] = f"{deep:.1f}"
            out['sleep_rem'] = f"{rem:.1f}"
            out['sleep_start'] = sleep_start
            out['sleep_end'] = sleep_end
            break

# 20260704: 睡眠夜晚归属校验（方案①+⑧）
# Apple Watch 的 sleepStart 记录入睡时刻。HAE 文件 date=N 中的睡眠是 N-1→N 夜。
# 校验 sleepStart 是否落在预期夜晚窗口 [expected_night 18:00, expected_night+1 12:00]。
if 'sleep_start' in out:
    try:
        ss = datetime.strptime(out['sleep_start'][:19], '%Y-%m-%d %H:%M:%S')
        if expected_sleep_night:
            expected_night = datetime.strptime(expected_sleep_night, '%Y-%m-%d')
        else:
            expected_night = datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)
        window_start = expected_night.replace(hour=18, minute=0, second=0)
        window_end = (expected_night + timedelta(days=1)).replace(hour=12, minute=0, second=0)
        if not (window_start <= ss <= window_end):
            out['sleep_night_mismatch'] = 'true'
            out['sleep_night_expected'] = f"{expected_night.strftime('%Y-%m-%d')} 18:00 → {(expected_night + timedelta(days=1)).strftime('%Y-%m-%d')} 12:00"
            out['sleep_night_actual'] = f"{ss.strftime('%Y-%m-%d %H:%M')}"
    except (ValueError, IndexError):
        pass

# Active energy — 日总和（HAE 按小时分条，需汇总）
if 'active_energy' in mm:
    total_ae = sum(p.get('qty', 0) or 0 for p in mm['active_energy']['data'])
    if total_ae > 0:
        out['active'] = f"{total_ae:.0f}"  # kJ

# VO2Max
if 'vo2_max' in mm:
    pts = [p['qty'] for p in mm['vo2_max']['data'] if p.get('qty')]
    if pts:
        out['vo2max'] = f"{pts[-1]:.1f}"

# Time in Daylight (20260718, #42) — Apple Watch 环境光传感器，watchOS 10+
# HAE 导出为日总量(分钟)，可能多 source 条目，sum 汇总。
# 用于"日照×入睡晚"观察规则（见 lifereview-daily SKILL.md）。
if 'time_in_daylight' in mm:
    total_dl = sum(p.get('qty', 0) or 0 for p in mm['time_in_daylight']['data'])
    if total_dl > 0:
        out['daylight_min'] = f"{total_dl:.0f}"

# Respiratory rate (nighttime) — sleep quality indicator
if 'respiratory_rate' in mm:
    pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['respiratory_rate']['data'] if p.get('qty')]
    night = [v for h, v in pts if 0 <= h < 9]
    if night:
        out['resp_rate'] = f"{statistics.median(night):.1f}"
        out['resp_rate_min'] = f"{min(night):.0f}"
        out['resp_rate_max'] = f"{max(night):.0f}"

# Walking HR — 取均值（可能有多条记录）
if 'walking_heart_rate_average' in mm:
    pts = [p['qty'] for p in mm['walking_heart_rate_average']['data'] if p.get('qty')]
    if pts:
        out['walk_hr'] = f"{sum(pts)/len(pts):.0f}"

# VO2Max (from 6-year CSV — most complete source, not in daily JSON)
vo2_csv = "/Users/nixon/.proma/agent-workspaces/default/be7433aa-7436-452b-9968-85888bc144b3/health_export_big/HealthAutoExport-2020-05-27-2026-06-03.csv"
if os.path.exists(vo2_csv):
    try:
        with open(vo2_csv) as vf:
            header = vf.readline().strip().split(',')
            vo2_col = next((i for i, c in enumerate(header) if 'VO2' in c), None)
            if vo2_col is not None:
                vo2_readings = []
                for line in vf:
                    parts = line.strip().split(',')
                    if len(parts) > vo2_col and parts[vo2_col]:
                        try:
                            v = float(parts[vo2_col])
                            if v > 0:
                                vo2_readings.append((parts[0][:10], v))
                        except: pass
                if vo2_readings:
                    latest_date, latest_val = vo2_readings[-1]
                    peak_val = max(v for _, v in vo2_readings)
                    out['vo2max'] = f"{latest_val:.1f}"
                    out['vo2max_date'] = latest_date
                    out['vo2max_peak'] = f"{peak_val:.1f}"
                    out['vo2max_to_peak'] = f"{peak_val - latest_val:.1f}"
                    # 90-day trend (VO2Max changes slowly)
                    cutoff = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')
                    recent90 = [(d, v) for d, v in vo2_readings if d >= cutoff]
                    if len(recent90) >= 3:
                        out['vo2max_90d_trend'] = f"{recent90[-1][1] - recent90[0][1]:+.1f}"
    except: pass

# v7: 写入 daily-canonical.jsonl（跨日查询不再逐文件读取）
canonical_file = os.path.expanduser("~/.life-log/daily-canonical.jsonl")
try:
    existing_dates = set()
    if os.path.exists(canonical_file):
        with open(canonical_file) as cf:
            for line in cf:
                line = line.strip()
                if line:
                    try:
                        existing_dates.add(json.loads(line).get('date', ''))
                    except: pass
    if date not in existing_dates:
        out['date'] = date
        with open(canonical_file, 'a') as cf:
            cf.write(json.dumps(out, ensure_ascii=False) + '\n')
except Exception:
    pass  # 静默失败，不影响主流程

print(json.dumps(out))

# v10: 方案⑧——若显式指定了 --expected-sleep-night 且不匹配，exit 2
# 调用方（如自动化脚本）可据此决定：降级生成 / 延迟重试 / 仅分析白天活动
if out.get('sleep_night_mismatch') == 'true' and expected_sleep_night:
    mismatch_msg = (
        f"SLEEP_NIGHT_MISMATCH: expected {expected_sleep_night}→"
        f"{(datetime.strptime(expected_sleep_night, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')}, "
        f"got sleepStart {out.get('sleep_night_actual', '?')}"
    )
    print(mismatch_msg, file=sys.stderr)
    sys.exit(2)
