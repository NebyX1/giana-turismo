"""Real provider comparison; does not change the running application's config."""
import concurrent.futures
import json
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env')
from backend.app.semantic_router import select_tool
from backend.app.intent_router import classify_intent

out=ROOT/'logs/test/architecture-repair'/f'comparison-{int(time.time())}'
out.mkdir(parents=True,exist_ok=True)
cases=json.loads((ROOT/'tests/routing_acceptance.json').read_text(encoding='utf-8'))
mapping={'CONVERSATION':'conversation','TOURISM_RAG':'knowledge','CURRENT_INFO':'web','WEB_FOLLOWUP':'web','CURRENT_TIME':'clock','GIANA_META':'persona','OUT_OF_SCOPE':'out_of_scope'}
results=[{'q':c['q'],'expected':c['tool'],'tool':mapping[classify_intent(c['q'])],
          'model':'rules-baseline','mode':'rules','seconds':0} for c in cases]
work=[(c,model,mode) for model in ['gemma4:31b-cloud','deepseek-v4.1-flash:cloud','glm-5.3:cloud']
      for mode in ['tools','json'] for c in cases]
def run(item):
    c,model,mode=item
    result=select_tool(c['q'],c.get('history',[]),model=model,mode=mode,timeout=12)
    return dict(q=c['q'],expected=c['tool'],**result)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(run,work):
        results.append(result)
        print(json.dumps(result,ensure_ascii=True),flush=True)
        (out/'RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
for model,mode in sorted({(x['model'],x['mode']) for x in results}):
    group=[x for x in results if x['model']==model and x['mode']==mode]
    print(json.dumps({'model':model,'mode':mode,'passed':sum(x['tool']==x['expected'] for x in group),
                      'total':len(group),'max_seconds':max(x['seconds'] for x in group)}),flush=True)
print('ARTIFACTS',out)
