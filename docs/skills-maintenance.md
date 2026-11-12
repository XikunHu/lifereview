# Skills 维护与验证

2026-11-12：daily **6.0.0** / weekly **3.0.0** / trajectory **2.5.0**。

## 单一发布源

本仓库的 `skills/` 是可分发包源。Proma本地包必须完整复制，不只覆盖SKILL.md。各包独立版本；要求一致的是同一包在GitHub和各安装位置的内容。

| 包目录 | 兼容安装目录 | 职责 |
|---|---|---|
| lifereview-daily | lifereview-daily-20260701 | 日期/来源审计与完整日报 |
| lifereview-weekly | lifereview-weekly-20260628 | 连续七日趋势，继承日报分析契约 |
| lifereview-trajectory-map | lifereview-trajectory-map-20260808 | 行为×身体时段表达 |

## 本次修订

- 日报从528行整理为56行主流程，聚合、覆盖、证据和指标细节下沉references；不再混放旧发布快照与推送群。
- 日报与周报共用analysis-contract.md，消除HRV中位数/均值冲突、旧CGM门控和固定个人基线。
- 将观察相关与因果区分；去除HRV前低后高必然表示紧急修复、基因可确认单次行为效应、深睡增加必然代表透支等确定论断。
- 停止默认精力/压力分数、体力/脑力百分数；报告围绕可核对的变化与行动。
- 去除不存在的weekly-review.py默认命令；说明生产日报脚本可能发消息、提取器可能改缓存。
- Looki参考不再关闭TLS校验或固定IP；明确empty/failed/disabled的区别。
- 轨迹同步安排背景、body_signal和无轨迹门禁，缩小触发范围；产品契约/UI规则只在产品集成适用。
- 三个云端脚本入口统一实现；不固定4991步、节点下限、恰好两句洞察或默认模型。单版默认，多版显式请求。续跑标识绑定输入、Skill、runner、模型、服务与生成参数；空正文和截断为失败。
- 增加完整包同步工具：只读检查默认；显式apply前完整备份；复制后逐文件哈希验证。

旧规范可用Git历史`80f82d3:skills/...`查阅，不放在现行references里重复加载。

## 更新流程

1. 修改对应包及version，涉及共享分析规则时更新daily的analysis-contract，并核对weekly依赖。
2. 执行离线检查：

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

3. 使用包内evals/evals.json的合成案例试跑，特别检查睡眠跨日、HRV稀疏/前低后高、CGM两点跨20h、日历安排和洞察不足。不要以生产推送命令验证Skill。
4. 提交推送后，将完整包同步到各本地工作区，再以只读模式检查差异为零：

```bash
python3 scripts/sync-skills.py --workspace /path/to/workspace --apply --backup-dir /path/to/new-backup
python3 scripts/sync-skills.py --workspace /path/to/workspace
```

工具支持重复传入workspace，也会更新同工作区现有的稳定名和日期名别名。备份必须可恢复；多工作区根目录请使用不同末级目录名，或分别指定不同备份目录。

## 验证边界

离线单元检查验证完整安装/备份、引用文件漂移检测、续跑输入/模型隔离、部分失败非零退出和截断拒绝。合成案例用于检查实际文字输出，不代表所有真实日期均已通过验收。

现有运行脚本不自动随Skill规范修正。需要另行核验的生产边界包括：CGM覆盖以首末点跨度计算、软链入口的相邻模块查找、睡眠归属校验之前回写canonical，以及主流程默认发送消息。新Skill明确要求检查这些边界，但没有在本次Skill发布中修改生产脚本或调度。

Skill Creator自带quick_validate采用通用frontmatter白名单，不接受本项目既有version/display_name扩展。本项目保留Proma现有格式，以YAML解析、必填字段、版本、引用与运行检查验收，不将该白名单报错当作安装成功证明。
