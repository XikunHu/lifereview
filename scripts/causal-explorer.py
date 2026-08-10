#!/usr/bin/env python3
"""causal-explorer.py v2 — 通过 curl 子进程调用 Looki API，规避 SSL 问题"""
import json, os, re, subprocess, sys
from pathlib import Path
from collections import defaultdict

LOG_DIR = Path.home() / ".life-log"
CRED_FILE = Path.home() / ".config/looki/credentials.json"

if not CRED_FILE.exists():
    print("❌ Looki credentials not found"); sys.exit(1)

creds = json.loads(CRED_FILE.read_text())
BASE = creds["base_url"]
KEY = creds["api_key"]

def looki(path, params=None):
    url = f"{BASE}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    try:
        r = subprocess.run(
            ["curl", "-sS", "--max-time", "20", "-H", f"X-API-Key: {KEY}", url],
            capture_output=True, text=True, timeout=25
        )
        return json.loads(r.stdout) if r.stdout else {}
    except Exception as e:
        return {"error": str(e)}

# ═══ 1. 加载每日评分 ═══
print("═" * 50)
print("1. 每日评分档案")
print("═" * 50)

daily = {}
for f in sorted(LOG_DIR.glob("2026-*.md")):
    date = f.stem
    text = f.read_text()
    # P2 修复（2026-08-08）：跳过 Looki 断流时按日历估算的假评分（6/5、6/9、6/17 等）
    # 这些天的精力分不是行为观察，是数据缺失时的估算值，混入基线会污染统计
    if re.search(r'评分根据日历负载估算|评分不可用|非行为观察|Looki 未开启', text):
        continue
    em = re.search(r'精力\s*\|\s*(\d+)/10', text)
    fm = re.search(r'专注\s*\|\s*(\d+)/10', text)
    sm = re.search(r'压力\s*\|\s*(\d+)/10', text)
    if em:
        daily[date] = {
            "energy": int(em.group(1)),
            "focus": int(fm.group(1)) if fm else None,
            "stress": int(sm.group(1)) if sm else None,
            "rescue": bool(re.search(r'精力求救.*?:\s*\S', text)),
            "indulge": bool(re.search(r'代偿/提神.*?:\s*\S', text)),
            "recover": bool(re.search(r'主动恢复.*?:\s*\S', text)),
        }

for d, s in sorted(daily.items()):
    print(f"  {d}  精力{s['energy']} 专注{s['focus']} 压力{s['stress']}")

# ═══ 2. 饮食-精力 ═══
print(f"\n{'═' * 50}")
print("2. 饮食-精力关联")
print("═" * 50)

fy = looki("/for_you/items", {"limit": 30})
items = fy.get("data", {}).get("items", [])
diet_items = [i for i in items if "饮食" in i.get("title", "")]
print(f"  For You 共 {len(items)} 条, 饮食分析 {len(diet_items)} 条")

diet_data = []
for item in diet_items:
    date = item.get("recorded_at", "")[:10]
    desc = item.get("description", "").strip()
    if date in daily:
        diet_data.append({"date": date, "desc": desc[:100], "energy": daily[date]["energy"]})
        print(f"  {date}  精力{daily[date]['energy']}  {desc[:80]}")

if diet_data:
    # 早餐信号
    with_bfast = [d for d in diet_data if "早餐" in d["desc"] and "补" not in d["desc"]]
    without_bfast = [d for d in diet_data if d not in with_bfast]
    if with_bfast and without_bfast:
        avg_w = sum(d["energy"] for d in with_bfast) / len(with_bfast)
        avg_wo = sum(d["energy"] for d in without_bfast) / len(without_bfast)
        print(f"\n  🔍 有早餐: 精力均值 {avg_w:.1f} ({len(with_bfast)}天) vs 无/补早餐: {avg_wo:.1f} ({len(without_bfast)}天)")
    else:
        print(f"\n  📊 已记录 {len(diet_data)} 天饮食-精力配对，待更多数据")
else:
    print("  ⚠️ 饮食分析日期与日志日期无交集")

# ═══ 3. 语义搜索 ═══
print(f"\n{'═' * 50}")
print("3. 语义搜索因果链")
print("═" * 50)

queries = [
    ("电话亭", "深度工作"),
    ("火锅", "饮食"),
    ("荔枝", "能量补给"),
    ("深夜", "夜间模式"),
    ("会议", "协作密度"),
]

search_results = {}
for q, label in queries:
    r = looki("/moments/search", {"query": q, "page_size": 5})
    err = r.get("error")
    if err:
        print(f"  {q}: ❌ {err}")
        continue
    items = r.get("data", {}).get("items", [])
    dates = sorted(set(i["date"] for i in items if "date" in i))
    search_results[q] = {"items": items, "dates": dates, "label": label}
    print(f"  🔎 {q} → {len(items)}条, {len(dates)}天: {dates}")

# ═══ 4. 因果发现 ═══
print(f"\n{'═' * 50}")
print("4. 初步因果发现")
print("═" * 50)

# 电话亭 ↔ 专注
if "电话亭" in search_results:
    booth_dates = set(search_results["电话亭"]["dates"])
    booth_s = [daily[d]["focus"] for d in booth_dates if d in daily]
    non_s = [daily[d]["focus"] for d in daily if d not in booth_dates]
    if booth_s and non_s:
        print(f"\n  📌 电话亭日专注 {sum(booth_s)/len(booth_s):.1f} vs 非电话亭日 {sum(non_s)/len(non_s):.1f}")

# 总体基线
es = [s["energy"] for s in daily.values()]
fs = [s["focus"] for s in daily.values() if s["focus"]]
ss = [s["stress"] for s in daily.values() if s["stress"]]
if es:
    print(f"\n  📊 {len(daily)}天基线: 精力均值{sum(es)/len(es):.1f} 专注均值{sum(fs)/len(fs):.1f} 压力均值{sum(ss)/len(ss):.1f}")

# 隔日对比
if len(daily) >= 2:
    dates_sorted = sorted(daily.keys())
    print(f"\n  📈 日间变化:")
    for i in range(1, len(dates_sorted)):
        prev = daily[dates_sorted[i-1]]
        curr = daily[dates_sorted[i]]
        print(f"     {dates_sorted[i-1]} → {dates_sorted[i]}: 精力{prev['energy']}→{curr['energy']} 专注{prev['focus']}→{curr['focus']}")

# ═══ 5. 行为信号 → 精力关联（P3 修复 2026-08-08：数据驱动，不固定三类）═══
print(f"\n{'═' * 50}")
print("5. 行为信号 → 精力关联（数据驱动）")
print("═" * 50)
print("  追踪：当天日报里实际出现的行为信号（无论哪类）与精力的关系")

def signal_corr(key, cn_name):
    """对比 有该信号日 vs 无该信号日 的精力均值"""
    with_sig = [daily[d]["energy"] for d in daily if daily[d].get(key)]
    without_sig = [daily[d]["energy"] for d in daily if not daily[d].get(key)]
    sig_dates = sorted(d for d in daily if daily[d].get(key))
    if with_sig and without_sig:
        diff = sum(with_sig)/len(with_sig) - sum(without_sig)/len(without_sig)
        print(f"\n  📌 {cn_name}")
        print(f"     出现日精力均值 {sum(with_sig)/len(with_sig):.1f} ({len(with_sig)}天) vs 未出现日 {sum(without_sig)/len(without_sig):.1f} ({len(without_sig)}天)")
        print(f"     差值 {diff:+.1f}  →  {'信号日精力更低' if diff < -0.5 else ('信号日精力更高' if diff > 0.5 else '暂无明显差异')}")
        print(f"     出现日期: {sig_dates}")
    elif with_sig:
        print(f"\n  📌 {cn_name}: {len(with_sig)}天全部出现，无对照组")
    else:
        print(f"\n  📌 {cn_name}: 暂未在任何一天捕捉到")

# P3：先动态扫描所有日志，收集实际出现的行为信号行（不只三类）
# 每行格式如「🍬 **代偿/提神**（刺激物或零食补偿）: 吃零食」
import re as _re
signal_rows = {}  # signal_line -> [dates]
for f in sorted(LOG_DIR.glob("2026-*.md")):
    date = f.stem
    text = f.read_text()
    for m in _re.finditer(r'^[-*]\s*([^:]{2,30}?)\s*[:：]\s*(.{2,60})$', text, _re.M):
        label = m.group(1).strip().lstrip('*').strip()
        detail = m.group(2).strip()
        # 只收录与行为信号相关的行（含 🆘/🍬/😴 emoji 或 求救/代偿/恢复/小憩/零食/刷手机 等关键词）
        if any(k in label for k in ['求救', '代偿', '恢复', '🆘', '🍬', '😴']) or any(k in detail for k in ['刷手机', '零食', '可乐', '奶茶', '小憩', '午睡', '咖啡', '发呆']):
            row = f"{label}: {detail}"
            signal_rows.setdefault(row, []).append(date)

if signal_rows:
    print(f"\n  实际捕捉到的行为信号行（{len(signal_rows)} 类）：")
    for row, dates in sorted(signal_rows.items(), key=lambda x: -len(x[1])):
        print(f"    {row}  ({len(dates)}天: {', '.join(dates[:6])}{'…' if len(dates)>6 else ''})")
    # 对出现≥2天的信号行，计算有/无该行为日的精力差异（数据驱动，不预设三类）
    print(f"\n  行为日 vs 无行为日 的精力差异（出现≥2天才算）：")
    for row, dates in sorted(signal_rows.items(), key=lambda x: -len(x[1])):
        if len(dates) < 2:
            continue
        with_e = [daily[d]["energy"] for d in dates if d in daily and daily[d].get("energy")]
        without_e = [daily[d]["energy"] for d in daily if d not in dates and daily[d].get("energy")]
        if with_e and without_e:
            diff = sum(with_e)/len(with_e) - sum(without_e)/len(without_e)
            verdict = "该行为日精力更低" if diff < -0.5 else ("该行为日精力更高" if diff > 0.5 else "无明显差异")
            print(f"    {row} → {diff:+.1f} ({verdict})")
else:
    print("  日志中未捕捉到行为信号行（日报格式可能已变化）")

print(f"\n{'═' * 50}")
print(f"数据: {len(daily)}天日志, {len(diet_data)}条饮食, {len(search_results)}个搜索维度")
print(f"里程碑: 需≥14天日志做首次完整因果建模 (还需{max(0,14-len(daily))}天)")
print("═" * 50)
