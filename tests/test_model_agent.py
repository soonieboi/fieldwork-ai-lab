"""Bounded workflow regressions with deterministic choices; no live agent judge."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from lab.agent_contracts import check,load_fixtures,run_case
from lab.core import ROOT,Index
from lab.generation import GenerationConfig
from lab.model_agent import (AgentBudget,AgentError,AgentJobs,ReadOnlyTools,agent_config,agent_status,
                             offline_choice,run_model_agent,validate_action)
from lab.server import Handler

QUESTION="I bought a pair of shoes 10 days ago and haven't worn them. Can I return them?"
ENV={'LAB_AGENT_ENABLED':'1','LAB_AGENT_MODEL':'fake-agent-not-a-model'}


class FakeAgentEndpoint(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(body);self.server.arrived.set()
        self.server.release.wait(3)
        context=json.loads(body['messages'][1]['content']);history=context['observations']
        searches=[o['result'] for o in history if o['tool']=='search_documents']
        reads=[o['result'] for o in history if o['tool']=='read_source']
        action={'schema_version':1,'action':'search_documents','query':'shoes receipt','source_id':'','claims':[],'reason':''}
        if reads:action.update(action='finish',query='',claims=[{'text':'The time/condition fit; a receipt is still required.','citations':[reads[0]['id']]}])
        elif searches:action.update(action='read_source',query='',source_id=searches[-1][0]['id'])
        if self.server.forbidden:action['action']='run_shell'
        result={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(action)}}],
                'usage':{'completion_tokens':4}}
        raw=json.dumps(result).encode();self.send_response(200)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass


@contextmanager
def endpoint(block=False,forbidden=False):
    server=ThreadingHTTPServer(('127.0.0.1',0),FakeAgentEndpoint)
    server.requests=[];server.forbidden=forbidden;server.arrived=threading.Event();server.release=threading.Event()
    if not block:server.release.set()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}/v1',server
    finally:
        server.release.set();server.shutdown();server.server_close();thread.join()


def wait_job(jobs,id):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        snapshot=jobs.snapshot(id)
        if snapshot['status']!='running':return snapshot
        time.sleep(.01)
    raise AssertionError('Local fixture job did not stop')


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):self.index=Index(ROOT/'examples/shop')

    def test_frozen_workflow_contracts_and_negative_control(self):
        rows=check();self.assertEqual(len(rows),23)
        wrong=next(r for r in rows if r['id']=='contract-valid-false-claim')
        self.assertEqual(wrong['status'],'completed');self.assertEqual(wrong['semantic_quality'],'not_assessed')

    def test_tool_allowlist_is_independent_of_schema(self):
        tools=ReadOnlyTools(self.index)
        for name in ('run_shell','write_file','browse','__dict__'):
            with self.assertRaises(AgentError):tools.execute(name,query='ignored')
        self.assertEqual(tools.executed,[])

    def test_source_must_be_discovered_and_provenance_unchanged(self):
        tools=ReadOnlyTools(self.index)
        with self.assertRaises(AgentError):tools.execute('read_source',source_id='returns:1')
        tools.execute('search_documents',query='shoes')
        tools.discovered['returns:1']=dict(tools.discovered['returns:1'],text='unverified replacement')
        with self.assertRaises(AgentError):tools.execute('read_source',source_id='returns:1')
        self.assertEqual(tools.executed,['search_documents'])

    def test_invalid_budget_types_and_ranges(self):
        for values in ({'max_steps':0},{'max_steps':9},{'max_steps':True},{'max_seconds':1},
                       {'max_seconds':float('nan')},{'max_requested_tokens':0},{'max_requested_tokens':2049}):
            with self.subTest(values=values),self.assertRaises(AgentError):AgentBudget(**values)

    def test_no_configuration_or_credential_borrowing(self):
        self.assertIsNone(agent_config({'LAB_GENERATION_ENABLED':'1','LAB_GENERATION_API_KEY':'PLACEHOLDER_ONLY'}))
        cfg=agent_config(dict(ENV,LAB_AGENT_BASE_URL='http://localhost/v1',LAB_GENERATION_API_KEY='PLACEHOLDER_ONLY'))
        self.assertEqual(cfg.api_key,'')
        self.assertEqual(agent_status(ENV)['state'],'misconfigured')
        self.assertNotIn('fake-agent',json.dumps(agent_status(dict(ENV,LAB_AGENT_BASE_URL='http://localhost/v1'))))

    def test_real_round_trips_drive_search_read_finish(self):
        with endpoint() as (url,server):
            config=agent_config(dict(ENV,LAB_AGENT_BASE_URL=url))
            result=run_model_agent(self.index,QUESTION,config)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(len(server.requests),3)
            self.assertEqual(result['accounting']['model_requests'],3)
            self.assertEqual(result['accounting']['requested_completion_token_caps'],3*256)
            self.assertEqual(result['accounting']['reported_completion_tokens'],12)
            first=json.loads(server.requests[0]['messages'][1]['content'])
            last=json.loads(server.requests[-1]['messages'][1]['content'])
            self.assertEqual(first['observations'],[])
            self.assertEqual([o['tool'] for o in last['observations']],['search_documents','read_source'])
            self.assertEqual(result['claims'][0]['citations'],['returns:1'])
            self.assertEqual(result['validation']['semantic_support'],'not_assessed')

    def test_forbidden_choice_cannot_dispatch_a_tool_over_http(self):
        with endpoint(forbidden=True) as (url,server):
            result=run_model_agent(self.index,QUESTION,agent_config(dict(ENV,LAB_AGENT_BASE_URL=url)))
            self.assertEqual(result['status'],'invalid_action')
            self.assertEqual(result['accounting']['tools_executed'],0)
            self.assertEqual(len(server.requests),1)

    def test_offline_walkthrough_never_calls_transport_or_claims_inference(self):
        with patch('lab.model_agent.post_completion') as post:
            result=run_model_agent(self.index,QUESTION,GenerationConfig('http://localhost/unused','fixture'),
                                   provider=offline_choice,mode='offline_scripted')
            post.assert_not_called()
        self.assertEqual(result['status'],'completed')
        self.assertIn('no model inference',result['mode'])
        self.assertIsNone(result['accounting']['reported_completion_tokens'])
        self.assertEqual(result['claims'][0]['text'],self.index.chunks[0]['text'])

    def test_request_context_is_bounded_before_dispatch(self):
        index=Index(documents={'big.md':'shoes '*80+'x'*26000})
        with patch('lab.model_agent.post_completion') as post:
            result=run_model_agent(index,'shoes',GenerationConfig('http://localhost/v1','fixture'),provider=offline_choice,mode='offline_scripted')
            self.assertEqual(result['status'],'context_budget')
            self.assertEqual(result['accounting']['model_requests'],2)
            self.assertEqual(result['accounting']['tools_executed'],1)
            post.assert_not_called()


class AgentJobTests(unittest.TestCase):
    def setUp(self):self.index=Index(ROOT/'examples/shop');self.jobs=AgentJobs()

    def test_cancel_inflight_request_stops_before_tool_and_is_acknowledged(self):
        with endpoint(block=True) as (url,server):
            job=self.jobs.start(self.index,QUESTION,'endpoint',environ=dict(ENV,LAB_AGENT_BASE_URL=url))
            self.assertTrue(server.arrived.wait(2))
            requested=self.jobs.request_cancel(job['id'])
            self.assertTrue(requested['cancel_requested'])
            self.assertEqual(requested['status'],'running')  # not a false cancel acknowledgment
            server.release.set();finished=wait_job(self.jobs,job['id'])
            self.assertEqual(finished['status'],'cancelled')
            self.assertEqual(finished['result']['accounting']['tools_executed'],0)
            self.assertEqual(len(server.requests),1)

    def test_two_active_jobs_and_bounded_retention(self):
        with endpoint(block=True) as (url,server):
            env=dict(ENV,LAB_AGENT_BASE_URL=url)
            first=self.jobs.start(self.index,QUESTION,'endpoint',environ=env)
            second=self.jobs.start(self.index,QUESTION,'endpoint',environ=env)
            with self.assertRaises(AgentError) as error:self.jobs.start(self.index,QUESTION,'endpoint',environ=env)
            self.assertEqual(error.exception.code,'busy')
            server.release.set();wait_job(self.jobs,first['id']);wait_job(self.jobs,second['id'])
        for _ in range(9):
            job=self.jobs.start(self.index,QUESTION);wait_job(self.jobs,job['id'])
        self.assertEqual(len(self.jobs.jobs),8)
        with self.assertRaises(AgentError):self.jobs.snapshot(first['id'])

    def test_disabled_endpoint_does_not_create_job(self):
        with self.assertRaises(AgentError) as error:self.jobs.start(self.index,QUESTION,'endpoint',environ={})
        self.assertEqual(error.exception.code,'disabled');self.assertEqual(len(self.jobs.jobs),0)

    def test_unknown_cancel_does_not_touch_other_job(self):
        job=self.jobs.start(self.index,QUESTION);wait_job(self.jobs,job['id'])
        with self.assertRaises(AgentError):self.jobs.request_cancel('not-a-job')
        self.assertFalse(self.jobs.snapshot(job['id'])['cancel_requested'])


class AgentFixtureIntegrityTests(unittest.TestCase):
    def test_unmanifested_source_is_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'data';shutil.copytree(ROOT/'evals/agent-contract-v1',root)
            (root/'corpus/extra.md').write_text('Unexpected')
            with self.assertRaises(ValueError):load_fixtures(root)


class QuietAgentApp(Handler):
    def log_message(self,*args):pass


class AgentRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),QuietAgentApp)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def post(self,path,data,origin=True):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=self.url
        request=urllib.request.Request(self.url+'/api/model-agent/'+path,json.dumps(data).encode(),headers)
        try:
            with urllib.request.urlopen(request,timeout=3) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as r:
            with r:return r.code,json.load(r)
    def until_done(self,id):
        for _ in range(100):
            status,job=self.post('status',{'id':id})
            self.assertEqual(status,200)
            if job['status']!='running':return job
            time.sleep(.01)
        self.fail('HTTP fixture job did not finish')

    def test_offline_job_status_without_endpoint_or_credentials(self):
        with patch.dict(os.environ,{},clear=True):
            status,job=self.post('start',{'question':QUESTION,'corpus':'shop','mode':'offline'})
            self.assertEqual(status,200)
            finished=self.until_done(job['id'])
            self.assertEqual(finished['status'],'completed')
            self.assertIn('no model inference',finished['result']['mode'])

    def test_origin_parameters_budget_and_disabled_endpoint(self):
        self.assertEqual(self.post('start',{'question':QUESTION},origin=False)[0],403)
        self.assertEqual(self.post('start',{'question':QUESTION,'base_url':'http://localhost/v1'})[0],400)
        self.assertEqual(self.post('start',{'question':QUESTION,'max_steps':99})[0],400)
        self.assertEqual(self.post('status',{'id':[]})[0],400)
        self.assertEqual(self.post('cancel',{'id':'0'*32})[0],404)
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.post('start',{'question':QUESTION,'mode':'endpoint'})[0],503)

    def test_http_cancel_is_server_side_not_only_client_abort(self):
        with endpoint(block=True) as (url,server),patch.dict(os.environ,dict(ENV,LAB_AGENT_BASE_URL=url),clear=True):
            status,job=self.post('start',{'question':QUESTION,'corpus':'shop','mode':'endpoint'})
            self.assertEqual(status,200);self.assertTrue(server.arrived.wait(2))
            status,requested=self.post('cancel',{'id':job['id']})
            self.assertEqual(status,200);self.assertTrue(requested['cancel_requested'])
            server.release.set();finished=self.until_done(job['id'])
            self.assertEqual(finished['status'],'cancelled')
            self.assertEqual(finished['result']['accounting']['tools_executed'],0)
            self.assertEqual(len(server.requests),1)


if __name__=='__main__':unittest.main()
