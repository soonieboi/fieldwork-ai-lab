"""Conservative lexical baseline. This does not establish semantic sufficiency."""
import json
import re
from pathlib import Path

# Versioned function words only; no evaluation IDs, labels, profiles or questions.
QUESTION_WORDS = frozenset('what how where when why which who much many explain describe please tell me do does did would could should according'.split())
BASE_WORDS = frozenset('a an the of to and or in is it this that for with how what does can on from are as by at'.split())
POLICY_PATH = Path(__file__).with_name('abstention-policy.json')


def load_policy(path=POLICY_PATH):
    policy = json.loads(Path(path).read_text(encoding='utf-8'))
    if policy.get('schema_version') != 1 or policy.get('stoplist_version') != 1:
        raise ValueError('Unsupported abstention policy version')
    for key in ('min_top_score', 'min_term_coverage'):
        if type(policy.get(key)) not in (int, float) or not 0 <= policy[key] <= 1:
            raise ValueError('Invalid lexical policy threshold')
    return policy


def features(question, hits):
    terms = set(re.findall(r'[a-z0-9]+', question.lower())) - BASE_WORDS - QUESTION_WORDS
    available = set(re.findall(r'[a-z0-9]+', ' '.join(h['text'] for h in hits).lower()))
    matched = terms & available
    return dict(top_score=hits[0]['score'] if hits else 0,
                content_terms=sorted(terms), matched_terms=sorted(matched),
                term_coverage=round(len(matched)/len(terms), 12) if terms else 0)


def decide(question, hits, policy):
    values = features(question, hits)
    if not hits:
        reason = 'no_matching_evidence'
    elif not values['content_terms']:
        reason = 'no_content_terms'
    elif values['top_score'] < policy['min_top_score']:
        reason = 'low_similarity'
    elif values['term_coverage'] < policy['min_term_coverage']:
        reason = 'low_term_coverage'
    else:
        reason = 'lexical_gate_passed'
    return dict(decision='answer' if reason == 'lexical_gate_passed' else 'abstain',
                reason=reason, features=values,
                limitation='Lexical heuristic only; not semantic support, conflict detection, or injection defense.')
