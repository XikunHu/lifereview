#!/usr/bin/env python3
"""Run lifereview-trajectory-map-20260808 with an existing Proma Cloud key.

Credential resolution: PROMA_API_KEY or LLM_API_KEY from the current machine environment.
No key is persisted or printed.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--model', default=os.getenv('LLM_MODEL', 'deepseek-v4-flash'))
    ap.add_argument('--max-tokens', type=int, default=12000)
    args = ap.parse_args()

    api_key = os.getenv('PROMA_API_KEY') or os.getenv('LLM_API_KEY')
    if not api_key:
        raise SystemExit('Missing PROMA_API_KEY/LLM_API_KEY in environment')
    api_root = (os.getenv('LLM_API_URL') or os.getenv('PROMA_API_ROOT') or 'https://api.proma.cool').rstrip('/')
    if api_root.endswith('/api/v1'):
        api_root = api_root[:-7]

    skill = (HERE / 'SKILL.md').read_text()
    data = json.loads(Path(args.input).read_text())
    prompt = (
        '基于下面同一天的真实结构化数据，严格按 system 中的 Skill 生成10个真正不同的版本。\n'
        '每版保留4–7个必要节点，不必覆盖所有时段；每节点最多2个数字，确有必要才3个。\n'
        '每版末尾必须有“两个洞察”，并且恰好两句编号洞察。\n'
        '只输出10个版本正文，不解释方法。\n\n'
        'DATA:\n' + json.dumps(data, ensure_ascii=False)
    )
    payload = {
        'model': args.model,
        'max_tokens': args.max_tokens,
        'system': skill,
        'messages': [{'role': 'user', 'content': prompt}],
    }
    proc = subprocess.run([
        'curl', '-sS', '--fail-with-body', '--noproxy', '*', '--max-time', '600',
        '-X', 'POST', f'{api_root}/v1/messages',
        '-H', f'Authorization: Bearer {api_key}',
        '-H', 'Content-Type: application/json',
        '-H', 'anthropic-version: 2023-06-01',
        '-d', json.dumps(payload, ensure_ascii=False),
    ], capture_output=True, text=True, timeout=620)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise SystemExit(proc.returncode)
    response = json.loads(proc.stdout)
    text = '\n'.join(block.get('text', '') for block in response.get('content', []) if block.get('type') == 'text').strip()
    if not text:
        raise SystemExit('Model returned no text content; raise max_tokens and retry')
    Path(args.output).write_text(text + '\n')
    usage = response.get('usage', {})
    print(json.dumps({'model': args.model, 'output': args.output, 'usage': usage}, ensure_ascii=False))


if __name__ == '__main__':
    main()
