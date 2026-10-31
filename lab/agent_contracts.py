"""Authored workflow fixtures: contract outcomes, never live-agent quality."""
import hashlib
import json
from pathlib import Path
import threading

from .core import ROOT, Index
from .generation import GenerationConfig, GenerationError
from .model_agent import AgentBudget, run_model_agent

DATA=ROOT/'evals/agent-contract-v1'


def load_fixtures(directory=DATA):
    directory=Path(directory)
    manifest_bytes=(directory/'manifest.json').read_bytes()
    manifest=json.loads(manifest_bytes)
    if (manifest.get('version')!='fieldwork-agent-contract-v1' or manifest.get('semantic_quality_assessed') is not False
        or set(manifest['files'])!={'cases.json','corpus/returns.md'}):
        raise ValueError('Unexpected agent fixture scope/inventory')
    entries=list(directory.rglob('*'))
    files={p.relative_to(directory).as_posix() for p in entries if p.is_file()}
    if (any(p.is_symlink() for p in entries) or files!=set(manifest['files'])|{'manifest.json'}
        or any(p.is_dir() and p.relative_to(directory).as_posix()!='corpus' for p in entries)):
        raise ValueError('Agent fixture inventory differs from manifest')
    verified={}
    for name,expected in manifest['files'].items():
        content=(directory/name).read_bytes()
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('Agent fixture hash mismatch')
        verified[name]=content
    cases=json.loads(verified['cases.json'])
    if len(cases)!=manifest['cases'] or len({c['id'] for c in cases})!=len(cases):
        raise ValueError('Invalid agent fixture case count or IDs')
    manifest['_loaded_manifest_sha256']=hashlib.sha256(manifest_bytes).hexdigest()
    return manifest,cases,{'returns.md':verified['corpus/returns.md'].decode('utf-8')}


def run_case(case,documents,cap=128):
    now=[0.0];cancel=threading.Event();sent=[]
    if case.get('cancel_at')=='before_request':cancel.set()
    def emit(entry):
        if case.get('cancel_at')=='after_response' and entry['phase']=='model_response':cancel.set()
        if case.get('cancel_at')=='before_tool' and entry['phase']=='action_selected':cancel.set()
    def provider(config,body):
        sent.append(json.loads(body))
        if case.get('clock_advance'):now[0]+=case['clock_advance']
        if case.get('provider_event')=='transport':raise GenerationError('transport')
        if case.get('provider_event')=='refusal':return {'choices':[{'message':{'refusal':'Authored fixture refusal'}}]}
        step=case['steps'][len(sent)-1]
        content=step if isinstance(step,str) else json.dumps(step)
        result={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':content}}]}
        if case.get('usage')!='missing':
            result['usage']={'completion_tokens':config.max_tokens+1 if case.get('usage')=='over-cap' else 4}
        return result
    result=run_model_agent(Index(documents=documents),case['question'],
        GenerationConfig('http://127.0.0.1/unused','contract-fixture-not-a-model',max_tokens=cap),
        AgentBudget(**case.get('limits',{})),cancel,emit,provider,clock=lambda:now[0],mode='contract_fixture')
    actual_tools=[t['tool'] for t in result['trace'] if t['phase']=='tool_result']
    if result['status']!=case['expected_status'] or actual_tools!=case['expected_tools']:
        raise AssertionError('Agent workflow fixture mismatch: '+case['id'])
    if result['accounting']['model_requests']!=len(sent):raise AssertionError('Request accounting mismatch')
    if result['accounting']['requested_completion_token_caps']>result['limits']['max_requested_tokens']:
        raise AssertionError('Requested completion budget exceeded')
    if len(sent)>result['limits']['max_steps']:raise AssertionError('Step budget exceeded')
    return {'id':case['id'],'status':result['status'],'tools':actual_tools,
            'request_count':len(sent),'accounting':result['accounting'],'semantic_quality':'not_assessed'}


def check(directory=DATA,with_metadata=False):
    manifest,cases,documents=load_fixtures(directory)
    results=[run_case(c,documents,manifest['per_call_requested_cap']) for c in cases]
    print(f'{len(results)} authored agent workflow fixtures matched. Live-agent quality: NOT ASSESSED.')
    return (manifest,results) if with_metadata else results
