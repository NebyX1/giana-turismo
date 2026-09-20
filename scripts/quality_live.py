"""Real HTTP/model/RAG/web acceptance; substantive assertions, no mocked replies.

Fresh sessions + shuffled order + repeated runs. Keeps failed attempts. Dates are
explicit acceptance fixtures, not silently weakened after their validity expires.
"""
import argparse
import concurrent.futures
import json
import random
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.temporal import plain

parser=argparse.ArgumentParser()
parser.add_argument('--repeat',type=int,default=2)
parser.add_argument('--ids',default='')
parser.add_argument('--out',default='')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
cases=json.loads((root/'tests/quality_cases.json').read_text(encoding='utf-8'))
if args.ids: cases=[x for x in cases if x['id'] in args.ids.split(',')]
out=Path(args.out) if args.out else root/'logs/test/deep-quality-repair'/f'live-{int(time.time())}'
out.mkdir(parents=True,exist_ok=True)

def run(entry):
    case, repetition=entry
    started=time.perf_counter()
    failures=[]
    response={}
    try:
        http=requests.post('http://127.0.0.1:5000/api/ask-text',json={'question':case['question'],'session_id':f'quality-{uuid.uuid4()}','source':'probe'},timeout=85)
        response=http.json()
        if http.status_code!=200: failures.append(f'HTTP {http.status_code}')
        answer=plain(response.get('answer') or '')
        expired_positive=bool(case.get('positive_until') and datetime.fromisoformat(response.get('time_context',{}).get('now', datetime.now().astimezone().isoformat())) >= datetime.fromisoformat(case['positive_until']))
        for word in ([] if expired_positive else case.get('all',[])):
            if plain(word) not in answer: failures.append('missing answer: '+word)
        if case.get('any') and not any(plain(x) in answer for x in case['any']): failures.append('none of expected facts')
        for pattern in case.get('regex',[]):
            if not re.search(pattern,answer): failures.append('missing pattern: '+pattern)
        for word in case.get('absent',[]):
            if plain(word) in answer: failures.append('forbidden: '+word)
        recommendations=' '.join(plain(x.get('name','')) for x in response.get('evidence_assessment',{}).get('events',[]))
        for word in case.get('not_recommended',[]):
            if plain(word) in recommendations:failures.append('expired recommendation: '+word)
        for key,actual in [('web',bool(response.get('web_invoked'))),('rag',bool(response.get('rag_invoked'))),('route',response.get('route'))]:
            if key in case and case[key]!=actual: failures.append(f'{key}: expected {case[key]}, got {actual}')
        evidence=' '.join(plain(x.get('text',''))+' '+plain(x.get('title','')) for x in response.get('evidence',[]))
        for word in case.get('evidence',[]):
            if plain(word) not in evidence: failures.append('missing retrieved evidence: '+word)
        if response.get('state')!='ANSWERABLE' and not ((case.get('allow_unconfirmed') or expired_positive) and response.get('state')=='NO_CONFIRMED_RESULT'):
            failures.append('bad state: '+str(response.get('state')))
        if expired_positive and re.search(r'(sera|podes ir|tenes|se hace).{0,80}entre sierras|entre sierras.{0,100}(sera|podes ir|se hace)',answer):
            failures.append('expired event offered as upcoming')
        if case.get('dated') and response.get('time_context',{}).get('date')!=case['dated']:
            failures.append('dated fixture expired; revalidate sources, do not relax expectations')
        window=response.get('requested_window')
        if case.get('period')=='week' and window!={'start':'2026-09-19','end':'2026-09-20'}: failures.append('wrong week')
        if case.get('period')=='october' and window!={'start':'2026-10-01','end':'2026-10-31'}: failures.append('wrong month')
        if response.get('route')=='CLOCK':
            clock=response['time_context']
            if clock['time'] not in response['answer'] or clock['date_label'] not in response['answer']: failures.append('clock mismatch')
        if response.get('web_invoked') and not response.get('search_attempts'): failures.append('no real search attempts')
        if '**' in (response.get('answer') or ''): failures.append('raw markdown in spoken answer')
    except Exception as exc:
        failures.append(f'{type(exc).__name__}: {exc}')
    elapsed=round(time.perf_counter()-started,2)
    if elapsed>60: failures.append('exceeds voice backend timeout')
    result={'id':case['id'],'repeat':repetition,'question':case['question'],'seconds':elapsed,'status':'FAIL' if failures else 'PASS','failures':failures,'response':response}
    (out/f"{case['id']}-{repetition}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

work=[(case,n) for n in range(args.repeat) for case in cases]
random.Random(20260919).shuffle(work)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for r in pool.map(run,work):
        results.append(r)
        print(json.dumps({k:r[k] for k in ('id','repeat','status','seconds','failures')},ensure_ascii=True),flush=True)
report={'total':len(results),'failed':sum(r['status']=='FAIL' for r in results),'results':results}
(out/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'ARTIFACTS {out}',flush=True)
sys.exit(int(report['failed']>0))
