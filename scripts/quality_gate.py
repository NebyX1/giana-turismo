"""One reproducible quality gate. Any failed/missing stage blocks acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.build_identity import backend_build_id

parser=argparse.ArgumentParser()
parser.add_argument('--repeat',type=int,default=2)
parser.add_argument('--skip-voice',action='store_true',help='Partial diagnostic only; never full PASS')
args=parser.parse_args()
out=ROOT/'logs/test/deep-quality-repair'/f'gate-{int(time.time())}'
out.mkdir(parents=True,exist_ok=True)
ready=requests.get('http://127.0.0.1:5000/ready',timeout=5).json()
if ready.get('build_id')!=backend_build_id():
    raise SystemExit('BLOCKED: backend is not running the code on disk; restart it before testing.')
files=[*ROOT.glob('backend/app/*.py'),*ROOT.glob('backend/app/*.json'),*ROOT.glob('voice/*.py'),*ROOT.glob('frontend/src/**/*.ts'),*ROOT.glob('frontend/src/**/*.tsx'),*ROOT.glob('scripts/test_*.py'),*ROOT.glob('scripts/quality*.py'),*ROOT.glob('tests/e2e/*.mjs'),*ROOT.glob('tests/*acceptance.json'),ROOT/'tests/quality_cases.json']
files.extend([ROOT/'scripts/create_deep_quality_fixtures.ps1',*ROOT.glob('tests/e2e/fixtures/deep-quality/*.wav'),*ROOT.glob('tests/e2e/fixtures/voice-resilience/*.wav'),*ROOT.glob('tests/e2e/fixtures/voice-context/*.wav')])
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
stages=[
    ('resilience',[sys.executable,'scripts/test_resilience.py']),
    ('web-tools-contracts',[sys.executable,'scripts/test_web_tools.py']),
    ('presentation-contracts',[sys.executable,'scripts/test_presentation.py']),
    ('deep-contracts',[sys.executable,'scripts/test_deep_quality.py']),
    ('time-web-contracts',[sys.executable,'scripts/test_time_web.py']),
    ('router',[sys.executable,'scripts/test_intent_router.py']),
    ('conversation-regressions',[sys.executable,'scripts/test_conversation_regressions.py']),
    ('turn-buffer',[sys.executable,'scripts/test_turn_taking.py']),
    ('ui-stale-response-contract',['node','tests/e2e/stale_text.mjs']),
    ('real-http-matrix',[sys.executable,'scripts/quality_live.py','--repeat',str(args.repeat),'--out',str(out/'http')]),
    ('real-dialogues',[sys.executable,'scripts/quality_dialogues.py']),
    ('real-browser-text',['node','tests/e2e/deep_quality_text.mjs']),
]
if not args.skip_voice: stages.append(('real-browser-voice',['node','tests/e2e/conversation_audio.mjs']))
if not args.skip_voice: stages.append(('real-voice-interruption',['node','tests/e2e/conversation_audio.mjs']))
if not args.skip_voice: stages.append(('real-voice-context',['node','tests/e2e/conversation_audio.mjs']))
results=[]
for name,cmd in stages:
    print(f'STAGE {name}',flush=True)
    env=dict(os.environ,GIANA_E2E_MODE='deep-quality',PYTHONUTF8='1')
    if name=='real-voice-interruption':env['GIANA_E2E_MODE']='voice-resilience'
    if name=='real-voice-context':env['GIANA_E2E_MODE']='voice-context'
    if name not in {'real-http-matrix','real-browser-text','real-browser-voice','resilience'}:
        env['GIANA_ROUTER_MODE']='rules'
    started=time.time()
    try:
        with (out/f'{name}.log').open('w',encoding='utf-8') as log:
            run=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
        code=run.returncode
    except subprocess.TimeoutExpired:
        code=124
    results.append({'stage':name,'exit_code':code,'seconds':round(time.time()-started,1),'status':'PASS' if code==0 else 'FAIL'})
    print(json.dumps(results[-1]),flush=True)
    (out/'RESULTS.json').write_text(json.dumps({'completed':False,'stages':results},indent=2),encoding='utf-8')
unchanged=all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==manifest[str(p.relative_to(ROOT))] for p in files)
passed=not args.skip_voice and unchanged and all(x['exit_code']==0 for x in results)
report={'completed':True,'pass':passed,'partial':args.skip_voice,'code_unchanged':unchanged,'backend_build_id':ready['build_id'],'manifest':manifest,'stages':results}
(out/'RESULTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(f'GATE {"PASS" if passed else "FAIL/PARTIAL"} ARTIFACTS {out}',flush=True)
sys.exit(int(not passed))
