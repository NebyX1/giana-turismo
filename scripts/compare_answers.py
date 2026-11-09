"""Same evidence/questions across models; evaluates substantive oracle, not tone."""
import concurrent.futures
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.main import llm_answer
from backend.app.answer_quality import CONTRACT, parse_assessment
from backend.app.temporal import plain
import re

out=ROOT/'logs/test/architecture-repair'/f'answers-{int(time.time())}'
out.mkdir(parents=True,exist_ok=True)
all_cases=json.loads((ROOT/'tests/quality_cases.json').read_text(encoding='utf-8'))
ids=['asado_exact','vegan','gluten','dog_salus','camp_electricity','parking_hotel',
     'asado_phone','vegan_mariscala','events_explicit_month','web_missing_rag']
cases=[c for c in all_cases if c['id'] in ids]
def run(item):
    c,model=item
    old=json.loads((ROOT/f"logs/test/deep-quality-repair/gate-1789859237/http/{c['id']}-0.json").read_text(encoding='utf-8'))['response']
    started=time.perf_counter()
    raw,error=llm_answer(c['question'],old['evidence'],answer_contract=CONTRACT,model_override=model)
    assessment,parse_error=parse_assessment(raw,old['evidence']) if not error else (None,error)
    failures=[parse_error] if parse_error else []
    answer=plain((assessment or {}).get('answer',''))
    if assessment:
        for term in c.get('all',[]):
            if plain(term) not in answer: failures.append('missing '+term)
        for pattern in c.get('regex',[]):
            if not re.search(pattern,answer): failures.append('missing pattern '+pattern)
        if not c.get('allow_unconfirmed') and not assessment['sufficient']: failures.append('incorrect insufficiency')
    return {'id':c['id'],'model':model,'seconds':round(time.perf_counter()-started,2),
            'failures':failures,'assessment':assessment,'raw':raw,'error':error}
work=[(c,m) for m in ['gemma4:31b-cloud','deepseek-v4.1-flash:cloud','glm-5.3:cloud'] for c in cases]
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for r in pool.map(run,work):
        results.append(r)
        print(json.dumps({k:r[k] for k in ['id','model','seconds','failures']},ensure_ascii=True),flush=True)
        (out/'RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('ARTIFACTS',out)
