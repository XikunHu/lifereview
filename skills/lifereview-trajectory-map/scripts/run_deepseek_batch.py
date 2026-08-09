#!/usr/bin/env python3
"""Generate ten LifeReview trajectory variants with DeepSeek V4 Flash.

Uses the machine's existing PROMA_API_KEY/LLM_API_KEY. Keys are never persisted or printed.
Each lens is a separate request to avoid reasoning tokens consuming a monolithic 10-version response.
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LENSES = [
    (1, '标准时间轴', '沿当天关键转折讲完整轨迹，删除次要节点。'),
    (2, '结论优先', '先给当天主矛盾，再用4到5个节点支撑。'),
    (3, '三种不动', '比较低步数时段，解释不动并不等于同一种状态。'),
    (4, '身体换挡', '观察训练、工作、低速、收尾之间，行为与身体何时同步或慢一拍。'),
    (5, '日程密度', '回答事情最多时身体是否最紧，必须把日程与生理数据配对。'),
    (6, '活动结构', '解释4991步由哪些时段组成，以及它与当天行为的关系。'),
    (7, '非步行活动', '解释为什么步数不高但力量训练与活动消耗并不少。'),
    (8, '多系统不同步', '比较心率、恢复弹性、血糖的不同节奏。'),
    (9, '晚间血糖', '描述代谢变化发生在哪个行为时段，不编造餐食。'),
    (10, '证据地图', '区分可以确认、较可能、继续观察和原因未知。'),
]


def call_one(api_root, api_key, model, max_tokens, system, data, item):
    num, name, focus = item
    prompt = f'''生成且只生成一个 LifeReview 版本：版本 {num}｜{name}。
本版问题：{focus}

严格要求：
- 4–7个必要节点；每节点标题后，数字行最多2项，必要时才3项；再用一句极短人话说明关系。
- 手机短行，不写长段落，不复述机制。
- 末尾输出“两个洞察”，恰好两句编号洞察；两句来自不同维度，且都包含行为与身体数据关系。
- 不解释方法，不输出质量检查。

DATA:
{json.dumps(data, ensure_ascii=False)}'''
    payload = {'model': model, 'max_tokens': max_tokens, 'system': system, 'messages': [{'role': 'user', 'content': prompt}]}
    proc = subprocess.run([
        'curl', '-sS', '--fail-with-body', '--noproxy', '*', '--max-time', '300',
        '-X', 'POST', f'{api_root}/v1/messages',
        '-H', f'Authorization: Bearer {api_key}',
        '-H', 'Content-Type: application/json',
        '-H', 'anthropic-version: 2023-06-01',
        '-d', json.dumps(payload, ensure_ascii=False),
    ], capture_output=True, text=True, timeout=320)
    if proc.returncode:
        return num, '', {'error': (proc.stderr or proc.stdout)[-500:]}
    response = json.loads(proc.stdout)
    text = '\n'.join(b.get('text', '') for b in response.get('content', []) if b.get('type') == 'text').strip()
    meta = {'usage': response.get('usage', {}), 'content_types': [b.get('type') for b in response.get('content', [])]}
    if not text:
        meta['error'] = 'empty_text'
    return num, text, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--model', default=os.getenv('LLM_MODEL', 'deepseek-v4-flash'))
    ap.add_argument('--max-tokens', type=int, default=6000)
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--only', type=int, choices=range(1, 11), help='Run only one lens for a probe')
    ap.add_argument('--from-num', type=int, default=1, choices=range(1, 11), help='Run lenses from this number')
    ap.add_argument('--retry-max-tokens', type=int, default=32000)
    args = ap.parse_args()
    key = os.getenv('PROMA_API_KEY') or os.getenv('LLM_API_KEY')
    if not key:
        raise SystemExit('Missing PROMA_API_KEY/LLM_API_KEY')
    root = (os.getenv('LLM_API_URL') or os.getenv('PROMA_API_ROOT') or 'https://api.proma.cool').rstrip('/')
    if root.endswith('/api/v1'):
        root = root[:-7]
    system = (HERE / 'SKILL.md').read_text()
    data = json.loads(Path(args.input).read_text())
    selected = [item for item in LENSES if (args.only is None and item[0] >= args.from_num) or (args.only is not None and item[0] == args.only)]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.workers, 10)) as ex:
        futures = [ex.submit(call_one, root, key, args.model, args.max_tokens, system, data, item) for item in selected]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    results.sort()
    failed_nums = {n for n, text, _ in results if not text}
    if failed_nums:
        selected_by_num = {item[0]: item for item in selected}
        retry_results = []
        for n in sorted(failed_nums):
            retry_results.append(call_one(root, key, args.model, args.retry_max_tokens, system, data, selected_by_num[n]))
        retry_by_num = {n: (n, text, meta) for n, text, meta in retry_results}
        original_by_num = {n: item for n, item in [(n, (n, text, meta)) for n, text, meta in results]}
        results = [retry_by_num.get(n, original_by_num[n]) if n in failed_nums else original_by_num[n] for n in sorted(original_by_num)]
    results.sort()
    failed = [(n, m) for n, text, m in results if not text]
    output = '\n\n---\n\n'.join(text for _, text, _ in results if text) + '\n'
    Path(args.output).write_text(output)
    meta_path = str(Path(args.output).with_suffix('.usage.json'))
    Path(meta_path).write_text(json.dumps({str(n): m for n, _, m in results}, ensure_ascii=False, indent=2))
    print(json.dumps({'model': args.model, 'completed': len(results)-len(failed), 'failed': [n for n,_ in failed], 'output': args.output, 'usage_file': meta_path}, ensure_ascii=False))
    if failed:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
