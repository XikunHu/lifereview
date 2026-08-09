#!/usr/bin/env python3
"""Resumable DeepSeek V4 Flash runner: one file per lens, then merge."""
import argparse, concurrent.futures, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LENSES = [
 (1,'标准时间轴','沿关键转折讲完整轨迹，删掉次要节点。'),
 (2,'结论优先','先说当天主矛盾，再用少量节点支撑。'),
 (3,'三种不动','比较低步数时段，说明不动不等于同一种状态。'),
 (4,'身体换挡','看训练、工作、低速、收尾之间何时同步、何时慢一拍。'),
 (5,'日程密度','回答事情最多时身体是否最紧，日程必须和生理配对。'),
 (6,'活动结构','解释4991步具体由哪些时段组成。'),
 (7,'非步行活动','解释步数不高但训练和活动消耗并不少。'),
 (8,'多系统不同步','比较心率、恢复弹性、血糖的不同节奏。'),
 (9,'晚间血糖','描述血糖变化发生在哪个行为时段，不编造餐食。'),
 (10,'证据地图','区分可确认、较可能、继续观察和原因未知。'),
]

def request(root,key,model,max_tokens,system,data,item,timeout):
 n,name,focus=item
 prompt=f'''只生成一个 LifeReview 版本：版本 {n}｜{name}。
本版要回答：{focus}
要求：4–6个必要节点；每节点最多2项数字，必要时才3项；每个节点短行；末尾必须有“两个洞察”，恰好两句编号洞察，且两句都包含行为与身体关系；不要解释方法。

真实数据：\n{json.dumps(data,ensure_ascii=False)}'''
 payload={'model':model,'max_tokens':max_tokens,'system':system,'messages':[{'role':'user','content':prompt}]}
 try:
  p=subprocess.run(['curl','-sS','--fail-with-body','--noproxy','*','--max-time',str(timeout),'-X','POST',f'{root}/v1/messages','-H',f'Authorization: Bearer {key}','-H','Content-Type: application/json','-H','anthropic-version: 2023-06-01','-d',json.dumps(payload,ensure_ascii=False)],capture_output=True,text=True,timeout=timeout+20)
  if p.returncode: return '',{'error':(p.stderr or p.stdout)[-800:],'max_tokens':max_tokens}
  r=json.loads(p.stdout)
  text='\n'.join(x.get('text','') for x in r.get('content',[]) if x.get('type')=='text').strip()
  meta={'usage':r.get('usage',{}),'content_types':[x.get('type') for x in r.get('content',[])],'max_tokens':max_tokens}
  if not text: meta['error']='empty_text'
  return text,meta
 except Exception as e:
  return '',{'error':type(e).__name__+': '+str(e),'max_tokens':max_tokens}

def one(item,args,system,data,outdir,root,key):
 n,_,_=item
 target=outdir/f'version-{n:02d}.md'; meta_path=outdir/f'version-{n:02d}.usage.json'
 if target.exists() and target.stat().st_size>30 and not args.fresh:
  return n,'skipped'
 text,meta=request(root,key,args.model,args.max_tokens,system,data,item,args.timeout)
 if not text:
  time.sleep(2)
  text,meta2=request(root,key,args.model,args.retry_max_tokens,system,data,item,args.retry_timeout)
  meta={'first':meta,'retry':meta2}
 if text: target.write_text(text+'\n'); status='ok'
 else: status='failed'
 meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2))
 return n,status

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--input',required=True); ap.add_argument('--outdir',required=True)
 ap.add_argument('--model',default='deepseek-v4-flash'); ap.add_argument('--workers',type=int,default=2)
 ap.add_argument('--max-tokens',type=int,default=16000); ap.add_argument('--retry-max-tokens',type=int,default=24000)
 ap.add_argument('--timeout',type=int,default=240); ap.add_argument('--retry-timeout',type=int,default=360)
 ap.add_argument('--fresh',action='store_true')
 args=ap.parse_args()
 key=os.getenv('PROMA_API_KEY') or os.getenv('LLM_API_KEY')
 if not key: raise SystemExit('Missing PROMA_API_KEY/LLM_API_KEY')
 root=(os.getenv('LLM_API_URL') or os.getenv('PROMA_API_ROOT') or 'https://api.proma.cool').rstrip('/')
 if root.endswith('/api/v1'): root=root[:-7]
 outdir=Path(args.outdir); outdir.mkdir(parents=True,exist_ok=True)
 system=(HERE/'SKILL.md').read_text(); data=json.loads(Path(args.input).read_text())
 if args.fresh:
  for p in outdir.glob('version-*.md'): p.unlink()
  for p in outdir.glob('version-*.usage.json'): p.unlink()
 results=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,3))) as ex:
  fs=[ex.submit(one,item,args,system,data,outdir,root,key) for item in LENSES]
  for f in concurrent.futures.as_completed(fs):
   r=f.result(); results.append(r); print(json.dumps({'version':r[0],'status':r[1]},ensure_ascii=False),flush=True)
 results.sort()
 merged=[]
 for n,_,_ in LENSES:
  p=outdir/f'version-{n:02d}.md'
  if p.exists(): merged.append(p.read_text().strip())
 (outdir/'merged-10-versions.md').write_text('\n\n---\n\n'.join(merged)+'\n')
 print(json.dumps({'ok':sum(s in ('ok','skipped') for _,s in results),'failed':[n for n,s in results if s=='failed'],'merged':str(outdir/'merged-10-versions.md')},ensure_ascii=False))

if __name__=='__main__': main()
