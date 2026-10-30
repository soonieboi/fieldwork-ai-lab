"""Inspectable retrieval, bounded orchestration, and streaming measurement."""
from __future__ import annotations

import collections
import hashlib
import json
import math
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = set('a an the of to and or in is it this that for with how what does can on from are as by at'.split())


def words(text):
    return [w for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in STOP]


class Index:
    def __init__(self, directory=ROOT / 'corpus', chunk_size=85, overlap=15, documents=None):
        if not 0 <= overlap < chunk_size:
            raise ValueError('overlap must be smaller than chunk_size')
        self.chunks = []
        if documents is None:
            documents = {p.name: p.read_text(encoding='utf-8') for p in sorted(Path(directory).glob('*.md'))}
        self.documents = dict(documents)
        for name, content in sorted(self.documents.items()):
            tokens = content.split()
            for start in range(0, len(tokens), chunk_size - overlap):
                self.chunks.append(dict(id=f'{Path(name).stem}:{start // (chunk_size-overlap)+1}',
                                        source=name, text=' '.join(tokens[start:start+chunk_size]),
                                        word_start=start, word_end=min(start+chunk_size, len(tokens)),
                                        source_sha256=hashlib.sha256(content.encode()).hexdigest()))
                if start + chunk_size >= len(tokens):
                    break
        counts = [collections.Counter(words(c['text'])) for c in self.chunks]
        df = collections.Counter(t for c in counts for t in c)
        self.idf = {t: math.log((1 + len(counts)) / (1 + n)) + 1 for t, n in df.items()}
        self.vectors = [self.vector(c) for c in counts]

    def vector(self, counts):
        v = {t: (1 + math.log(n)) * self.idf[t] for t, n in counts.items() if t in self.idf}
        norm = math.sqrt(sum(x*x for x in v.values())) or 1
        return {t: x/norm for t, x in v.items()}

    def search(self, question, k=3):
        q = self.vector(collections.Counter(words(question)))
        scores = [(sum(q.get(t, 0)*v for t, v in vec.items()), c)
                  for c, vec in zip(self.chunks, self.vectors)]
        return [dict(c, score=round(score, 4)) for score, c in
                sorted(scores, key=lambda pair: (-pair[0], pair[1]['id']))[:k] if score > 0]

    def answer(self, question):
        from .abstention import decide, load_policy
        hits = self.search(question)
        support = decide(question, hits, load_policy())
        sources = hits if support['decision'] == 'answer' else []
        message = ('No matching evidence in the sample corpus.' if not hits else
                   'Not enough lexical evidence to return an answer. Try a more specific question using the document vocabulary.')
        return dict(mode='offline · extractive / TF-IDF · lexical gate', question=question, sources=sources,
                    decision=support['decision'], support_check=support,
                    retrieval_evidence=hits,
                    answer='\n\n'.join(f"[{h['id']}] {h['text']}" for h in sources) or message)


EVAL_CASES = [
    ('How does TF-IDF retrieval preserve citations?', 'retrieval.md'),
    ('What does time to first token measure?', 'serving.md'),
    ('What tools can a bounded agent use?', 'agents.md'),
    ('Where does the lab server bind?', 'operations.md'),
]


def evaluate(index):
    cases = []
    for question, expected in EVAL_CASES:
        hits = index.search(question)
        cases.append(dict(question=question, expected=expected, hit=any(h['source'] == expected for h in hits),
                          retrieved=[h['id'] for h in hits]))
    return dict(metric='legacy smoke · document hit rate @ 3', value=sum(c['hit'] for c in cases)/len(cases),
                cases=cases, note='Four instructional fixtures; not held-out production evaluation.')


TASKS = {
    'retrieval': ('Explain the retrieval pipeline with citations', 'RAG chunk embed index cited answer', ['retrieval']),
    'safety': ('Audit the agent tool boundary', 'bounded agent tools shell steps restrictions', ['agent']),
    'serving': ('Prepare a serving measurement checklist', 'TTFT throughput inter token latency serving', ['serving']),
}


def run_agent(index, task='retrieval', budget=6):
    if task not in TASKS:
        raise ValueError('Choose a known task: ' + ', '.join(TASKS))
    if type(budget) is not int or not 1 <= budget <= 6:
        raise ValueError('Step budget must be an integer from 1 to 6')
    title, query, required = TASKS[task]
    trace, evidence = [], []
    phases = [('planner', 'plan'), ('researcher', 'search_corpus'), ('reviewer', 'check_evidence'), ('planner', 'finish')]
    result = None
    for role, action in phases:
        if len(trace) >= budget:
            break
        if action == 'plan':
            detail = 'Search the sample corpus, check source coverage, then return cited evidence.'
        elif action == 'search_corpus':
            evidence = index.search(query)
            detail = f'Retrieved {len(evidence)} chunks: ' + ', '.join(h['id'] for h in evidence)
        elif action == 'check_evidence':
            passed = bool(evidence) and all(any(term in h['text'].lower() for h in evidence) for term in required)
            detail = 'Source coverage check ' + ('passed' if passed else 'failed')
            if not passed:
                trace.append(dict(step=len(trace)+1, role=role, action=action, detail=detail))
                return dict(status='check_failed', trace=trace, result=None, sources=evidence, task=title)
        else:
            result = '\n\n'.join(f"[{h['id']}] {h['text']}" for h in evidence)
            detail = 'Returned an extractive evidence bundle with citations.'
        trace.append(dict(step=len(trace)+1, role=role, action=action, detail=detail))
    return dict(task=title, status='completed' if result is not None else 'budget_exhausted', trace=trace,
                result=result, sources=evidence, mode='deterministic fixture · sequential roles',
                allowed_tools=['search_corpus', 'check_evidence'], steps_used=len(trace), budget=budget)


def sse_events(lines):
    """Parse SSE event boundaries, comments, and multiline data."""
    data = []
    for raw in lines:
        line = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        line = line.rstrip('\r\n')
        if not line:
            if data:
                payload = '\n'.join(data)
                if payload == '[DONE]':
                    return
                yield json.loads(payload)
                data = []
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
    if data and '\n'.join(data) == '[DONE]':
        return
    raise ValueError('Stream ended without [DONE]; partial result discarded')


def measure(events, start, clock=time.perf_counter):
    times, content, usage = [], [], None
    for event in events:
        if event.get('error'):
            raise ValueError('Provider reported a stream error; partial result discarded')
        if event.get('usage'):
            usage = event['usage'].get('completion_tokens')
        for choice in event.get('choices', []):
            piece = choice.get('delta', {}).get('content')
            if piece:
                times.append(clock())
                content.append(piece)
    elapsed = clock()-start
    if not times:
        raise ValueError('Stream produced no content; no latency result recorded')
    gaps = [1000*(b-a) for a, b in zip(times, times[1:])]
    return dict(ttft_ms=round((times[0]-start)*1000, 2), duration_ms=round(elapsed*1000, 2),
                mean_inter_content_event_ms=round(sum(gaps)/len(gaps), 2) if gaps else None,
                content_events=len(times), completion_tokens=usage,
                output_tokens_per_second=round(usage/elapsed, 2) if type(usage) is int and usage > 0 and elapsed > 0 else None,
                output=''.join(content))


def replay():
    def events():
        for piece in ['This ', 'is ', 'a ', 'synthetic ', 'stream.']:
            time.sleep(0.012)
            yield {'choices': [{'delta': {'content': piece}}]}
    result = measure(events(), time.perf_counter())
    return dict(result, mode='synthetic replay · no model inference',
                note='Measured local fixture delays. No token count or model throughput is claimed.')


BENCH_PROMPT = 'Explain retrieval augmented generation in three short sentences.'


def benchmark(base_url, model, api_key='', runs=3, timeout=30):
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Endpoint must be an explicit http(s) URL without credentials, query, or fragment')
    if not model or not 1 <= runs <= 10 or not 1 <= timeout <= 120:
        raise ValueError('Supply a model, 1–10 runs, and a timeout of 1–120 seconds')
    body = json.dumps(dict(model=model, messages=[dict(role='user', content=BENCH_PROMPT)],
                           max_tokens=128, stream=True, stream_options={'include_usage': True})).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    # Do not forward credentials or benchmark traffic through redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    results, failures = [], []
    for i in range(runs):
        start = time.perf_counter()
        try:
            req = urllib.request.Request(base_url.rstrip('/')+'/chat/completions', body, headers)
            with opener.open(req, timeout=timeout) as response:
                def bounded_lines():
                    total = 0
                    while True:
                        if time.perf_counter()-start > timeout:
                            raise TimeoutError('Request deadline exceeded')
                        line = response.readline(65537)
                        if not line:
                            break
                        total += len(line)
                        if len(line) > 65536 or total > 2_000_000:
                            raise ValueError('Stream exceeded response size limit')
                        yield line
                results.append(measure(sse_events(bounded_lines()), start))
        except Exception as exc:
            # Avoid echoing provider bodies, URLs, or credentials.
            failures.append(dict(run=i+1, error=type(exc).__name__))
            if hasattr(exc, 'close'):
                exc.close()
    return dict(mode='real endpoint · sequential client', model=model, prompt=BENCH_PROMPT,
                warmup='none; first request included', requested_runs=runs, successful_runs=len(results),
                results=results, failures=failures, note='Client-observed content events are not token-level ITL. No saturation test.')
