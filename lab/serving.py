"""Finite serving experiments; fixtures are not model performance evidence."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit
from .generation import GenerationConfig, GenerationError, StrictHTTPResponse, strict_json

WORKLOAD=[
    {'id':'short','prompt':'Suggest one easy weekday breakfast.','max_tokens':32},
    {'id':'medium','prompt':'A fictional shopper has unworn shoes bought ten days ago and a receipt. A shop allows returns within thirty days with a receipt. Explain the next step in two sentences.','max_tokens':64},
    {'id':'long','prompt':'Help plan a simple weekend picnic for four friends. '+
     'One friend avoids nuts, another prefers vegetarian food, and everyone will walk to the park. '+
     'There is no refrigerator or cooking equipment at the picnic site. '+
     'Suggest a practical shopping list and explain safe packing, drinks, cleanup, and a rain alternative. '+
     'Keep the response organized and avoid assuming a budget or specific shop.','max_tokens':128},
]
MAX_BYTES=131072

class BenchError(Exception):
    def __init__(self,status):self.status=status;super().__init__(status)

@dataclass(frozen=True)
class SuiteConfig:
    runs:int=9
    warmup:int=1
    concurrency:int=2
    rate:float=2
    timeout:float=10
    seed:int=17
    def __post_init__(self):
        if (type(self.runs) is not int or not 1<=self.runs<=30 or type(self.warmup) is not int or not 0<=self.warmup<=3
            or type(self.concurrency) is not int or not 1<=self.concurrency<=4
            or type(self.seed) is not int or not 0<=self.seed<=2**31-1
            or type(self.rate) not in (int,float) or not math.isfinite(self.rate) or not .2<=self.rate<=10
            or type(self.timeout) not in (int,float) or not math.isfinite(self.timeout) or not 1<=self.timeout<=30
            or (self.runs+self.warmup)*(self.timeout+1/self.rate)>180):
            raise ValueError('Use finite suite limits within a conservative 180-second experiment bound')


def percentile(values):
    ordered=sorted(values);n=len(ordered)
    return {'n':n,'estimator':'nearest_rank_ceil_p_times_n',
            **{'p'+str(p):round(ordered[math.ceil(p*n/100)-1],3) if n else None for p in (50,90,95)}}


def measure_stream(chunks,start,clock=time.perf_counter):
    """Drain complete framed body, not just DONE; no partial success metrics."""
    buffer=b'';data=[];data_bytes=0;done=False;finished=False;times=[];tokens=None;usage_seen=False;total=0
    def event(payload):
        nonlocal done,finished,tokens,usage_seen
        if done:raise BenchError('protocol')
        if payload==b'[DONE]':done=True;return
        try:value=strict_json(payload)
        except GenerationError:raise BenchError('protocol') from None
        if not isinstance(value,dict):raise BenchError('protocol')
        if value.get('error'):raise BenchError('provider_error')
        usage=value.get('usage')
        if usage is not None:
            if usage_seen or not isinstance(usage,dict):raise BenchError('protocol')
            usage_seen=True;tokens=usage.get('completion_tokens')
            if tokens is not None and (type(tokens) is not int or not 0<=tokens<=1_000_000):raise BenchError('protocol')
        choices=value.get('choices')
        if not isinstance(choices,list) or len(choices)>1:raise BenchError('protocol')
        if not choices:return
        choice=choices[0]
        if not isinstance(choice,dict) or choice.get('index',0)!=0:raise BenchError('protocol')
        delta=choice.get('delta')
        if not isinstance(delta,dict):raise BenchError('protocol')
        if delta.get('refusal'):raise BenchError('refusal')
        if delta.get('tool_calls') or delta.get('function_call'):raise BenchError('protocol')
        piece=delta.get('content')
        if piece is not None and not isinstance(piece,str):raise BenchError('protocol')
        if piece:
            if finished:raise BenchError('protocol')
            times.append(clock())
        reason=choice.get('finish_reason')
        if reason is not None:
            if finished:raise BenchError('protocol')
            if reason=='length':raise BenchError('length_limit')
            if reason=='content_filter':raise BenchError('refusal')
            if reason!='stop':raise BenchError('protocol')
            finished=True
    for block in chunks:
        total+=len(block)
        if total>MAX_BYTES:raise BenchError('response_size')
        buffer+=block
        while b'\n' in buffer:
            line,buffer=buffer.split(b'\n',1);line=line.removesuffix(b'\r')
            if len(line)>32768:raise BenchError('response_size')
            if not line:
                if data:event(b'\n'.join(data));data=[];data_bytes=0
            elif line.startswith(b'data:'):
                piece=line[5:].lstrip(b' ');data_bytes+=len(piece)+1;data.append(piece)
                if data_bytes>32768:raise BenchError('response_size')
            elif line.startswith(b':'):pass
            else:raise BenchError('protocol')
        if len(buffer)>32768:raise BenchError('response_size')
    if buffer.strip() or data or not done or not finished:raise BenchError('incomplete')
    if not times:raise BenchError('empty')
    end=clock()
    return {'status':'success','duration_ms':(end-start)*1000,'first_content_ms':(times[0]-start)*1000,
            'content_events':len(times),'event_gaps_ms':[(b-a)*1000 for a,b in zip(times,times[1:])],
            'completion_tokens':tokens,'token_provenance':'provider_completion_usage' if tokens is not None else 'unknown'}


def stream_request(config,prompt,seed,clock=time.perf_counter):
    """Direct verified TLS/loopback only; same strict framing as cited generation."""
    p=urlsplit(config.base_url);start=clock();deadline=time.monotonic()+config.timeout
    connection=None;response=None;timer=None;expired=threading.Event()
    try:
        connection=(http.client.HTTPSConnection(p.hostname,p.port,timeout=config.timeout,context=ssl.create_default_context())
                    if p.scheme=='https' else http.client.HTTPConnection(p.hostname,p.port,timeout=config.timeout))
        connection.response_class=StrictHTTPResponse
        connection.connect() # OS DNS remains outside a hard cancellation guarantee.
        remaining=deadline-time.monotonic()
        if remaining<=0:raise BenchError('timeout')
        sock=connection.sock;sock.settimeout(remaining)
        def interrupt():
            expired.set()
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(remaining,interrupt);timer.daemon=True;timer.start()
        body=json.dumps({'model':config.model,'messages':[{'role':'user','content':prompt['prompt']}],
                         config.token_field:prompt['max_tokens'],'stream':True,'stream_options':{'include_usage':True},
                         'temperature':0,'seed':seed,'n':1}).encode()
        headers={'Content-Type':'application/json','Accept':'text/event-stream','Accept-Encoding':'identity'}
        if config.api_key:headers['Authorization']='Bearer '+config.api_key
        connection.request('POST',p.path.rstrip('/')+'/chat/completions',body,headers);response=connection.getresponse()
        if 300<=response.status<400:raise BenchError('redirect')
        if response.status!=200:raise BenchError('http_error')
        if (response.getheader('Content-Type','').split(';')[0].strip().lower()!='text/event-stream'
            or response.getheader('Content-Encoding','identity').lower()!='identity'):raise BenchError('protocol')
        lengths=[v.strip() for k,v in response.getheaders() if k.lower()=='content-length']
        encodings=[v.strip().lower() for k,v in response.getheaders() if k.lower()=='transfer-encoding']
        if len(lengths)>1 or len(encodings)>1 or (lengths and encodings):raise BenchError('protocol')
        if encodings and (encodings!=['chunked'] or not response.chunked):raise BenchError('protocol')
        size=None
        if lengths:
            if not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0])>10:raise BenchError('protocol')
            size=int(lengths[0])
            if size>MAX_BYTES:raise BenchError('response_size')
        def chunks():
            total=0
            while True:
                if expired.is_set() or time.monotonic()>=deadline:raise BenchError('timeout')
                block=response.read1(min(4096,MAX_BYTES+1-total))
                if not block:break
                total+=len(block)
                if total>MAX_BYTES:raise BenchError('response_size')
                yield block
            if expired.is_set():raise BenchError('timeout')
            if size is not None and total!=size:raise BenchError('incomplete')
        return measure_stream(chunks(),start,clock)
    except BenchError as exc:status='timeout' if expired.is_set() else exc.status
    except (TimeoutError,socket.timeout):status='timeout'
    except http.client.IncompleteRead:status='timeout' if expired.is_set() else 'incomplete'
    except (OSError,http.client.HTTPException):status='timeout' if expired.is_set() else 'transport'
    finally:
        if timer:timer.cancel()
        if response:response.close()
        if connection:connection.close()
    return {'status':status,'duration_ms':(clock()-start)*1000}


def workload(config,count):
    rows=[dict(WORKLOAD[i%len(WORKLOAD)]) for i in range(count)]
    random.Random(config.seed).shuffle(rows);return rows


def schedule(config,prompts,invoke,clock=time.perf_counter,sleep=time.sleep):
    """No queue of network work: dispatch only with a free slot and rate permit."""
    rows=[];pending={};next_start=clock();i=0
    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        while i<len(prompts) or pending:
            if i<len(prompts) and len(pending)<config.concurrency:
                delay=next_start-clock()
                if delay>0:sleep(delay)
                prompt=prompts[i];number=i;i+=1
                def run(prompt=prompt,number=number):
                    start=clock();result=invoke(prompt);end=clock()
                    return dict(result,request=number+1,prompt_id=prompt['id'],start=start,end=end)
                pending[pool.submit(run)]=True;next_start=clock()+1/config.rate
            else:
                complete,_=wait(pending,return_when=FIRST_COMPLETED)
                for future in complete:rows.append(future.result());del pending[future]
    return sorted(rows,key=lambda r:r['request'])


def summarize(rows):
    success=[r for r in rows if r['status']=='success'];failure=[r for r in rows if r['status']!='success']
    window=max(r['end'] for r in rows)-min(r['start'] for r in rows) if rows else 0
    known=[r for r in success if r['completion_tokens'] is not None];tokens=sum(r['completion_tokens'] for r in known)
    return {'window_scope':'earliest start through latest end of requests in this summary; slice rates are not additive',
        'requested':len(rows),'successful':len(success),'status_counts':{s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})},
        'first_content_ms':percentile([r['first_content_ms'] for r in success]),'duration_ms':percentile([r['duration_ms'] for r in success]),
        'failure_duration_ms':percentile([r['duration_ms'] for r in failure]),
        'inter_content_event_ms':percentile([g for r in success for g in r['event_gaps_ms']]),
        'elapsed_window_seconds':round(window,6),'successful_requests_per_second':len(success)/window if window>0 else None,
        'token_coverage':{'known_successes':len(known),'successful_requests':len(success),'known_completion_tokens':tokens},
        'successful_output_tokens_per_second':tokens/window if window>0 and success and len(known)==len(success) else None}


def report(config,rows,warmups,metadata):
    origin=min((r['start'] for r in rows),default=0)
    records=[{k:(round((v-origin)*1000,3) if k in ('start','end') else v) for k,v in r.items()} for r in rows]
    return {'version':'fieldwork-serving-v1','config':asdict(config),'metadata':metadata,
        'implementation_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('serving.py','generation.py')},
        'workload':WORKLOAD,'workload_sha256':hashlib.sha256(json.dumps(WORKLOAD,sort_keys=True).encode()).hexdigest(),
        'summary':summarize(rows),'by_prompt':{p['id']:summarize([r for r in rows if r['prompt_id']==p['id']]) for p in WORKLOAD},
        'warmup':{'excluded_from_metrics':True,'results':[{'status':r['status'],'prompt_id':r['prompt_id']} for r in warmups]},
        'requests_relative_ms':records,'caveats':['First content is not first header or token. Event gaps are not token ITL.',
        'Nearest-rank percentiles describe these samples only; prompt slices have different workloads.',
        'Aggregate successful tokens use the full mixed-request elapsed window, including failures and pacing.',
        'Unknown token usage is never estimated. Warmup excluded. No saturation or semantic quality claim.']}


def run_suite(config,endpoint,hardware='not supplied',model_label='not supplied'):
    for label in (hardware,model_label):
        if not isinstance(label,str) or not re.fullmatch(r'[A-Za-z0-9 ._()+-]{1,120}',label):raise ValueError('Use a short non-sensitive model/hardware label')
    started_at=datetime.now(timezone.utc).isoformat()
    invoke=lambda prompt:stream_request(endpoint,prompt,config.seed)
    warmups=schedule(config,workload(config,config.warmup),invoke)
    if warmups:
        # Preserve the dispatch-rate bound across the phase boundary as well.
        time.sleep(max(0,max(r['start'] for r in warmups)+1/config.rate-time.perf_counter()))
    rows=schedule(config,workload(config,config.runs),invoke)
    return report(config,rows,warmups,{'mode':'endpoint client experiment; hardware and model quality unverified',
        'started_at_utc':started_at,'endpoint_sha256':hashlib.sha256(endpoint.base_url.encode()).hexdigest(),'model_sha256':hashlib.sha256(endpoint.model.encode()).hexdigest(),
        'model_label_operator_supplied':model_label,'hardware_operator_supplied':hardware,'seed_support':'requested; provider support unverified',
        'client':{'python':platform.python_version(),'os':platform.system(),'architecture':platform.machine()}})


def synthetic_suite(config=None):
    """Virtual fixture times/counts, no sockets or real elapsed performance."""
    config=config or SuiteConfig();rng=random.Random(config.seed)
    def phase(count):
        slots=[0.0]*config.concurrency;rows=[];next_start=0.0
        for i,p in enumerate(workload(config,count)):
            slot=min(range(len(slots)),key=slots.__getitem__);start=max(slots[slot],next_start)
            first=.03+rng.random()*.02;duration=first+.01*(1+i%3);end=start+duration;slots[slot]=end;next_start=start+1/config.rate
            rows.append({'request':i+1,'prompt_id':p['id'],'start':start,'end':end,'status':'success','duration_ms':duration*1000,
                         'first_content_ms':first*1000,'content_events':2,'event_gaps_ms':[(duration-first)*1000],
                         'completion_tokens':p['max_tokens']//2,'token_provenance':'synthetic_fixture_count_not_model_tokens'})
        return rows
    warmups=phase(config.warmup);rows=phase(config.runs)
    return report(config,rows,warmups,{'mode':'SYNTHETIC virtual fixture — no inference or measured model performance',
        'hardware_operator_supplied':'not supplied','model':'none','clock':'virtual seconds; no wall-clock performance'})


def endpoint_from_env(config,environ=None):
    env=os.environ if environ is None else environ
    if env.get('LAB_SERVING_ENABLED')!='1':raise ValueError('Set LAB_SERVING_ENABLED=1 to opt into endpoint traffic')
    try:return GenerationConfig(env.get('LAB_SERVING_BASE_URL',''),env.get('LAB_SERVING_MODEL',''),env.get('LAB_SERVING_API_KEY',''),timeout=config.timeout)
    except GenerationError:raise ValueError('Invalid serving endpoint configuration; HTTPS required beyond loopback') from None
