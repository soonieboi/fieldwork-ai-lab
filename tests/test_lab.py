import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lab.core import Index, benchmark, evaluate, measure, replay, run_agent, sse_events
from lab.server import Handler


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.index = Index()

    def test_retrieves_expected_source_and_citations(self):
        r = self.index.answer('TF-IDF retrieval citations')
        self.assertEqual(r['sources'][0]['source'], 'retrieval.md')
        for hit in r['sources']:
            self.assertIn('['+hit['id']+']', r['answer'])
            self.assertIn(hit['text'], r['answer'])

    def test_unknown_vocabulary_abstains(self):
        r = self.index.answer('xylophonically zzznonexistent')
        self.assertEqual(r['sources'], [])
        self.assertIn('No matching evidence', r['answer'])

    def test_empty_index(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Index(directory).search('retrieval'), [])

    def test_chunk_overlap_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'tiny.md').write_text('one two three four five six seven')
            chunks = Index(directory, chunk_size=4, overlap=1).chunks
            self.assertEqual([c['text'] for c in chunks], ['one two three four', 'four five six seven'])
            self.assertEqual(chunks[1]['id'], 'tiny:2')

    def test_evaluation_fixture(self):
        r = evaluate(self.index)
        self.assertEqual(len(r['cases']), 4)
        self.assertEqual(r['value'], 1.0)


class AgentTests(unittest.TestCase):
    def test_all_tasks_complete_with_allowlisted_actions(self):
        for task in ('retrieval', 'safety', 'serving'):
            r = run_agent(Index(), task, 6)
            self.assertEqual(r['status'], 'completed')
            self.assertEqual(r['steps_used'], 4)
            self.assertEqual([s['action'] for s in r['trace']], ['plan','search_corpus','check_evidence','finish'])
            self.assertTrue(r['result'])

    def test_budget_stops_without_final_answer(self):
        for budget in (1, 2, 3):
            r = run_agent(Index(), budget=budget)
            self.assertEqual(r['status'], 'budget_exhausted')
            self.assertEqual(r['steps_used'], budget)
            self.assertIsNone(r['result'])

    def test_invalid_tasks_and_budgets(self):
        with self.assertRaises(ValueError):
            run_agent(Index(), 'run_shell')
        for budget in (0, 7, -1, True, 2.5, '3'):
            with self.assertRaises(ValueError):
                run_agent(Index(), budget=budget)

    def test_missing_evidence_fails_review(self):
        with tempfile.TemporaryDirectory() as directory:
            r = run_agent(Index(directory))
            self.assertEqual(r['status'], 'check_failed')
            self.assertIsNone(r['result'])


class MeasurementTests(unittest.TestCase):
    def test_sse_parser_handles_comments_usage_and_done(self):
        stream = b': heartbeat\n\ndata: {"choices": []}\n\ndata: {"usage": {"completion_tokens": 4}}\n\ndata: [DONE]\n\n'
        self.assertEqual(len(list(sse_events(io.BytesIO(stream)))), 2)

    def test_truncated_stream_is_not_success(self):
        with self.assertRaises(ValueError):
            list(sse_events(['data: {"choices": []}\n', '\n']))

    def test_multiline_sse(self):
        self.assertEqual(list(sse_events(['data: {\n','data: "choices": []}\n','\n','data: [DONE]\n','\n'])), [{'choices': []}])

    def test_precise_timestamps_and_server_token_usage(self):
        clock = iter([10.1, 10.3, 10.5])
        events = [{'choices':[{'delta':{'role':'assistant'}}]},
                  {'choices':[{'delta':{'content':'hello '}}]},
                  {'choices':[{'delta':{'content':'world'}}]},
                  {'usage':{'completion_tokens':8}, 'choices':[]}]
        r = measure(events, 10, lambda: next(clock))
        self.assertEqual(r['ttft_ms'], 100)
        self.assertEqual(r['mean_inter_content_event_ms'], 200)
        self.assertEqual(r['duration_ms'], 500)
        self.assertEqual(r['output_tokens_per_second'], 16)
        self.assertEqual(r['output'], 'hello world')

    def test_missing_usage_and_single_event(self):
        clock = iter([1.1, 1.2])
        r = measure([{'choices':[{'delta':{'content':'hi'}}]}], 1, lambda: next(clock))
        self.assertIsNone(r['output_tokens_per_second'])
        self.assertIsNone(r['mean_inter_content_event_ms'])

    def test_empty_response_has_no_latency(self):
        with self.assertRaises(ValueError):
            measure([], 0, lambda: 1)

    def test_provider_stream_error_discards_partial_output(self):
        with self.assertRaises(ValueError):
            measure([{'choices':[{'delta':{'content':'partial'}}]}, {'error':{'message':'failed'}}], 0, lambda: 1)

    def test_replay_labels_and_missing_tokens(self):
        r = replay()
        self.assertIn('synthetic', r['mode'])
        self.assertIsNone(r['completion_tokens'])
        self.assertIsNone(r['output_tokens_per_second'])

    def test_invalid_real_benchmark_configuration(self):
        for url in ('file:///etc/passwd', 'http://user:secret@localhost/v1', 'http://localhost/v1?key=secret'):
            with self.assertRaises(ValueError):
                benchmark(url, 'model')
        with self.assertRaises(ValueError):
            benchmark('http://localhost/v1', 'model', runs=11)


class MockModel(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.requests.append(body)
        if body['model'] == 'failure':
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'Sensitive provider detail must not be reported')
            return
        if body['model'] == 'redirect':
            self.send_response(302)
            self.send_header('Location', '/redirected')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for event in [{'choices':[{'delta':{'content':'Test output'}}]}, {'choices':[], 'usage':{'completion_tokens':2}}]:
            self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
            self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/v1'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_real_adapter_against_mock_sse(self):
        r = benchmark(self.url, 'mock', runs=2)
        self.assertEqual(r['successful_runs'], 2)
        self.assertEqual(r['failures'], [])
        self.assertEqual(r['results'][0]['completion_tokens'], 2)
        self.assertIn('three short sentences', MockModel.requests[-1]['messages'][0]['content'])

    def test_failures_are_counted_without_provider_details(self):
        r = benchmark(self.url, 'failure', runs=1)
        self.assertEqual(r['successful_runs'], 0)
        self.assertEqual(r['failures'][0]['error'], 'HTTPError')
        self.assertNotIn('Sensitive', json.dumps(r))

    def test_redirect_is_refused(self):
        r = benchmark(self.url, 'redirect', runs=1)
        self.assertEqual(r['successful_runs'], 0)
        self.assertEqual(r['failures'][0]['error'], 'HTTPError')


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, path, data, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        return urllib.request.urlopen(urllib.request.Request(self.url+path, json.dumps(data).encode(), headers))

    def test_dashboard_and_status(self):
        with urllib.request.urlopen(self.url) as r:
            self.assertIn(b'fieldwork', r.read())
        with urllib.request.urlopen(self.url+'/api/status') as r:
            self.assertEqual(json.load(r)['mode'], 'offline')

    def test_rag_and_agent_routes(self):
        with self.post('/api/ask', {'question':'TF-IDF retrieval citations'}) as r:
            self.assertTrue(json.load(r)['sources'])
        with self.post('/api/agent', {'task':'serving','budget':3}) as r:
            self.assertEqual(json.load(r)['status'], 'budget_exhausted')

    def test_unsupported_question_returns_abstention_without_answer_sources(self):
        with self.post('/api/ask', {'question':'What is the vLLM subscription refund policy?'}) as r:
            result=json.load(r)
            self.assertEqual(result['decision'],'abstain')
            self.assertEqual(result['sources'],[])
            self.assertTrue(result['retrieval_evidence'])

    def test_cross_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post('/api/replay', {}, 'https://example.com')
        self.assertEqual(e.exception.code, 403)
        e.exception.close()

    def test_invalid_body_task_and_budget(self):
        for data in ([], {'question':''}, {'question':42}):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.post('/api/ask', data)
            self.assertEqual(e.exception.code, 400)
            e.exception.close()
        for data in ({'task':'shell'}, {'budget':99}):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.post('/api/agent', data)
            self.assertEqual(e.exception.code, 400)
            e.exception.close()

    def test_arbitrary_benchmark_route_absent(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post('/api/benchmark', {'base_url':'https://example.com'})
        self.assertEqual(e.exception.code, 404)
        e.exception.close()


if __name__ == '__main__':
    unittest.main()
