import json
import base64
import hashlib
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .core import ROOT, TASKS, Index, evaluate, replay, run_agent
from .generation import GenerationError, generate, public_status, strict_json
from .model_agent import AgentBudget,AgentError,AgentJobs,agent_status

INDEX = Index()
INDICES = {'lab': INDEX, 'shop': Index(ROOT/'examples/shop')}
GENERATION_SLOTS = threading.BoundedSemaphore(2)
AGENT_JOBS = AgentJobs()
BODY_TIMEOUT = 5


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def parse_request(self):
        if not super().parse_request():return False
        hosts=self.headers.get_all('Host',[])
        if hosts != [f'127.0.0.1:{self.server.server_port}']:
            self.send(403,{'error':'Use the exact local host and port'})
            return False
        if not self.path.startswith('/') or self.path.startswith('//'):
            self.send(400,{'error':'Use a local origin-form request target'})
            return False
        return True

    def send_error(self,code,message=None,explain=None):
        self.send(code,{'error':'Request rejected'})

    def send(self, status, body, content_type='application/json'):
        payload = json.dumps(body).encode() if content_type == 'application/json' else body
        self.send_response(status)
        self.send_header('Content-Type', content_type+'; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        scripts=re.findall(rb'<script>(.*?)</script>',payload,re.S) if content_type=='text/html' else []
        hashes=' '.join("'sha256-"+base64.b64encode(hashlib.sha256(script).digest()).decode()+"'" for script in scripts)
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src "+(hashes or "'none'")+"; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Connection','close')
        self.close_connection=True
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            return self.send(200, (ROOT / 'web/index.html').read_bytes(), 'text/html')
        if path == '/api/status':
            return self.send(200, dict(mode='offline', chunks=len(INDEX.chunks), documents=len({c['source'] for c in INDEX.chunks}),
                                       tasks={k: v[0] for k, v in TASKS.items()},
                                       generation=public_status(),model_agent=agent_status(),corpora=['shop','lab']))
        if path == '/api/evaluate':
            return self.send(200, evaluate(INDEX))
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        # Only same-origin JSON requests; no browser-selected network endpoints.
        origin = self.headers.get('Origin')
        allowed = f'http://127.0.0.1:{self.server.server_port}'
        if len(self.headers.get_all('Origin',[]))>1 or (origin and origin != allowed):
            return self.send(403, {'error': 'Origin rejected'})
        try:
            lengths=self.headers.get_all('Content-Length',[])
            if (len(lengths)!=1 or self.headers.get_all('Transfer-Encoding',[]) or
                len(lengths[0])>5 or not lengths[0].isascii() or not lengths[0].isdigit()):
                raise ValueError('Use one valid Content-Length and no Transfer-Encoding')
            size = int(lengths[0])
            if not 0 < size <= 8192:
                raise ValueError('Request must be 1–8192 bytes')
            if (len(self.headers.get_all('Content-Type',[]))!=1 or self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json'):
                raise ValueError('Use application/json')
            if self.headers.get_all('Expect',[]):
                return self.send(417,{'error':'Expect is not supported'})
            if self.headers.get_all('Content-Encoding',[]) not in ([],['identity']):
                raise ValueError('Compressed request bodies are not supported')
            expired=threading.Event()
            def interrupt_body():
                expired.set()
                try:self.connection.shutdown(socket.SHUT_RD)
                except OSError:pass
            timer=threading.Timer(BODY_TIMEOUT,interrupt_body);timer.daemon=True;timer.start()
            try:raw=self.rfile.read(size)
            finally:timer.cancel()
            if expired.is_set():return self.send(408,{'error':'Request body deadline exceeded'})
            if len(raw)!=size:raise ValueError('Incomplete request body')
            try:data=strict_json(raw)
            except GenerationError:raise ValueError('Use valid UTF-8 JSON with unique keys and finite numbers') from None
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            if self.path in ('/api/model-agent/start','/api/model-agent/status','/api/model-agent/cancel'):
                if origin != allowed or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.send(403, {'error':'Agent jobs require the exact local browser origin and host'})
                try:
                    if self.path.endswith('/start'):
                        if set(data)-{'question','corpus','mode','max_steps','max_seconds','max_requested_tokens'}:
                            raise ValueError('Unexpected agent job parameter')
                        corpus=data.get('corpus','shop')
                        if not isinstance(corpus,str) or corpus not in INDICES:raise ValueError('Choose shop or lab documents')
                        budget=AgentBudget(**{k:data[k] for k in ('max_steps','max_seconds','max_requested_tokens') if k in data})
                        return self.send(200,AGENT_JOBS.start(INDICES[corpus],data.get('question',''),data.get('mode','offline'),budget))
                    if set(data)!={'id'} or not isinstance(data['id'],str) or len(data['id'])!=32 or any(c not in '0123456789abcdef' for c in data['id']):
                        raise ValueError('Expected a local job ID')
                    return self.send(200,AGENT_JOBS.request_cancel(data['id']) if self.path.endswith('/cancel') else AGENT_JOBS.snapshot(data['id']))
                except AgentError as exc:
                    status=503 if exc.code in ('configuration','disabled') else 429 if exc.code=='busy' else 404 if exc.code=='not_found' else 400
                    return self.send(status,{'error':str(exc),'error_code':exc.code})
            if self.path in ('/api/ask', '/api/generate'):
                if set(data) - {'question','corpus'}:
                    raise ValueError('Only question and corpus are accepted')
                q = data.get('question', '')
                if not isinstance(q, str) or not 1 <= len(q.strip()) <= 1000:
                    raise ValueError('Question must be 1–1000 characters')
                corpus = data.get('corpus', 'lab')
                if not isinstance(corpus,str) or corpus not in INDICES:
                    raise ValueError('Choose the shop or lab corpus')
                if self.path == '/api/ask':
                    return self.send(200, INDICES[corpus].answer(q))
                if origin != allowed or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.send(403, {'error':'Generation requires the exact local browser origin and host'})
                if not GENERATION_SLOTS.acquire(blocking=False):
                    return self.send(429, {'error':'Two generation requests are already active. Try again later.','error_code':'busy'})
                try:
                    return self.send(200, generate(INDICES[corpus],q))
                except GenerationError as exc:
                    status = 503 if exc.code in ('configuration','disabled') else 504 if exc.code == 'timeout' else 413 if exc.code == 'request_size' else 502
                    return self.send(status, {'error':str(exc),'error_code':exc.code,'mode':'no generated answer'})
                finally:
                    GENERATION_SLOTS.release()
            if self.path == '/api/agent':
                return self.send(200, run_agent(INDEX, data.get('task', 'retrieval'), data.get('budget', 6)))
            if self.path == '/api/replay':
                return self.send(200, replay())
            if self.path == '/api/serving-suite':
                if data:raise ValueError('Only the fixed synthetic suite is available in the browser')
                from .serving import synthetic_suite
                return self.send(200, synthetic_suite())
            self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except (TimeoutError,socket.timeout):
            self.send(408,{'error':'Request body deadline exceeded'})


def serve(port=8080):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'AI Engineering Lab → http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
