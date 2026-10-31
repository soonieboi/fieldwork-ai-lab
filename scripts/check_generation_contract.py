"""Contract fixtures only: no inference, semantic judging or frozen-v1 scoring."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from lab.generation import GenerationError, response_schema, strict_json, validate_response


def check(directory=ROOT/'evals/generation-contract-v1'):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_bytes())
    if manifest.get('version')!='fieldwork-generation-contract-v1' or manifest.get('model_quality_assessed') is not False:
        raise ValueError('Unexpected contract fixture version/scope')
    if set(manifest['files'])!={'cases.json','response.schema.json'}:
        raise ValueError('Unexpected contract manifest inventory')
    entries=list(directory.rglob('*'))
    if any(p.is_symlink() or not p.is_file() for p in entries) or {p.name for p in entries}!=set(manifest['files'])|{'manifest.json'}:
        raise ValueError('Contract fixture inventory differs from manifest')
    verified={}
    for name,expected in manifest['files'].items():
        content=(directory/name).read_bytes()
        if hashlib.sha256(content).hexdigest()!=expected:
            raise ValueError('Contract fixture hash mismatch')
        verified[name]=json.loads(content)
    if response_schema(manifest['allowed_ids'])!=verified['response.schema.json']:
        raise ValueError('Wire schema changed without versioned contract update')
    cases=verified['cases.json']
    if len(cases)!=manifest['cases'] or len({c['id'] for c in cases})!=len(cases):
        raise ValueError('Invalid contract case count or IDs')
    for case in cases:
        try:
            validate_response(strict_json(case['raw_json']),manifest['allowed_ids'])
            accepted=True
        except GenerationError:
            accepted=False
        if type(case['expected_valid']) is not bool or accepted!=case['expected_valid']:
            raise AssertionError('Contract fixture mismatch: '+case['id'])
    print(f'{len(cases)} authored contract fixtures matched. Model factual support/quality: NOT ASSESSED.')
    return len(cases)


if __name__=='__main__':
    check()
