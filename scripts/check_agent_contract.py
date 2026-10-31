"""Reproduce scripted workflow outcomes without endpoint calls or quality claims."""
from pathlib import Path
import sys
import argparse
import hashlib
import json
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from lab.agent_contracts import check

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Write the reviewed scripted report; never tune fixtures')
    args=parser.parse_args()
    manifest,results=check(with_metadata=True)
    report={'version':'fieldwork-agent-contract-v1','scope':manifest['provenance'],
            'semantic_quality_assessed':False,'results':results,
            'fixture_manifest_sha256':manifest['_loaded_manifest_sha256'],
            'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                             for name in ('lab/model_agent.py','lab/agent_contracts.py')}}
    encoded=json.dumps(report,indent=2,sort_keys=True)+'\n'
    path=ROOT/'evals/agent-reports/v1-scripted.json'
    if args.write:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(encoded)
    else:
        assert path.read_text()==encoded,'Scripted workflow artifact changed; inspect results and provenance'
        print('Scripted per-case artifact reproduced. No live-agent quality score.')

if __name__=='__main__':main()
