#!/usr/bin/env python3
"""health-freshness.py — 检查 HAE 数据新鲜度
输出 JSON: {fresh, mtime_age_h, data_lag_h, internal_latest, file_mtime, warning}
fresh=false 且 mtime_age_h > 4 → 数据已过期，解读需谨慎

⚠️ 使用前替换 <YOUR_HEALTH_EXPORT_PATH> → HAE JSON 所在目录
"""
import json, os, sys
from datetime import datetime

date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
now = datetime.now().timestamp()

# 双目录检查 — 替换为你的 HAE 路径
dirs = [
    os.path.expanduser("<YOUR_HEALTH_EXPORT_PATH>/iCloud for Proma"),
    os.path.expanduser("<YOUR_HEALTH_EXPORT_PATH>/新自动化流程"),
]

result = {"fresh": False, "mtime_age_h": None, "data_lag_h": None,
          "internal_latest": None, "file_mtime": None, "warning": "", "file_found": False}

for d in dirs:
    fname = os.path.join(d, f"HealthAutoExport-{date}.json")
    if not os.path.exists(fname):
        continue

    result["file_found"] = True
    mtime = os.path.getmtime(fname)
    mtime_dt = datetime.fromtimestamp(mtime)
    result["file_mtime"] = mtime_dt.strftime('%Y-%m-%d %H:%M:%S')
    result["mtime_age_h"] = round((now - mtime) / 3600, 1)

    # 检查数据内部最新时间戳
    data = json.load(open(fname))
    mm = {m['name']: m for m in data['data']['metrics']}
    latest_ts = ""
    for name, metric in mm.items():
        for p in metric.get('data', []):
            dstr = p.get('date', '')
            if dstr and dstr > latest_ts:
                latest_ts = dstr

    if latest_ts:
        result["internal_latest"] = latest_ts[:19]
        try:
            internal_dt = datetime.strptime(latest_ts[:19], '%Y-%m-%d %H:%M:%S')
            result["data_lag_h"] = round((now - internal_dt.timestamp()) / 3600, 1)
        except:
            pass

    # 新鲜度判定
    age = result["mtime_age_h"]
    if age <= 2:
        result["fresh"] = True
        result["warning"] = ""
    elif age <= 4:
        result["fresh"] = True
        result["warning"] = f"数据 {age:.0f}h 未更新，可能有延迟"
    elif age <= 8:
        result["fresh"] = False
        result["warning"] = f"⚠️ 数据已 {age:.0f}h 未同步——解读可能基于不完整信息"
    else:
        result["fresh"] = False
        result["warning"] = f"🔴 数据已 {age:.0f}h 未同步——严重过期，优先用日历+Looki，HAE 数据仅供参考"

    break  # 只在第一个找到的目录检查

if not result["file_found"]:
    result["warning"] = "🔴 未找到 HAE 数据文件"

print(json.dumps(result, ensure_ascii=False))
