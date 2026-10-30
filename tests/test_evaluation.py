import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.abstention import decide, features, load_policy
from lab.core import Index
from lab.evaluation import (DATA, calibrate, evidence_metrics, load_dataset, predict,
                            ratio, score_case, summarize, token_positions)


class EvidenceScoringTests(unittest.TestCase):
    def setUp(self):
        self.index = Index(documents={'a.md':'alpha beta gamma delta epsilon zeta',
                                      'b.md':'other unrelated document'})
        self.label = {'fact':dict(source='a.md', start=1, end=3, quote='beta gamma')}
        self.case = dict(id='toy', question='beta gamma', category='answerable', profile='base',
                         disposition='answer', rationale='Toy exact evidence span',
                         gold_evidence=['fact'], forbidden_evidence=[])
        self.policy = dict(min_top_score=0, min_term_coverage=0)

    def row(self, prediction=None, case=None):
        return score_case(case or self.case, prediction or predict(self.index,'beta gamma','positive_score_extractive',self.policy), self.index,self.label)

    def test_partial_span_is_fractional_recall_not_success(self):
        r = evidence_metrics([dict(source='a.md', word_start=0, word_end=2)], list(self.label.values()))
        self.assertEqual(r, dict(token_recall=0.5, complete=False, mrr=1))

    def test_union_of_overlapping_chunks_does_not_double_count(self):
        chunks = [dict(source='a.md',word_start=0,word_end=2),dict(source='a.md',word_start=1,word_end=4)]
        self.assertEqual(evidence_metrics(chunks,list(self.label.values()))['token_recall'],1)

    def test_multi_source_evidence_requires_both_sources(self):
        spans = [self.label['fact'],dict(source='b.md',start=0,end=2)]
        self.assertFalse(evidence_metrics(self.index.search('beta'), spans)['complete'])

    def test_mrr_uses_rank_and_null_for_no_gold(self):
        chunks = [dict(source='b.md',word_start=0,word_end=3),dict(source='a.md',word_start=0,word_end=6)]
        self.assertEqual(evidence_metrics(chunks,list(self.label.values()))['mrr'],0.5)
        self.assertIsNone(evidence_metrics(chunks,[])['token_recall'])

    def test_citation_presence_does_not_validate_forged_text(self):
        p = predict(self.index,'beta gamma','positive_score_extractive',self.policy)
        p['sources'][0]['text'] = 'invented unsupported claim'
        p['answer'] = f"[{p['sources'][0]['id']}] invented unsupported claim"
        row = self.row(p)
        self.assertFalse(row['extractive_provenance_valid'])
        self.assertIn('invalid_extractive_provenance',row['failures'])

    def test_modified_answer_and_unknown_citation_fail_provenance(self):
        p = predict(self.index,'beta gamma','positive_score_extractive',self.policy)
        p['answer'] += ' invented'
        self.assertFalse(self.row(p)['extractive_provenance_valid'])
        p = predict(self.index,'beta gamma','positive_score_extractive',self.policy)
        p['sources'][0]['id'] = 'unknown:1'
        self.assertFalse(self.row(p)['extractive_provenance_valid'])

    def test_exact_provenance_is_not_full_relevance(self):
        row = self.row()
        self.assertTrue(row['extractive_provenance_valid'])
        self.assertTrue(row['output_evidence']['complete'])
        self.assertAlmostEqual(row['gold_evidence_token_precision'],2/6,places=6)

    def test_forbidden_source_span_is_measured_even_with_valid_provenance(self):
        c = dict(self.case, forbidden_evidence=['fact'])
        row = self.row(case=c)
        self.assertTrue(row['extractive_provenance_valid'])
        self.assertTrue(row['forbidden_span_exposed'])
        self.assertIn('forbidden_instruction_exposure',row['failures'])

    def test_confusion_counts_and_denominators(self):
        answer = self.row()
        false_answer = dict(answer, expected='abstain')
        abstained = dict(answer, predicted='abstain',extractive_provenance_valid=None)
        summary = summarize([answer,false_answer,abstained])
        self.assertEqual(summary['decision_vs_gold_answerability'],dict(correct_answers=1,false_answers=1,correct_abstentions=0,unnecessary_abstentions=1))
        self.assertEqual(summary['abstention']['unnecessary_abstention'],ratio(1,2))
        self.assertEqual(summary['abstention']['answer_coverage'],ratio(2,3))
        self.assertIsNone(summarize([])['abstention']['correct_abstention']['rate'])


class GateTests(unittest.TestCase):
    def test_low_coverage_abstains_without_claiming_semantic_judgment(self):
        hits = [dict(score=.8,text='vLLM serving metrics')]
        r = decide('vLLM refund policy',hits,dict(min_top_score=.2,min_term_coverage=.5))
        self.assertEqual(r['decision'],'abstain')
        self.assertEqual(r['reason'],'low_term_coverage')

    def test_no_terms_and_no_evidence_always_abstain(self):
        self.assertEqual(decide('what is it', [dict(score=.8,text='anything')], dict(min_top_score=0,min_term_coverage=0))['decision'],'abstain')
        self.assertEqual(decide('vLLM',[],dict(min_top_score=0,min_term_coverage=0))['decision'],'abstain')

    def test_similarity_boundary_is_inclusive(self):
        p = dict(min_top_score=.2,min_term_coverage=1)
        self.assertEqual(decide('alpha',[dict(score=.2,text='alpha')],p)['decision'],'answer')
        self.assertEqual(decide('alpha',[dict(score=.1999,text='alpha')],p)['decision'],'abstain')

    def test_actual_app_abstains_on_refund_and_separates_diagnostics(self):
        r = Index().answer('What is the vLLM subscription refund policy?')
        self.assertEqual(r['decision'],'abstain')
        self.assertEqual(r['sources'],[])
        self.assertTrue(r['retrieval_evidence'])
        self.assertNotIn('[serving:',r['answer'])

    def test_default_policy_matches_frozen_calibration(self):
        report = json.loads((DATA.parent/'reports/v1-calibration.json').read_text())
        self.assertEqual(load_policy(),report['selected']['policy'])

    def test_feature_order_is_deterministic(self):
        self.assertEqual(features('gamma beta beta',[dict(score=.3,text='beta gamma')])['content_terms'],['beta','gamma'])

    def test_scored_gate_matches_app_outputs_on_development_cases(self):
        data=load_dataset('development')
        for case in data['cases']:
            index=Index(documents=data['profiles'][case['profile']])
            actual=index.answer(case['question'])
            scored=predict(index,case['question'],'lexical_gate',load_policy())
            self.assertEqual(actual['decision'],scored['decision'])
            self.assertEqual(actual['support_check']['reason'],scored['reason'])
            self.assertEqual(actual['sources'],scored['sources'])
            if scored['decision']=='answer':
                self.assertEqual(actual['answer'],scored['answer'])


class DatasetValidationTests(unittest.TestCase):
    def test_public_split_sizes_categories_and_disjoint_ids(self):
        # Structural validation only: no held-out predictions or policy tuning.
        dev=load_dataset('development');held=load_dataset('heldout')
        self.assertEqual(len(dev['cases']),30)
        self.assertEqual(len(held['cases']),20)
        self.assertFalse({c['id'] for c in dev['cases']} & {c['id'] for c in held['cases']})
        expected={'answerable':(16,10),'unanswerable':(8,4),'ambiguous':(2,2),'conflicting':(2,2),'adversarial':(2,2)}
        for category,(a,b) in expected.items():
            self.assertEqual(sum(c['category']==category for c in dev['cases']),a)
            self.assertEqual(sum(c['category']==category for c in held['cases']),b)

    def test_calibration_does_not_read_heldout_file(self):
        original=Path.read_bytes
        original_text=Path.read_text
        def guarded_bytes(path,*a,**kw):
            if path.name=='heldout.json':raise AssertionError('Held-out file read by calibration')
            return original(path,*a,**kw)
        def guarded_text(path,*a,**kw):
            if path.name=='heldout.json':raise AssertionError('Held-out file read by calibration')
            return original_text(path,*a,**kw)
        with patch.object(Path,'read_bytes',guarded_bytes),patch.object(Path,'read_text',guarded_text):
            r=calibrate()
        self.assertEqual(r['cases'],30)
        self.assertEqual(len(r['candidates']),16)
        self.assertEqual(r['selected']['policy'],load_policy())

    def test_corpus_tampering_fails_before_scoring(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(DATA,Path(d)/'data')
            p=Path(d)/'data/corpus/agents.md'
            p.write_text(p.read_text()+' changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                load_dataset('development',Path(d)/'data')

    def test_stale_quote_rejected_even_with_updated_manifest_hash(self):
        import hashlib
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'data'
            shutil.copytree(DATA,root)
            labels=json.loads((root/'evidence.json').read_text())
            labels['agent-tools']['quote']='This statement does not exist.'
            (root/'evidence.json').write_text(json.dumps(labels))
            manifest=json.loads((root/'manifest.json').read_text())
            manifest['files']['evidence.json']=hashlib.sha256((root/'evidence.json').read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'stale evidence'):
                load_dataset('development',root)

    def test_no_pooled_split(self):
        with self.assertRaises(ValueError):
            load_dataset('all')


if __name__=='__main__':
    unittest.main()
