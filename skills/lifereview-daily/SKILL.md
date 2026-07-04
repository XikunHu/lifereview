---
name: lifereview-daily
version: 4.4.0
description: "Nixon 每日生命回顾——裁决/叙事/新视角/碎步指数/心率-活动耦合。不负责：周报(用weekly skill)、营养咨询(用ask-guzhongyi)、体检报告解读(单独处理)。"
metadata:
  requires:
    bins: [python3, jq, lark-cli]
---

# lifereview-daily — 每日生命回顾

为 Nixon 提供每日状态分析，融合 Apple Watch HAE + Looki AI 相机 + 飞书日历。

## 快速索引

| 细节主题 | 参考文件 |
|---------|---------|
| HAE 同步机制、新鲜度检查、数据自查 | `references/data-pipeline.md` |
| Looki 双管道、VPN 绕过、离线协议 | `references/looki-protocol.md` |
| 睡眠建议、误判保护 | `references/sleep-recovery.md` |
| 已知失败模式与测试用例 | `references/test-cases.md` |

## 数据源

### HAE JSON（`HealthAutoExport-YYYY-MM-DD.json`）
两个目录都检查：`iCloud for Proma/`（主要）、`新自动化流程/`（备用）

### 聚合规则 ⚠️
| 方式 | 指标 |
|------|------|
| **sum()** | steps, active_energy, distance, flights, exercise_time, stand_hour |
| **median()** | rhr, hrv, respiratory_rate, walking_hr, heart_rate, blood_o2 |
| **first** | sleep_analysis, vo2_max |

> 曾因取首个条目而非 sum() 导致步数被低估 100 倍。接入新指标先确认聚合方式。

### 碎步指数（v6，参考 JeffenCheung/personal-health-dashboard）
连续活跃小时合并为 bout。短 bout=单小时<500步，长 bout=≥2h 或 ≥2000步。
碎步指数 0-100 = 短bout比(40%) + 频率(30%) + 平均时长倒数(30%)。A-E 等级：A=持续型 → E=高碎片型。

### 步态指标（v6 新增）
`walk_speed`(3.5-5.5 km/h)、`walk_step_len`(55-75 cm)、`walk_asymmetry`(<3%)、`walk_double_support`(20-30%)

### 跑步步态（周报用）
`running_stride_length`、`running_ground_contact_time`、`running_power`、`running_vertical_oscillation`（仅跑步日有数据）

### Looki API — 两条独立管道
🔵 Moments（AI 处理，数小时延迟）/ 🟢 Realtime（即时）。先 realtime 后 moments。VPN 用 Python 直连 IP 绕过。
详见 `references/looki-protocol.md`

### 飞书日历（仅已接受）
三层漏斗：① accept ② 自己是组织者 ③ 航班/高铁/→箭头。排除系统日程和提醒型。
API 失败时保留已有数据，不覆盖。

### REST 接收器（可选）
`rest-receiver.py --port 8765` 接收 HAE App POST，绕开 iCloud 7h+ 延迟。详见 `references/data-pipeline.md`

## 关键脚本

| 脚本 | 版本 | 用途 |
|------|------|------|
| `health-extract.py` | **v10** | RHR/HRV/睡眠/步数/碎步/步态/VO2Max → daily-canonical.jsonl。v10: 睡眠夜晚归属校验 + --expected-sleep-night |
| `health-freshness.py` | **v2** | 数据新鲜度检查 + 睡眠文件就绪检查（sleep_file_ready） |
| `focus-predict.py` | — | 专注力预判 |
| `score.py` | — | 精力+压力评分 |
| `daily-narrative.py` | — | 16视角轮换叙事引擎 |
| `looki-x-parser.py` | **v1** | 从 Looki moments 自动提取 X 事件（服药/饮酒/咖啡等）→ x-events.jsonl |
| `rest-receiver.py` | — | HAE REST 接收器（可选，绕开 iCloud 延迟） |

## 健康基线

| 指标 | 基线 | 区间 |
|------|------|------|
| RHR | 50 bpm | <47:深度恢复 47-50:良好 >55:关注 |
| HRV | 63 ms | >70:极佳 60-70:良好 <48:不充分 |
| 深睡 | 0.9h | 6年改善 0.3→0.9 |
| 运动底线 | 周均3-4次 | 6年1155次 |

## 评分逻辑

- **精力+压力**：Looki ≥5 moments→权重0.8，3-4→0.6，<3→0.3；Looki离线用日历+生理替代
- **专注（晨间预判）**：睡眠+HRV+RHR+呼吸+昨日🆘🍬级联
- **状态信号**：🆘求救（刷手机/发呆）、🍬代偿（可乐/零食/咖啡）、😴恢复（小憩/午睡）

## 已验证因果规律

- 🔴 酒精 → RHR +5~+6 bpm（最强预测器，APOE ε4+GSTM1 Null 基因确认）
- 🔴 深睡翻倍 ≠ 睡得好（白天透支的维修账单）
- 🟡 代偿日精力低 ~0.7（不是意志力，是生理信号）
- 🟡 运动日精力反而更低（恢复没跟上）
- 🟡 A/G>1.0+VAT+斑块（腹部脂肪独立风险维度）

## HRV 数据口径（v4.5 · 2026-07-02 事故教训）

**事故**：7/1→7/2 酒店夜 HRV 5 次采样 [71, 41, 42, 39, 71]，中位数=42。报告说「HRV 69→42，系统透支」。实际早晨已恢复至 71，用户主观感受「非常好」。中位数 42 把 V 型恢复曲线压成了一个灾难数字。

**规则**：

1. **主报 7 日滚动均值，不报单夜中位数**。`hrv_7d_avg` 才是稳定信号。单夜中位数只作为补充参考
2. **HRV 数字必须带口径**：样本数（hrv_n）、范围（hrv_range）、早晨恢复读数（hrv_morning）。格式：`7 晚均值 56ms（4 晚），昨晚中位数 42ms（5 次采样，范围 40-71，晨间已恢复至 71）`
3. **<5 次夜间采样时强制标注「小样本」**（hrv_sparse=true），此时中位数参考价值有限
4. **HRV 单夜值聚合方式**：取 0-9 点所有读数的**均值**（v9.1 从中位数改为均值，V 型分布时均值更诚实），排除 >2 倍均值的离群值
5. **绝对禁止**：只报一个孤零零的 HRV 数字不说明口径。禁止把单夜中位数当成「你的 HRV 是 XX」

## 睡眠数据校验（v4.5 · 2026-07-04）

**事故**：7/4 晨报拿 7/3 HAE 文件的睡眠（7/2→7/3 上海夜）当成「昨晚 7/3→7/4 北京夜」分析，整篇报告的睡眠结论全错。

**双重防护**：

### 第一层：提取时校验（health-extract.py v10）
入睡时间是否在预期窗口。分析 7/3→7/4 夜 → 入睡必须在 7/3 18:00 ~ 7/4 12:00。不在窗口 → `sleep_night_mismatch=true`。
用法：`health-extract.py file.json 2026-07-04 --expected-sleep-night 2026-07-03`。不匹配时 exit 2。

### 第二层：报告前检查（health-freshness.py v2）
生成晨报前检查今天的 HAE 文件是否到达。≥09:00 但文件缺失 → `sleep_file_ready=false` → 仅分析白天活动，不编造睡眠数据。

## 五大防护规则

1. **Looki 用 Python 直连 IP**（禁止 curl——VPN SNI 拦截）
2. **每次实时跑 freshness**（禁止缓存）
3. **消息走 stdin**（禁止 argv——shell 破坏换行符）
4. **聚合显式声明**（sum/median/first，禁止假设）
5. **HRV 必须报 7 日均值 + 带口径**（禁止裸数字，禁止单夜中位数当主数字）

详见 `references/data-pipeline.md`

## 视角系统（16 个轮换 · 6 家族）

A.工作节奏：`meeting_type` `looki_gap`
B.生理恢复：`hrv_trend` `rhr_recovery` `sleep_quality` `load_recovery_balance` **`hr_activity_coupling`** ← v4.4 新增
C.感官/环境：`steps_vs_energy`
D.行为信号：`indulge_signal` `signal_cascade` `boundary_erosion`
E.纵向自我：`mindful_paradox` `deep_sleep_trend` `last_drink_linger` `movement_deficit`
F.社交/连接：`social_connection`

连续 3 天家族不重复。

### hr_activity_coupling 视角（v4.4 新增）

步数 vs 实时心率的 Pearson r：心脏在跟你合作还是在抗拒？
- r > 0.6 → 高耦合，心脏响应灵敏
- r 0.3-0.6 → 正常
- r 0-0.3 → 弱耦合，可能疲劳
- r < 0 → 解耦，需关注。但**力量训练日解耦是正常的**——训练时高心率+低步数会拉低相关性。如果当天有力量训练且用户主观感受良好，解耦可能是训练效应而非恢复赤字。

**校准记录（7/1）**：6/30 上午力量训练 + 全天精力平稳感受好，但 r=−0.43 显示解耦。用户反馈："精力比较平稳，晚上困得早因为醒得早"。结论：力量训练日的负耦合不宜直接解读为"恢复系统罢工"，需结合主观感受和 Looki 场景。

## 定时任务

| 任务 | 时间 | 方式 |
|------|------|------|
| AI 晨间简报 | 10:00 | Proma automation |
| 晚间日志生成 | 23:07 | launchd → `daily-log-gen.sh`（不推送） |
| 因果探索 | 23:17 | launchd → `causal-explorer.py` |
| AI 周报 | 周日 11:00 | Proma automation |


## 晨间报告模板（v4.3）

1. **数据审计** — `HAE ✅ | Looki ✅10段 | Realtime ✅ | 日历 ✅`
2. **一句话裁决** — 🔴/🟡/🟢 + 核心判断
3. **Looki 叙事** — 时间线 + 场景 + 原型聚类
4. **生理基线** — RHR/HRV/睡眠/深睡 + 7d偏差
5. **步数+碎步** — `步数 XXXX | X bout | 指数 XX (A-E) | 步速 X.X | 步长 XX`
6. **证伪推理** — 「先别怪 X，更像 Y」
7. **今日预判+决策**
8. **每日新视角** — 15视角轮换
9. **状态信号** — 🆘🍬😴

底部：`有偏差就告诉我。精力X 专注X 压力X，我来调整。`

## 关键规范

- 禁止用「今天」「今日」描述被分析日，统一用「当天」
- 不强行归因——数据缺位时标注事实
- 生理指标解读限于数据形态标记，不做医学诊断
- 睡眠按醒来日归属——分析 X 日晚睡眠读 X+1 日文件
