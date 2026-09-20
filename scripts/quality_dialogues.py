"""Held-out natural dialogues, real backend and providers, sessions kept distinct."""
import concurrent.futures
import json
import re
import sys
import time
import uuid
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.temporal import plain
out=ROOT/'logs/test/architecture-repair'/f'dialogues-{int(time.time())}'
out.mkdir(parents=True,exist_ok=True)
cases=json.loads((ROOT/'tests/dialogue_acceptance.json').read_text(encoding='utf-8'))
def run(case):
    session='dialogue-'+uuid.uuid4().hex
    results=[]
    for turn in case['turns']:
        started=time.perf_counter();failures=[];r={}
        try:
            http=requests.post('http://localhost:5000/api/ask-text',json={'question':turn['q'],'session_id':session,'source':'probe'},timeout=65)
            r=http.json();answer=plain(r.get('answer') or '')
            if http.status_code!=200:failures.append('HTTP '+str(http.status_code))
            if r.get('state')!='ANSWERABLE' and not (turn.get('allow_unconfirmed') and r.get('state')=='NO_CONFIRMED_RESULT'): failures.append('state '+str(r.get('state')))
            for word in turn.get('all',[]):
                if plain(word) not in answer:failures.append('missing '+word)
            if turn.get('regex') and not re.search(turn['regex'],answer):failures.append('missing pattern '+turn['regex'])
            for key,actual in [('route',r.get('route')),('window',r.get('requested_window')),('web',bool(r.get('web_invoked')))]:
                if key in turn and turn[key]!=actual:failures.append(key+' mismatch: '+str(actual))
            if r.get('route')=='CONVERSATION' and (r.get('rag_invoked') or r.get('web_invoked')):failures.append('small talk invoked knowledge')
            if r.get('route')=='CLOCK' and r['time_context']['time'] not in r['answer']:failures.append('clock mismatch')
        except Exception as exc:failures.append(type(exc).__name__+': '+str(exc))
        result={'q':turn['q'],'response':r,'failures':failures,'seconds':round(time.perf_counter()-started,2)}
        results.append(result)
        print(json.dumps({'dialogue':case['name'],'q':turn['q'],'failures':failures},ensure_ascii=True),flush=True)
        (out/(case['name']+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results=[r for group in pool.map(run,cases) for r in group]
report={'turns':len(results),'failed':sum(bool(r['failures']) for r in results),'results':results}
(out/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('ARTIFACTS',out)
sys.exit(int(report['failed']>0))
