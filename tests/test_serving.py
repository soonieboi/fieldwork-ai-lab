"""Authored fake streams test instrumentation, never real model performance."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
from tests.http_client import urlopen as direct_urlopen
import urllib.error
from lab.generation import GenerationConfig,GenerationError
from lab.serving import (SuiteConfig,WORKLOAD,BenchError,endpoint_from_env,measure_stream,percentile,
                         report,run_suite,schedule,stream_request,summarize,synthetic_suite)
from lab.server import Handler


def event(value):return b'data: '+json.dumps(value).encode()+b'\n\n'
def delta(content=None,finish=None):
    return event({'choices':[{'index':0,'delta':{'content':content},'finish_reason':finish}]})
def normal(tokens=6):
    return b': heartbeat\n\n'+delta()+delta('hello')+delta(' there')+delta(finish='stop')+event({'choices':[],'usage':{'completion_tokens':tokens}})+b'data: [DONE]\n\n'

class FakeStream(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.lock:
            self.server.bodies.append(body);self.server.starts.append(time.perf_counter())
            self.server.active+=1;self.server.peak=max(self.server.peak,self.server.active)
        mode=self.server.mode
        self.close_connection=True
        payload=normal()
        if mode=='refusal':payload=event({'choices':[{'delta':{'refusal':'authored fixture'}}]})+b'data: [DONE]\n\n'
        if mode=='error':payload=delta('discard me')+event({'error':{'message':'PRIVATE_PROVIDER_FIXTURE'}})
        if mode=='partial':payload=delta('discard me')
        if mode=='length':payload=delta('discard me')+delta(finish='length')+b'data: [DONE]\n\n'
        if mode=='missing-usage':payload=delta('hi')+delta(finish='stop')+b'data: [DONE]\n\n'
        if mode=='oversize':payload=b'x'*131073
        if mode=='interleave':payload=delta()+payload
        try:
            if mode=='redirect':
                self.send_response(302);self.send_header('Location','http://127.0.0.1:9/no');self.send_header('Content-Length','0');self.end_headers();return
            self.send_response(200);self.send_header('Content-Type','text/event-stream')
            if mode.startswith('chunk'):
                self.send_header('Transfer-Encoding','chunked');self.end_headers()
                self.wfile.write(('%x\r\n'%len(payload)).encode()+payload+b'\r\n')
                if mode=='chunk-valid':self.wfile.write(b'0\r\nX-Fixture: yes\r\n\r\n')
                self.wfile.flush();self.close_connection=True;return
            self.send_header('Content-Length',str(len(payload)+(20 if mode=='short-body' else 0)))
            self.end_headers()
            if mode=='timeout':time.sleep(1.2)
            if mode=='interleave':
                # Header/role are available well before content. Requests overlap.
                prefix=delta();self.wfile.write(prefix);self.wfile.flush();time.sleep(.12);payload=payload[len(prefix):]
            for i in range(0,len(payload),11):
                self.wfile.write(payload[i:i+11]);self.wfile.flush()
                if mode=='interleave':time.sleep(.001)
            self.close_connection=True
        except (BrokenPipeError,ConnectionResetError):pass
        finally:
            with self.server.lock:self.server.active-=1

@contextmanager
def server(mode='normal',handler=FakeStream):
    s=ThreadingHTTPServer(('127.0.0.1',0),handler)
    s.mode=mode;s.lock=threading.Lock();s.bodies=[];s.starts=[];s.active=s.peak=0
    t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
    try:yield s,GenerationConfig(f'http://127.0.0.1:{s.server_port}/v1','fake-fixture-not-a-model',timeout=2)
    finally:s.shutdown();s.server_close();t.join()

class Measurements(unittest.TestCase):
    def test_nearest_rank_and_empty_denominators(self):
        self.assertEqual(percentile([])['n'],0);self.assertIsNone(percentile([])['p95'])
        self.assertEqual(percentile([40,10,30,20]),{'n':4,'estimator':'nearest_rank_ceil_p_times_n','p50':20,'p90':40,'p95':40})
        self.assertEqual(percentile([5])['p95'],5)
        self.assertIsNone(summarize([])['successful_output_tokens_per_second'])

    def test_known_clock_role_heartbeat_not_content_and_event_not_tokens(self):
        values=iter([1.2,1.5,2.0]);r=measure_stream([normal(42)],1,clock=lambda:next(values))
        self.assertAlmostEqual(r['first_content_ms'],200);self.assertEqual(r['duration_ms'],1000)
        self.assertAlmostEqual(r['event_gaps_ms'][0],300);self.assertEqual(r['content_events'],2)
        self.assertEqual(r['completion_tokens'],42)
        self.assertNotIn('output',r)

    def test_protocol_failures_do_not_return_partial_metrics(self):
        cases=[delta('partial'),normal()[:-2],delta('x')+delta(finish='stop')+delta('late')+b'data: [DONE]\n\n',
               delta('x')+delta(finish='stop')+b'data: [DONE]\n\n'+event({'choices':[]}),
               event({'choices':[],'usage':{'completion_tokens':True}}),
               event({'choices':[],'usage':{'completion_tokens':-1}}),
               b'data: {"choices":[],"choices":[]}\n\n',b'data: []\n\n',b'x'*32769,
               event({'choices':[{'delta':{'content':3}}]}),delta('x')+b'data: [DONE]\n\n']
        for data in cases:
            with self.subTest(data_length=len(data)),self.assertRaises(BenchError):measure_stream([data],time.perf_counter())

    def test_window_includes_failures_and_pacing_token_coverage_not_estimated(self):
        a={'status':'success','start':1,'end':2,'duration_ms':1000,'first_content_ms':200,'event_gaps_ms':[10], 'completion_tokens':10}
        b={'status':'timeout','start':3,'end':6,'duration_ms':3000}
        s=summarize([a,b]);self.assertEqual(s['elapsed_window_seconds'],5)
        self.assertEqual(s['successful_output_tokens_per_second'],2);self.assertEqual(s['first_content_ms']['n'],1)
        self.assertEqual(s['failure_duration_ms']['n'],1)
        missing=dict(a,start=2,end=3,completion_tokens=None)
        self.assertIsNone(summarize([a,b,missing])['successful_output_tokens_per_second'])
        self.assertEqual(summarize([a,b,missing])['token_coverage']['known_successes'],1)

    def test_config_finite_limits_and_no_insecure_remote_or_key_borrowing(self):
        for kw in ({'runs':0},{'runs':31},{'warmup':4},{'concurrency':5},{'rate':float('nan')},{'rate':11},{'timeout':31},{'runs':30,'timeout':30},{'seed':True}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):SuiteConfig(**kw)
        with self.assertRaises(ValueError):endpoint_from_env(SuiteConfig(),{'LAB_API_KEY':'PLACEHOLDER_ONLY'})
        env={'LAB_SERVING_ENABLED':'1','LAB_SERVING_BASE_URL':'http://example.invalid/v1','LAB_SERVING_MODEL':'fixture'}
        with self.assertRaises(ValueError):endpoint_from_env(SuiteConfig(),env)
        env['LAB_SERVING_BASE_URL']='https://example.invalid/v1';env['LAB_API_KEY']='PLACEHOLDER_ONLY'
        self.assertEqual(endpoint_from_env(SuiteConfig(),env).api_key,'')

    def test_virtual_fixture_reproducible_slices_and_explicit_provenance(self):
        a=synthetic_suite();self.assertEqual(a,synthetic_suite())
        self.assertIn('SYNTHETIC',a['metadata']['mode']);self.assertEqual(a['summary']['requested'],9)
        self.assertEqual(len(a['warmup']['results']),1)
        self.assertEqual([r['requested'] for r in a['by_prompt'].values()],[3,3,3])
        self.assertTrue(all(r['token_provenance']=='synthetic_fixture_count_not_model_tokens' for r in a['requests_relative_ms']))
        self.assertNotEqual(a,synthetic_suite(SuiteConfig(seed=18)))

class Transport(unittest.TestCase):
    def test_concurrent_interleaving_warmup_excluded_rate_and_payload(self):
        with server('interleave') as (s,endpoint):
            result=run_suite(SuiteConfig(runs=6,warmup=1,concurrency=2,rate=10,timeout=2),endpoint)
            self.assertEqual(result['summary']['successful'],6);self.assertEqual(len(s.bodies),7)
            self.assertEqual(len(result['requests_relative_ms']),6);self.assertEqual(len(result['warmup']['results']),1)
            self.assertEqual(s.peak,2);self.assertTrue(all(b-a>=.085 for a,b in zip(s.starts,s.starts[1:])))
            self.assertTrue(all(r['first_content_ms']>=100 for r in result['requests_relative_ms']))
            self.assertTrue(all(b['stream'] and b['n']==1 and b['seed']==17 for b in s.bodies))
            self.assertEqual({b['max_tokens'] for b in s.bodies},{32,64,128})
            self.assertNotIn(endpoint.base_url,json.dumps(result));self.assertNotIn(endpoint.model,json.dumps(result))
            self.assertEqual(result['metadata']['hardware_operator_supplied'],'not supplied')
            for row in result['requests_relative_ms']:self.assertEqual(row['completion_tokens'],6)

    def test_failure_statuses_and_missing_usage(self):
        for mode,status in [('refusal','refusal'),('error','provider_error'),('partial','incomplete'),('length','length_limit'),
                            ('short-body','incomplete'),('chunk-missing','incomplete'),('oversize','response_size'),('redirect','redirect')]:
            with self.subTest(mode=mode),server(mode) as (s,endpoint):
                r=stream_request(endpoint,WORKLOAD[0],17);self.assertEqual(r['status'],status)
                self.assertNotIn('first_content_ms',r);self.assertNotIn('PRIVATE_PROVIDER_FIXTURE',json.dumps(r))
                self.assertEqual(len(s.bodies),1)
        for mode in ('chunk-valid','missing-usage'):
            with self.subTest(mode=mode),server(mode) as (s,endpoint):
                r=stream_request(endpoint,WORKLOAD[0],17);self.assertEqual(r['status'],'success')
                if mode=='missing-usage':self.assertIsNone(r['completion_tokens'])

    def test_timeout_discards_partial_and_no_retry(self):
        with server('timeout') as (s,endpoint):
            endpoint=GenerationConfig(endpoint.base_url,endpoint.model,timeout=1)
            r=stream_request(endpoint,WORKLOAD[0],17)
            self.assertEqual(r['status'],'timeout');self.assertNotIn('first_content_ms',r);self.assertEqual(len(s.bodies),1)

    def test_https_uses_standard_verified_context_without_network(self):
        endpoint=GenerationConfig('https://example.invalid/v1','fixture')
        with patch('lab.serving.http.client.HTTPSConnection',side_effect=OSError) as connection:
            result=stream_request(endpoint,WORKLOAD[0],17)
        context=connection.call_args.kwargs['context']
        import ssl
        self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertEqual(result['status'],'transport')

    def test_proxy_environment_is_not_used(self):
        with server() as (s,endpoint),patch.dict(os.environ,{'http_proxy':'http://127.0.0.1:9','HTTP_PROXY':'http://127.0.0.1:9'}):
            self.assertEqual(stream_request(endpoint,WORKLOAD[0],17)['status'],'success')

    def test_warmup_failure_never_enters_measurement_denominator(self):
        count=[0]
        def fake(endpoint,prompt,seed):
            count[0]+=1
            if count[0]==1:return {'status':'refusal','duration_ms':1}
            return {'status':'success','duration_ms':2,'first_content_ms':1,'content_events':1,'event_gaps_ms':[],'completion_tokens':None,'token_provenance':'unknown'}
        with patch('lab.serving.stream_request',fake):
            r=run_suite(SuiteConfig(runs=2,warmup=1,rate=10),GenerationConfig('http://localhost/v1','fixture'))
        self.assertEqual(r['warmup']['results'][0]['status'],'refusal')
        self.assertEqual(r['summary']['status_counts'],{'success':2});self.assertIsNone(r['summary']['successful_output_tokens_per_second'])

    def test_warmup_to_measurement_preserves_dispatch_rate(self):
        starts=[]
        def fake(endpoint,prompt,seed):
            starts.append(time.perf_counter())
            return {'status':'refusal','duration_ms':1}
        with patch('lab.serving.stream_request',fake):
            result=run_suite(SuiteConfig(runs=1,warmup=1,rate=10),GenerationConfig('http://localhost/v1','fixture'))
        self.assertGreaterEqual(starts[1]-starts[0],.09)
        self.assertEqual(result['summary']['requested'],1)
        self.assertEqual(result['summary']['successful'],0)
        self.assertIsNone(result['summary']['first_content_ms']['p50'])

    def test_labels_rejected_before_network(self):
        with patch('lab.serving.stream_request') as request,self.assertRaises(ValueError):
            run_suite(SuiteConfig(),GenerationConfig('http://localhost/v1','fixture'),hardware='https://bad/secret')
        request.assert_not_called()

class Surface(unittest.TestCase):
    def test_cli_offline_and_optin(self):
        root=Path(__file__).resolve().parent.parent
        r=subprocess.run([sys.executable,'-m','lab','benchmark-suite','--runs','3'],cwd=root,capture_output=True,text=True,check=True)
        self.assertIn('SYNTHETIC',json.loads(r.stdout)['metadata']['mode'])
        env={k:v for k,v in os.environ.items() if not k.startswith('LAB_SERVING_')}
        r=subprocess.run([sys.executable,'-m','lab','benchmark-suite','--mode','endpoint'],cwd=root,env=env,capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('LAB_SERVING_ENABLED',r.stderr)

    def test_browser_route_cannot_select_real_endpoint(self):
        with server(handler=Handler) as (s,_):
            url=f'http://127.0.0.1:{s.server_port}/api/serving-suite'
            def post(data,origin=None):
                req=urllib.request.Request(url,json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':origin or f'http://127.0.0.1:{s.server_port}'})
                return direct_urlopen(req,timeout=3)
            with post({}) as response:self.assertIn('SYNTHETIC',json.load(response)['metadata']['mode'])
            with self.assertRaises(urllib.error.HTTPError) as e:post({'mode':'endpoint'})
            self.assertEqual(e.exception.code,400);e.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as e:post({},'http://example.invalid')
            self.assertEqual(e.exception.code,403);e.exception.close()
