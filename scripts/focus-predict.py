#!/usr/bin/env python3
"""focus-predict.py — 从昨晚恢复数据预判今日专注能力

用法: focus-predict.py <health_json> [yesterday_log]

⚠️ 使用前替换脚本中的基线值为你的个人基线（当前为作者的值）
"""
import json, sys, os, statistics

def predict_focus(health_file, yesterday_log=None):
    """从昨晚恢复数据预判今日专注能力"""
    try:
        health = json.load(open(health_file))
        mm = {m["name"]: m for m in health["data"]["metrics"]}
    except:
        return None

    score = 7  # baseline
    factors = []
    recs = []

    # --- Sleep: the strongest predictor ---
    sleep_h = None
    deep_h = None
    if "sleep_analysis" in mm:
        for p in mm["sleep_analysis"]["data"]:
            c = float(p.get("core", 0)); d = float(p.get("deep", 0)); r = float(p.get("rem", 0))
            if c + d + r > 0:
                sleep_h = c + d + r
                deep_h = d
                break

    if sleep_h is not None:
        if sleep_h < 5:
            score -= 3
            factors.append(f"昨晚只睡了{sleep_h:.1f}h——深度专注不可能，保护性降级")
            recs.append("上午只做执行类任务（回复/审批），决策推到下午")
        elif sleep_h < 6.5:
            score -= 2
            factors.append(f"睡眠{sleep_h:.1f}h偏少——前额叶供血不足，专注时长打七折")
            recs.append("每45分钟强制暂停3分钟，不要连续深度工作超过1h")
        elif sleep_h < 7:
            score -= 1
            factors.append(f"睡眠{sleep_h:.1f}h勉强够——可以专注但容易早衰")
        else:
            score += 1
            factors.append(f"睡眠{sleep_h:.1f}h充足——今天专注的地基是好的")

    if deep_h is not None and deep_h < 0.6 and sleep_h and sleep_h < 7:
        score -= 1
        factors.append(f"深睡只有{deep_h:.1f}h——身体修复不充分，下午精力会提前掉")

    # --- HRV: autonomic recovery ---
    hrv = None
    if "heart_rate_variability" in mm:
        pts = [(int(p["date"].split()[1][:2]), p["qty"]) for p in mm["heart_rate_variability"]["data"] if p.get("qty")]
        night = [v for h, v in pts if 0 <= h < 9]
        if night:
            m = statistics.median(night)
            clean = [v for v in night if v <= m * 2] or night
            hrv = round(statistics.median(clean))

    if hrv is not None:
        if hrv < 48:
            score -= 1
            factors.append(f"睡眠HRV {hrv}偏低——自主神经还在压抑中，今天容易走神")
            recs.append("避免背靠背排会，每个会之间留10分钟清空")
        elif hrv > 62:
            score += 1
            factors.append(f"睡眠HRV {hrv}良好——自主神经恢复充分")

        # HRV 夜间分布：前半段 vs 后半段
        # 如果前半夜低、后半夜飙升（V 型），中位数可能虚高，恢复质量打折扣
        # 这不是医学判断，是数据形态标记
        if "heart_rate_variability" in mm:
            night_pts = [(int(p["date"].split()[1][:2]), p["qty"]) for p in mm["heart_rate_variability"]["data"] if p.get("qty")]
            early = [v for h, v in night_pts if 0 <= h < 4]   # 0:00-4:00
            late = [v for h, v in night_pts if 4 <= h < 9]    # 4:00-9:00
            if early and late and len(early) >= 2 and len(late) >= 2:
                early_med = statistics.median(early)
                late_med = statistics.median(late)
                # 后半夜比前半夜高出 50% 以上 → 前半夜恢复不充分
                if early_med > 0 and late_med / early_med > 1.5:
                    score -= 1
                    factors.append(f"睡眠HRV前低后高（前半夜{early_med:.0f}→后半夜{late_med:.0f}）——前半夜恢复被压制，中位数可能虚高")
                    recs.append("下午精力可能提前衰减，重要决策排上午")

    # --- RHR: physiological stress ---
    # ⚠️ 替换基线值 <YOUR_RHR_BASELINE> 为你的 RHR 年度均值
    RHR_BASELINE = 49  # <YOUR_RHR_BASELINE> — 替换为你的年度 RHR 均值
    rhr = None
    if "resting_heart_rate" in mm:
        r_vals = [p["qty"] for p in mm["resting_heart_rate"]["data"] if p.get("qty")]
        if r_vals: rhr = round(sum(r_vals) / len(r_vals))

    if rhr is not None:
        if rhr > RHR_BASELINE + 3:
            score -= 2
            factors.append(f"RHR {rhr}偏高（基线{RHR_BASELINE}）——身体在扛东西，认知资源被占用")
            recs.append("今天最大的贡献可能是「不做错误决策」而非「多做」")
        elif rhr < RHR_BASELINE - 3:
            score += 1
            factors.append(f"RHR {rhr}深度恢复——身体给了你今天全开的绿灯")

    # --- Respiratory rate: sleep quality indicator ---
    if "respiratory_rate" in mm:
        pts = [(int(p["date"].split()[1][:2]), p["qty"]) for p in mm["respiratory_rate"]["data"] if p.get("qty")]
        night = [v for h, v in pts if 0 <= h < 9]
        if night and len(night) >= 5:
            resp_med = statistics.median(night)
            if resp_med > 17.5:
                score -= 1
                factors.append(f"夜间呼吸 {resp_med:.1f}/min 偏快——睡眠中身体在做功，恢复深度不足")
                recs.append("今天多喝水，帮助代谢")
            elif resp_med <= 15.5:
                factors.append(f"夜间呼吸 {resp_med:.1f}/min 深慢——身体在深度放松中")

    # --- Yesterday's signals: cognitive carry-over ---
    if yesterday_log:
        from pathlib import Path
        log_path = Path(yesterday_log)
        if log_path.exists():
            yt = log_path.read_text()
            y_rescue = "求救" in yt and ("刷手机" in yt or "刷短视频" in yt)
            y_indulge = "代偿" in yt and ("可乐" in yt or "零食" in yt or "咖啡" in yt or "甜食" in yt)
            if y_rescue and y_indulge:
                score -= 1
                factors.append("昨天出现🆘+🍬级联——认知疲劳可能延续到今天上午")
                recs.append("上午第一件事不要开会，先做15分钟轻量任务热身")

    # --- Clamp ---
    score = max(1, min(10, score))

    # --- Generate label ---
    if score >= 8:
        label = "🟢 高——今天是你深度工作的窗口，把最重要的任务排上午"
    elif score >= 6:
        label = "🟡 中等——可以专注但续航有限，重要决策排在下午3点前"
    elif score >= 4:
        label = "🟠 偏低——今天更适合执行类任务，不要勉强深度工作"
    else:
        label = "🔴 低——今天的认知资源很有限，保护>产出"

    return {
        "score": score,
        "label": label,
        "factors": factors,
        "recommendations": recs
    }

if __name__ == "__main__":
    import sys, os
    health_file = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "<YOUR_HEALTH_EXPORT_PATH>/新自动化流程/HealthAutoExport-2026-06-16.json")
    yesterday_log = sys.argv[2] if len(sys.argv) > 2 else None
    result = predict_focus(health_file, yesterday_log) or {}
    print(json.dumps(result, ensure_ascii=False, indent=2))
