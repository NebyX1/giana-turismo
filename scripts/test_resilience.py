"""Fault injection plus compositional cases, separate from real-provider tests."""
import itertools
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app import main as app
from backend.app.intent_router import classify_intent, pure_conversation, CONVERSATION
from backend.app.answer_quality import assessed_answer, parse_assessment
from backend.app.semantic_router import select_tool
import requests

GOOD=json.dumps({'answer':'Don Jorgito [1].','sufficient':True,'evidence_ids':[1],'missing':''})
EVIDENCE=[{'title':'Parrilla','text':'Don Jorgito, Minas','source_refs':[]}]

class Resilience(unittest.TestCase):
    def setUp(self):
        app.SESSION_HISTORY.clear(); app.ACTIVE_GENERATIONS.clear()
        self.client=app.app.test_client()

    def test_greeting_compositions_and_factual_suffixes(self):
        for prefix,name,check,punct in itertools.product(['Hola','Buenas noches','Che, hola'],['Giana','Gianna',''],['¿estás ahí?','¿me recibís bien?','¿me escuchás?','¿estás funcionando?'],[', ','. ',' ']):
            q=prefix+' '+name+punct+check
            with self.subTest(q=q):
                self.assertTrue(pure_conversation(q))
                self.assertEqual(classify_intent(q),CONVERSATION)
                for suffix in [' Quiero comer en Minas',' ¿Hay hospital en Minas?',' ¿Llueve mañana?',' ¿A qué hora abre Don Jorgito?']:
                    self.assertFalse(pure_conversation(q+suffix))

    def test_greeting_with_every_provider_down(self):
        with patch.object(app,'ROUTER_MODE','tools'),patch.object(app,'select_tool',side_effect=AssertionError('provider not needed')),patch.object(app,'retrieve',side_effect=AssertionError('RAG not needed')):
            r=self.client.post('/api/ask-text',json={'question':'Hola Giana, ¿estás ahí?','session_id':'offline'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['route'],'CONVERSATION')
        self.assertIn('escucho',r.json['answer'])

    def test_semantic_conversation_not_in_phrase_list(self):
        with patch.object(app,'ROUTER_MODE','tools'),patch.object(app,'select_tool',return_value={'tool':'conversation','error':None}),patch.object(app,'retrieve',side_effect=AssertionError('no retrieval')):
            r=self.client.post('/api/ask-text',json={'question':'Me estás entendiendo mal'})
        self.assertEqual(r.json['route'],'CONVERSATION')

    def test_format_retry_once_uses_original_evidence(self):
        with patch.object(app,'llm_answer',side_effect=[('broken',None),(GOOD,None)]) as gen:
            value,error=assessed_answer(gen,'q',EVIDENCE)
        self.assertIsNone(error);self.assertTrue(value['recovered_format']);self.assertEqual(gen.call_count,2)
        self.assertEqual(gen.call_args.args,('q',EVIDENCE))

    def test_invalid_citation_and_permanent_bad_format_never_pass(self):
        for raw in ['not json',GOOD.replace('[1]','[99]'),GOOD.replace('true','"true"')]:
            with patch.object(app,'llm_answer',return_value=(raw,None)) as gen:
                value,error=assessed_answer(gen,'q',EVIDENCE)
            self.assertIsNone(value);self.assertEqual(error,'LLM_EVIDENCE_CONTRACT_INVALID');self.assertEqual(gen.call_count,2)

    def test_tool_failures_are_bounded(self):
        for exc in [requests.Timeout(),requests.ConnectionError(),ValueError()]:
            with patch('backend.app.semantic_router.requests.post',side_effect=exc) as post:
                result=select_tool('q',model='test')
            self.assertIsNone(result['tool']);self.assertTrue(result['error']);self.assertEqual(post.call_count,1)

    def test_event_start_crossing_and_window_are_not_model_opinions(self):
        value=json.loads(GOOD)
        value['events']=[{'name':'Encuentro','date':'2026-09-19','time':'20:30','source_id':1}]
        window={'start':'2026-09-19','end':'2026-09-20'}
        for hour,expected in [('20:29:59',None),('20:30:00','EVENT_START_ALREADY_PAST'),('21:00:00','EVENT_START_ALREADY_PAST')]:
            self.assertEqual(parse_assessment(json.dumps(value),EVIDENCE,window,{'date':'2026-09-19','time':hour})[1],expected)
        value['events'][0]['date']='2026-10-07'
        self.assertEqual(parse_assessment(json.dumps(value),EVIDENCE,window,{'date':'2026-09-19','time':'19:00:00'})[1],'EVENT_OUTSIDE_REQUESTED_WINDOW')

    def test_invalid_api_inputs_rejected_before_tools(self):
        with patch.object(app,'select_tool',side_effect=AssertionError('invalid request reached model')):
            for body in [[],42,{'question':45},{'question':['hola']},{'question':'x'*4001},{'question':'hola','session_id':[]},{'question':'hola','generation_id':42},{}]:
                with self.subTest(body=str(body)[:90]):
                    self.assertEqual(self.client.post('/api/ask-text',json=body).status_code,400)

    def test_temporal_recovery_retains_good_candidates_not_bad_prose(self):
        value=json.loads(GOOD)
        value['answer']='Hoy podés ir al evento vencido [1].'
        value['events']=[{'name':'Vencido','date':'2026-09-19','time':'20:30','source_id':1},
                         {'name':'Festival futuro','place':'Teatro','date':'2026-10-07','end_date':'2026-10-11','time':None,'source_id':1}]
        with patch.object(app,'llm_answer',return_value=(json.dumps(value),None)) as gen:
            result,error=assessed_answer(gen,'agenda',EVIDENCE,requested_window={'start':'2026-09-19','end':'2026-10-19'},time_context={'now':'2026-09-19T21:00:00-03:00','date':'2026-09-19','time':'21:00:00'})
        self.assertIsNone(error);self.assertEqual(gen.call_count,2)
        self.assertTrue(result['sufficient']);self.assertNotIn('vencido',result['answer'].lower())
        self.assertIn('Festival futuro',result['answer']);self.assertIn('7 al 11',result['answer'])

    def test_stream_failure_does_not_approve_partial_answer(self):
        with patch.dict('os.environ',{'OLLAMA_API_KEY':'unit-test'}),patch.object(app.LLM_SESSION,'post') as post:
            first=post.return_value.__enter__.return_value
            first.iter_lines.return_value=iter([json.dumps({'message':{'content':'texto parcial'},'done':False})])
            answer,error=app.llm_answer('q',EVIDENCE,model_override='unit-test')
        self.assertIsNone(answer);self.assertEqual(error,'LLM_UNAVAILABLE')
        self.assertTrue(any(x['role']=='user' for x in post.call_args.kwargs['json']['messages']))

    def test_unknown_or_multiple_tools_not_executed(self):
        for calls in [[{'function':{'name':'delete_files','arguments':{}}}], [{'function':{'name':'knowledge','arguments':{}}}]*2, [{'function':{'name':'knowledge','arguments':{'command':'x'}}}]]:
            with patch('backend.app.semantic_router.requests.post') as post:
                post.return_value.json.return_value={'message':{'tool_calls':calls}}
                result=select_tool('q',model='test')
            self.assertIsNone(result['tool'])

    def test_router_outage_falls_back_and_next_turn_works(self):
        with patch.object(app,'ROUTER_MODE','tools'),patch.object(app,'select_tool',return_value={'tool':None,'error':'Timeout'}) as router:
            r=self.client.post('/api/ask-text',json={'question':'Qué hora es'})
        self.assertEqual(router.call_count,2);self.assertEqual(r.json['route'],'CLOCK')
        self.assertEqual(self.client.post('/api/ask-text',json={'question':'Hola Giana, ¿estás ahí?'}).json['route'],'CONVERSATION')

    def test_web_transient_retry_bounded_and_auth_not_retried(self):
        def response(status,headers=None):
            r=requests.Response();r.status_code=status;r._content=b'{"results": []}';r.headers.update(headers or {});return r
        for status in [408,429,500,502,503,504]:
            with self.subTest(status=status),patch.object(app.requests,'post',side_effect=[response(status),response(200)]) as post,patch.object(app.time,'sleep'):
                data,error=app.web_provider_request('web_search',{},(1,1),'WEB_SEARCH_ERROR')
                self.assertIsNone(error);self.assertEqual(data,{'results':[]});self.assertEqual(post.call_count,2)
        for result in [response(401),response(403),response(429,{'Retry-After':'120'})]:
            with patch.object(app.requests,'post',return_value=result) as post,patch.object(app.time,'sleep'):
                data,error=app.web_provider_request('web_search',{},(1,1),'WEB_SEARCH_ERROR')
                self.assertEqual(error,'WEB_SEARCH_ERROR');self.assertEqual(post.call_count,1)
        with patch.object(app.requests,'post',side_effect=requests.Timeout()) as post,patch.object(app.time,'sleep'):
            data,error=app.web_provider_request('web_search',{},(1,1),'WEB_SEARCH_ERROR')
            self.assertEqual(error,'WEB_SEARCH_ERROR');self.assertEqual(post.call_count,2)
        quota=response(429);quota._content=b'{"error":"you have reached your web search session request limit"}'
        with patch.object(app.requests,'post',return_value=quota) as post,patch.object(app.time,'sleep') as sleep:
            data,error=app.web_provider_request('web_search',{},(1,1),'WEB_SEARCH_ERROR')
            self.assertEqual(error,'WEB_QUOTA_EXCEEDED');self.assertEqual(post.call_count,1);sleep.assert_not_called()
        with patch.object(app,'ROUTER_MODE','rules'),patch.dict(app.CONFIG,{'web_research_mode':'native'}),patch.object(app,'web_search',return_value=(None,'WEB_QUOTA_EXCEEDED')):
            result=self.client.post('/api/ask-text',json={'question':'Buscá eventos culturales en Minas'})
        self.assertEqual(result.json['error_code'],'WEB_QUOTA_EXCEEDED')
        self.assertIn('límite de uso',result.json['answer'])

    def test_rewrite_cannot_erase_original_place_evidence(self):
        original='Puedo llevar un perro al Penitente.'
        rewrite='Se permiten perros en el Cerro Penitente'
        correct={**EVIDENCE[0],'chunk_id':'original','title':'Salto del Penitente','text':'Mascotas permitidas con correa.'}
        unrelated={**EVIDENCE[0],'chunk_id':'rewrite','title':'Otra fuente','text':'Paisaje serrano.'}
        def retrieve(q,**kw):return ([correct] if q==original else [unrelated]),'HYBRID_RERANK'
        with patch.object(app,'ROUTER_MODE','tools'),patch.object(app,'select_tool',return_value={'tool':'knowledge','query':rewrite,'error':None}),patch.object(app,'retrieve',side_effect=retrieve) as retrieval,patch.object(app,'llm_answer',return_value=(GOOD,None)) as generate:
            result=self.client.post('/api/ask-text',json={'question':original})
        self.assertEqual(result.status_code,200)
        self.assertEqual([c.args[0] for c in retrieval.call_args_list],[original,rewrite])
        self.assertEqual(generate.call_args.args[1],[correct,unrelated])

    def test_transport_reconnect_keeps_logical_context_and_new_chat_isolated(self):
        app.remember_turn('chat-a','Dirección de Don Jorgito','Av Varela 947')
        captured=[]
        def tool(q,history,**kw):
            captured.append(list(history))
            return {'tool':'knowledge','query':'teléfono Don Jorgito','error':None}
        with patch.object(app,'ROUTER_MODE','tools'),patch.object(app,'select_tool',side_effect=tool),patch.object(app,'retrieve',return_value=(EVIDENCE,'HYBRID_RERANK')),patch.object(app,'llm_answer',return_value=(GOOD,None)):
            self.client.post('/api/ask-text',json={'question':'¿Y su teléfono?','session_id':'voice-new','conversation_id':'chat-a'})
            self.client.post('/api/ask-text',json={'question':'Una consulta','session_id':'voice-other','conversation_id':'chat-b'})
        self.assertEqual(captured[0][0]['assistant'],'Av Varela 947');self.assertEqual(captured[1],[])

if __name__=='__main__':unittest.main()
