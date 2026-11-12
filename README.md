# LifeReview — 个人因果建模系统

用 AI 把 Apple Watch 生理数据、可穿戴相机行为和日历，变成每天早上一条「昨天你是个什么样的人」的日报。

**Skills 当前版（2026-11-12）：daily 6.0.0 / weekly 3.0.0 / trajectory 2.5.0。**

Skill 是分析规范；仓库历史脚本和本机生产管线可能不同。先检查真实入口、覆盖和副作用，不能把安装Skill等同于已修复或部署生产晨报。

## 原理

系统对照个人参照、真实行为与同一时段的身体变化；单个HRV、静息心率或睡眠分期不能独立证明压力、恢复或生理机制。

目标是建立可复核的个人关联与待验证假设，逐步探索行为和身体的关系。

## 你需要什么

| 硬件/服务 | 用途 | 备注 |
|-----------|------|------|
| Apple Watch | 生理数据采集 | 任何支持 Health 导出 App 的手表均可 |
| [Health Auto Export](https://apps.apple.com/us/app/health-auto-export/id1614518400) | 把 Health 数据导出为 JSON → iCloud | 美区 App Store，约 $7 |
| Looki AI 相机（可选） | 全天行为记录 | 无 Looki 也能用日历+生理模式 |
| 飞书 | 日历读取 + 消息推送 | lark-cli OAuth |
| Mac | 运行脚本 | 需要 Python 3、jq |

## 快速开始

### 1. 安装依赖

```bash
# macOS
brew install jq python3

# lark-cli（飞书日历和消息）
# 安装并配置 OAuth 登录
# 参考 lark-cli 文档完成 auth login
lark-cli config init
lark-cli auth login
```

### 2. 配置

```bash
# 克隆仓库
git clone https://github.com/<你的用户名>/lifereview.git
cd lifereview

# 复制脚本到工作目录
mkdir -p ~/.life-log/tmp
cp scripts/* ~/.life-log/tmp/
chmod +x ~/.life-log/tmp/*.sh

# 完整安装Skills（包括references、evals和scripts）
# 先检查差异；有差异时退出码为1，不写文件
python3 scripts/sync-skills.py --workspace ~/.proma/agent-workspaces/default
# 确认目标后安装，旧包会完整备份；备份目录须未用于同一包
python3 scripts/sync-skills.py --workspace ~/.proma/agent-workspaces/default \
  --apply --backup-dir ~/lifereview-skill-backup-20261112
# 多工作区可重复传 --workspace；不要只复制SKILL.md
```

三个Skill分别负责完整日报、七日汇总和行为×身体轨迹。周报读取日报包的现行分析契约；轨迹允许安排背景与稀疏日达标身体信号，不凑节点或两句洞察。安装保留历史目录ID以兼容既有调用，三个包的版本号独立演进，无需相同。

`references/aug04-input.json`为仓库既有示例；日常验证优先使用各包`evals/evals.json`中的合成输入。可选云端runner默认只生成1版，需要明确配置兼容Anthropic Messages的模型与服务地址；输入将发送至所配置服务。正常使用Skill可以直接在Agent内完成。

```bash
python3 -m unittest discover -s tests -v
# 可选：已有明确云端处理授权并设置PROMA_API_KEY后
python3 skills/lifereview-trajectory-map/scripts/run_deepseek_resumable.py \
  --input facts.json --outdir output --model YOUR_MODEL --api-root https://YOUR_HOST/v1
```

### 3. 替换占位符

所有文件中的 `<YOUR_*>` 占位符需要替换为你的实际值：

| 占位符 | 说明 | 在哪获取 |
|--------|------|---------|
| `<YOUR_LOOKI_API_KEY>` | Looki API 密钥 | Looki App → 设置 → API |
| `<YOUR_FEISHU_CHAT_ID>` | 飞书消息接收人/群的 open_id | 飞书开发者后台 |
| `<YOUR_HEALTH_EXPORT_PATH>` | HAE JSON 文件的 iCloud 路径 | 在 Finder 中找到 `HealthAutoExport-*.json` 所在目录 |
| `<YOUR_NAME>` | 你的飞书显示名（日历过滤用） | 你的飞书姓名 |
| `<YOUR_VO2MAX_CSV_PATH>` | 6 年健康数据 CSV（可选） | HAE 导出的长期 CSV |
| `<YOUR_APP_ID>` / `<YOUR_APP_SECRET>` | 飞书应用凭据 | 飞书开发者后台 → 应用详情 |

**批量替换命令**：
```bash
cd ~/.life-log/tmp
# macOS
find . -name "*.py" -o -name "*.sh" | xargs sed -i '' 's/<YOUR_LOOKI_API_KEY>/lk-你的真实key/g'
find . -name "*.py" -o -name "*.sh" | xargs sed -i '' 's/<YOUR_FEISHU_CHAT_ID>/ou_你的真实chat_id/g'
# ... 以此类推
```

### 4. 设置定时任务

```bash
# macOS launchd — 每天早上 10:00 跑晨间简报
cat > ~/Library/LaunchAgents/com.lifereview.morning-brief.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.lifereview.morning-brief</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/你的用户名/.life-log/tmp/morning-brief.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/Users/你的用户名/.life-log/tmp/cron-morning.log</string>
    <key>StandardErrorPath</key><string>/Users/你的用户名/.life-log/tmp/cron-morning.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.lifereview.morning-brief.plist
```

### 5. 手动跑一次

```bash
python3 ~/.life-log/tmp/morning-brief.py
```

## 架构

```
Apple Watch ──→ Health Auto Export ──→ iCloud JSON ──┐
Looki AI 相机 ──→ API (Moments + Realtime) ──────────┤
飞书日历 ──→ lark-cli ───────────────────────────────┤
                                                      ├──→ health-extract.py ──→ score.py
                                                      ├──→ focus-predict.py
                                                      └──→ daily-narrative.py
                                                                  │
                                                          morning-brief.py
                                                                  │
                                                          飞书消息 / Markdown
```

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `health-extract.py` | 从 HAE JSON 提取 RHR/HRV/睡眠/步数/VO2Max（v4，已修复 sum 聚合） |
| `health-freshness.py` | 检查 iCloud 数据新鲜度，>4h 标过期 |
| `score.py` | 双维度评分引擎：精力（行为持续性）+ 压力（日历负载） |
| `focus-predict.py` | 晨间专注力预判：基于睡眠 + HRV + RHR + 昨日信号 |
| `morning-brief.py` | 晨间简报生成：一句话裁决 → 审计 → 叙事 → 基线对比 → 今日预判 |
| `daily-narrative.py` | 15 视角轮换叙事引擎（核心） |
| `daily-log-gen.sh` | 每日日志生成主脚本（晚间跑，存 raw 数据） |
| `proma-send.py` | 飞书消息推送（stdin 读消息体，避免 shell 转义） |
| `causal-explorer.py` | 跨日因果发现（状态信号 → 精力关联） |

## 四个核心规则

1. **HAE 数据聚合**：步数/活跃能量必须用 `sum()`（按小时存储），心率/HRV 用 `median()`
2. **数据新鲜度**：每次报告前必须跑 `health-freshness.py`，禁止缓存
3. **消息走 stdin**：禁止 argv 传消息体，shell 会把 `\n` 当字面量
4. **不强行归因**：数据缺位时标注事实，不补构想

## 已验证的因果规律

- **酒精** → RHR +5~+6 bpm（+8-13%），最强的单因素精力预测器
- **深睡翻倍** ≠ 睡得好 —— 是白天透支了，身体被迫加班修复
- **恢复期运动** = 借明天的钱 —— 睡眠不够时运动不是自律
- **代偿行为**（可乐/零食）出现日精力低 ~0.7 —— 不是意志力问题，是生理信号

## 许可

MIT
