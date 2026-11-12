# 数据管线参考

以 analysis-contract.md 的日期、聚合与覆盖规则为准。目录和速度只是配置线索，不能代替读取本次文件证据。

## 常见 HAE 目录

```text
HealthExport/Documents/
├── iCloud for Proma/       # HealthAutoExport-YYYY-MM-DD.json
├── 新自动化流程/           # 部分旧安装的备用 JSON
└── AutoSync/
    ├── Workouts/           # 独立训练记录
    ├── Routes/             # GPS（按任务需要才读取）
    └── HealthMetrics/      # 各指标 .hae
```

本机路径优先从现有配置读取，不把某个人的iCloud路径硬编码到公共Skill。三个通道独立同步，不承诺哪个永远先到。文件夹mtime不代表文件内容到达；新文件也可能不完整。

## 读取检查

1. 定位目标日期的源文件，检查内部日期、单位、最新样本和样本间隙。
2. macOS iCloud SF_DATALESS占位跳过并记录，避免无期限阻塞。不能把读取失败当零。
3. `.hae` 为LZFSE流时从文件开头解压；不要无条件丢弃“前4字节”。格式不匹配就明确失败，不猜私有header。
4. 确认每项是增量、累计、单次观测还是聚合记录，再选择sum/mean/median；跨设备重叠去重。
5. 训练时间可能使用CFAbsoluteTime；只有字段声明该口径才加978307200转Unix，不对所有时间戳统一加偏移。
6. 历史日期看覆盖，实时晨报额外看同步状态。回退旧数据时明确实际日期。

## canonical与提取脚本

`daily-canonical.jsonl`通常位于本机运行数据目录，包含历史逐日摘要。使用前核对日期唯一性、来源、单位与处理版本；不能假定它永远比原始文件正确。不要将运行数据和凭据同步进公开仓库。

现有`health-extract.py`可能会去重并回写canonical；读取报告不等于允许修复或重建缓存。需要重新提取时先核对副作用与任务授权。`health-freshness.py`只作实时辅助，不用当前mtime给历史完整性打分。

## 可选REST通道

现有安装如已提供rest-receiver.py，可按配置读取HAE直推数据；审查Skill不默认启动接收服务、开放端口或更改手机同步设置。
