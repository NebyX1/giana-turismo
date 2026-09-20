"""Security, budget and degradation contracts for model-controlled web tools."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app import web_tools as wt

SNAPSHOT={'now':'2026-09-19T21:00:00-03:00'}
WINDOW={'start':'2026-09-19','end':'2026-09-20'}
ROW={'title':'Agenda Minas','url':'https://example.com/agenda','content':'Evento en Minas el 20 de septiembre.'}


class WebToolContracts(unittest.TestCase):
    def setUp(self):
        wt._SEARCH_CACHE.clear()

    def test_private_and_credential_urls_are_rejected(self):
        for url in ['http://127.0.0.1/x','http://localhost/x','http://169.254.169.254/latest',
                    'file:///etc/passwd','https://user:pass@example.com/x']:
            with self.subTest(url=url):
                self.assertFalse(wt._public_url(url))

    def test_redirect_target_is_revalidated_before_second_request(self):
        redirect=Mock(is_redirect=True,is_permanent_redirect=False,headers={'Location':'http://127.0.0.1/private'})
        with patch.object(wt,'_public_url',side_effect=[True,False]),patch.object(wt.requests,'get',return_value=redirect) as get:
            page,error=wt.fetch_public_page('https://example.com')
        self.assertIsNone(page);self.assertEqual(error,'WEB_URL_REJECTED');self.assertEqual(get.call_count,1)

    def test_unknown_tool_and_unsearched_url_are_never_executed(self):
        messages=[
            {'content':'','tool_calls':[{'function':{'name':'delete_files','arguments':{}}},
                                         {'function':{'name':'open_page','arguments':{'url':'https://example.com/secret'}}}]},
            {'content':'DONE'},
            {'content':'DONE'}]
        with patch.object(wt,'_chat',side_effect=messages),patch.object(wt,'search_ddgs',return_value=({'results':[ROW]},None)) as search,patch.object(wt,'fetch_public_page') as fetch:
            result=wt.agentic_web_research('información turística Minas',None,SNAPSHOT,model='test')
        fetch.assert_not_called();self.assertEqual(search.call_count,1)
        self.assertIn('WEB_AGENT_DEGRADED_SEARCH',result['errors'])

    def test_agent_obeys_search_and_page_budgets(self):
        calls=[]
        for index in range(7):
            calls.append({'content':'','tool_calls':[
                {'function':{'name':'search_web','arguments':{'query':f'q{index}','max_results':8}}},
                {'function':{'name':'open_page','arguments':{'url':'https://example.com/agenda'}}}]})
        with patch.object(wt,'_chat',side_effect=calls),patch.object(wt,'search_ddgs',return_value=({'results':[ROW]},None)) as search,patch.object(wt,'fetch_public_page',return_value=({'title':'Agenda','url':ROW['url'],'content':'Minas 20 septiembre'},None)) as fetch:
            result=wt.agentic_web_research('eventos Minas',WINDOW,SNAPSHOT,model='test')
        self.assertLessEqual(search.call_count,3);self.assertLessEqual(fetch.call_count,5)
        self.assertLessEqual(len(result['tool_trace']),8)

    def test_model_outage_degrades_to_one_bounded_search(self):
        with patch.object(wt,'_chat',side_effect=requests.Timeout()),patch.object(wt,'search_ddgs',return_value=({'results':[ROW]},None)) as search:
            result=wt.agentic_web_research('eventos actuales en Minas',WINDOW,SNAPSHOT,model='test')
        self.assertEqual(search.call_count,2)
        self.assertEqual(search.call_args_list[0].args,('eventos actuales en Minas',8))
        self.assertIn('fechas exactas etapas',search.call_args_list[1].args[0])
        self.assertEqual(len(result['evidence']),1)
        self.assertIn('WEB_AGENT_MODEL_ERROR',result['errors'])
        self.assertIn('WEB_AGENT_DEGRADED_SEARCH',result['errors'])

    def test_ddgs_cache_avoids_duplicate_provider_call(self):
        provider=Mock();provider.text.return_value=[ROW]
        with patch.object(wt,'DDGS',return_value=provider),patch.object(wt,'_public_url',return_value=True):
            first,error1=wt.search_ddgs('agenda cultural Minas',5)
            second,error2=wt.search_ddgs('agenda cultural Minas',5)
        self.assertIsNone(error1);self.assertIsNone(error2);self.assertFalse(first.get('cache_hit',False));self.assertTrue(second['cache_hit'])
        self.assertEqual(provider.text.call_count,1)

    def test_native_quota_has_specific_error(self):
        response=requests.Response();response.status_code=429;response._content=b'{"error":"request limit reached"}'
        with patch.dict(os.environ,{'OLLAMA_API_KEY':'test'}),patch.object(wt.requests,'post',return_value=response):
            data,error=wt.search_ollama('agenda',5)
        self.assertIsNone(data);self.assertEqual(error,'WEB_QUOTA_EXCEEDED')

    def test_hybrid_provider_falls_back_per_failed_query(self):
        messages=[{'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'agenda','max_results':5}}}]},
                  {'content':'DONE'},
                  {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'agenda fechas exactas','max_results':5}}}]},
                  {'content':'DONE'}]
        native={'results':[ROW],'provider':'ollama_native'}
        with patch.object(wt,'_chat',side_effect=messages),patch.object(wt,'search_ddgs',return_value=(None,'WEB_SEARCH_ERROR:DDGSException')) as ddgs,patch.object(wt,'search_ollama',return_value=(native,None)) as ollama:
            result=wt.agentic_web_research('agenda',WINDOW,SNAPSHOT,model='test',provider='ddgs_with_ollama_fallback')
        self.assertEqual(ddgs.call_count,2);self.assertEqual(ollama.call_count,2)
        ddgs.assert_any_call('agenda',5);ollama.assert_any_call('agenda',5)
        self.assertEqual(len(result['evidence']),1)
        self.assertEqual(result['tool_trace'][0]['provider'],'ollama_native')
        self.assertEqual(result['tool_trace'][0]['fallback_from'],'WEB_SEARCH_ERROR:DDGSException')

    def test_every_agent_query_keeps_requested_place_anchor(self):
        messages=[
            {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'eventos septiembre 2026','max_results':5}}}]},
            {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'sitio:serrano.uy agenda domingo','max_results':5}}}]},
            {'content':'DONE'}]
        with patch.object(wt,'_chat',side_effect=messages),patch.object(wt,'search_ddgs',return_value=({'results':[ROW]},None)) as search:
            result=wt.agentic_web_research('¿Y en Mariscala?',WINDOW,SNAPSHOT,model='test',provider='ddgs')
        self.assertEqual(search.call_count,2)
        self.assertTrue(all('mariscala' in query.casefold() for query in result['queries']))
        self.assertEqual(result['tool_trace'][1]['model_query'],'sitio:serrano.uy agenda domingo')

    def test_event_agent_requires_independent_verification_search(self):
        messages=[
            {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'Semana de Lavalleja','max_results':5}}}]},
            {'content':'DONE'},
            {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'Semana de Lavalleja programación etapas','max_results':5}}}]},
            {'content':'DONE'}]
        with patch.object(wt,'_chat',side_effect=messages),patch.object(wt,'search_ddgs',return_value=({'results':[ROW]},None)) as search:
            result=wt.agentic_web_research('eventos en Minas',WINDOW,SNAPSHOT,model='test',provider='ddgs')
        self.assertEqual(search.call_count,2)
        self.assertEqual(len(result['queries']),2)
        self.assertRegex(result['queries'][1],r'etapas|tramos|dos fines')
        self.assertNotIn('WEB_AGENT_DEGRADED_SEARCH',result['errors'])

    def test_event_verification_query_cannot_hide_umbrella_range_details(self):
        messages=[
            {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'eventos octubre 2026','max_results':5}}}]},
            {'content':'','tool_calls':[{'function':{'name':'search_web','arguments':{'query':'Semana Lavalleja 2026 fechas','max_results':5}}}]},
            {'content':'DONE'}]
        with patch.object(wt,'_chat',side_effect=messages),patch.object(wt,'search_ddgs',return_value=({'results':[ROW]},None)) as search:
            result=wt.agentic_web_research('eventos en Minas',WINDOW,SNAPSHOT,model='test',provider='ddgs')
        verification=search.call_args_list[1].args[0]
        self.assertIn('fechas exactas',verification)
        self.assertRegex(verification,r'etapas|tramos|dos fines')
        self.assertEqual(result['tool_trace'][1]['model_query'],'Semana Lavalleja 2026 fechas')


if __name__=='__main__':
    unittest.main()
