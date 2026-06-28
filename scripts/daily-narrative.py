#!/usr/bin/env python3
"""daily-narrative.py — 多源数据融合，生成大白话日常叙事

⚠️ 使用前替换所有 <YOUR_*> 占位符为你的实际值。
   搜索 <YOUR_ 可找到所有需要替换的位置。
"""

#!/usr/bin/env python3

"""daily-narrative.py — 多源数据融合，生成大白话日常叙事

替换原来的「精力 5 | 专注 8 | 压力 1」数字格式

输出三部分：叙事段落 + 身体一句话 + 昨日新视角

用法: daily-narrative.py <health_json> <log_file> <date>

"""

import json, re, sys, random

from pathlib import Path

from datetime import datetime



if len(sys.argv) < 3:

    sys.exit(0)



health_json = sys.argv[1]

log_file = sys.argv[2]

date = sys.argv[3]



# ═══ 加载数据 ═══

try:

    health = json.load(open(health_json))

    mm = {m['name']: m for m in health['data']['metrics']}

except Exception:

    mm = {}



def _hour(p):

    try: return int(p['date'].split()[1][:2])

    except Exception: return -1



# RHR

rhr = None

if 'resting_heart_rate' in mm:

    vals = [p['qty'] for p in mm['resting_heart_rate']['data'] if p.get('qty')]

    if vals: rhr = round(sum(vals)/len(vals))



# HRV (夜间窗口)

hrv = None

if 'heart_rate_variability' in mm:

    pts = [(_hour(p), p['qty']) for p in mm['heart_rate_variability']['data'] if p.get('qty')]

    night = [v for h, v in pts if 0 <= h < 9]

    if night:

        import statistics

        m = statistics.median(night)

        clean = [v for v in night if v <= m * 2] or night

        hrv = round(statistics.median(clean))



# 睡眠

sleep_total = sleep_deep = sleep_rem = None

if 'sleep_analysis' in mm:

    for p in mm['sleep_analysis']['data']:

        c = float(p.get('core', 0)); d = float(p.get('deep', 0)); r = float(p.get('rem', 0))

        if c+d+r > 0: sleep_total = c+d+r; sleep_deep = d; sleep_rem = r; break



# 步数

steps = None

if 'step_count' in mm:

    vals = [p['qty'] for p in mm['step_count']['data'] if p.get('qty')]

    if vals: steps = round(sum(vals))



# ═══ Looki 日志 ═══

log_text = ""

looki_moments = 0

looki_scenes = []  # 解析后的 Looki 场景列表，含标题/时间/描述/特征

meetings = []

mtg_count = 0

b2b = 0

cal_h = 0

indulge_signals = []

rescue_signals = []

recover_signals = []

early_wake = False

late_night = False

phone_booth = 0



if Path(log_file).exists():

    log_text = Path(log_file).read_text()

    em = re.search(r'精力\s*\|\s*(\d+)/10', log_text)

    fm = re.search(r'专注\s*\|\s*(\d+)/10', log_text)

    sm = re.search(r'压力\s*\|\s*(\d+)/10', log_text)

    energy = int(em.group(1)) if em else None

    focus = int(fm.group(1)) if fm else None

    stress = int(sm.group(1)) if sm else None



    # 会议

    meetings = re.findall(r'\| (\d{2}:\d{2}) - (\d{2}:\d{2}) \| (.+?) \|', log_text)

    mtg_count = len(meetings)

    b2b_m = re.search(r'背靠背 ≥(\d+) 连', log_text)

    b2b = int(b2b_m.group(1)) if b2b_m else 0

    cal_h_m = re.search(r'总时长约 ([\d.]+)h', log_text)

    cal_h = float(cal_h_m.group(1)) if cal_h_m else 0



    # 状态信号

    m = re.search(r'精力求救.*?:\s*(.+?)(?:\n|$)', log_text)

    if m: rescue_signals = m.group(1).strip().split('、')

    m = re.search(r'代偿/提神.*?:\s*(.+?)(?:\n|$)', log_text)

    if m: indulge_signals = m.group(1).strip().split('、')

    m = re.search(r'主动恢复.*?:\s*(.+?)(?:\n|$)', log_text)

    if m: recover_signals = m.group(1).strip().split('、')



    # 电话亭

    phone_booth = len(re.findall(r'电话亭', log_text))

    # Looki moments count

    looki_moments = len(re.findall(r'^\d+\. \*\*', log_text, re.MULTILINE))

    # 解析 Looki moments 的完整内容（标题+时间+描述）——这是 Looki 真正的价值
    moment_pattern = re.compile(r'^(\d+)\. \*\*(.+?)\*\*\s*\n\s*(\d{4}-\d{2}-\d{2}T[\d:]+) → (\d{4}-\d{2}-\d{2}T[\d:]+)\s*\n\s*(.+?)(?=\n\d+\. \*\*|\n> |\Z)', re.MULTILINE | re.DOTALL)
    for m in moment_pattern.finditer(log_text):
        num, title, start, end, desc = m.groups()
        # 计算时长
        try:
            from datetime import datetime as _dt
            dur = (_dt.fromisoformat(start) - _dt.fromisoformat(end.replace('Z',''))).total_seconds() / 60
            dur_min = abs(int(dur))
        except:
            dur_min = 0
        looki_scenes.append({
            'num': int(num),
            'title': title.strip(),
            'start': start,
            'end': end,
            'duration_min': dur_min,
            'description': desc.strip()
        })

    # 如果日志中 Looki moments 异常少（<8），尝试从 API 直接补充
    if looki_moments < 8:
        try:
            import subprocess as _sp, json as _jm
            _cr = Path.home() / ".config/looki/credentials.json"
            if _cr.exists():
                _cred = _jm.loads(_cr.read_text())
                _api_r = _sp.run(['curl', '-sS', '--max-time', '15',
                    '-H', f"X-API-Key: {_cred.get('api_key','')}",
                    '--noproxy', '*',
                    f"{_cred.get('base_url','https://open.looki.ai')}/api/v1/moments?on_date={date}"],
                    capture_output=True, text=True, timeout=20)
                _api_d = _jm.loads(_api_r.stdout)
                _api_m = _api_d.get('data', [])
                if len(_api_m) > looki_moments:
                    looki_scenes = []
                    for mi, mv in enumerate(_api_m):
                        dur_min = 0
                        try:
                            from datetime import datetime as _dt2
                            dur_min = abs(int((_dt2.fromisoformat(mv['start_time']) - _dt2.fromisoformat(mv['end_time'].replace('Z',''))).total_seconds() / 60))
                        except: pass
                        looki_scenes.append({
                            'num': mi+1, 'title': mv.get('title','').strip(),
                            'start': mv.get('start_time',''), 'end': mv.get('end_time',''),
                            'duration_min': dur_min, 'description': mv.get('description','').strip()
                        })
                    looki_moments = len(looki_scenes)
        except: pass

    # 早起

    early_wake = bool(re.search(r'早起', log_text))

    # 深夜

    late_night = bool(re.search(r'晚间日程延至', log_text))

else:

    energy = focus = stress = None



# ═══ 1. 大白话叙事 ═══

narrative_parts = []

# HAE 时效性检查——HAE 文件日期晚于分析日期=睡眠数据有昨晚信息；早于=回退数据
_hae_date_label = ""
try:
    import datetime as _hdt
    _he_name = Path(sys.argv[1]).name.replace("HealthAutoExport-", "").replace(".json", "")
    _he_dt = _hdt.datetime.strptime(_he_name[:10], '%Y-%m-%d')
    _target_dt = _hdt.datetime.strptime(date, '%Y-%m-%d')
    if _he_dt < _target_dt:
        _days_off = (_target_dt - _he_dt).days
        _hae_date_label = f"（HAE数据延迟{_days_off}天，以下健康数字来自{_he_name[:10]}）"
except: pass

if _hae_date_label:
    narrative_parts.append(_hae_date_label)

# 睡眠数据：优先用今天 HAE（昨晚睡眠），HAE JSON 中的睡眠是前一晚→当天早晨
# 分析"昨天"时传入的是昨天的 HAE，其中睡眠是前天晚上的——时态会错
# 修正：睡眠数据从今天 HAE 读取
_today_he = f"<YOUR_HEALTH_EXPORT_PATH>/新自动化流程/HealthAutoExport-{(datetime.strptime(date, "%Y-%m-%d") + __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")}.json"
_narrative_sleep = sleep_total
_narrative_deep = sleep_deep
if Path(_today_he).exists():
    try:
        _hd = json.loads(Path(_today_he).read_text())
        _hm = {m['name']: m for m in _hd['data']['metrics']}
        if 'sleep_analysis' in _hm:
            for _p in _hm['sleep_analysis']['data']:
                _c = float(_p.get('core', 0)); _d = float(_p.get('deep', 0)); _r = float(_p.get('rem', 0))
                if _c+_d+_r > 0:
                    _narrative_sleep = _c+_d+_r
                    _narrative_deep = _d
                    break
    except: pass

# 睡眠开路

if _narrative_sleep and rhr:

    if _narrative_sleep >= 7 and rhr < 50:

        narrative_parts.append(f"睡了 {_narrative_sleep:.1f}h，心率 {rhr}，身体恢复得不错")

    elif _narrative_sleep < 6.5:

        deep_note = f"，深睡只有{_narrative_deep:.1f}h" if _narrative_deep and _narrative_deep < 0.8 else ""

        narrative_parts.append(f"只睡了 {_narrative_sleep:.1f}h{deep_note}——当天的精力天花板被睡眠压低了")

    elif rhr and rhr >= 53:

        narrative_parts.append(f"心率 {rhr} 偏高，身体在扛东西（前晚喝酒或高强度残留）")

    else:

        narrative_parts.append(f"睡了 {_narrative_sleep:.1f}h，心率 {rhr}")



# 心率数据（白天心率范围——比 RHR 更能说明当天真实负载）

try:

    if 'heart_rate' in mm:

        hr_pts = [(int(p['date'].split()[1][:2]), float(p.get('Avg', 0))) for p in mm['heart_rate']['data'] if p.get('Avg')]

        daytime = [(h, v) for h, v in hr_pts if 8 <= h < 22]

        if daytime:

            d_vals = [v for _, v in daytime]

            d_min = min(d_vals); d_max = max(d_vals); d_avg = sum(d_vals)/len(d_vals)

            if d_max > 100:

                narrative_parts.append(f"白天心率最高到 {d_max:.0f}（平均 {d_avg:.0f}）——当天的身体负载不轻")

            elif d_max > 85:

                narrative_parts.append(f"白天心率波动在 {d_min:.0f}-{d_max:.0f}，正常范围")

            else:

                narrative_parts.append(f"全天心率很平稳（{d_min:.0f}-{d_max:.0f}），身体负荷不高")

except: pass



# 会议 — 语义分类而不是只计数
if mtg_count > 0:
    # 对每个日程做语义归类
    mtg_cats = []
    for s, e, title in meetings:
        if any(kw in title for kw in ['会','讨论','对齐','评审','周会','同步','沟通','汇报','方案','需求','项目','设计']):
            mtg_cats.append('协作')
        elif any(kw in title for kw in ['健身','跑步','训练','锻炼','椭圆机','力量']):
            mtg_cats.append('运动')
        elif any(kw in title for kw in ['写','搞','做','整理','准备','材料','文档','产出','测试']):
            mtg_cats.append('产出')
        elif any(kw in title for kw in ['吃饭','午餐','晚餐','聚餐']):
            mtg_cats.append('用餐')
        elif any(kw in title for kw in ['飞机','航班','高铁','火车','出发','去','抵达','机场']):
            mtg_cats.append('出行')
        elif any(kw in title for kw in ['咖啡','茶','饮品','星巴克']):
            mtg_cats.append('茶歇')
        elif any(kw in title for kw in ['买','取','寄','快递','缴费','房租']):
            mtg_cats.append('琐事')
        elif any(kw in title for kw in ['休息','假期','休假','放假']):
            mtg_cats.append('休息')
    if mtg_cats:
        cat_summary = '·'.join(list(dict.fromkeys(mtg_cats))[:4])  # dedup & limit
        if b2b >= 5:
            narrative_parts.append(f"{mtg_count}个日程({cat_summary})、{b2b}连背靠背——下午基本没喘气缝")
        elif b2b >= 3:
            narrative_parts.append(f"{mtg_count}个日程({cat_summary})，连着{b2b}场")
        elif mtg_cats.count('协作') >= mtg_cats.count('产出'):
            narrative_parts.append(f"{mtg_count}个日程({cat_summary})，以协作讨论为主")
        else:
            narrative_parts.append(f"{mtg_count}个日程({cat_summary})，以产出/执行为主")
    else:
        # fallback: just count
        if b2b >= 3:
            narrative_parts.append(f"{mtg_count} 个会、连着排了 {b2b} 场")
        elif mtg_count >= 8:
            narrative_parts.append(f"{mtg_count} 个会但不密——中间有空档")
        else:
            narrative_parts.append(f"{mtg_count} 个会")



# Looki 行为 — 从场景描述中提取真实活动特征
if looki_scenes:
    # 提取所有场景的描述合并
    all_desc = " ".join([s['description'] for s in looki_scenes])
    all_titles = " ".join([s['title'] for s in looki_scenes])
    all_looki_text = all_desc + " " + all_titles

    # 关键场景特征
    scene_kw = {
        '深度工作': ['代码', '敲击键盘', '调试', '编写', '录入', '编辑', '文档', '键盘'],
        '会议讨论': ['讨论', '交流', '会议', '围坐', '汇报', '研讨', '聊'],
        '通勤移动': ['高铁', '飞机', '机场', '网约车', '出租车', '地铁', '步行', '车厢', '航班', '驶向'],
        '用餐': ['用餐', '吃饭', '午餐', '早餐', '晚餐', '品尝', '进食'],
        '运动': ['健身', '锻炼', '跑步', '骑行', '力量训练', '椭圆机', '瑜伽'],
        '休息恢复': ['小憩', '午睡', '闭眼', '休息', '稍作休整', '宁静', '静谧'],
        '社交': ['朋友', '伙伴', '聚餐', '相聚', '相约'],
        '家庭生活': ['婴儿', '组装', '安装', '婴儿床', '宝宝', '孩子', '整理', '收纳', '布置', '打扫', '下厨', '厨房', '烹饪', '做饭', '修理', '维修'],
    }

    detected_scenes = []
    for cat, kws in scene_kw.items():
        if any(kw in all_looki_text for kw in kws):
            detected_scenes.append(cat)

    # 场景跨度（首个→最后 moment）
    if len(looki_scenes) >= 2:
        try:
            from datetime import datetime as _dt
            first = _dt.fromisoformat(looki_scenes[0]['start'])
            last = _dt.fromisoformat(looki_scenes[-1]['end'])
            span_h = (last - first).total_seconds() / 3600
        except:
            span_h = 0
    else:
        span_h = 0

    # 拼接 Looki 叙事
    looki_narr = []
    if detected_scenes:
        looki_narr.append(f"Looki 看到 {len(looki_scenes)} 段场景：" + "、".join(detected_scenes))

    if phone_booth >= 2:
        looki_narr.append(f"进了 {phone_booth} 次电话亭保护深度时间")

    if span_h > 16:
        looki_narr.append(f"活动跨度 {span_h:.0f}h——拉得太长")
    elif span_h > 0 and span_h < 8 and len(looki_scenes) >= 3:
        looki_narr.append(f"活动集中在 {span_h:.0f}h 内——节奏紧凑")

    # 提取首尾场景作为一天的"开场"和"收尾"
    if looki_scenes:
        first_scene = looki_scenes[0]['title']
        last_scene = looki_scenes[-1]['title']
        if first_scene != last_scene:
            looki_narr.append(f"从「{first_scene[:20]}」到「{last_scene[:20]}」")

    # 高亮特别场景：时长异常长或标题有明显感情的 moment
    highlight_moments = []
    for s in looki_scenes:
        if s['duration_min'] >= 60:
            # Long moments — likely significant activities
            if any(kw in s['title'] + s['description'] for kw in ['婴儿', '组装', '安装', '宝宝', '大餐', '聚会', '生日', '朋友家', '父母', '家人']):
                highlight_moments.append(s)
            elif s['duration_min'] >= 120:
                highlight_moments.append(s)
    
    if highlight_moments:
        for hm in highlight_moments[:2]:
            hm_dur = f"{hm['duration_min']//60}h{hm['duration_min']%60}min" if hm['duration_min'] >= 60 else f"{hm['duration_min']}min"
            narrative_parts.append(f"花{hm_dur}「{hm['title']}」")

    if looki_narr:
        narrative_parts.append("。".join(looki_narr))
    elif looki_moments > 0:
        narrative_parts.append(f"Looki 捕捉了 {looki_moments} 段场景")

elif looki_moments == 0:
    narrative_parts.append("Looki 没开，只能根据日历大概推断")



# ═══ Looki 深度：能量节奏 + 行为异常 ═══
if looki_scenes:
    all_scene_text = ' '.join([s['description'] + ' ' + s['title'] for s in looki_scenes])
    # 能量标签
    energy_labels = []
    for s in looki_scenes:
        t = s['description'] + s['title']; time_str = s['start'][11:16]
        if any(kw in t for kw in ['专注','高效','投入','全神','快速','活跃','奋力','战斗模式','训练','力量','硬拉','卧推','深蹲','跑步','锻炼']):
            energy_labels.append((time_str, '高'))
        elif any(kw in t for kw in ['疲惫','疲劳','累','困','无精打采','刷手机','发呆','走神','休息','放松','小憩','静谧','躺','眯','睡眠']):
            energy_labels.append((time_str, '低'))
        elif any(kw in t for kw in ['办公','处理','操作','整理','讨论','交流','会议','键盘','代码','文档']):
            energy_labels.append((time_str, '中'))
        else:
            energy_labels.append((time_str, '中'))
    if energy_labels:
        hi_n = sum(1 for _, l in energy_labels if l == '高')
        lo_n = sum(1 for _, l in energy_labels if l == '低')
        mid_n = len(energy_labels) - hi_n - lo_n
        if hi_n >= len(energy_labels) * 0.4:
            narrative_parts.append(f"精力充沛（{hi_n}/{len(energy_labels)}段高能）")
        elif lo_n >= len(energy_labels) * 0.4:
            narrative_parts.append(f"全天偏低（{lo_n}/{len(energy_labels)}段低能）")
        else:
            narrative_parts.append(f"精力平稳（{hi_n}高·{mid_n}中·{lo_n}低）")

    # 行为异常
    anomalies = []
    n_s = len(looki_scenes)
    first_h = int(looki_scenes[0]['start'][11:13])
    if first_h < 6: anomalies.append(f"早起{looki_scenes[0]['start'][11:16]}")
    elif first_h >= 9: anomalies.append(f"晚起{looki_scenes[0]['start'][11:16]}")
    if n_s <= 3: anomalies.append(f"场景极简({n_s}段)")
    elif n_s >= 14: anomalies.append(f"场景密集({n_s}段)")
    work_n = sum(1 for s in looki_scenes if any(kw in s['description'] for kw in ['办公','会议','代码','键盘','文档','电脑']))
    social_n = sum(1 for s in looki_scenes if any(kw in s['description'] for kw in ['家人','朋友','伙伴','同事','聊天','畅谈','交流']))
    late_n = sum(1 for s in looki_scenes if int(s['start'][11:13]) >= 22)
    if work_n >= n_s * 0.8: anomalies.append("全天办公")
    if social_n >= 3: anomalies.append(f"社交活跃({social_n}段)")
    if late_n: anomalies.append(f"深夜活动({late_n}段≥22点)")
    if anomalies:
        narrative_parts.append("异常：" + "；".join(anomalies[:3]))


# 求救/代偿

if indulge_signals and ('可乐' in str(indulge_signals) or '零食' in str(indulge_signals)):

    narrative_parts.append(f"下午吃了{indulge_signals[0] if indulge_signals else '点东西'}——身体在用代偿信号提醒你精力在掉")

elif '⚡长时间看手机' in str(rescue_signals):

    narrative_parts.append("中间有一段长时间刷手机——大脑在求救，需要暂停了")



# 身体一句话（含多层基线对比：7天 / 14天 / 全年）

body_line = ""



# 计算多层基线

def compute_hrv_baseline(days_back):

    """计算过去 N 天的睡眠 HRV 中位数"""

    vals = []

    for offset in range(days_back, 0, -1):

        d = (datetime.strptime(date, '%Y-%m-%d') - __import__('datetime').timedelta(days=offset)).strftime('%Y-%m-%d')

        f2 = Path(str(Path.home()) + f"/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/新自动化流程/HealthAutoExport-{d}.json")

        if f2.exists():

            try:

                dd = json.loads(f2.read_text())

                mm2 = {m['name']: m for m in dd['data']['metrics']}

                if 'heart_rate_variability' in mm2:

                    pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm2['heart_rate_variability']['data'] if p.get('qty')]

                    night = [v for h,v in pts if 0 <= h < 9]

                    if night:

                        m = statistics.median(night)

                        clean = [v for v in night if v <= m*2] or night

                        vals.append(statistics.median(clean))

            except: pass

    return sum(vals)/len(vals) if vals else None



def compute_rhr_baseline(days_back):

    vals = []

    for offset in range(days_back, 0, -1):

        d = (datetime.strptime(date, '%Y-%m-%d') - __import__('datetime').timedelta(days=offset)).strftime('%Y-%m-%d')

        f2 = Path(str(Path.home()) + f"/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/新自动化流程/HealthAutoExport-{d}.json")

        if f2.exists():

            try:

                dd = json.loads(f2.read_text())

                mm2 = {m['name']: m for m in dd['data']['metrics']}

                if 'resting_heart_rate' in mm2:

                    r_vals = [p['qty'] for p in mm2['resting_heart_rate']['data'] if p.get('qty')]

                    if r_vals: vals.append(sum(r_vals)/len(r_vals))

            except: pass

    return sum(vals)/len(vals) if vals else None



hrv_7d = compute_hrv_baseline(7)

hrv_14d = compute_hrv_baseline(14)

rhr_7d = compute_rhr_baseline(7)

# 年度基线：来自健康分析报告（2026 年均值）

ANNUAL_RHR = 50.1

ANNUAL_HRV = 62.8



# HAE 失效时跳过 body_line
if rhr is not None and hrv is not None and _narrative_sleep is not None and not _hae_date_label:

    parts = []

    # RHR

    if rhr_7d:

        delta = rhr - rhr_7d

        if abs(delta) >= 3:

            parts.append(f"心率 {rhr}（7天均值 {rhr_7d:.0f}，{'偏高' if delta>0 else '偏低'}{abs(delta):.0f}）")

        else:

            parts.append(f"心率 {rhr}（接近 7 天均值 {rhr_7d:.0f}）")

    else:

        parts.append(f"心率 {rhr}")



    # HRV — 三层对比

    hrv_notes = []

    if hrv_7d:

        hrv_notes.append(f"7天均值 {hrv_7d:.0f}")

    if hrv_14d:

        hrv_notes.append(f"14天均值 {hrv_14d:.0f}")

    hrv_notes.append(f"年度基线 {ANNUAL_HRV:.0f}")



    if hrv_7d:

        delta = hrv - hrv_7d

        if delta >= 5:

            parts.append(f"睡眠HRV {hrv}（高于7天均值 {hrv_7d:.0f}，恢复好）")

        elif delta <= -5:

            parts.append(f"睡眠HRV {hrv}（低于7天均值 {hrv_7d:.0f}，恢复不足）")

        else:

            parts.append(f"睡眠HRV {hrv}（接近7天均值 {hrv_7d:.0f}）")

    else:

        parts.append(f"睡眠HRV {hrv}")



    # 基线参考行

    if hrv_7d or rhr_7d:

        refs = []

        if rhr_7d: refs.append(f"心率7天均值 {rhr_7d:.0f}")

        if hrv_7d: refs.append(f"HRV 7天 {hrv_7d:.0f} / 14天 {hrv_14d:.0f}" if hrv_14d else f"HRV 7天 {hrv_7d:.0f}")

        refs.append(f"年度 HRV {ANNUAL_HRV:.0f}")

        parts.append(f"(参考: {' | '.join(refs)})")



    # 睡眠

    if _narrative_sleep >= 7:

        parts.append(f"睡眠 {_narrative_sleep:.1f}h 够")

    else:

        parts.append(f"睡眠 {_narrative_sleep:.1f}h 偏少")



    body_line = " | ".join(parts)



# 步数只在晚间通知展示，晨间略过

# (morning-brief.sh 里不调用 body_line 中的步数段)



# ═══ 2. 每日新视角（真分析 + 文件追踪轮换） ═══

TRACKER = Path.home() / ".life-log/tmp/perspective-tracker.txt"



def next_perspective():

    """从追踪文件读上次用的是哪个，轮换到下一个，写回文件"""

    used = set()

    if TRACKER.exists():

        used = set(TRACKER.read_text().strip().split('\n'))

    # 全部视角

    all_p = ['hrv_trend', 'steps_vs_energy', 'meeting_type', 'looki_gap', 'sleep_quality', 'indulge_signal', 'rhr_recovery', 'load_recovery_balance', 'boundary_erosion', 'signal_cascade', 'meeting_energy', 'recovery_efficiency', 'day_ahead_risk', 'vo2max_trend', 'exercise_tracker']

    available = [p for p in all_p if p not in used]

    if not available:

        used = set()

        TRACKER.write_text('')

        available = all_p

    pick = available[0]

    with open(TRACKER, 'a') as f:

        f.write(pick + '\n')

    return pick



def gen_perspective(pick, rhr, hrv, steps, sleep_total, sleep_deep, sleep_rem, mtg_count, b2b, indulge_signals, rescue_signals, looki_moments, phone_booth, health_mm, meetings_list):

    """真正跑分析的视角"""



    if pick == 'hrv_trend':

        # 拉最近7天HRV趋势

        trend = []

        for offset in range(7, 0, -1):

            d = (datetime.strptime(date, '%Y-%m-%d') - __import__('datetime').timedelta(days=offset)).strftime('%Y-%m-%d')

            f2 = Path(str(Path.home()) + f"/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/新自动化流程/HealthAutoExport-{d}.json")

            if f2.exists():

                try:

                    dd = json.loads(f2.read_text())

                    mm2 = {m['name']: m for m in dd['data']['metrics']}

                    if 'heart_rate_variability' in mm2:

                        pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm2['heart_rate_variability']['data'] if p.get('qty')]

                        night = [v for h,v in pts if 0 <= h < 9]

                        if night:

                            m = statistics.median(night)

                            clean = [v for v in night if v <= m*2] or night

                            trend.append((d[-5:], round(statistics.median(clean))))

                except: pass

        if trend:

            vals = [v for _,v in trend]

            min_h = min(vals); max_h = max(vals)

            arrow = "↗ 恢复中" if vals[-1] > vals[0] else ("↘ 下滑中" if vals[-1] < vals[0] else "→ 平稳")

            bars = " → ".join([f"{d}:{v}" for d,v in trend])

            return f"💡 **昨日新视角：HRV 7天趋势**\n你的睡眠HRV最近7天: {bars}\n趋势: {arrow}。数据日的睡眠HRV {hrv}，7天内最高{max_h}最低{min_h}。如果连续两天低于50，说明自主神经还在压抑状态——你的身体在告诉你需要更多恢复日。"



    if pick == 'steps_vs_energy':

        return f"💡 **昨日新视角：步数在说什么**\n当天步数 {steps if steps else '?'}。过去两周你步数<5000的日子精力偏低——不是因为步数低导致精力差，而是精力差的时候你更不想动。这是一个'果'而不是'因'。反过来用：如果你发现当天步数特别低，问自己一句：是真的忙到没动，还是精力已经在掉了？"



    if pick == 'meeting_type':

        # 拉昨天的每个会 + 心率变化（实际数据）

        items = []

        try:

            if 'heart_rate' in health_mm:

                hr_pts = [(datetime.strptime(p['date'], "%Y-%m-%d %H:%M:%S %z"), float(p.get('Avg', 0))) for p in health_mm['heart_rate']['data'] if p.get('Avg')]

                if hr_pts and meetings_list:

                    all_v = [v for _, v in hr_pts]

                    baseline = sum(all_v)/len(all_v) if all_v else 60

                    for s, e, title in meetings_list[:10]:

                        if 'Proma' in title or 'Looki' in title or 'Mira' in title: continue

                        sh, sm = int(s[:2]), int(s[3:5]); eh, em = int(e[:2]), int(e[3:5])

                        yr, mo, dy = int(date[:4]), int(date[5:7]), int(date[8:10])

                        from datetime import timedelta, timezone

                        tz = hr_pts[0][0].tzinfo if hr_pts else None

                        start_dt = datetime(yr, mo, dy, sh, sm, tzinfo=tz)

                        end_dt = datetime(yr, mo, dy, eh, em, tzinfo=tz)

                        during = [v for dt, v in hr_pts if start_dt <= dt < end_dt]

                        before = [v for dt, v in hr_pts if start_dt - timedelta(minutes=15) <= dt < start_dt]

                        avg_b = sum(before)/len(before) if before else baseline

                        avg_d = sum(during)/len(during) if during else None

                        if avg_d is None: continue

                        delta = avg_d - avg_b

                        if delta > 5: icon = "🔥"

                        elif delta > 2: icon = "⚠️"

                        elif delta < -2: icon = "🧘"

                        else: icon = "→"

                        items.append((s, icon, delta, title.strip()[:45], avg_b, avg_d))

            if items:

                lines = ["💡 **昨日新视角：每个会的心率变化**\n"]

                for s, icon, d, title, ab, ad in items:

                    lines.append(f"{s}  {icon} {d:+.0f} bpm  会前{ab:.0f}→会中{ad:.0f}  {title}")

                return "\n".join(lines)

        except: pass

        return f"💡 **昨日新视角：会议类型**\n当天 {mtg_count} 个会。（心率数据不足，无法逐个分析）"



    if pick == 'looki_gap':

        # 实际拉 Looki 数据做对比

        try:

            import subprocess, json as jmod

            r = subprocess.run(["curl", "-sS", "--max-time", "10",

                "-H", f"X-API-Key: <YOUR_LOOKI_API_KEY>",

                f"https://open.looki.ai/api/v1/moments?on_date={date}"], capture_output=True, text=True)

            lm_data = jmod.loads(r.stdout)

            lm_count = len(lm_data.get("data", []))

            cal_count = mtg_count

            if lm_count == 0:

                return f"💡 **昨日新视角：Looki 没开**\n{cal_count} 个会，但 Looki 零记录——下午和晚上的真实状态全在黑暗里。如果当天你觉得特别累但不知道为什么，这就是原因：你的身体在被消耗，但没有任何客观记录能帮你回溯。"

            elif lm_count <= 3:

                return f"💡 **昨日新视角：Looki 只记录了上午**\nLooki 只捕捉到 {lm_count} 个时刻——全在上午。下午的 {cal_count} 个会全是盲区。这段时间你的心率、注意力、真实状态——全都没有客观记录。"

            else:

                return f"💡 **昨日新视角：Looki 捕捉了 {lm_count} 个时刻**\n日历上有 {cal_count} 个会。试着对比一下——Looki 拍到你在干什么的时候，和日历上写你应该在干什么的时候，是同一件事吗？gap 越大，说明你被日程推着走的程度越大。"

        except:

            return f"💡 **昨日新视角：Looki 捕捉了 {looki_moments} 个时刻**\n和日历上的 {mtg_count} 个会比起来——你的真实状态和日程表之间的gap有多大？"



    if pick == 'sleep_quality':
        # 睡眠数据来自 HAE JSON，睡眠是前一晚→当天早晨
        # 修正：用今天 HAE 读取昨晚睡眠，避免时态错乱
        today_he = f"<YOUR_HEALTH_EXPORT_PATH>/新自动化流程/HealthAutoExport-{(datetime.strptime(date, "%Y-%m-%d") + __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")}.json"
        latest_sleep = sleep_total
        latest_deep = sleep_deep
        night_label = "前一晚"
        if Path(today_he).exists():
            try:
                hd = json.loads(Path(today_he).read_text())
                hm = {m['name']: m for m in hd['data']['metrics']}
                if 'sleep_analysis' in hm:
                    for p in hm['sleep_analysis']['data']:
                        c = float(p.get('core', 0)); d = float(p.get('deep', 0)); r = float(p.get('rem', 0))
                        if c+d+r > 0:
                            latest_sleep = c+d+r
                            latest_deep = d
                            ss = p.get('sleepStart', '')[:10] if p.get('sleepStart') else ''
                            se = p.get('sleepEnd', '')[:16] if p.get('sleepEnd') else ''
                            if ss and se:
                                night_label = f"{ss}→{se[5:16]} 夜间"
                            break
            except: pass

        if latest_deep and latest_sleep and latest_sleep > 0:
            deep_pct = latest_deep / latest_sleep * 100
            if deep_pct >= 18:
                return f"💡 **昨日新视角：深睡是你的超能力**\n{night_label} 深睡 {latest_deep:.1f}h（{deep_pct:.0f}%）——很好的深睡比例。深睡是身体修复的窗口，下午精力低谷会来得更晚。"
            else:
                return f"💡 **昨日新视角：深睡不足的连锁反应**\n{night_label} 深睡只有 {latest_deep:.1f}h（{deep_pct:.0f}%）——深睡不足最直接的影响是下午的判断力下降。下午重要决策尽量排在 3 点前。"
        return f"💡 **昨日新视角：睡眠**\n睡了 {latest_sleep:.1f}h。"




    if pick == 'indulge_signal':

        if indulge_signals:

            return f"💡 **昨日新视角：代偿信号在说什么**\n当天 Looki 看到你{indulge_signals[0] if indulge_signals else '有代偿行为'}。过去两周的数据说：代偿信号（零食/可乐/咖啡）+ RHR≥53 + 精力≤2 = 身体在求救。同样的行为 + RHR正常 + 精力正常 = 纯粹享受。当天的代偿信号属于哪种？结合你的心率来判断。"

        return f"💡 **昨日新视角：代偿信号**\n当天没有捕捉到明显的零食/咖啡代偿信号。这是一个中性信号——要么状态不错不需要补偿，要么当天忙到连拿起零食的时间都没有。"



    if pick == 'rhr_recovery':

        return f"💡 **昨日新视角：心率 47 的秘密**\n你的静息心率基线是 47-50，来自6年1155次训练的运动员心脏。RHR<47=深度恢复，47-50=良好，>53=身体在扛东西。当天 RHR {rhr if rhr else '?'}，处于什么区间？这个数字比任何精力自评都诚实。明天早上看一眼——如果突然跳到53以上，问问自己昨晚发生了什么。"

    if pick == 'load_recovery_balance':

        load_score = 0

        recovery_score = 0

        details = []

        if mtg_count > 0:

            b2b_penalty = 1 + b2b * 0.15

            load_score += cal_h * b2b_penalty

            if b2b >= 5:

                details.append(f"背靠背{b2b}连")

            elif b2b >= 2:

                details.append(f"连排{b2b}场")

        eve_count = sum(1 for s, e, t in meetings if s >= "20:00" or e >= "21:00")

        if eve_count > 0:

            load_score *= 1.2

            details.append(f"{eve_count}个晚间会")

        span_m = re.search(r'超长活动跨度\s*\((\d+)h\)', log_text)

        if span_m:

            span_h = int(span_m.group(1))

            if span_h > 16:

                load_score *= 1.25

                details.append(f"活动跨度{span_h}h")

        if sleep_total:

            if sleep_total >= 7:

                recovery_score += 2

            elif sleep_total >= 6.5:

                recovery_score += 1

            else:

                recovery_score -= 1

        if hrv and hrv_7d:

            if hrv - hrv_7d > 5:

                recovery_score += 1

            elif hrv - hrv_7d < -5:

                recovery_score -= 1

        if rhr and rhr_7d:

            if rhr - rhr_7d > 3:

                recovery_score -= 1

            elif rhr - rhr_7d < -2:

                recovery_score += 1

        if load_score < 3:

            tilt = "平衡"

        elif load_score < 7 and recovery_score >= 1:

            tilt = "略偏负荷——但昨晚恢复还行，能扛"

        elif load_score >= 7 and recovery_score <= 0:

            tilt = "⚠️ 透支——当天负荷重+前晚恢复不足"

        elif load_score >= 5 and recovery_score < 0:

            tilt = "偏透支——身体还没完全恢复就被拉回高负载"

        else:

            tilt = "中性"

        detail_str = "、".join(details) if details else "负荷适中"

        eve_note = "晚间日程存在——飞机上闭眼替代刷手机。" if eve_count > 0 else "下午给自己排15分钟无会议窗口。"

        return (

            f"💡 **昨日新视角：负荷-恢复天平**\n"

            f"负荷端: {detail_str}（负荷分 {load_score:.1f}）\n"

            f"恢复端: 睡眠{sleep_total:.1f}h, 睡眠HRV {hrv}, RHR {rhr}（恢复分 {recovery_score}）\n"

            f"天平: {tilt}\n\n"

            f"颈动脉斑块是慢性透支>存钱的产物。运动员心脏让你高负荷日心率反而低——但心率平静不意味血管平静。{eve_note}"

        )



    if pick == 'boundary_erosion':

        today_dt = datetime.strptime(date, "%Y-%m-%d")

        def _get_evening(s, e):

            latest_times = []

            weekend_work = []

            for offset in range(s, e + 1):

                d = (today_dt - __import__("datetime").timedelta(days=offset)).strftime("%Y-%m-%d")

                f2 = Path(str(Path.home()) + f"/.life-log/{d}.md")

                if f2.exists():

                    txt = f2.read_text()

                    mtgs = re.findall(r'\| (\d{2}:\d{2}) - (\d{2}:\d{2}) \| (.+?) \|', txt)

                    for ss, ee, title in mtgs:

                        if "Proma" in title or "Looki" in title or "Mira" in title or "上传 Looki" in title:

                            continue

                        end_h = int(ee[:2]) + int(ee[3:5]) / 60

                        if end_h >= 18:

                            latest_times.append(end_h)

                    dow = (today_dt - __import__("datetime").timedelta(days=offset)).weekday()

                    if dow >= 5:

                        mtg_h = sum((int(e2[:2]) * 60 + int(e2[3:5]) - int(s2[:2]) * 60 - int(s2[3:5])) / 60

                                   for s2, e2, t2 in mtgs if "Proma" not in t2 and "Looki" not in t2 and "Mira" not in t2)

                        weekend_work.append(mtg_h)

            return latest_times, weekend_work

        recent_times, recent_weekend = _get_evening(1, 7)

        prior_times, prior_weekend = _get_evening(8, 14)

        lines = ["💡 **昨日新视角：边界侵蚀**\n"]

        if recent_times:

            med_recent = statistics.median(recent_times)

            h = int(med_recent)

            mv = int((med_recent - h) * 60)

            lines.append(f"过去7天晚间日程中位数: {h:02d}:{mv:02d}")

            if prior_times:

                med_prior = statistics.median(prior_times)

                h2 = int(med_prior)

                m2 = int((med_prior - h2) * 60)

                drift = med_recent - med_prior

                if drift > 0.5:

                    lines.append(f"比前7天 {h2:02d}:{m2:02d} 推迟 {int(drift*60)}分钟——边界在向后侵蚀")

                elif drift < -0.3:

                    lines.append(f"比前7天 {h2:02d}:{m2:02d} 提前 {int(abs(drift)*60)}分钟——边界在好转")

                else:

                    lines.append("边界稳定，无明显偏移")

        else:

            lines.append("过去7天无晚间日程——边界保护完好")

        if recent_weekend:

            avg_wk = sum(recent_weekend) / len(recent_weekend)

            lines.append(f"周末工作入侵: {avg_wk:.1f}h/天")

            if prior_weekend:

                avg_pwk = sum(prior_weekend) / len(prior_weekend)

                trend = "↑" if avg_wk > avg_pwk + 0.5 else ("↓" if avg_wk < avg_pwk - 0.5 else "→")

                lines.append(f"前7天 {avg_pwk:.1f}h/天，趋势 {trend}")

        lines.append("\n2024年运动371→134次——边界侵蚀是最可能的前兆。")

        return "\n".join(lines)



    if pick == 'signal_cascade':

        today_dt3 = datetime.strptime(date, "%Y-%m-%d")

        yesterday = (today_dt3 - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

        y_file = Path(str(Path.home()) + f"/.life-log/{yesterday}.md")

        lines = ["💡 **昨日新视角：信号级联**\n"]

        if y_file.exists():

            y_text = y_file.read_text()

            y_rescue = "求救" in y_text and ("刷手机" in y_text or "刷短视频" in y_text)

            y_indulge = "代偿" in y_text and ("可乐" in y_text or "零食" in y_text or "咖啡" in y_text or "甜食" in y_text)

            y_recover = "恢复" in y_text and ("小憩" in y_text or "午睡" in y_text or "躺下" in y_text)

            signals_today = [x.strip() for x in (rescue_signals + indulge_signals) if x and x.strip()]

            signal_list = []

            if y_rescue:

                signal_list.append("🆘")

            if y_indulge:

                signal_list.append("🍬")

            if y_recover:

                signal_list.append("😴")

            if signal_list:

                lines.append(f"昨天信号: {'+'.join(signal_list)}")

            else:

                lines.append("昨天信号干净")

            if signals_today:

                lines.append(f"当天信号: {', '.join(signals_today[:3])}")

            if y_rescue and y_indulge:

                lines.append("\n昨天 🆘+🍬 同时出现——最强级联前兆。历史中此组合后次日 RHR 平均+2、精力-1.5。")

                if rhr and rhr_7d and rhr > rhr_7d + 2:

                    lines.append(f"当天 RHR {rhr} 已高于 7 天均值 {rhr_7d:.0f}——级联进行中。")

                lines.append("当天主动加一个恢复动作（午休15分钟），打断级联。")

            elif y_rescue and not y_recover:

                lines.append("\n昨天有求救但无恢复——级联风险中等。")

            elif y_recover and not y_rescue:

                lines.append("\n昨天有恢复——你在主动管理。保持。")

            lines.append("\n慢性级联不中断=交感持续激活=血管承压。每次打断都是对颈动脉的保护。")

        else:

            lines.append("昨日日志缺失，无法计算级联。")

        return "\n".join(lines)


    if pick == 'meeting_energy':
        items = []
        try:
            if 'heart_rate' in health_mm:
                hr_pts = [(datetime.strptime(p['date'], "%Y-%m-%d %H:%M:%S %z"), float(p.get('Avg', 0))) for p in health_mm['heart_rate']['data'] if p.get('Avg')]
                if hr_pts and meetings_list:
                    all_v = [v for _, v in hr_pts]
                    baseline = sum(all_v)/len(all_v) if all_v else 60
                    yr, mo, dy = int(date[:4]), int(date[5:7]), int(date[8:10])
                    tz = hr_pts[0][0].tzinfo if hr_pts else None
                    from datetime import timedelta as tdelta
                    for s, e, title in meetings_list:
                        if 'Proma' in title or 'Looki' in title or 'Mira' in title: continue
                        sh, sm = int(s[:2]), int(s[3:5]); eh, em = int(e[:2]), int(e[3:5])
                        start_dt = datetime(yr, mo, dy, sh, sm, tzinfo=tz)
                        end_dt = datetime(yr, mo, dy, eh, em, tzinfo=tz)
                        during = [v for dt, v in hr_pts if start_dt <= dt < end_dt]
                        before = [v for dt, v in hr_pts if start_dt - tdelta(minutes=15) <= dt < start_dt]
                        avg_b = sum(before)/len(before) if before else baseline
                        avg_d = sum(during)/len(during) if during else None
                        if avg_d is None: continue
                        delta = avg_d - avg_b
                        cat = "🔋充能" if delta <= 0 else ("⚡耗能" if delta <= 10 else "🔥高耗能")
                        items.append((s, cat, delta, title.strip()[:45], avg_b, avg_d))
            if items:
                pos = sum(1 for _, c, _, _, _, _ in items if c == "🔋充能")
                neg = sum(1 for _, c, _, _, _, _ in items if c in ("⚡耗能", "🔥高耗能"))
                balance = "充能日" if pos >= neg else ("能量赤字日" if neg > pos else "中性日")
                lines = [f"💡 **昨日新视角：会议能量收支**\\n"]
                lines.append(f"当天{len(items)}个会: {pos}充能 {neg}耗能 → **{balance}**\\n")
                for s, cat, d, title, ab, ad in items:
                    lines.append(f"{s}  {cat} {d:+.0f} bpm  会前{ab:.0f}→会中{ad:.0f}  {title}")
                if neg > pos:
                    lines.append(f"\\n连续能量赤字日会累积恢复债务——如果连着3天赤字，第四天精力崩的概率超过70%。")
                return "\\n".join(lines)
        except: pass
        return f"💡 **昨日新视角：会议能量**\\n当天心率数据不足，无法分析。"

    if pick == 'recovery_efficiency':
        lines = ["💡 **昨日新视角：恢复效率**\\n"]
        if hrv and rhr and sleep_total:
            eff = hrv / rhr * sleep_total
            # Compare with 7-day average efficiency
            rhr_7d = compute_rhr_baseline(7)
            hrv_7d = compute_hrv_baseline(7)
            lines.append(f"当天恢复效率: **{eff:.1f}** (HRV{hrv}/RHR{rhr}×睡眠{sleep_total:.1f}h)")
            if hrv_7d and rhr_7d:
                avg_eff = hrv_7d / rhr_7d * 6.6
                if eff > avg_eff * 1.2:
                    lines.append(f"高于7天均值 {avg_eff:.1f}——当天是高效恢复日")
                elif eff < avg_eff * 0.8:
                    lines.append(f"低于7天均值 {avg_eff:.1f}——睡眠时长可能骗了你，恢复质量打折")
                    lines.append(f"\\n💡 同样的睡眠时长，恢复效率低了{(1 - eff/avg_eff)*100:.0f}%。原因通常在：酒精、深夜社交、睡前屏幕。")
                else:
                    lines.append(f"接近7天均值 {avg_eff:.1f}——恢复效率正常")
            lines.append(f"\\n这个指标回答一个问题：每睡1小时，你的身体修复了多少？HRV高+RHR低=高效；HRV低+RHR高=低效（常见于酒精/深夜社交后）。")
        else:
            lines.append("数据不足，无法计算恢复效率。")
        return "\\n".join(lines)

    if pick == 'day_ahead_risk':
        lines = ["💡 **昨日新视角：今日风险预判**\\n"]
        risk_score = 0
        flags = []

        # Yesterday's load
        if mtg_count >= 8:
            risk_score += 2
            flags.append(f"昨天{mtg_count}会——高负荷残留")
        elif mtg_count >= 5:
            risk_score += 1
        if b2b >= 3:
            risk_score += 1
            flags.append(f"背靠背{b2b}连——切换成本高")

        # Recovery quality
        if hrv and hrv < 50:
            risk_score += 2
            flags.append(f"HRV {hrv}偏低——恢复不充分")
        elif hrv and hrv < 55:
            risk_score += 1
        if rhr and rhr > 51:
            risk_score += 2
            flags.append(f"RHR {rhr}偏高——身体应激")
        if sleep_total and sleep_total < 6.5:
            risk_score += 2
            flags.append(f"睡眠{sleep_total:.1f}h不足")

        # Yesterday signals
        if rescue_signals:
            risk_score += 1
            flags.append("昨天有求救信号")

        # Today's calendar load (would need calendar data — use mtg_count as proxy)
        # For now, note that today's load isn't available in this context

        if risk_score <= 2:
            level = "🟢 低风险"
            advice = "今天按正常节奏走就行"
        elif risk_score <= 4:
            level = "🟡 中等风险"
            advice = "今天在背靠背间隙主动插一个5分钟暂停"
        elif risk_score <= 6:
            level = "🟠 偏高风险"
            advice = "今天主动保护恢复窗口——午休15分钟、会间闭眼3分钟"
        else:
            level = "🔴 高风险"
            advice = "今天最大的贡献可能是不做错误决策——非关键会议推迟、重要决策推到明天上午"

        lines.append(f"风险评分: {risk_score}/10 — {level}")
        for f in flags:
            lines.append(f"  • {f}")
        lines.append(f"\\n建议: {advice}")
        lines.append(f"\\n历史数据中，风险≥6的日子精力崩的概率>70%。这不是预言，是可打断的因果链。")
        return "\\n".join(lines)



    if pick == 'vo2max_trend':
        lines = ["💡 **昨日新视角：VO2Max 心肺适能**\\n"]
        vo2_csv = "<YOUR_VO2MAX_CSV_PATH>"
        import os as _os
        if _os.path.exists(vo2_csv):
            with open(vo2_csv) as vf:
                header = vf.readline().split(',')
                vo2_col = next((i for i, c in enumerate(header) if 'VO2' in c), None)
                if vo2_col is not None:
                    readings = []
                    for line in vf:
                        parts = line.strip().split(',')
                        if len(parts) > vo2_col and parts[vo2_col]:
                            try:
                                v = float(parts[vo2_col])
                                if v > 0: readings.append((parts[0][:10], v))
                            except: pass
                    if readings:
                        latest = readings[-1]
                        peak = max(readings, key=lambda x: x[1])
                        min_v = min(readings, key=lambda x: x[1])
                        # 90-day trend
                        from datetime import timedelta as _td
                        cutoff = (datetime.strptime(date, '%Y-%m-%d') - _td(days=90)).strftime('%Y-%m-%d')
                        recent = [(d, v) for d, v in readings if d >= cutoff]
                        
                        lines.append(f"当前: **{latest[1]:.1f}** ({latest[0]})")
                        if len(recent) >= 2:
                            delta = recent[-1][1] - recent[0][1]
                            arrow = "↗" if delta > 0.5 else ("↘" if delta < -0.5 else "→")
                            lines.append(f"90天趋势: {arrow} {delta:+.1f}")
                        lines.append(f"历史峰值: {peak[1]:.1f} ({peak[0]}) — 距峰值 {peak[1]-latest[1]:.1f}")
                        lines.append(f"历史最低: {min_v[1]:.1f} ({min_v[0]})")
                        
                        # 6-year journey in one line
                        by_year = {}
                        for d, v in readings:
                            yr = d[:4]
                            if yr not in by_year: by_year[yr] = []
                            by_year[yr].append(v)
                        journey = []
                        for yr in sorted(by_year.keys()):
                            avg = sum(by_year[yr])/len(by_year[yr])
                            journey.append(f"{yr}:{avg:.0f}")
                        lines.append(f"\\n6年轨迹: {' → '.join(journey)}")
                        
                        if len(recent) >= 3 and recent[-1][1] < recent[0][1]:
                            lines.append(f"\\n⚠️ 最近3个月 VO2Max 在下降——心肺适能是健康的长期底盘。检查: 有氧运动频率是否下降？户外跑步是否减少了？")
                        elif latest[1] > 42:
                            lines.append(f"\\n✅ VO2Max 在健康区间（>42），并保持上升趋势。继续保持每周户外跑步，目标 45。")
        else:
            lines.append("VO2Max 数据源未找到。")
        return "\\n".join(lines)



    if pick == 'exercise_tracker':
        # 从 6 年运动 CSV 提取最近 30 天运动数据
        import os as _os
        w_csv = "<YOUR_WORKOUTS_CSV_PATH>"
        from datetime import timedelta as _td2, datetime as _dt2
        cutoff = (_dt2.strptime(date, '%Y-%m-%d') - _td2(days=30)).strftime('%Y-%m-%d')
        workouts = []
        if _os.path.exists(w_csv):
            with open(w_csv) as wf:
                wf.readline()
                for line in wf:
                    p = line.strip().split(',')
                    if p[1][:10] < cutoff: continue
                    try:
                        w_type = p[0]
                        w_start = p[1][:16]
                        w_hr_max = float(p[6]) if len(p)>6 and p[6] else 0
                        w_hr_avg = float(p[7]) if len(p)>7 and p[7] else 0
                        dur_parts = p[3].split(':')
                        dur_min = int(dur_parts[0])*60 + int(dur_parts[1])
                        workouts.append({'type': w_type, 'start': w_start, 'hr_max': w_hr_max, 'hr_avg': w_hr_avg, 'dur': dur_min})
                    except: pass

        lines = ["💡 **昨日新视角：运动追踪**\\n"]
        if workouts:
            w_count = len(workouts)
            w_types = list(set(w['type'] for w in workouts))
            w_weeks = len(set(w['start'][:10] for w in workouts))
            w_hrs = sum(w['dur'] for w in workouts) // 60

            # Weekly frequency
            freq_per_wk = w_count / 4.3  # ~4.3 weeks in 30 days
            
            lines.append(f"最近30天: {w_count}次运动, 约{freq_per_wk:.1f}次/周, 总{w_hrs}h")
            lines.append(f"类型: {', '.join(w_types[:5])}")
            lines.append(f"\\n你6年月均15-20次、周均3-4次是健康底线。当前{freq_per_wk:.1f}次/周")

            if freq_per_wk < 3:
                lines.append(f"⚠️ 低于底线3次/周——运动量下降直接关联代谢恶化(2025年脂肪肝教训)")
            elif freq_per_wk < 4:
                lines.append(f"🟡 接近底线——维持≥3次/周是守住代谢健康的最低要求")
            else:
                lines.append(f"✅ 达标——运动习惯在恢复通道上")

            # Exercise → next-day RHR/HRV relationship (from causal rules)
            lines.append(f"\\n已知规律: 运动日次日精力反而更低(运动消耗+恢复不足→RHR升高)")
            lines.append(f"今天的RHR和HRV会反映昨天运动对恢复的影响——如果昨天有运动且今天RHR偏高，说明恢复没跟上")

            # Show recent workouts
            lines.append(f"\\n最近的运动:")
            for w in workouts[-5:]:
                hrs = w['dur'] // 60
                mins = w['dur'] % 60
                lines.append(f"  • {w['start'][:10]} {w['type']} {hrs}h{mins}min HRmax{w['hr_max']:.0f}")
        else:
            lines.append(f"最近30天CSV中无运动记录。数据可能不完整——最新的运动在HAE中。")

        return "\\n".join(lines)


# 生成视角

pick = next_perspective()

perspective = gen_perspective(pick, rhr, hrv, steps, sleep_total, sleep_deep, sleep_rem, mtg_count, b2b, indulge_signals, rescue_signals, looki_moments, phone_booth, mm, meetings)



# ═══ 输出 ═══

print(json.dumps({

    "narrative": "。".join(narrative_parts) + "。",

    "body_line": body_line,

    "perspective": perspective,

    "mtg_summary": f"{mtg_count}会/{cal_h:.1f}h" if mtg_count > 0 else "无会",

}, ensure_ascii=False))
