"""Local HTTP boundary tests, not a claim of production security."""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
import re
import socket
import threading
import time
import unittest
import urllib.request
from unittest.mock import patch
from lab import server
from tests.http_client import urlopen

class Quiet(server.Handler):
    def log_message(self,*args):pass

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        cls.port=cls.server.server_port;cls.url=f'http://127.0.0.1:{cls.port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def raw(self,headers='',body=b'{}',method='POST',path='/api/replay',length=True,halfclose=False):
        request=(f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\n'+
                 (f'Content-Length: {len(body)}\r\n' if length else '')+headers+'\r\n').encode()+body
        with socket.create_connection(('127.0.0.1',self.port),timeout=2) as sock:
            sock.sendall(request)
            if halfclose:sock.shutdown(socket.SHUT_WR)
            data=b''
            while True:
                part=sock.recv(16384)
                if not part:break
                data+=part
        status=int(data.split(b' ',2)[1]);return status,data

    def test_security_headers_and_exact_script_hash(self):
        with urlopen(self.url) as response:
            body=response.read();headers=response.headers
        scripts=re.findall(rb'<script>(.*?)</script>',body,re.S);self.assertEqual(len(scripts),1)
        expected="'sha256-"+base64.b64encode(hashlib.sha256(scripts[0]).digest()).decode()+"'"
        self.assertIn(expected,headers['Content-Security-Policy'])
        self.assertNotIn("script-src 'unsafe-inline'",headers['Content-Security-Policy'])
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'],'DENY');self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['Connection'],'close')
        self.assertEqual(headers['Cross-Origin-Resource-Policy'],'same-origin')
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')

    def test_duplicate_host_and_absolute_targets_rejected_before_work(self):
        with patch('lab.server.replay') as work:
            self.assertEqual(self.raw('Host: evil.invalid\r\n')[0],403)
            self.assertEqual(self.raw(path='http://evil.invalid/api/replay')[0],400)
        work.assert_not_called()
        with socket.create_connection(('127.0.0.1',self.port),timeout=2) as sock:
            sock.sendall(b'GET /api/status HTTP/1.1\r\nHost: evil.invalid\r\n\r\n')
            self.assertIn(b'403',sock.recv(1024))

    def test_ambiguous_or_oversize_framing_never_dispatches(self):
        headers=['Content-Length: 2\r\n','Transfer-Encoding: chunked\r\n','Content-Length: +2\r\n',
                 'Content-Length: -1\r\n','Content-Length: 8193\r\n','Content-Length: 999999999999999\r\n']
        with patch('lab.server.replay') as work:
            for header in headers:
                with self.subTest(header=header):
                    self.assertEqual(self.raw(header,length=not header.startswith('Content-Length: +') and not header.startswith('Content-Length: -') and '8193' not in header and '999999' not in header)[0],400)
        work.assert_not_called()

    def test_compressed_expect_duplicate_origin_and_content_type_rejected(self):
        cases=[('Content-Encoding: gzip\r\n',400),('Expect: 100-continue\r\n',417),
               ('Origin: '+self.url+'\r\nOrigin: '+self.url+'\r\n',403),('Content-Type: application/json\r\n',400)]
        with patch('lab.server.replay') as work:
            for headers,status in cases:self.assertEqual(self.raw(headers)[0],status)
        work.assert_not_called()

    def test_short_body_and_strict_json_errors_are_sanitized(self):
        with patch('lab.server.replay') as work:
            self.assertEqual(self.raw('Content-Length: 20\r\n',length=False,halfclose=True)[0],400)
            for body in (b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff',b'{"PRIVATE_BODY_FIXTURE":'):
                status,raw=self.raw(body=body);self.assertEqual(status,400);self.assertNotIn(b'PRIVATE_BODY_FIXTURE',raw)
        work.assert_not_called()

    def test_slow_body_has_finite_deadline(self):
        start=time.monotonic()
        with patch('lab.server.BODY_TIMEOUT',.1),patch('lab.server.replay') as work:
            status,_=self.raw('Content-Length: 20\r\n',length=False)
        self.assertEqual(status,408);self.assertLess(time.monotonic()-start,1.5);work.assert_not_called()

    def test_unknown_files_methods_and_queries_do_not_expose_files(self):
        for path in ('/.env','/README.md','/../lab/server.py'):
            status,raw=self.raw(method='GET',path=path,body=b'');self.assertEqual(status,404)
            self.assertNotIn(b'from .core',raw)
        self.assertEqual(self.raw(method='TRACE',body=b'')[0],501)

    def test_direct_test_client_ignores_empty_bypass_and_cached_proxy(self):
        cached=urllib.request.build_opener(urllib.request.ProxyHandler({'http':'http://127.0.0.1:9'}))
        with patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:9','HTTPS_PROXY':'http://127.0.0.1:9',
                                    'ALL_PROXY':'http://127.0.0.1:9','NO_PROXY':'','no_proxy':''}),patch.object(urllib.request,'_opener',cached):
            with urlopen(self.url+'/api/status') as r:self.assertEqual(json.load(r)['mode'],'offline')

    def test_serve_binds_only_loopback(self):
        class StopServer:
            server_port=8088
            def serve_forever(self):raise KeyboardInterrupt
            def server_close(self):pass
        with patch('lab.server.ThreadingHTTPServer',return_value=StopServer()) as factory:
            server.serve(8088)
        self.assertEqual(factory.call_args.args[0],('127.0.0.1',8088))
