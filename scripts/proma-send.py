#!/usr/bin/env python3
"""proma-send.py — 用飞书应用凭据发送消息到指定对话
v2: 消息从 stdin 读取，避免 shell argv 转义问题（\n → 字面量）

⚠️ 使用前：
  1. 创建 ~/.life-log/.proma-credentials.json：
     {"app_id": "<YOUR_APP_ID>", "app_secret": "<YOUR_APP_SECRET>", "chat_id": "<YOUR_FEISHU_CHAT_ID>"}
  2. 替换 <YOUR_FEISHU_CHAT_ID> 为接收消息的 chat_id
"""
import json, sys, os, subprocess

CRED_FILE = os.path.expanduser("~/.life-log/.proma-credentials.json")

def send_message(cred, text):
    # Get token via curl (respects system proxy)
    token_req = subprocess.run(['curl', '-s', '--max-time', '10',
        '-X', 'POST',
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({"app_id": cred["app_id"], "app_secret": cred["app_secret"]})],
        capture_output=True, text=True)
    token_data = json.loads(token_req.stdout)
    token = token_data.get("tenant_access_token", "")
    if not token:
        return {"ok": False, "error": f"token failed: {token_req.stdout[:200]}"}

    # Send message
    content = json.dumps({"text": text})
    body = json.dumps({"receive_id": cred["chat_id"], "msg_type": "text", "content": content})
    result = subprocess.run(['curl', '-s', '--max-time', '10',
        '-X', 'POST',
        f'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id',
        '-H', f'Authorization: Bearer {token}',
        '-H', 'Content-Type: application/json',
        '-d', body],
        capture_output=True, text=True)
    resp = json.loads(result.stdout)
    if resp.get("code") == 0:
        return {"ok": True, "message_id": resp["data"]["message_id"]}
    return {"ok": False, "error": resp.get("msg", result.stdout[:200])}

if __name__ == "__main__":
    with open(CRED_FILE) as f:
        cred = json.load(f)
    # v2: 从 stdin 读取，避免 shell 对 \n 等转义符的二次处理
    text = sys.stdin.read()
    result = send_message(cred, text)
    print(json.dumps(result, ensure_ascii=False))
