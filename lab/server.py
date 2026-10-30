import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .core import ROOT, TASKS, Index, evaluate, replay, run_agent

INDEX = Index()


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
                                       tasks={k: v[0] for k, v in TASKS.items()}))
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
            if self.path == '/api/ask':
                q = data.get('question', '')
                if not isinstance(q, str) or not 1 <= len(q.strip()) <= 1000:
                    raise ValueError('Question must be 1–1000 characters')
                return self.send(200, INDEX.answer(q))
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
