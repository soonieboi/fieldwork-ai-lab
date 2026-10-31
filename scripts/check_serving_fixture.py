"""Reproduce virtual fixture arithmetic, not measured model performance."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from lab.serving import synthetic_suite
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--write',action='store_true')
args=parser.parse_args()
first=json.dumps(synthetic_suite(),indent=2,sort_keys=True)+'\n'
assert first==json.dumps(synthetic_suite(),indent=2,sort_keys=True)+'\n'
path=ROOT/'evals/serving-v1/synthetic-virtual.json'
if args.write:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(first)
else:assert path.read_text()==first,'Synthetic serving artifact changed; inspect arithmetic and provenance'
print('Virtual serving fixture reproduced twice. No measured inference performance.')
