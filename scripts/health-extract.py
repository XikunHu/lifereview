#!/usr/bin/env python3
"""health-extract.py v4 — 从 HAE 自动化 JSON 提取指定日期的生理指标
HRV/RHR 取中位数抗离群，避免单个噪声采样点污染结果
v4: 修复步数/活跃能量按小时汇总（原仅取首个条目）、Walking HR 改用均值

⚠️ 使用前替换：
  - <YOUR_HEALTH_EXPORT_PATH> → HAE JSON 所在目录
  - <YOUR_VO2MAX_CSV_PATH> → 长期健康数据 CSV 路径（可选）
"""
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
if 'step_count' in mm:
    total_steps = sum(p.get('qty', 0) or 0 for p in mm['step_count']['data'])
    if total_steps > 0:
        out['steps'] = f"{total_steps:.0f}"

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
# 替换 <YOUR_VO2MAX_CSV_PATH> 为你的长期健康数据 CSV
vo2_csv = os.path.expanduser("<YOUR_VO2MAX_CSV_PATH>")
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
