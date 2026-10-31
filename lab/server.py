import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .core import ROOT, TASKS, Index, evaluate, replay, run_agent
from .generation import GenerationError, generate, public_status

INDEX = Index()
INDICES = {'lab': INDEX, 'shop': Index(ROOT/'examples/shop')}
GENERATION_SLOTS = threading.BoundedSemaphore(2)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type='application/json'):
        payload = json.dumps(body).encode() if content_type == 'application/json' else body
        self.send_response(status)
        self.send_header('Content-Type', content_type+'; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            return self.send(200, (ROOT / 'web/index.html').read_bytes(), 'text/html')
        if path == '/api/status':
            return self.send(200, dict(mode='offline', chunks=len(INDEX.chunks), documents=len({c['source'] for c in INDEX.chunks}),
                                       tasks={k: v[0] for k, v in TASKS.items()},
                                       generation=public_status(), corpora=['shop','lab']))
        if path == '/api/evaluate':
            return self.send(200, evaluate(INDEX))
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        # Only same-origin JSON requests; no browser-selected network endpoints.
        origin = self.headers.get('Origin')
        allowed = f'http://127.0.0.1:{self.server.server_port}'
        if origin and origin != allowed:
            return self.send(403, {'error': 'Origin rejected'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError('Request must be 1–8192 bytes')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Use application/json')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
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
            self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError) as exc:
            self.send(400, {'error': str(exc)})


def serve(port=8080):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'AI Engineering Lab → http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
