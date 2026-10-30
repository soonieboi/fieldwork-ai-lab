"""Reproduce committed reports without rewriting fixtures or tuning held-out data."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lab.abstention import load_policy
from lab.evaluation import calibrate, run_suite


def encoded(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)+'\n'


def check():
    calibration = calibrate()
    assert calibration['selected']['policy'] == load_policy(), 'Policy differs from development calibration'
    expected = ROOT/'evals/reports/v1-calibration.json'
    assert encoded(calibration) == expected.read_text(), 'Calibration artifact is stale'
    for split in ('development', 'heldout'):
        first = encoded(run_suite(split, load_policy()))
        second = encoded(run_suite(split, load_policy()))
        assert first == second, f'{split} report is nondeterministic'
        expected = ROOT/f'evals/reports/v1-{split}.json'
        assert first == expected.read_text(), f'{split} artifact differs from the frozen baseline'
        print(f'{split}: two byte-identical runs match committed report')
    print('Policy unchanged; no held-out tuning or quality threshold asserted.')


if __name__ == '__main__':
    check()
