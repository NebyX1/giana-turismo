"""Reproducible same-query comparison: Ollama native, DDGS, and LLM-controlled DDGS."""
import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env')
from backend.app.runtime_config import CONFIG
from backend.app.temporal import clock_snapshot
from backend.app.web_tools import agentic_web_research, search_ddgs, search_ollama

CASES=[
    {'id':'october_events','query':'eventos culturales octubre 2026 Minas Lavalleja Uruguay',
     'question':'¿Qué eventos culturales hay en octubre de 2026 en Minas?',
     'window':{'start':'2026-10-01','end':'2026-10-31'},'expected':['semana','lavalleja']},
    {'id':'current_agenda','query':'agenda cultural Minas Lavalleja septiembre 2026',
     'question':'Buscá eventos culturales actuales en Minas, Lavalleja.',
     'window':{'start':'2026-09-19','end':'2026-10-19'},'expected':['minas','lavalleja']},
    {'id':'official_theatre','query':'Teatro Lavalleja Minas sitio oficial programación',
     'question':'Buscá la información oficial actual del Teatro Lavalleja de Minas.',
     'window':None,'expected':['teatro','lavalleja']},
]


def compact(provider, data, error, seconds):
    rows=(data or {}).get('results',[])
    text=' '.join((str(r.get('title',''))+' '+str(r.get('url',''))+' '+str(r.get('content',''))) for r in rows).casefold()
    return {'provider':provider,'available':error is None,'error':error,'seconds':round(seconds,2),
            'result_count':len(rows),'urls':[r.get('url') for r in rows[:8]],
            'official_sources':sum('.gub.uy' in str(r.get('url','')) or 'lavalleja.uy' in str(r.get('url','')) for r in rows),
            'text':text}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    snapshot=clock_snapshot()
    report={'generated_at':snapshot['now'],'model':CONFIG['router_model'],'cases':[]}
    native_quota=False
    for case in CASES:
        item={'id':case['id'],'query':case['query'],'expected':case['expected'],'providers':{}}
        if native_quota:
            native={'provider':'ollama_native','available':False,'error':'WEB_QUOTA_EXCEEDED_PREVIOUS_PROBE',
                    'seconds':0,'result_count':0,'urls':[],'text':''}
        else:
            started=time.perf_counter();data,error=search_ollama(case['query'],8)
            native=compact('ollama_native',data,error,time.perf_counter()-started)
            native_quota=error=='WEB_QUOTA_EXCEEDED'
        item['providers']['ollama_native']=native

        started=time.perf_counter();data,error=search_ddgs(case['query'],8)
        direct=compact('ddgs_direct',data,error,time.perf_counter()-started)
        item['providers']['ddgs_direct']=direct

        started=time.perf_counter()
        agent=agentic_web_research(case['question'],case['window'],snapshot,
            model=CONFIG['router_model'],provider='ddgs')
        agent_text=' '.join(str(x.get('title',''))+' '+str(x.get('url',''))+' '+str(x.get('text','')) for x in agent['evidence']).casefold()
        item['providers']['ddgs_agent']={'provider':'ddgs_agent','available':bool(agent['evidence']),
            'error':agent['errors'],'seconds':round(time.perf_counter()-started,2),
            'result_count':len(agent['evidence']),'sources_read':agent['sources_read'],
            'official_sources':sum('.gub.uy' in str(x.get('url','')) or 'lavalleja.uy' in str(x.get('url','')) for x in agent['evidence']),
            'queries':agent['queries'],'urls':[x.get('url') for x in agent['evidence']],
            'tool_trace':agent['tool_trace'],'text':agent_text}
        for value in item['providers'].values():
            searchable=value.pop('text','')
            value['expected_hits']={term:term.casefold() in searchable for term in case['expected']}
        report['cases'].append(item)
        print(json.dumps({'case':case['id'],'ollama':native['error'],
                          'ddgs_results':direct['result_count'],'agent_evidence':len(agent['evidence']),
                          'agent_pages':agent['sources_read']},ensure_ascii=False),flush=True)
    report['summary']={
        name:{'available_cases':sum(bool(c['providers'][name]['available']) for c in report['cases']),
              'expected_checks_passed':sum(sum(c['providers'][name]['expected_hits'].values()) for c in report['cases']),
              'expected_checks_total':sum(len(c['expected']) for c in report['cases'])}
        for name in ('ollama_native','ddgs_direct','ddgs_agent')}
    out=args.out or ROOT/'logs/test/web-provider-comparison.json'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'REPORT {out}')


if __name__=='__main__':main()
