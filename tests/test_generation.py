"""Local deterministic protocol fixtures. No live-model quality is evaluated."""
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import threading
import time
import unittest
import urllib.error
import urllib.request
from tests.http_client import urlopen as direct_urlopen
from unittest.mock import patch

from lab.core import Index, ROOT
from lab.generation import (GenerationConfig, GenerationError, MAX_RESPONSE_BYTES,
    config_from_env, generate, post_completion, public_status, strict_json, validate_completion, validate_response)
from lab.server import Handler, GENERATION_SLOTS

QUESTION="I bought a pair of shoes 10 days ago and haven't worn them. Can I return them?"
ENV={'LAB_GENERATION_ENABLED':'1','LAB_GENERATION_MODEL':'deterministic-fixture-not-a-model'}


class FakeEndpoint(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):
        pass

    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append({'path':self.path,'body':body,'auth':self.headers.get('Authorization')})
        evidence=json.loads(body['messages'][1]['content'])['evidence']
        payload={'schema_version':1,'status':'answer','reason':'','claims':[
            {'text':'The time and condition requirements fit; you still need a receipt.','citations':[evidence[0]['id']]}]}
        scenario=self.server.scenario
        message={'role':'assistant','content':json.dumps(payload)}
        self.close_connection=True
        status=200;headers={'Content-Type':'application/json','Connection':'close'}
        extra_headers=[]
        if scenario=='unknown-citation':
            payload['claims'][0]['citations']=['not-supplied:99'];message['content']=json.dumps(payload)
        if scenario=='model-abstain':
            message['content']=json.dumps({'schema_version':1,'status':'abstain','reason':'Evidence is insufficient.','claims':[]})
        if scenario=='provider-refusal':
            message={'role':'assistant','content':None,'refusal':'Private fixture refusal detail'}
        if scenario=='content-parts':
            message['content']=[{'type':'text','text':message['content']}]
        if scenario=='tool-call':
            message['tool_calls']=[{'id':'unused','function':{'name':'not-executed'}}]
        envelope={'choices':[{'message':message,'finish_reason':'length' if scenario=='truncated' else 'stop'}]}
        raw=json.dumps(envelope).encode()
        if scenario=='redirect':
            status=302;headers['Location']='/must-not-follow'
        elif scenario=='unauthorized':
            status=401;raw=b'Private fixture provider detail'
        elif scenario=='malformed':
            raw=b'{'
        elif scenario=='wrong-content-type':
            headers['Content-Type']='text/html'
        elif scenario=='declared-oversize':
            headers['Content-Length']=str(MAX_RESPONSE_BYTES+1)
        elif scenario=='body-oversize':
            raw=b'x'*(MAX_RESPONSE_BYTES+1)
        elif scenario=='valid-length':
            headers['Content-Length']=str(len(raw))
        elif scenario=='short-length-body':
            headers['Content-Length']=str(len(raw)+100)
        elif scenario=='duplicate-length':
            headers['Content-Length']=str(len(raw));extra_headers=[('Content-Length',str(len(raw)))]
        elif scenario=='signed-length':
            headers['Content-Length']='+'+str(len(raw))
        elif scenario=='long-numeric-length':
            headers['Content-Length']='0'*5000
        if 'chunked' in scenario:
            headers['Transfer-Encoding']='chunked'
            if scenario=='chunked-and-length':headers['Content-Length']=str(len(raw))
            if scenario=='chunked-short-body':
                raw=f'{len(raw)+100:x}\r\n'.encode()+raw
            else:
                split=len(raw)//2
                raw=b''.join(f'{len(part):x}\r\n'.encode()+part+b'\r\n' for part in (raw[:split],raw[split:]))
                if scenario=='chunked-missing-zero':pass
                elif scenario=='chunked-missing-trailer-end':raw+=b'0\r\n'
                elif scenario=='valid-chunked-trailer':raw+=b'0\r\nX-Demo: fixture\r\n\r\n'
                elif scenario=='chunked-bad-delimiter':raw=raw[:-2]+b'XX0\r\n\r\n'
                else:raw+=b'0\r\n\r\n'
        self.send_response(status)
        for name,value in headers.items():self.send_header(name,value)
        for name,value in extra_headers:self.send_header(name,value)
        self.end_headers()
        if scenario=='slow':time.sleep(1.5)
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass


@contextmanager
def fake_endpoint(scenario='valid'):
    server=ThreadingHTTPServer(('127.0.0.1',0),FakeEndpoint)
    server.scenario=scenario;server.requests=[]
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}/v1',server
    finally:
        server.shutdown();server.server_close();thread.join()


class ConfigurationTests(unittest.TestCase):
    def test_disabled_is_default_and_key_is_not_borrowed_from_benchmark(self):
        self.assertIsNone(config_from_env({}))
        config=config_from_env(dict(ENV,LAB_GENERATION_BASE_URL='http://127.0.0.1:8000/v1',LAB_API_KEY='PLACEHOLDER_ONLY'))
        self.assertEqual(config.api_key,'')

    def test_remote_http_credentials_urls_and_bad_ports_are_rejected(self):
        urls=['http://example.invalid/v1','http://user:placeholder@localhost/v1',
              'https://example.invalid/v1?token=placeholder','https://example.invalid/v1#part',
              'http://localhost:0/v1','http://localhost:99999/v1','http://localhost.evil.invalid/v1',
              'http://localhost/v1\r\n','http://localhost\\evil/v1']
        for url in urls:
            with self.subTest(url=url),self.assertRaises(GenerationError):GenerationConfig(url,'fixture')

    def test_loopback_http_and_remote_https_are_configurable_without_connecting(self):
        for url in ['http://127.0.0.1:8000/v1','http://[::1]:8000/v1','http://localhost:8000/v1','https://example.invalid/v1']:
            self.assertIsInstance(GenerationConfig(url,'fixture'),GenerationConfig)

    def test_invalid_limits_and_formats_fail_safely(self):
        changes=[{'timeout':0},{'timeout':31},{'timeout':float('nan')},{'timeout':True},
                 {'max_tokens':0},{'max_tokens':1025},{'max_tokens':True},
                 {'response_format':'text'},{'token_field':'arbitrary'},{'api_key':'bad\nheader'}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(GenerationError):
                GenerationConfig('http://localhost/v1','fixture',**change)
        for env in [dict(ENV,LAB_GENERATION_TIMEOUT='bad'),dict(ENV,LAB_GENERATION_ENABLED='yes')]:
            with self.assertRaises(GenerationError):config_from_env(env)

    def test_status_and_repr_do_not_disclose_configuration_values(self):
        env=dict(ENV,LAB_GENERATION_BASE_URL='https://example.invalid/v1',LAB_GENERATION_API_KEY='PLACEHOLDER_ONLY')
        rendered=json.dumps(public_status(env))+repr(config_from_env(env))
        self.assertNotIn('PLACEHOLDER_ONLY',rendered)
        self.assertNotIn('example.invalid',rendered)
        self.assertEqual(public_status(ENV)['state'],'misconfigured')


class GenerationIntegrationTests(unittest.TestCase):
    def setUp(self):self.index=Index(ROOT/'examples/shop')

    def test_valid_conditional_answer_citations_and_prompt_boundary(self):
        with fake_endpoint() as (url,server):
            result=generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))
            self.assertEqual(result['status'],'answer')
            self.assertEqual(result['claims'][0]['citations'],['returns:1'])
            self.assertEqual(result['validation']['semantic_support'],'not_assessed')
            self.assertEqual(result['sources'][0]['source'],'returns.md')
            request=server.requests[0]
            self.assertEqual(request['path'],'/v1/chat/completions')
            self.assertFalse(request['body']['stream'])
            self.assertEqual([m['role'] for m in request['body']['messages']],['system','user'])
            content=json.loads(request['body']['messages'][1]['content'])
            self.assertEqual(content['question'],QUESTION)
            self.assertEqual(content['evidence'][0]['text'],self.index.chunks[0]['text'])
            self.assertIn('untrusted data',request['body']['messages'][0]['content'])
            self.assertEqual(request['body']['response_format']['json_schema']['schema']['properties']['claims']['items']['properties']['citations']['items']['enum'],['returns:1'])

    def test_insufficient_evidence_does_not_dispatch(self):
        with fake_endpoint() as (url,server):
            result=generate(self.index,'Can I return a bicycle helmet?',dict(ENV,LAB_GENERATION_BASE_URL=url))
            self.assertEqual(result['status'],'abstain')
            self.assertEqual(result['claims'],[])
            self.assertEqual(server.requests,[])
            self.assertIn('no request sent',result['mode'])

    def test_disabled_never_dispatches(self):
        with patch('lab.generation.post_completion') as post:
            with self.assertRaises(GenerationError) as error:generate(self.index,QUESTION,{})
            self.assertEqual(error.exception.code,'disabled');post.assert_not_called()

    def test_json_object_and_alternate_token_field_require_explicit_configuration(self):
        with fake_endpoint() as (url,server):
            generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url,LAB_GENERATION_FORMAT='json_object',LAB_GENERATION_TOKEN_FIELD='max_completion_tokens'))
            request=server.requests[0]['body']
            self.assertEqual(request['response_format'],{'type':'json_object'})
            self.assertEqual(request['max_completion_tokens'],512)
            self.assertNotIn('max_tokens',request)

    def test_model_abstention_and_provider_refusal_return_no_claims(self):
        for scenario in ['model-abstain','provider-refusal']:
            with self.subTest(scenario=scenario),fake_endpoint(scenario) as (url,server):
                result=generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))
                self.assertEqual(result['status'],'abstain');self.assertEqual(result['claims'],[])
                self.assertEqual(result['sources'],[])
                self.assertNotIn('Private fixture',json.dumps(result))

    def test_invalid_or_incomplete_protocol_has_no_partial_answer(self):
        expected={'unknown-citation':'contract','truncated':'incomplete','malformed':'contract',
                  'content-parts':'protocol','tool-call':'protocol','wrong-content-type':'protocol',
                  'redirect':'redirect','unauthorized':'provider_rejected',
                  'declared-oversize':'response_size','body-oversize':'response_size'}
        for scenario,code in expected.items():
            with self.subTest(scenario=scenario),fake_endpoint(scenario) as (url,server):
                with self.assertRaises(GenerationError) as error:
                    generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))
                self.assertEqual(error.exception.code,code)
                self.assertNotIn('Private fixture',str(error.exception))
                self.assertEqual(len(server.requests),1)  # no retry or redirect request

    def test_slow_response_is_interrupted(self):
        with fake_endpoint('slow') as (url,server):
            started=time.monotonic()
            with self.assertRaises(GenerationError) as error:
                generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url,LAB_GENERATION_TIMEOUT='1'))
            self.assertEqual(error.exception.code,'timeout')
            self.assertLess(time.monotonic()-started,2.5)

    def test_valid_length_close_delimited_and_chunked_responses(self):
        for scenario in ['valid','valid-length','valid-chunked','valid-chunked-trailer']:
            with self.subTest(scenario=scenario),fake_endpoint(scenario) as (url,server):
                self.assertEqual(generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))['status'],'answer')

    def test_valid_json_is_not_accepted_from_incomplete_framing(self):
        for scenario in ['short-length-body','chunked-short-body','chunked-missing-zero',
                         'chunked-missing-trailer-end','chunked-bad-delimiter']:
            with self.subTest(scenario=scenario),fake_endpoint(scenario) as (url,server):
                with self.assertRaises(GenerationError) as error:
                    generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))
                self.assertEqual(error.exception.code,'incomplete')
                self.assertEqual(len(server.requests),1)

    def test_ambiguous_or_invalid_framing_headers_are_rejected(self):
        for scenario in ['duplicate-length','signed-length','long-numeric-length','chunked-and-length']:
            with self.subTest(scenario=scenario),fake_endpoint(scenario) as (url,server):
                with self.assertRaises(GenerationError) as error:
                    generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))
                self.assertEqual(error.exception.code,'protocol')

    def test_oversized_context_is_rejected_before_network(self):
        index=Index(documents={'long.md':'word '*80+'a'*25000})
        with patch('lab.generation.post_completion') as post:
            with self.assertRaises(GenerationError) as error:
                generate(index,'word',dict(ENV,LAB_GENERATION_BASE_URL='http://127.0.0.1:8000/v1'))
            self.assertEqual(error.exception.code,'request_size');post.assert_not_called()

    def test_modified_source_provenance_is_rejected_before_dispatch(self):
        source=dict(self.index.chunks[0],text='Unverified replacement excerpt')
        with patch.object(self.index,'answer',return_value={'decision':'answer','sources':[source]}),patch('lab.generation.post_completion') as post:
            with self.assertRaises(GenerationError) as error:
                generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL='http://127.0.0.1:8000/v1'))
            self.assertEqual(error.exception.code,'evidence');post.assert_not_called()

    def test_proxy_environment_is_not_used(self):
        with fake_endpoint() as (url,server),patch.dict(os.environ,{'HTTP_PROXY':'http://example.invalid:1','HTTPS_PROXY':'http://example.invalid:1'}):
            self.assertEqual(generate(self.index,QUESTION,dict(ENV,LAB_GENERATION_BASE_URL=url))['status'],'answer')

    def test_tls_verification_and_auth_header_without_real_network(self):
        content=json.dumps({'choices':[{'message':{'role':'assistant','content':json.dumps({'schema_version':1,'status':'abstain','reason':'Fixture','claims':[]})},'finish_reason':'stop'}]}).encode()
        with patch('lab.generation.http.client.HTTPSConnection') as factory:
            conn=factory.return_value;response=conn.getresponse.return_value;response.status=200
            response.getheader.side_effect=lambda name,default=None:{'Content-Type':'application/json'}.get(name,default)
            response.getheaders.return_value=[('Content-Type','application/json')]
            response.read1.side_effect=[content,b'']
            post_completion(GenerationConfig('https://example.invalid/v1','fixture',api_key='PLACEHOLDER_ONLY'),b'{}')
            context=factory.call_args.kwargs['context']
            self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
            self.assertEqual(conn.request.call_args.args[3]['Authorization'],'Bearer PLACEHOLDER_ONLY')


class QuietApp(Handler):
    def log_message(self,*args):pass


class GenerationRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),QuietApp)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def request(self,data,origin=True,host=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=self.url
        if host:headers['Host']=host
        try:
            with direct_urlopen(urllib.request.Request(self.url+'/api/generate',json.dumps(data).encode(),headers),timeout=3) as r:
                return r.status,json.load(r)
        except urllib.error.HTTPError as r:
            with r:return r.code,json.load(r)

    def test_disabled_endpoint_and_no_browser_credentials(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.request({'question':QUESTION,'corpus':'shop'})[0],503)
            status,result=self.request({'question':QUESTION,'api_key':'PLACEHOLDER_ONLY'})
            self.assertEqual(status,400)
            self.assertNotIn('PLACEHOLDER_ONLY',json.dumps(result))

    def test_generation_requires_exact_origin_and_body_cannot_choose_endpoint(self):
        self.assertEqual(self.request({'question':QUESTION},origin=False)[0],403)
        self.assertEqual(self.request({'question':QUESTION},host='localhost')[0],403)
        self.assertEqual(self.request({'question':QUESTION,'base_url':'https://example.invalid'})[0],400)

    def test_busy_generation_slots_reject_without_dispatch(self):
        GENERATION_SLOTS.acquire();GENERATION_SLOTS.acquire()
        try:
            with patch('lab.server.generate') as dispatch:
                status,result=self.request({'question':QUESTION,'corpus':'shop'})
                self.assertEqual(status,429);self.assertEqual(result['error_code'],'busy')
                dispatch.assert_not_called()
        finally:
            GENERATION_SLOTS.release();GENERATION_SLOTS.release()

    def test_configured_fake_endpoint_and_status_do_not_leak_config(self):
        with fake_endpoint() as (url,server),patch.dict(os.environ,dict(ENV,LAB_GENERATION_BASE_URL=url),clear=True):
            status,result=self.request({'question':QUESTION,'corpus':'shop'})
            self.assertEqual(status,200);self.assertEqual(result['status'],'answer')
            with direct_urlopen(self.url+'/api/status') as r:public=json.load(r)
            self.assertEqual(public['generation']['state'],'configured')
            self.assertNotIn(url,json.dumps(public));self.assertNotIn('deterministic-fixture-not-a-model',json.dumps(public))


class VersionedContractTests(unittest.TestCase):
    def test_refusal_field_type_is_validated(self):
        with self.assertRaises(GenerationError) as error:
            validate_completion({'choices':[{'finish_reason':'stop','message':{'content':None,'refusal':True}}]},['returns:1'])
        self.assertEqual(error.exception.code,'protocol')

    def test_authored_contract_cases_do_not_assess_model_quality(self):
        from scripts.check_generation_contract import check
        self.assertEqual(check(),19)

    def test_citation_valid_but_false_claim_is_accepted_only_as_a_contract(self):
        response={'schema_version':1,'status':'answer','reason':'','claims':[{'text':'Worn shoes are always returnable without a receipt.','citations':['returns:1']}]}
        self.assertEqual(validate_response(response,['returns:1']),response)


if __name__=='__main__':unittest.main()
