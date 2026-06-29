#!/usr/bin/env python3
"""health-extract.py v6 — 从 HAE 自动化 JSON 提取指定日期的生理指标
HRV/RHR 取中位数抗离群，避免单个噪声采样点污染结果
v4: 修复步数/活跃能量按小时汇总（原仅取首个条目）、Walking HR 改用均值
v5: 新增碎步比——间歇性走动的能耗指数（hourly阈值版）
v6: 碎步升级为 bout 检测（参考 JeffenCheung/personal-health-dashboard）、新增步态指标"""
import json, sys, statistics, os
from datetime import datetime, timedelta

data = json.load(open(sys.argv[1]))
date = sys.argv[2]
out = {}

mm = {m['name']: m for m in data['data']['metrics']}

# RHR — 取中位数（静息心率一般稳定，但仍防离群）
if 'resting_heart_rate' in mm:
    vals = [p['qty'] for p in mm['resting_heart_rate']['data'] if p.get('qty')]
    if vals:
        out['rhr'] = f"{statistics.median(vals):.0f}"
# Fallback: RHR 未同步时扫描附近几天（今天优先，昨天次之）
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
if 'heart_rate_variability' in mm:
    pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['heart_rate_variability']['data'] if p.get('qty')]
    night = [v for h, v in pts if 0 <= h < 9]
    pool = night if night else [v for _, v in pts]
    if pool:
        m = statistics.median(pool)
        clean = [v for v in pool if v <= m * 2] or pool
        out['hrv'] = f"{statistics.median(clean):.0f}"

# Steps — 日总和（HAE 按小时分条，需汇总）
# v6: 碎步指标升级为 bout 检测——合并相邻活跃小时识别步行段落
# 参考 JeffenCheung/personal-health-dashboard 的 bout 合并思路（5分钟阈值），
# 适配 HAE 小时级数据：相邻活跃小时 = 一个 bout，孤立的低步数小时 = 碎片
if 'step_count' in mm:
    total_steps = sum(p.get('qty', 0) or 0 for p in mm['step_count']['data'])
    if total_steps > 0:
        out['steps'] = f"{total_steps:.0f}"
    hourly = [p.get('qty', 0) or 0 for p in mm['step_count']['data']]

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
vo2_csv = "<YOUR_VO2MAX_CSV_PATH>"
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

print(json.dumps(out))
