---
name: lifereview-daily
version: 4.3.0
description: "每日生命回顾——生成晨间简报含裁决/叙事/新视角/碎步指数。不负责：周报(用weekly skill)、营养咨询(用ask-guzhongyi)、体检报告解读(单独处理)。"
metadata:
  requires:
    bins: [python3, jq, lark-cli]
---

# lifereview-daily — 每日生命回顾

为 提供每日状态分析，融合 Apple Watch HAE + Looki AI 相机 + 飞书日历。

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

| 脚本 | 用途 |
|------|------|
| `health-extract.py` (v6) | RHR/HRV/睡眠/步数/碎步/步态/VO2Max |
| `health-freshness.py` | 数据新鲜度检查 |
| `focus-predict.py` | 专注力预判 |
| `score.py` | 精力+压力评分 |
| `daily-narrative.py` | 15视角轮换叙事引擎 |
| `proma-send.py` | 飞书消息推送（凭据在 `~/.life-log/secrets/`） |

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

## 四大防护规则

1. **Looki 用 Python 直连 IP**（禁止 curl——VPN SNI 拦截）
2. **每次实时跑 freshness**（禁止缓存）
3. **消息走 stdin**（禁止 argv——shell 破坏换行符）
4. **聚合显式声明**（sum/median/first，禁止假设）

详见 `references/data-pipeline.md`

## 视角系统（15 个轮换 · 6 家族）

A.工作节奏：`meeting_type` `looki_gap`
B.生理恢复：`hrv_trend` `rhr_recovery` `sleep_quality` `load_recovery_balance`
C.感官/环境：`steps_vs_energy`
D.行为信号：`indulge_signal` `signal_cascade` `boundary_erosion`
E.纵向自我：`mindful_paradox` `deep_sleep_trend` `last_drink_linger` `movement_deficit`
F.社交/连接：`social_connection`

连续 3 天家族不重复。轮换状态在 `~/.life-log/tmp/perspective-tracker.txt`

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
