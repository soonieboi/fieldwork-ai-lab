"""Versioned, deterministic evaluation of authored documentation QA fixtures.

No model calls or semantic judging. See docs/evaluation-design.md for the contract.
"""
import argparse
import hashlib
import json
from pathlib import Path

from .abstention import decide, features, load_policy
from .core import ROOT, Index

DATA = ROOT / 'evals' / 'v1'
CATEGORIES = {'answerable', 'unanswerable', 'ambiguous', 'conflicting', 'adversarial'}
BASELINES = ('positive_score_extractive', 'lexical_gate')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)+'\n', encoding='utf-8')


def safe_path(root, relative):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Dataset path escapes its root')
    return path


def validate_inventory(directory, manifest):
    """Require hash coverage for exactly the fixture bytes that may be loaded."""
    files = manifest.get('files')
    required = {'development.json', 'heldout.json', 'evidence.json'}
    if not isinstance(files, dict) or not required <= files.keys():
        raise ValueError('Missing manifest hash coverage for required case/evidence files')
    for name, expected in files.items():
        parts = Path(name).parts
        fixture = (len(parts) == 2 and parts[0] in ('corpus', 'profiles')
                   and Path(parts[1]).suffix == '.md')
        if name not in required and not fixture:
            raise ValueError('Unexpected manifest fixture path: '+name)
        if Path(name).as_posix() != name or '\\' in name:
            raise ValueError('Noncanonical manifest fixture path')
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Invalid manifest SHA256: '+name)
    corpus = sorted(name for name in files if name.startswith('corpus/'))
    if not corpus:
        raise ValueError('Manifest must cover a nonempty corpus')
    profiles = manifest.get('profiles')
    if not isinstance(profiles, dict) or profiles.get('base') != []:
        raise ValueError('Invalid manifest profiles')
    referenced = set()
    for extra in profiles.values():
        if not isinstance(extra, list) or any(not isinstance(name, str) for name in extra) or len(extra) != len(set(extra)):
            raise ValueError('Invalid or duplicate profile source')
        for name in extra:
            if not isinstance(name, str) or Path(name).name != name or Path(name).suffix != '.md' or '\\' in name:
                raise ValueError('Invalid profile source path')
            referenced.add('profiles/'+name)
    if referenced != {name for name in files if name.startswith('profiles/')}:
        raise ValueError('Profile references and manifest hash coverage differ')
    actual = set()
    for path in directory.rglob('*'):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            raise ValueError('Symlink fixture is not allowed: '+relative)
        if path.is_dir():
            if relative not in ('corpus', 'profiles'):
                raise ValueError('Unexpected fixture directory: '+relative)
        elif path.is_file():
            actual.add(relative)
        else:
            raise ValueError('Unexpected fixture entry: '+relative)
    expected = set(files) | {'manifest.json'}
    if actual != expected:
        raise ValueError('Fixture inventory differs from manifest; unexpected='+
                         ','.join(sorted(actual-expected))+'; missing='+','.join(sorted(expected-actual)))
    return corpus


def load_dataset(split, directory=DATA):
    if split not in ('development', 'heldout'):
        raise ValueError('Choose development or heldout; splits are never pooled')
    directory = Path(directory)
    manifest_bytes = (directory/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('version') != 'fieldwork-docqa-v1':
        raise ValueError('Unsupported dataset version')
    corpus = validate_inventory(directory, manifest)
    # Calibration checks the full inventory but never reads held-out case bytes.
    selected = f'{split}.json'
    verified = {}
    for name, expected in manifest['files'].items():
        if name in ('development.json', 'heldout.json') and name != selected:
            continue
        content = safe_path(directory, name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError('Dataset hash mismatch: '+name)
        verified[name] = content
    cases = json.loads(verified[selected])
    evidence = json.loads(verified['evidence.json'])
    texts = {Path(name).name: verified[name].decode('utf-8') for name in corpus}
    profiles = {}
    for profile, extra in manifest['profiles'].items():
        docs = dict(texts)
        for name in extra:
            if Path(name).name != name or name in docs:
                raise ValueError('Invalid or duplicate profile source')
            docs[name] = verified['profiles/'+name].decode('utf-8')
        profiles[profile] = docs
    all_docs = {name: text for docs in profiles.values() for name, text in docs.items()}
    for label, span in evidence.items():
        if span['source'] not in all_docs:
            raise ValueError('Unknown evidence source: '+label)
        tokens = all_docs[span['source']].split()
        start, end = span['start'], span['end']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(tokens):
            raise ValueError('Invalid evidence offsets: '+label)
        quote = span['quote'].split()
        matches = [i for i in range(len(tokens)) if tokens[i:i+len(quote)] == quote]
        if matches != [start] or tokens[start:end] != quote:
            raise ValueError('Missing, duplicate or stale evidence quote: '+label)
    if len(cases) != manifest['split_counts'][split] or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Invalid split count or duplicate case IDs')
    for case in cases:
        if case['category'] not in CATEGORIES or case['disposition'] not in ('answer', 'abstain'):
            raise ValueError('Invalid case category or disposition')
        if case['profile'] not in profiles or not case['question'].strip() or not case['rationale'].strip():
            raise ValueError('Invalid case profile, question or rationale')
        if case['disposition'] == 'answer' and not case['gold_evidence']:
            raise ValueError('Answerable cases require gold evidence')
        for key in ('gold_evidence', 'forbidden_evidence'):
            if len(case[key]) != len(set(case[key])):
                raise ValueError('Duplicate evidence labels')
            for label in case[key]:
                if label not in evidence or evidence[label]['source'] not in profiles[case['profile']]:
                    raise ValueError('Evidence unavailable in case profile')
    return dict(manifest=manifest, cases=cases, evidence=evidence, profiles=profiles,
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(), split=split)


def token_positions(spans):
    return {(s['source'], i) for s in spans for i in range(s['start'], s['end'])}


def chunk_positions(chunks):
    return {(c['source'], i) for c in chunks for i in range(c['word_start'], c['word_end'])}


def evidence_metrics(chunks, spans):
    gold = token_positions(spans)
    if not gold:
        return dict(token_recall=None, complete=None, mrr=None)
    covered = chunk_positions(chunks) & gold
    first = next((i for i, chunk in enumerate(chunks, 1) if chunk_positions([chunk]) & gold), None)
    return dict(token_recall=round(len(covered)/len(gold), 6), complete=covered == gold,
                mrr=round(1/first, 6) if first else 0)


def predict(index, question, baseline, policy):
    hits = index.search(question, k=3)
    if baseline == 'positive_score_extractive':
        check = dict(decision='answer' if hits else 'abstain', reason='positive_score' if hits else 'no_matching_evidence',
                     features=features(question, hits))
    elif baseline == 'lexical_gate':
        check = decide(question, hits, policy)
    else:
        raise ValueError('Unknown baseline')
    sources = hits if check['decision'] == 'answer' else []
    return dict(check, sources=sources, retrieved=hits,
                answer='\n\n'.join(f"[{h['id']}] {h['text']}" for h in sources))


def score_case(case, prediction, index, labels):
    spans = [labels[label] for label in case['gold_evidence']]
    forbidden = [labels[label] for label in case['forbidden_evidence']]
    sources = prediction['sources']
    answered = prediction['decision'] == 'answer'
    registry = {chunk['id']: chunk for chunk in index.chunks}
    provenance = None
    if answered:
        provenance = bool(sources) and prediction['answer'] == '\n\n'.join(f"[{h['id']}] {h['text']}" for h in sources)
        for source in sources:
            actual = registry.get(source['id'])
            provenance = provenance and actual is not None and all(source.get(k) == actual[k] for k in
                          ('source', 'word_start', 'word_end', 'text', 'source_sha256'))
    retrieved = evidence_metrics(prediction['retrieved'], spans)
    output = evidence_metrics(sources, spans)
    output_tokens = chunk_positions(sources)
    precision = len(output_tokens & token_positions(spans))/len(output_tokens) if output_tokens and spans else None
    forbidden_exposure = bool(output_tokens & token_positions(forbidden)) if forbidden else None
    failures = []
    if prediction['decision'] != case['disposition']:
        failures.append('false_answer' if answered else 'unnecessary_abstention')
    if answered and provenance is not True:
        failures.append('invalid_extractive_provenance')
    if answered and case['disposition'] == 'answer' and output['complete'] is not True:
        failures.append('incomplete_gold_evidence')
    if forbidden_exposure:
        failures.append('forbidden_instruction_exposure')
    return dict(id=case['id'], question=case['question'], category=case['category'], profile=case['profile'],
                expected=case['disposition'], predicted=prediction['decision'], reason=prediction['reason'],
                rationale=case['rationale'], gold_evidence=case['gold_evidence'],
                forbidden_evidence=case['forbidden_evidence'], features=prediction['features'],
                retrieved_ids=[h['id'] for h in prediction['retrieved']],
                returned_ids=[h['id'] for h in sources], retrieval=retrieved,
                output_evidence=output, extractive_provenance_valid=provenance,
                gold_evidence_token_precision=round(precision, 6) if precision is not None else None,
                forbidden_span_exposed=forbidden_exposure, failures=failures)


def ratio(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                rate=round(numerator/denominator, 6) if denominator else None)


def mean(values):
    values = [v for v in values if v is not None]
    return dict(eligible_cases=len(values), value=round(sum(values)/len(values), 6) if values else None)


def summarize(rows):
    answerable = [r for r in rows if r['expected'] == 'answer']
    abstain = [r for r in rows if r['expected'] == 'abstain']
    answered = [r for r in rows if r['predicted'] == 'answer']
    answered_answerable = [r for r in answered if r['expected'] == 'answer']
    retrieval = [r for r in rows if r['gold_evidence']]
    forbidden = [r for r in rows if r['forbidden_evidence']]
    false_answers = sum(r['predicted'] == 'answer' for r in abstain)
    false_abstentions = sum(r['predicted'] == 'abstain' for r in answerable)
    return dict(cases=len(rows),
        retrieval=dict(required_evidence_token_recall_at_3=mean(r['retrieval']['token_recall'] for r in retrieval),
                       complete_evidence_set_at_3=ratio(sum(r['retrieval']['complete'] is True for r in retrieval), len(retrieval)),
                       mrr=mean(r['retrieval']['mrr'] for r in retrieval)),
        decision_vs_gold_answerability=dict(correct_answers=len(answerable)-false_abstentions,
            false_answers=false_answers, correct_abstentions=len(abstain)-false_answers,
            unnecessary_abstentions=false_abstentions),
        abstention=dict(correct_abstention=ratio(len(abstain)-false_answers, len(abstain)),
                        unnecessary_abstention=ratio(false_abstentions, len(answerable)),
                        answer_coverage=ratio(len(answered), len(rows))),
        extractive_output=dict(exact_provenance=ratio(sum(r['extractive_provenance_valid'] is True for r in answered),len(answered)),
            complete_gold_evidence_when_answered=ratio(sum(r['output_evidence']['complete'] is True for r in answered_answerable),len(answered_answerable)),
            required_evidence_token_recall=mean(r['output_evidence']['token_recall'] for r in answered_answerable),
            gold_evidence_token_precision=mean(r['gold_evidence_token_precision'] for r in answered_answerable),
            forbidden_span_exposure=ratio(sum(r['forbidden_span_exposed'] is True for r in forbidden),len(forbidden)),
            semantic_factuality='NOT ASSESSED; exact extraction is provenance, not semantic answer correctness'))


def run_suite(split, policy, directory=DATA):
    data = load_dataset(split, directory)
    indices = {name: Index(documents=docs) for name, docs in data['profiles'].items()}
    baselines = {}
    for baseline in BASELINES:
        rows = [score_case(c, predict(indices[c['profile']], c['question'], baseline, policy),
                           indices[c['profile']], data['evidence']) for c in data['cases']]
        baselines[baseline] = dict(summary=summarize(rows),
            category_slices={c: summarize([r for r in rows if r['category'] == c]) for c in sorted(CATEGORIES)},
            profile_slices={p: summarize([r for r in rows if r['profile'] == p]) for p in sorted(indices)},
            failure_examples=[r for r in rows if r['failures']][:8], per_case=rows)
    return dict(dataset=data['manifest']['version'], split=split,
        manifest_sha256=data['manifest_sha256'], dataset_files=data['manifest']['files'],
        source_sha256={name:digest(ROOT/name) for name in ('lab/core.py','lab/abstention.py','lab/evaluation.py')},
        policy=policy, provenance=data['manifest']['provenance'], split_note=data['manifest']['split_note'],
        scope='Authored synthetic documentation QA; extractive baselines only. No LLM, human/model judge, agent or serving score.',
        baselines=baselines)


def calibrate(directory=DATA):
    # This entry point deliberately has no split argument.
    data = load_dataset('development', directory)
    indices = {name: Index(documents=docs) for name, docs in data['profiles'].items()}
    examples = [(case, indices[case['profile']].search(case['question'])) for case in data['cases']]
    candidates = []
    for score in (0.0, 0.10, 0.15, 0.20):
        for coverage in (0.0, 0.50, 0.75, 1.0):
            policy = dict(schema_version=1, stoplist_version=1, min_top_score=score, min_term_coverage=coverage,
                          calibrated_on='development', dataset_version=data['manifest']['version'])
            decisions = [(c['disposition'], decide(c['question'], hits, policy)['decision']) for c, hits in examples]
            false_answers = sum(expected == 'abstain' and actual == 'answer' for expected, actual in decisions)
            false_abstentions = sum(expected == 'answer' and actual == 'abstain' for expected, actual in decisions)
            candidates.append(dict(policy=policy, false_answers=false_answers,
                unnecessary_abstentions=false_abstentions, objective=2*false_answers+false_abstentions))
    selected = min(candidates, key=lambda c:(c['objective'], -c['policy']['min_term_coverage'], -c['policy']['min_top_score']))
    return dict(dataset=data['manifest']['version'], split='development', cases=len(examples),
                manifest_sha256=data['manifest_sha256'], selected=selected, candidates=candidates,
                objective='2 * false_answers + unnecessary_abstentions; ties prefer higher coverage then score',
                limitation='Authored 2:1 error tradeoff, not measured user utility. Held-out cases not read.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    tuning = sub.add_parser('calibrate')
    tuning.add_argument('--policy-output', required=True)
    tuning.add_argument('--report-output', required=True)
    suite = sub.add_parser('run')
    suite.add_argument('--split', choices=('development','heldout'), required=True)
    suite.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'calibrate':
        report = calibrate()
        write_json(args.policy_output, report['selected']['policy'])
        write_json(args.report_output, report)
        print(json.dumps(report['selected'], sort_keys=True))
    else:
        report = run_suite(args.split, load_policy())
        write_json(args.output, report)
        print(json.dumps({b:r['summary'] for b,r in report['baselines'].items()}, indent=2))


if __name__ == '__main__':
    main()
