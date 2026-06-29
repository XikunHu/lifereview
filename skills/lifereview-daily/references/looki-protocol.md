# Looki API 协议参考

## 双管道架构

| 管道 | 延迟 | 内容 |
|------|------|------|
| 🔵 Moments | 数小时（AI 离线处理） | 完整场景片段 |
| 🟢 Realtime | 即时（蓝牙上传） | 当前实时状态 |

## 调用规则

1. **先 realtime → 后 moments**
2. Moments=0 ≠ Looki 离线——先查 realtime
3. realtime 有 + moments=0 → 「🟢 Looki 在线，moments 生成中」
4. realtime 空 + moments=0 → 「🔴 Looki 可能离线」

## VPN 绕过

mihomo/Tyty 透明代理拦截 `open.looki.ai` 的 DNS 和 TLS SNI。必须用 Python + 直连 IP：

```python
import urllib.request, ssl, json
API_KEY = '<YOUR_LOOKI_API_KEY>'
IP = '<YOUR_LOOKI_SERVER_IP>'  # 直连真实 IP，绕过 DNS 劫持
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request(f'https://{IP}/api/v1/moments?on_date=DATE',
    headers={'Host': 'open.looki.ai', 'X-API-Key': API_KEY})
```

## API 端点

- `GET /moments?on_date=YYYY-MM-DD`
- `GET /moments/calendar?start_date=...&end_date=...`
- `GET /moments/search?query=...&page_size=10`
- `GET /me`
- `GET /realtime/latest-event`
- `GET /for_you/items?limit=20&group=comic`

## 离线日协议

Looki 未开启时启用日历+生理替代模式：

### 运动检测（最高优先级）
1. 步数小时分布——连续 2h >500 步 + 活跃 >100kJ → 运动
2. 距离小时峰值——单小时 >1.5km → 跑步
3. AutoSync/Workouts/ 目录——`running_*` 文件 = 确认的跑步

### 评分替代
- 精力：RHR 偏离度 + 睡眠 + 运动 + 日历
- 专注：睡眠 + HRV + 日历间隙
- 压力：日历密度 + 晚间跨度
- 标注 `⚠️ Looki 离线，基于日历+生理估算`

### 日历分类
- 协作：含「会/讨论/对齐/评审/周会/同步/沟通/汇报/方案」
- 产出：含「写/搞/做/整理/准备/材料/文档」
