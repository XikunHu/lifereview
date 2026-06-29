---
name: lifereview-daily
version: 4.3.0
description: "每日生命回顾系统。v4.3: 碎步bout检测+步态指标(参考JeffenCheung)，含四大防护规则、15视角轮换。"
metadata:
  requires:
    bins: [python3, jq, lark-cli]
---

# lifereview-daily — 每日生命回顾

为 提供每日状态分析，所有结论基于 6 年 Apple Watch 数据 + 7 份体检报告 + Looki 行为数据。

## 数据源配置

### HAE JSON（每日综合）
**两个目录都检查**：
- `~/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/iCloud for Proma/`（主要）
- `~/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/新自动化流程/`（备用）

文件命名：`HealthAutoExport-YYYY-MM-DD.json`

### HAE 数据聚合规则 ⚠️ 关键

HAE JSON 中部分指标按**小时**分条存储，提取时**必须**按类型正确聚合：

| 聚合方式 | 指标 | 原因 |
|---------|------|------|
| **sum()** | step_count, active_energy, walking_running_distance, flights_climbed, apple_exercise_time, apple_stand_hour, apple_stand_time, mindful_minutes, basal_energy_burned | 每小时一条，需全天汇总 |
| **median()** | resting_heart_rate, heart_rate_variability, respiratory_rate, walking_heart_rate_average, heart_rate, blood_oxygen_saturation | 多点采样，中位数抗离群 |
| **first** | sleep_analysis, vo2_max | 每天仅一条记录 |

> ⚠️ 过去曾因取首个条目而非 sum() 导致步数被低估约 100 倍（6/20 显示 8 步而非 13422 步）。任何新增指标接入前必须先确认聚合方式。

### 碎步指数（v6 bout 检测，参考 JeffenCheung/personal-health-dashboard）

**原理**：连续走一万步不累，但间歇性的频繁启停是高功耗的——每次从静止到走起来需要启动能耗（克服惯性+姿势控制重置），像一脚油门一脚刹车。

**算法**（health-extract.py v6）：
1. 连续活跃小时合并为一个 bout
2. 短 bout = 单小时且 <500 步（孤立碎片）；长 bout = ≥2h 连续或 ≥2000 步
3. 碎步指数 0-100 = 短bout比例(40%) + bout频率(30%) + 平均时长倒数(30%)
4. A-E 等级：A(≤20) 持续型·能耗经济 → E(>80) 高碎片型

**输出字段**：`frag_index`、`frag_grade`、`frag_label`、`frag_bouts`、`frag_short_bouts`、`frag_long_bouts`、`frag_avg_bout_h`、`step_concentration`

### 步态指标（v6 新增）

从 HAE JSON 提取步行相关的 biomechanical 指标：

| 字段 | 指标 | 正常范围 |
|------|------|---------|
| `walk_speed` | 步行速度 | 3.5-5.5 km/h |
| `walk_step_len` | 步长 | 55-75 cm |
| `walk_asymmetry` | 步行不对称性 | <3% |
| `walk_double_support` | 双支撑相 | 20-30% |

> 异常步态（不对称>5%、双支撑>35%、步速<3 km/h）可能提示疲劳或代偿模式。

### 跑步步态指标（周报用，v6 新增）

从 AutoSync/HealthMetrics/*.hae 提取（仅跑步日有数据）：
- `running_stride_length` — 跑步步幅
- `running_ground_contact_time` — 触地时间
- `running_power` — 跑步功率
- `running_vertical_oscillation` — 垂直振幅

> 这些指标仅在跑步 Workout 日有数据，周报中展示趋势。

### HAE 多通道同步机制 ⚠️ v4.1 新增

**Health Export 的数据不是单文件同步——有三条独立的管线，速度不同。**

#### 目录结构与作用

```
HealthExport/Documents/
├── iCloud for Proma/        ← 主 JSON 管线（最慢，延迟可达 7h+）
│   └── HealthAutoExport-YYYY-MM-DD.json
├── AutoSync/                ← 增量同步管线（中等）
│   ├── Workouts/            ← 🏃 运动记录（独立通道！结束几分钟后就到）
│   │   └── mixed_cardio_20260624_*.hae
│   ├── Routes/              ← GPS 轨迹（随 Workout 同步）
│   │   └── *.hae
│   └── HealthMetrics/       ← 113 个指标，每个一个 .hae（下午后常停）
│       ├── active_energy/20260624.hae
│       ├── step_count/20260624.hae
│       ├── heart_rate/20260624.hae
│       └── ...
├── Automations/             ← App 自动化脚本目录（2026-06-24 新出现）
│   └── *.json / *.fp
└── 新自动化流程/            ← 旧版自动化目录（已不用）
```

#### 同步速度差异（6/24 实测）

| 管线 | 6/24 最后更新 | 延迟 | 晚间运动数据 |
|------|-------------|------|------------|
| 🏃 Workouts/ | 22:50 | **0.8h** | ✅ 完整（20:00结束，22:50到） |
| 📊 AutoSync .hae | 16:14 | 6.7h | ❌ 16点后全停 |
| 📄 主 JSON | 15:18 | 7.7h | ❌ 只到15:00 |

#### 运动数据提取规则

1. **优先检查 Workouts/ 目录**——不要等主 JSON。Workout 走独立通道，运动结束后几分钟到几十分钟就能到
2. Workout .hae 文件命名：`{type}_{date}_{UUID}.hae`
3. 解析 Workout .hae：二进制文件，前 4 字节 `bvx-` 头，后面跟 JSON  payload：
   ```json
   {"start":803996620.096, "activeEnergy":3999.3, "duration":6816.2,
    "end":804003436.283, "totalDistance":4.022, "name":"Mixed Cardio",
    "METs":8.41, "temperature":23.4, "humidity":80}
   ```
4. 时间戳是 CFAbsoluteTime（从 2001-01-01 起的秒数），转 Unix 加 978307200
5. 如果 Workouts/ 有记录但主 JSON 没更新 → 用手动解析的 Workout 数据补充日报
6. 如果主 JSON 的步数/活跃 < 预期且 Workouts/ 有新文件 → 数据不完整，标注待同步

#### 主 JSON 更新延迟的识别

- **文件夹 mtime ≠ 文件 mtime**：文件夹会在子文件变化时更新。iCloud 有时只更新了文件夹元数据而未写入新文件内容。看到的「21:29 更新」可能是文件夹 mtime，不是 JSON 文件 mtime
- **有效判断**：只看 `HealthAutoExport-YYYY-MM-DD.json` 的 mtime 和内部最新时间戳
- **历史数据为何被更新**：AutoSync 有时会批量更新旧日期的 .hae 文件（如 6/24 晚 21:29 更新了 `environmental_audio_exposure/20260304.hae`），这是 iCloud 的延迟同步冲刷，不代表当天数据已到

### HAE 数据新鲜度检查 ⚠️ v3.3 新增

**问题**：iCloud 同步可能在夜间中断，导致 HAE 文件 mtime 停留在前一天。如果不在报告中标注数据截止时间，解读会基于不完整数据。6/23 案例：数据内含 23:00，但文件 mtime 到次日 15:18 才更新——同步延迟 16.3h。早间报告如果基于旧文件，会漏掉晚间数据。

**规则**：
1. **所有 HAE 解读必须先检查数据新鲜度**——运行 `health-freshness.py <date>` 获取 `mtime_age_h`
2. 检查两个维度：
   - **文件 mtime**：最后一次 iCloud 同步时间（`mtime_age_h`）
   - **内部最新时间戳**：数据内最后一条记录的时间（`data_lag_h`）
3. 新鲜度状态：

| mtime_age_h | 状态 | 输出 |
|-------------|------|------|
| ≤2h | ✅ 新鲜 | 无需标注 |
| 2-4h | ✅ 可接受 | `数据 {age}h 未更新，可能有延迟` |
| 4-8h | ⚠️ 过期 | `⚠️ 数据已 {age}h 未同步——解读可能不完整` |
| >8h | 🔴 严重过期 | `🔴 HAE 数据严重过期，优先用日历+Looki` |

4. **晨报必须显示数据截止时间**——如果 `data_lag_h > 1`，报告开头显示：
   ```
   ⚠️ 健康数据更新至 {internal_latest}，已 {mtime_age_h}h 未同步
   ```
5. **晚间回顾必须报告同步状态**——如果 `mtime_age_h > 4`，标注"今晚的生理数据可能不完整"
6. **脚本位置**：`~/.life-log/tmp/health-freshness.py`

### Looki API — 两条独立的数据管道 ⚠️ v4.1

mihomo/Tyty 透明代理会拦截 `open.looki.ai` 的 DNS（→127.0.0.1）和 TLS SNI。绕过方法：Python + 直连 IP `<YOUR_LOOKI_SERVER_IP>`。

**Looki 有两条独立的数据管道，速度和内容完全不同：**

| 管道 | 端点 | 内容 | 延迟 | 用途 |
|------|------|------|------|------|
| 🔵 Moments | `GET /moments?on_date=YYYY-MM-DD` | AI 处理后的完整场景片段 | 数小时（需等 AI 离线处理） | 行为评分、叙事 |
| 🟢 Realtime | `GET /realtime/latest-event` | 设备当前实时状态 | **即时**（蓝牙上传即达） | 实时状态确认 |

**关键规则**：
- **调 API 顺序：先 realtime → 后 moments**。realtime 即时到达，moments 延迟数小时。先拿到实时状态，再补 AI 总结
- Moments = 0 **不等于** Looki 离线——先查 realtime，realtime 有数据 = Looki 在线
- If realtime 有 + moments = 0 → 标注「🟢 Looki 在线，moments 生成中」
- If realtime 空 + moments = 0 → 标注「🔴 Looki 可能离线」
- realtime 描述是粗颗粒度的连续状态（如「持续坐在车内办公」），不能替代 moments 的精细分段——但在 moments 缺失时可以用于行为信号提取
- 实际案例：6/24 moments=0 但 realtime 返回「篮球后返程车中办公（杨浦长阳路）」——Looki 全程在线

```python
import urllib.request, ssl, json, statistics
API_KEY = '<YOUR_LOOKI_API_KEY>'
IP = '<YOUR_LOOKI_SERVER_IP>'  # 直连真实 IP，绕过 DNS 劫持
ctx = ssl.create_default_context()
ctx.check_hostname = False  # 关闭 SNI，绕过 TLS 层面拦截
ctx.verify_mode = ssl.CERT_NONE

def looki_api(path):
    req = urllib.request.Request(f'https://{IP}/api/v1{path}',
        headers={'Host': 'open.looki.ai', 'X-API-Key': API_KEY})
    return json.loads(urllib.request.urlopen(req, context=ctx, timeout=30).read().decode())

# 获取某天的 moments
moments = looki_api('/moments?on_date=2026-06-22')
```

**API 端点**：
- `GET /moments?on_date=YYYY-MM-DD` — 某天所有 moments
- `GET /moments/calendar?start_date=...&end_date=...` — 日历视图（highlight moments）
- `GET /moments/search?query=...&page_size=10` — 搜索
- `GET /me` — 用户信息
- `GET /realtime/latest-event` — 最新实时事件
- `GET /for_you/items?limit=20&group=comic` — AI 生成的高光内容

### 飞书日历（仅已接受）

**三层漏斗**（同时满足才算参与）：
1. ① 点了「接受」② 自己是组织者 ③ 标题含行程语义（航班号/高铁/火车/→箭头）
2. 排除：打开 Proma / Looki 每日 / Looki 周报 / 上传 Looki
3. 排除提醒型：交费/缴费/还款/预约/挂号/报备/审批/Review持仓/确认订阅 等
4. **不排除**：洗/修/打扫/审阅/打电话/师傅上门——花了真实时间

API 失败保护：如果 `lark-cli calendar +agenda` 返回 `ok: false`，检查已有日志文件中的日历数据恢复，避免正确数据被空数据覆盖。

### 健康快照

| 文件 | 用途 |
|------|------|
| `~/.life-log/tmp/health-extract.py` | RHR/HRV/睡眠/步数/VO2Max/碎步/步态 提取（v6） |
| `~/.life-log/tmp/score.py` | Looki 优先评分引擎（精力+压力+身体恢复） |
| `~/.life-log/tmp/focus-predict.py` | 专注力预判引擎（晨间，基于生理前导指标） |
| `~/.life-log/daily-log-gen.sh` | 每日日志生成主脚本 |
| `~/.life-log/morning-brief.sh` | 晨间简报 |
| `~/.life-log/tmp/daily-narrative.py` | 多源融合+15视角轮换叙事引擎 |
| `~/.life-log/tmp/proma-send.py` | Proma App 飞书消息推送 |

## 健康基线

| 指标 | 年度基线 | 来源 |
|------|---------|------|
| RHR | 50.1 bpm | 2026 Apple Watch 均值 |
| HRV | 62.8 ms | 2026 Apple Watch 均值 |
| VO2Max | 42-49 (峰值→当前) | Apple Watch |
| 深度睡眠 | 0.9h (2026 当前) | Apple Watch 趋势 |
| REM | 1.5h+ (治疗后) | Apple Watch |
| 运动 | 1155 次 / 6 年 | Apple Watch |
| 运动底线 | 周均 3-4 次 | 6 年数据验证 |

**RHR 区间**：<47=深度恢复、47-50=良好、50-55=轻度应激、>55=需关注
**HRV 区间**：>70=极佳、60-70=良好、<48=恢复不充分、<45=严重压抑

## 评分逻辑

### 精力 + 压力（回顾指标）
- Looki 优先级：≥5 moments → 权重 0.8/0.2；3-4 → 0.6/0.4；<3 → 0.3/0.7
- 基于 Looki 行为信号 + 日历负载

### 专注（晨间预判）
- 专注预判基于昨晚睡眠/RHR/HRV/呼吸频率 推断今日认知资源
- 由 `focus-predict.py` 独立输出
- 因子：睡眠时长(0-3)、深睡比例(0-2)、HRV 中位数+夜间分布形态(0-2→V型曲线-1)、RHR 偏离度(0-2)、呼吸频率(0-1)、昨日🆘+🍬 级联(0 or -1)

### 状态信号
- 🆘 求救：刷手机/刷短视频/发呆/长时间看手机
- 🍬 代偿：可乐/奶茶/零食/咖啡
- 😴 恢复：眯一会/小憩/午睡
- 长时间看手机 = 明确求救信号（和刷短视频同级）

## 已验证的因果规律

### 酒精 → RHR +5~+6 bpm（+8-13%）→ 次日精力 -2
- 6/16-6/23 多次验证：15 个会不影响 RHR，一次喝酒就飙升
- 6/19 80ml 威士忌 → 6/20 RHR 59（+11，全周最高）
- 这是最强的单因素精力预测器

### 差旅 + 假期 ≠ 恢复
- 6/19-21 端午三天：5.5h → 7.5h → 3.8h——只有中间一天补了觉
- 假期更多用于跨城移动而非休息

### 代偿行为（可乐/零食）出现日精力低 ~0.7
- 用户直觉"放纵=精力低"得到生理数据验证

### 运动日精力反而更低
- 运动消耗+恢复不足 → 次日 RHR 升高
- 不是运动不好，是恢复没跟上
- **新发现（6/23）**：睡眠 ≥7.5h 是晨跑的必要前提
  - 6/20 晨跑前晚睡眠 7.5h → 完成
  - 6/23 晨跑前晚睡眠 7.7h → 完成
  - 睡眠 <6h 的日子（6/19、6/21）运动完全缺席
  - 假设：睡眠是运动的燃料，不是奢侈

### 睡前心率 vs 深睡质量
- 睡前 HR 峰值 → 深睡比例：r = +0.70（p<0.01）
- 睡前 HRV → 深睡比例：r = -0.87（p<0.01）
- 高 HR 睡前 = 活动充分日，身体需要修复 → 深睡多

## HRV 方法论

- 取 0:00-9:00 之间所有 HRV 采样
- 计算中位数 m，剔除 >2m 的离群值
- 取剔除后的中位数
- 夜间分布形态检测：前半夜（0-4点）低 + 后半夜（4-9点）飙升 = V 型曲线 → 专注预判 -1
- 所有生理指标解读仅限于数据形态标记，不做医学诊断

## 视角系统（15 个轮换）

`hrv_trend`, `steps_vs_energy`, `meeting_type`, `looki_gap`, `sleep_quality`, `indulge_signal`, `rhr_recovery`, `load_recovery_balance`, `boundary_erosion`, `signal_cascade`, `mindful_paradox`, `deep_sleep_trend`, `last_drink_linger`, `movement_deficit`, `social_connection`

每次运行 `daily-narrative.py` 自动取下一个未使用的视角。

## 定时任务

| 任务 | 时间 | 内容 |
|------|------|------|
| 晨间简报（含昨日回顾） | 10:00 | `morning-brief.sh` ——昨天完整故事 + 今天预判 + 今日日程 |
| 晚间日志生成 | 23:07 | `daily-log-gen.sh` ——生成日志文件（获取 raw 数据），**不推送** |
| 因果探索 | 23:17 | `causal-explorer.py` |
| HAE 清理 | 周日 03:00 | `cleanup-hae.sh` |

### 为什么不晚间推送 ⚠️ v4.1

**23:07 时数据不完整——推送没有意义。**

| 数据源 | 23:07 状态 | 10:00 状态 |
|--------|-----------|-----------|
| Looki moments | ❌ AI 处理中（需数小时） | ✅ 完整（前一天的 moments 已生成） |
| Looki realtime | ⚠️ 只有「此刻」快照，无全天历史 | ⚠️ 同上 |
| HAE JSON | ⚠️ 常卡在下午/傍晚（iCloud 延迟） | ✅ 通常已完成夜间同步 |
| AutoSync .hae | ⚠️ 同上 | ✅ 同上 |
| Workouts | ✅ 运动后几分钟到 | ✅ 完整 |
| 飞书日历 | ✅ 完整 | ✅ 完整 |

**结论**：晚间唯一可靠的增量数据是日历和 Workout。Looki 的核心价值（moments 叙事）要到次日早晨才能解锁。所以晚间生成日志文件（存 raw 数据）但不推送——次日 10:00 的早报带着完整数据一起发。

过去的晚间推送（23:07 `daily-log-notify.sh`）应改为仅记录、不推送。如果用户有即时睡眠建议需求，可以用轻量版（仅 HAE + 日历，不含 Looki），但默认不打扰。

## 通知通道

飞书 Proma bot IM 直投：chat_id `<YOUR_FEISHU_CHAT_ID>`
通过 `proma-send.py` 使用 tenant_access_token 发送

## 叙事文案规范

- **禁止使用「今天」「今日」描述被分析日**
- 统一使用「当天」指代被分析日
- 视角标题使用「昨日新视角」

## 睡眠误判保护

深夜（23:00-06:00）若 moment 描述同时含「屏幕亮 + 卧室/睡眠环境词」，按睡眠处理，不计入活动跨度。

## 日历 API 失败保护

`lark-cli` 返回 `ok: false` 时，检查已有日志文件。若已有日程数据则保留，仅在 stderr 输出 warning。

## Looki 离线日协议 ⚠️ v3.2

当 Looki 未开启（moments=0）时，不能简单输出「数据不足」。必须启用**日历+生理替代模式**：

### ⚠️ Workout/运动检测（最高优先级）
**即使 Looki 离线，HAE 中的运动数据仍然完整可用。必须主动检测，不能遗漏。**

检测步骤：
1. 检查 HAE `step_count` 的**小时分布**——连续 2+ 小时步数 >500 且活跃能量 >100kJ → 运动时段
2. 检查 HAE `walking_running_distance` 的小时峰值——单小时 >1.5km → 跑步
3. 检查 `AutoSync/Workouts/` 目录——`running_YYYYMMDD_*.hae` 文件 = Apple Watch 确认的跑步记录
4. 如果检测到运动 → 在日报中**显著标注**（🏃 emoji + 距离/时长/时段）
5. 如果检测到运动 → 检查前晚睡眠是否 ≥7h → 如 ≥7h，标注「睡眠→运动」关联

**案例**：6/23 Looki 离线，但 HAE 显示 07:00-08:00 步数 3395+661kJ+3.4km，AutoSync 有 `running_20260623` Workout。第一次生成的日报完全漏掉了这次晨跑——这是不可接受的。

### 评分替代规则
- **精力**：基于 RHR 偏离度 + 睡眠时长 + 运动完成 + 日历总时长估算
  - 🏃 完成晨跑 → **+1**（强正向信号），RHR > 基线+5 → -2，睡眠 <6h → -3，睡眠 6-7h → -1，睡眠 ≥7.5h → +1，日历 >6h → -1，日历 >10h → -2
- **专注**：基于睡眠+HRV+日历块间隙估算
  - 睡眠 ≥7.5h → +1，HRV >65 → +1，日历最大间隙 >60min → +1，背靠背 ≥4 → -2
- **压力**：基于日历密度+晚间跨度估算
  - 日历 >10h → +3，背靠背 ≥5 → +2，最晚会议 >21:00 → +1，5:00 前开始 → +1
- 所有评分标注 `⚠️ Looki 离线，基于日历+生理估算`

### 叙事要求
- 即使 Looki 离线，仍必须根据日历类型分布（协作/产出/学习/社交）生成日程语义分析
- 日历类型判定规则：含「会/讨论/对齐/评审/周会/同步/沟通/汇报/方案/需求/项目/设计」→ 协作
  含「写/搞/做/整理/准备/材料/文档/产出/测试」→ 产出
- 视角系统在 Looki 离线时自动跳过 `looki_gap`，只用不需要 Looki 的视角

### 睡眠建议生成规则
晚间回顾必须包含睡眠建议，基于当日负载 × 生理状态：

1. **如果今日日历 > 8h 且最晚会议 > 21:00** → 警告"认知激活风险"，建议 30-45min 切离期
2. **如果 RHR > 基线 + 5** → 警告"自主神经应激"，建议睡前呼吸训练（5-4-7 呼吸法）
3. **如果昨晚睡眠 < 6h** → 强烈建议今晚 ≥ 7.5h，明天不排 9:00 前会议
4. **如果 HRV（白天）有明显低谷**（如 < 50ms）→ 标注压力峰值时段，建议该时段后主动恢复
5. **酒精警告**：如果 RHR 波动范围（日间）> 20bpm 或近期有饮酒记录 → 明确建议今晚不喝酒
6. **正面强化**：如果 RHR < 50 且 HRV > 65 且睡眠 ≥ 7h → 告诉用户身体扛住了，恢复系统工作正常

## 数据自查清单 ⚠️ 每次接入新指标必查

1. 该指标的 HAE 存储粒度是每小时还是每天？
2. 如果是每小时 → 使用 **sum()**（不是 first、不是 last）
3. 如果是多点采样 → 使用 **median()**（抗离群）
4. 如果是单条记录 → 可用 first
5. 取数后至少人工核对一天的值是否合理（如步数 <100 在差旅日正常，但 <10 基本是 bug）

## 四大防护规则 ⚠️ v4.0 — 已编码的错误及预防

这些是 6/23-24 两天内踩过的坑，每条都有实际数据损失。**任何新增或修改代码时必须遵守。**

### 规则 1：Looki API 必须用 Python，禁止 curl

**错误**：`daily-log-gen.sh` 用 `curl` 调 Looki API。mihomo/Tyty 透明代理在 TLS SNI 层拦截 `open.looki.ai`，curl 请求返回空。
**后果**：6/23 晚间回顾显示「Looki 未开启（0 moments）」，实际有 14 个 moments。数据完全可用，是通道被阻。
**修复**：`daily-log-gen.sh` 中 Looki 调用已改为 Python 直连 IP `<YOUR_LOOKI_SERVER_IP>` + 关闭 SNI（`ctx.check_hostname = False`）。
**防护**：任何调用 `open.looki.ai` 的代码必须使用 Python + 直连 IP 模式。`curl`、`wget`、`requests`（走 DNS）都会失败。

### 规则 2：所有报告必须**实时**检查数据新鲜度（禁止缓存）

**错误**：晚间回顾 22:54 生成时，用了下午 16:00 缓存的 freshness check 结果。实际上 JSON 在 21:29 已更新（文件从 27175B → 39310B，新增 5 小时晚间数据）。缓存导致报告漏掉了 20:00 篮球的高峰数据（3158步/1544kJ）。
**后果**：报告步数 1884（实际 6200）、活跃 309kJ（实际 2729kJ）——和 6/23 早上完全一样的错误模式，但这次根因不是 iCloud 延迟，是我自己没重新读文件。
**修复**：每次生成报告前**必须重新**运行 `health-freshness.py` 并**重新读取** JSON 文件。不得复用上一轮会话中的数据。
**防护**：
- 晨报/晚报开头必须跑 `health-freshness.py <date>`（不接受缓存值）
- 报告生成时必须用 `os.path.getmtime()` 重新读文件 mtime，如果比上次读取时更新了 → 重新加载 JSON
- `mtime_age_h > 4` → ⚠️ 过期标注
- `mtime_age_h > 8` → 🔴 严重过期，降低 HAE 权重，优先日历+Looki
- 报告中必须显示数据截止时间戳和文件 mtime

### 规则 3：消息发送用 stdin，禁止 argv

**错误**：`proma-send.py` 用 `sys.argv[1]` 接收消息文本。shell 将换行符 `\n` 作为两个字面量字符传递。
**后果**：飞书消息中出现字面量 `\n` 而非换行——用户看到的是乱码。
**修复**：`proma-send.py` 改为 `sys.stdin.read()`，所有调用方改为 `echo "$MSG" | python3 proma-send.py`。
**防护**：任何向外部系统发送文本的脚本，消息体必须走 stdin 或文件，禁止走 argv。

### 规则 4：聚合方式必须显式声明

**错误**：`health-extract.py` 用 `break` 取第一个条目——步数/活跃能量只取了凌晨 01:00 的数据点。
**后果**：6/20 步数显示 8 步（实际 13422），全周被误判为「极端静坐」。
**修复**：改为 `sum()`。同时在接入任何新指标前必须确认其 HAE 存储粒度。
**防护**：见上方「HAE 数据聚合规则」表。新增指标必须先分类（sum/median/first），再编码。不得假设「取第一条就行」。

## 晨间报告模板 ⚠️ v4.2 — 融合版

结合朋友日报的优秀实践和 偏好的叙事风格，形成以下结构。不是死模板——保留灵活性，但关键要素每次都要在。

### 结构优先级

1. **一句话裁决**（必选·新增）— 红🟡/黄🟡/绿🟢 灯 + 一行核心判断
   - 基于 RHR 偏离度 + HRV + 睡眠 + 昨日负载综合
   - 不是评分，是建议。例如：「黄灯——今天适合执行，别勉强深度判断」
   - 放在最顶部，让用户 3 秒内知道今天状态

2. **数据审计**（必选·新增）— 每个数据管道一行状态
   ```
   HAE ✅ 09:35 | Looki ✅ 10段 | Workout ✅ | Realtime ❌ | 日历 ✅
   ```
   替代了 health-freshness check 的输出位置——更直观

3. **昨天 Looki 叙事**（保留·核心）— 用户最喜欢的部分
   - 保持现在的时间线 + 场景描述 + 位置 + emoji
   - 这是我们的差异化优势，朋友的日报没有 Looki

4. **生理基线对比**（新增）— 关键指标带 7d 基线
   - RHR 51 bpm（7d 均值 47.3 ↑3.7）
   - HRV 54 ms（7d 均值 56.5 ↓2.5）
   - 深睡 0.53h（7d 均值 0.74h ↓0.21）
   - 不只是报数字，标注偏离方向

5. **证伪式推理**（新增）— 「先别怪 X」
   - 每个异常指标都要做一次证伪
   - 例如：RHR 51 →「先别怪深睡——0.53h 是偏低但不是崩盘。RHR 51 更像是 14h 会议的累积疲劳。」
   - 避免单因解释

6. **行为观察 + 评分**（保留·精简）— 精力/专注/压力 + Looki 证据
   - 保持现在格式

7. **今日预判 + 决策建议**（升级）— 从描述升级为具体行动
   - 旧：「今天 10 会 13.5h，注意休息」
   - 新：「下午算力宝 2.5h 是认知主战场。19 点后别排额外输出——赶书稿 23 点必须停。」

8. **每日新视角**（保留·核心）— 用户最认可的部分
   - 15 个轮换视角，每早一个
   - 结合前一天数据做深度分析

9. **状态信号**（保留）
   - 🆘🍬😴

### 底部固定收尾
```
有偏差就告诉我。精力X 专注X 压力X，我来调整。
```
保留这个——用户在多次对话中都用了这个反馈通道。

### 原则

- **叙事 ≠ 堆积数据**——每次 Looki 的故事应该是「你昨天是个什么样的人」，不是「你昨天走了多少步」
- **裁决 + 证伪 = 可信度**——先判断再解释，先排除再归因
- **决策 > 观察**——「今天别喝酒」比「HRV 偏低」有用
- **保持人味**——墨西哥塔可、曼谷篮球梦、黑色眼罩……这些是数据给不了的

## 借鉴自 Mira 系统的改进 ⚠️ v4.2 新增

参考另一套独立运行的 lifereview 系统（Mira），吸收其优点，避开其问题（输出过长、重点不突出）。

### 1. 铁律结构

将关键规则从"防护规则"（事后总结）升级为"铁律"（事前必读）。每条铁律 = 规则 + 曾犯错误 + 自检方法。

**铁律 0：日期时态**。每次开跑前先算。「今天」以当前时间为准，「昨天」= 今天 −1。睡眠按醒来日归属——分析 X 日晚的睡眠，必须读 X+1 日文件。自检：写睡眠前看 sleepEnd 是否落在目标日的次日早晨。

**铁律 0.5：数据新鲜度**。任何健康数据解读前，必须先跑 `health-freshness.py`。stale 或 incomplete 为 true 时，报告最开头醒目提示数据截止时间。数据不完整时禁止做跨全天结论。

**铁律 0.6：数据质量判断**。部分 Apple Watch 指标会系统性漏采——不是用户没做，是设备没采到。判断标准：当一个指标低到反常识、且其采集依赖"手表必须戴着且处于特定状态"时，需标注"此数存疑"。已知步数和日照分钟曾出现漏采情况，但当前处理方式（标注存疑 + 不单独做因果推断）已足够——不需要拉进硬黑名单，继续按现有方法处理即可。

### 2. 不强行归因

数据缺位时标注事实，不补构想。Looki/日历/Health 任一源缺位时，显式标注缺位事实。大模型有"完成欲"——倾向于输出连贯叙事而非坦诚不确定。健康因果建模里这是致命的。

### 3. 视角反同源硬约束

15 个视角归入 6 个家族，连续 3 天家族不重复：

| 家族 | 包含视角 |
|------|---------|
| A. 工作节奏 | meeting_type, looki_gap |
| B. 生理恢复 | hrv_trend, rhr_recovery, sleep_quality, load_recovery_balance |
| C. 感官/环境 | steps_vs_energy |
| D. 行为信号 | indulge_signal, signal_cascade, boundary_erosion |
| E. 纵向自我 | mindful_paradox, deep_sleep_trend, last_drink_linger, movement_deficit |
| F. 社交/连接 | social_connection |

自检：写完新视角后问"这和昨天那条是不是都在用工作时长+生理学解读？"是 → 换家族重写。

### 4. Health-first 优先级

生理数据以 HAE Drive JSON 为第一手主源，Looki 仅作行为交叉验证。两者冲突时明确标注以 Health 为准。三级优先级：Drive JSON（主源）→ health_daily 数据库（回落）→ Looki（仅当 Health 完全缺位）。

### 5. 场景原型聚类

从 Looki moment 描述中提取场景原型（办公室深度/通勤/餐饮/深夜居家/社交沟通/个人创作），用语料关键词匹配。日报中的"昨天 Looki 轨迹"段优先展示场景原型分布，让用户一眼看到昨天的时间花在哪类场景上。

### 不借鉴的部分

Mira 系统的输出格式（极长的每日反馈、大量表格）——重点不突出、读着费劲。保持我们的简洁格式：一句话裁决 + 审计 + Looki 叙事 + 基线对比 + 新视角 + 决策建议。
