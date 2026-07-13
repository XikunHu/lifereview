#!/usr/bin/env python3
"""fetch-environment.py — 拉取昨晚环境空气质量，写入 daily-canonical.jsonl（公开脱敏版）

位置逻辑（三级 fallback）：
  1. 取昨晚（分析日 N-1）20:00-23:59 + 今日 00:00-03:00 的 Looki location → 时间最晚 = 过夜地
  2. 提取城市级 → 查内置映射表得坐标
  3. 未命中 → Open-Meteo geocoding 兜底 + 缓存 geo-cache.json
  4. fallback：今日无 location → 昨日过夜地 → 常驻地（默认值，请改成你自己的）

空气质量：Open-Meteo Air Quality API（PM2.5/PM10/O3/NO2）
日期语义：分析日 N 的 environment = 昨晚（N-1）环境（匹配 date=N 的 HRV/睡眠反映 N-1 夜恢复）

用法: python3 fetch-environment.py [YYYY-MM-DD]   # 不带日期默认今天
依赖：~/.config/looki/credentials.json（无则降级到常驻地）

⚠️ 配置：把下方 HOME_COORDS 和 fallback addr 改成你自己的常驻地。
"""
import json, os, sys, ssl, urllib.request, urllib.parse, re
from datetime import datetime, timedelta

# ── 常驻地 + 主要城市坐标映射（统一用市中心级别坐标，避免暴露私人精确位置）──
# 如需更精确的常驻地，自行替换 HOME_COORDS。
CITY_COORDS = {
    "北京市": (39.9042, 116.4074, "市中心"),
    "北京":   (39.9042, 116.4074, "市中心"),
    "上海市": (31.2304, 121.4737, "市中心"),
    "上海":   (31.2304, 121.4737, "市中心"),
    "深圳市": (22.5431, 114.0579, "市中心"),
    "深圳":   (22.5431, 114.0579, "市中心"),
    "广州市": (23.1291, 113.2644, "市中心"),
    "广州":   (23.1291, 113.2644, "市中心"),
    "成都市": (30.5728, 104.0668, "市中心"),
    "成都":   (30.5728, 104.0668, "市中心"),
    "杭州市": (30.2741, 120.1551, "市中心"),
    "南京":   (32.0603, 118.7969, "市中心"),
    "西安":   (34.3416, 108.9398, "市中心"),
    "武汉":   (30.5928, 114.3055, "市中心"),
    "重庆":   (29.5630, 106.5516, "市中心"),
    "苏州":   (31.2989, 120.5853, "市中心"),
    "天津":   (39.3434, 117.3616, "市中心"),
    "青岛":   (36.0671, 120.3826, "市中心"),
    "东京":   (35.6762, 139.6503, "市中心"),
    "首尔":   (37.5665, 126.9780, "市中心"),
    "新加坡": (1.3521, 103.8198, "市中心"),
    "纽约":   (40.7128, -74.0060, "市中心"),
    "伦敦":   (51.5074, -0.1278, "市中心"),
}
# ⚠️ 替换为你自己的常驻地（默认北京）
HOME_COORDS = CITY_COORDS["北京市"]

GEO_CACHE     = os.path.expanduser("~/.life-log/tmp/geo-cache.json")
CANONICAL     = os.path.expanduser("~/.life-log/daily-canonical.jsonl")
LOOKI_CRED    = os.path.expanduser("~/.config/looki/credentials.json")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

def http_get(url, headers=None, timeout=25):  # 25s：Looki 偶尔慢
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, context=_ctx, timeout=timeout) as r:
        return json.loads(r.read())

# ── 城市提取 + 坐标解析 ──
def extract_city(address):
    """从中文地址提取城市级 key，兼容 '北京市'/'北京'"""
    if not address:
        return None
    # 去掉常见国家前缀，避免正则贪婪吃掉
    addr = re.sub(r'^(中国|中華|United States|USA)[，,]?\s*', '', address)
    # 优先匹配已知城市名（长 key 优先，处理 '北京市' vs '北京'）
    for k in sorted(CITY_COORDS.keys(), key=len, reverse=True):
        if k in addr:
            return k
    # 兜底：正则提取 XX市
    m = re.search(r'([一-龥]{2,3}市)', addr)
    if m:
        return m.group(1)
    return None

def resolve_coords(city):
    """城市 → (lat, lon, label)，内置映射优先，未命中 geocoding + 缓存"""
    if city and city in CITY_COORDS:
        return CITY_COORDS[city]
    if not city:
        return HOME_COORDS
    cache = {}
    if os.path.exists(GEO_CACHE):
        try:
            cache = json.load(open(GEO_CACHE))
        except Exception:
            pass
    if city in cache:
        return tuple(cache[city])
    try:
        data = http_get(
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={urllib.parse.quote(city)}&count=1&language=zh&format=json"
        )
        results = data.get("results", [])
        if results:
            r = results[0]
            coords = (r["latitude"], r["longitude"], r.get("name", city))
            cache[city] = list(coords)
            json.dump(cache, open(GEO_CACHE, "w"), ensure_ascii=False)
            return coords
    except Exception as e:
        print(f"geocode failed for {city}: {e}", file=sys.stderr)
    return HOME_COORDS

# ── Looki 过夜地提取 ──
def looki_client():
    if not os.path.exists(LOOKI_CRED):
        return None
    cred = json.load(open(LOOKI_CRED))
    base = cred.get("base_url", "").rstrip("/")
    key = cred.get("api_key", "")
    if not base or not key:
        return None
    def fetch(path):
        return http_get(f"{base}{path}", headers={"X-API-Key": key})
    return fetch

def get_overnight_location(anal_date, looki_fetch):
    """分析日 N 的昨晚过夜地。返回 (address, source) 或 (None, None)
    优先级：
      1. looki_overnight — N-1 晚(20-23点) + N 凌晨(0-3点) 最晚 location（最准）
      2. looki_daytime  — N-1 全天最晚 location（出差时白天 location 反映所在城市）
    （后续 main 还有 looki_yesterday / home_default 两级 fallback）"""
    if not looki_fetch:
        return None, None
    n_minus1 = (datetime.strptime(anal_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    strict = []   # 晚间窗口
    daytime = []  # N-1 全天（含白天）
    for d in [n_minus1, anal_date]:
        try:
            res = looki_fetch(f"/moments?on_date={d}")
            for m in res.get("data", []):
                cover = m.get("cover_file") or {}
                loc = cover.get("location")
                addr = loc.get("street") if isinstance(loc, dict) else None
                if not addr:
                    continue
                st = m.get("start_time") or ""
                try:
                    dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
                except Exception:
                    continue
                is_n1_late = (d == n_minus1 and 20 <= dt.hour <= 23)
                is_n0_early = (d == anal_date and dt.hour < 3)
                if is_n1_late or is_n0_early:
                    strict.append((dt, addr))
                if d == n_minus1:
                    daytime.append((dt, addr))
        except Exception as e:
            print(f"looki fetch {d} failed: {e}", file=sys.stderr)
    if strict:
        strict.sort(key=lambda x: x[0])
        return strict[-1][1], "looki_overnight"
    if daytime:
        daytime.sort(key=lambda x: x[0])
        return daytime[-1][1], "looki_daytime"
    return None, None

# ── Open-Meteo 空气质量 ──
def fetch_air_quality(lat, lon, asof_date):
    """返回各指标日均+峰值 dict，或 None"""
    try:
        url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=pm2_5,pm10,ozone,nitrogen_dioxide"
            f"&start_date={asof_date}&end_date={asof_date}"
            f"&timezone=Asia/Shanghai"
        )
        h = http_get(url).get("hourly", {})

        def agg(key):
            vals = [v for v in h.get(key, []) if v is not None]
            if not vals:
                return None, None
            return round(sum(vals) / len(vals), 1), round(max(vals), 1)

        pm25a, pm25m = agg("pm2_5")
        pm10a, pm10m = agg("pm10")
        o3a, o3m = agg("ozone")
        no2a, no2m = agg("nitrogen_dioxide")
        return {
            "pm25_avg": pm25a, "pm25_max": pm25m,
            "pm10_avg": pm10a, "pm10_max": pm10m,
            "o3_avg": o3a, "o3_max": o3m,
            "no2_avg": no2a, "no2_max": no2m,
        }
    except Exception as e:
        print(f"air quality fetch failed: {e}", file=sys.stderr)
        return None

def pm25_flag(v):
    if v is None:
        return None
    if v <= 35:
        return "good"          # 中国一级标准 / WHO 指导值放宽
    if v <= 75:
        return "moderate"      # 中国二级标准上限
    return "unhealthy"

# ── canonical upsert（原子写：tmp + os.replace）──
def upsert_canonical(anal_date, env):
    records = []
    if os.path.exists(CANONICAL):
        for line in open(CANONICAL):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    found = False
    for rec in records:
        if rec.get("date") == anal_date:
            rec["environment"] = env
            found = True
            break
    if not found:
        records.append({"date": anal_date, "environment": env})
    tmp = CANONICAL + ".tmp"
    with open(tmp, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, CANONICAL)

def read_prev_env(asof_date):
    """读昨日(asof_date)的 environment，用于 location 判断和 fallback"""
    if not os.path.exists(CANONICAL):
        return None
    for line in open(CANONICAL):
        try:
            rec = json.loads(line)
            if rec.get("date") == asof_date:
                return rec.get("environment")
        except Exception:
            pass
    return None

# ── main ──
def main():
    anal_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
    asof_date = (datetime.strptime(anal_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    prev_env = read_prev_env(asof_date) or {}
    prev_city = prev_env.get("city")

    # 1. 过夜地（三级 fallback）
    looki_fetch = looki_client()
    addr, source = get_overnight_location(anal_date, looki_fetch)
    if not addr and prev_env.get("overnight_address"):
        addr = prev_env["overnight_address"]
        source = "looki_yesterday"
    if not addr:
        # ⚠️ 替换为你自己的常驻地
        addr = "<YOUR_HOME_ADDRESS>"
        source = "home_default"

    city = extract_city(addr) or HOME_COORDS[2]
    lat, lon, label = resolve_coords(city)

    # 2. 空气质量
    aq = fetch_air_quality(lat, lon, asof_date) or {}

    env = {
        "as_of": asof_date,
        "city": city,
        "city_label": label,
        "overnight_address": addr,
        "lat": lat,
        "lon": lon,
        "location_source": source,
        "location_changed": bool(prev_city and city != prev_city),
        "pm25_avg": aq.get("pm25_avg"),
        "pm25_max": aq.get("pm25_max"),
        "pm10_avg": aq.get("pm10_avg"),
        "pm10_max": aq.get("pm10_max"),
        "o3_avg": aq.get("o3_avg"),
        "o3_max": aq.get("o3_max"),
        "no2_avg": aq.get("no2_avg"),
        "no2_max": aq.get("no2_max"),
        "pm25_flag": pm25_flag(aq.get("pm25_avg")),
        "fetch_status": "ok" if aq.get("pm25_avg") is not None else "aq_failed",
    }

    upsert_canonical(anal_date, env)
    print(json.dumps(env, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
