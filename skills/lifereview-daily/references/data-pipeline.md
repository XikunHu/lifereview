# 数据管线参考

## HAE 多通道同步机制 ⚠️

Health Export 的数据不是单文件同步——有三条独立的管线，速度不同。

### 目录结构

```
HealthExport/Documents/
├── iCloud for Proma/        ← 主 JSON 管线（最慢，延迟可达 7h+）
├── AutoSync/
│   ├── Workouts/            ← 🏃 运动记录（独立通道！结束几分钟后就到）
│   ├── Routes/              ← GPS 轨迹
│   └── HealthMetrics/       ← 113 个指标 .hae 文件
├── Automations/
└── 新自动化流程/            ← 旧版目录
```

### 同步速度差异（实测）

| 管线 | 延迟 | 晚间运动数据 |
|------|------|------------|
| 🏃 Workouts/ | **0.8h** | ✅ 完整 |
| 📊 AutoSync .hae | 6.7h | ❌ 16点后常停 |
| 📄 主 JSON | 7.7h | ❌ 滞后半天 |

### 运动数据提取规则

1. **优先查 Workouts/**——不要等主 JSON
2. 文件命名：`{type}_{date}_{UUID}.hae`
3. 解析：前 4 字节 `bvx-` 头 + JSON payload
4. 时间戳：CFAbsoluteTime + 978307200 = Unix
5. 步数/活跃 < 预期且 Workouts/ 有新文件 → 数据不完整

### 文件夹 mtime ≠ 文件 mtime

iCloud 可能只更新目录元数据，不以文件夹 mtime 判断数据新鲜度。只看文件 mtime 和内部时间戳。

## 数据新鲜度检查 ⚠️

每次报告前必须跑 `health-freshness.py <date>`。

| mtime_age_h | 状态 | 输出 |
|-------------|------|------|
| ≤2h | ✅ 新鲜 | — |
| 2-4h | ✅ 可接受 | 可能有延迟 |
| 4-8h | ⚠️ 过期 | 解读可能不完整 |
| >8h | 🔴 严重过期 | 优先用日历+Looki |

## 数据自查清单

1. HAE 存储粒度是每小时还是每天？
2. 每小时 → **sum()**（不是 first/last）
3. 多点采样 → **median()**（抗离群）
4. 单条记录 → first
5. 取数后人工核对（步数 <10 基本是 bug）

## REST 接收器（可选，推荐）

HAE App 支持 POST 到自定义 URL。跑 `rest-receiver.py` 后，iPhone 通过 WiFi 直推数据到 Mac，秒级到达，绕开 iCloud 延迟。

```bash
python3 ~/.life-log/tmp/rest-receiver.py --port 8765
```

HAE App 配置：Custom REST Endpoint → `http://<Mac-IP>:8765/health`

## daily-canonical 表（v7 新增）

health-extract.py v7 每次运行后自动追加一行到 `~/.life-log/daily-canonical.jsonl`（JSONL 格式，每行一天）。自动按日期去重，同一天不会重复写入。

**用途**：周报/月报不再需要逐日重读原始 JSON 文件——直接读 canonical 文件，Python 一行搞定 `[json.loads(l) for l in open('daily-canonical.jsonl')]`。
