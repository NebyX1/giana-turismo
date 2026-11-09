import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.main import llm_answer
from backend.app.answer_quality import assessed_answer
from backend.app.temporal import clock_snapshot
case=json.loads((ROOT/'logs/test/deep-quality-repair/live-1789861532/events_broad-1.json').read_text(encoding='utf-8'))
attempts=[]
def generate(*args,**kwargs):
    raw,error=llm_answer(*args,**kwargs)
    attempts.append({'model':kwargs.get('model_override','primary'),'raw':raw,'error':error})
    return raw,error
value,error=assessed_answer(generate,case['question'],case['response']['evidence'],requested_window=case['response']['requested_window'],time_context=clock_snapshot())
report={'value':value,'error':error,'attempts':attempts}
(ROOT/'logs/test/architecture-repair/event-contract-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
