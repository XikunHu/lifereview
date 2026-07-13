#!/bin/bash
# secret_scan.sh — 提交前扫描敏感信息
# 参考 duanyu119/open-health-database 的 secret_scan.sh
# 用法: ./secret_scan.sh (手动) 或作为 git pre-commit hook

set -euo pipefail
cd "$(dirname "$0")/.."

# 如果没有 ripgrep, 回退到 grep -r
if command -v rg &>/dev/null; then
  SCAN_CMD="rg -n --glob '!.git' --glob '!*.duckdb' --glob '!.venv' --glob '!secret_scan.sh'"
else
  SCAN_CMD="grep -rnI --exclude-dir=.git --exclude=secret_scan.sh"
fi

FOUND=0

echo "🔍 扫描敏感信息..."

# 1. Looki API Key
if $SCAN_CMD 'lk-[A-Za-z0-9]{30,}' . 2>/dev/null | grep -qv 'YOUR_LOOKI_API_KEY'; then
  echo "❌ 发现 Looki API Key"
  $SCAN_CMD 'lk-[A-Za-z0-9]{30,}' . 2>/dev/null | grep -v 'YOUR_LOOKI_API_KEY'
  FOUND=1
fi

# 2. 飞书 Chat ID
if $SCAN_CMD 'ou_[a-z0-9]{20,}' . 2>/dev/null | grep -qv 'YOUR_FEISHU_CHAT_ID'; then
  echo "❌ 发现飞书 Chat ID"
  $SCAN_CMD 'ou_[a-z0-9]{20,}' . 2>/dev/null | grep -v 'YOUR_FEISHU_CHAT_ID'
  FOUND=1
fi

# 3. 硬编码 IP (Looki server)
if $SCAN_CMD '52\.27\.31\.164' . 2>/dev/null | grep -qv 'YOUR_LOOKI'; then
  echo "❌ 发现硬编码 IP"
  $SCAN_CMD '52\.27\.31\.164' . 2>/dev/null | grep -v 'YOUR_LOOKI'
  FOUND=1
fi

# 4. 个人路径 (含有用户名)
if $SCAN_CMD '/Users/nixon|/Users/xikun|胡熙坤' . 2>/dev/null | grep -qv 'YOUR_\|example'; then
  echo "❌ 发现个人路径或姓名"
  $SCAN_CMD '/Users/nixon|/Users/xikun|胡熙坤' . 2>/dev/null | grep -v 'YOUR_\|example'
  FOUND=1
fi

# 5. 飞书 App Secret
if $SCAN_CMD 'app_secret|APP_SECRET' . 2>/dev/null | grep -qv 'YOUR_'; then
  echo "❌ 发现 App Secret"
  $SCAN_CMD 'app_secret|APP_SECRET' . 2>/dev/null | grep -v 'YOUR_'
  FOUND=1
fi

# 6. 飞书 Bot app_id (cli_*)
if $SCAN_CMD 'cli_[a-f0-9]{16}' . 2>/dev/null | grep -qv 'YOUR_'; then
  echo "❌ 发现飞书 Bot app_id (cli_*)"
  $SCAN_CMD 'cli_[a-f0-9]{16}' . 2>/dev/null | grep -v 'YOUR_'
  FOUND=1
fi

# 7. 飞书群聊 chat_id (oc_*)
if $SCAN_CMD 'oc_[a-z0-9]{30,}' . 2>/dev/null | grep -qv 'YOUR_'; then
  echo "❌ 发现飞书群聊 chat_id (oc_*)"
  $SCAN_CMD 'oc_[a-z0-9]{30,}' . 2>/dev/null | grep -v 'YOUR_'
  FOUND=1
fi

if [ "$FOUND" -eq 1 ]; then
  echo ""
  echo "⚠️  提交已阻止。请将敏感信息替换为 <YOUR_*> 占位符后重试。"
  exit 1
fi

echo "✅ 未发现敏感信息"
