# 数据备份方案

> Life Review 系统的数据保护层。三重保护，每天自动触发，零干预。

## 为什么需要

健康/行为数据是个人资产，重建要几周。这套方案让数据 **永不丢失**，且能 **看到历史变化**。

**设计动机**：原本数据散在 iCloud JSON 文件，磁盘满触发 iCloud evict 后 `open()` 陷入内核态 deadlock，晨报卡死一上午。迁移到本地 SQLite 后，备份成了新问题——单副本。这套三重保护是答案。

## 三重保护

| 层 | 机制 | 频率 | 恢复速度 | 看历史 | 异地容灾 |
|----|------|------|---------|--------|---------|
| 主库 | 本地 SQLite | 实时 | — | ❌ | ❌ |
| ② cp | 二进制副本（滚动 14 天）| 每天 | 秒级 | ❌ | ❌ |
| ③ git dump | 文本 SQL + push 私有仓库 | 每天 | 稍慢 | ✅ `git diff` | ✅ |

## 工作流

每天定时（launchd / cron）跑 import 脚本，灌完数据后自动：

```
import-hae.py
  ├─ 灌今天数据进主库
  ├─ ② cp health.db → backups/health-YYYYMMDD.db（滚动清 14 天前）
  ├─ ③ sqlite3 .dump > health-dump.sql
  ├─ ③ git add -A && git commit -m "health data YYYYMMDD"
  └─ ③ git push origin main（异地容灾）
```

## 文件

| 文件 | 作用 |
|------|------|
| `import-hae.py` | 数据导入 + 备份钩子（cp + dump + push）。改 `HAE_BASES` 指向你的 HAE 导出目录 |
| `schema.sql` | SQLite 表结构（6 张表）|
| `.gitignore.template` | 版本控制排除规则（凭据/日志/缓存/DB 二进制）|

## 配置

```bash
# 1. 建库
sqlite3 health.db < schema.sql

# 2. 初始化 git 仓库（用私有仓库做异地容灾）
git init -b main
cp .gitignore.template .gitignore
git remote add origin https://github.com/<你>/your-private-log.git

# 3. 配定时任务（launchd / cron）每天跑 import
#    脚本会自动 cp + dump + commit + push，零干预
```

## 恢复

- **误删 / 文件损坏**：`cp backups/health-YYYYMMDD.db health.db`（秒级）
- **电脑丢 / 火灾**：`git clone <私有仓库>` → `sqlite3 health.db < db/health-dump.sql`

## 为什么两个都要（② + ③）

- **② 解决「误删 / 损坏」** —— 二进制副本，秒级恢复，零思考
- **③ 解决「看历史 + 异地容灾」** —— 文本能 diff（"上周 HRV 怎么变的"），push 后本地全毁也能 clone 回来
- **互补**：② 是保险绳，③ 是档案柜。重叠的保护是"DB 被毁"，但 ③ 独占"看变化+异地"，② 独占"秒级恢复"

## 关键设计点

- **DB 不进 git**：二进制不能 diff，且每次变化都触发整文件存储。用 `.dump` 导成文本 SQL 代替
- **凭据绝不进 git**：`.gitignore` 硬排除 credentials/secrets/token。每次 commit 前应扫描
- **push 在脚本里**：import 成功才 commit + push，失败不污染远端
