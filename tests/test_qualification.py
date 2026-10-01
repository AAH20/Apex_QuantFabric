# SPDX-License-Identifier: Apache-2.0
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from adapters.completions import CompletionQueue
from adapters.interchange import make, read_events, validate, wire
from economics.cost import accepted_cost
from oracle.model import Reference
from qualification.check import check
from qualification.acceptance import evaluate
from qualification.run import ROOT, MUTANTS, digest, execute, write_inputs
from qualification.verify import verify
from research.fixtures import directed, workload


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.events=self.root/'events.jsonl'
        self.input=self.root/'input.tsv'
        self.trace=self.root/'baseline.tsv'

    def tearDown(self):
        self.temp.cleanup()

    def run_case(self,events,variant='baseline'):
        write_inputs(events,self.events,self.input)
        return execute(ROOT/'build/quantfabric',variant,self.events,self.input,self.trace)

    def test_directed_dispositions(self):
        result=self.run_case(directed())
        self.assertEqual(result['verdict'],'pass')
        expected={'ADMITTED','CAPACITY_UNITS','CAPACITY_SLOTS','DUPLICATE','EXPIRED','FEED_BLOCKED',
                  'FEED_GAP','MARKET','MARKET_DUPLICATE','NO_SIGNAL','NUMERICAL','QUEUE_DROPPED',
                  'RELEASED','RESET','RESET_BLOCKED','RESET_OLD','STALE_WATERMARK','UNKNOWN_ACTION',
                  'UNRESOLVED','WRONG_SESSION','WRONG_VERSION','ADVANCE'}
        self.assertEqual(set(result['reference_dispositions']),expected)

    def test_random_matrix(self):
        for seed in (0,7,19,1001):
            with self.subTest(seed=seed):
                self.assertEqual(self.run_case(workload(3000,seed))['verdict'],'pass')

    def test_equivalent_candidate(self):
        result=self.run_case(workload(2000,41),'equivalent')
        self.assertEqual(result['verdict'],'pass')
        self.assertGreater(result['maximum_absolute_score_difference'],0)

    def test_all_unsafe_variants(self):
        for variant in MUTANTS:
            with self.subTest(variant=variant):
                self.assertEqual(self.run_case(directed(),variant)['verdict'],'fail')

    def test_near_threshold_numeric_similarity_is_insufficient(self):
        events=[make('MARKET',0,sequence=1,score=75),
                make('PREDICTION',1,id=1,watermark=1,model=1,policy=1,config=1,
                     expiry=2,score=.5-5e-9,quantity=1)]
        self.assertEqual(self.run_case(events)['verdict'],'pass')
        self.assertEqual(self.run_case(events,'equivalent')['verdict'],'fail')

    def test_expiry_boundary(self):
        e=[make('MARKET',0,sequence=1,score=75),make('PREDICTION',1,id=1,watermark=1,
                model=1,policy=1,config=1,expiry=1,score=.5,quantity=1)]
        r=self.run_case(e)
        self.assertEqual(r['reference_admitted_actions'],1)

    def test_uncertain_does_not_release(self):
        e=[make('MARKET',0,sequence=1,score=80),make('PREDICTION',1,id=1,watermark=1,
                model=1,policy=1,config=1,expiry=9,score=.6,quantity=16),
           make('UNCERTAIN',2,action=1),make('RESET',3,session=2)]
        r=self.run_case(e)
        self.assertEqual(r['verdict'],'pass')
        self.assertEqual(r['reference_unresolved_reservations_at_end'],1)
        self.assertEqual(r['reference_dispositions']['RESET_BLOCKED'],1)

    def test_old_session_cannot_release(self):
        e=[make('RESET',0,session=2),make('MARKET',1,session=2,sequence=1,score=80),
           make('PREDICTION',2,session=2,id=1,watermark=1,model=1,policy=1,config=1,expiry=3,score=.6,quantity=1),
           make('RELEASE',3,session=1,action=1)]
        self.assertEqual(self.run_case(e)['reference_unresolved_reservations_at_end'],1)

    def test_prediction_identity_edges(self):
        e=[make('MARKET',0,sequence=1,score=80)]
        for identifier in (1,64,65,128,129,192,193,256):
            e.extend([make('PREDICTION',1,id=identifier,watermark=1,model=1,policy=1,config=1,expiry=2,score=.6,quantity=1),
                      make('RELEASE',1,action=identifier)])
        self.assertEqual(self.run_case(e)['verdict'],'pass')

    def test_feed_gap_blocks_following_correction(self):
        e=[make('MARKET',0,sequence=2,score=80),make('MARKET',1,sequence=1,score=80)]
        r=self.run_case(e)
        self.assertEqual(r['reference_dispositions'],{'FEED_BLOCKED':1,'FEED_GAP':1})

    def test_nonfinite_result_policy(self):
        for score in ('nan','inf','-inf'):
            with self.subTest(score=score):
                e=[make('MARKET',0,sequence=1,score=80),make('PREDICTION',1,id=1,watermark=1,
                   model=1,policy=1,config=1,expiry=2,score=score,quantity=1)]
                self.assertEqual(self.run_case(e)['reference_dispositions']['NUMERICAL'],1)

    def test_missing_trace(self):
        self.run_case(directed())
        rows=self.trace.read_text().splitlines(keepends=True)
        self.trace.write_text(''.join(rows[:-1]))
        self.assertEqual(check(self.events,self.trace)['verdict'],'fail')

    def test_extra_trace(self):
        self.run_case(directed())
        text=self.trace.read_text()
        self.trace.write_text(text+text.splitlines(keepends=True)[-1])
        self.assertEqual(check(self.events,self.trace)['verdict'],'fail')

    def test_negative_timing(self):
        self.run_case(directed())
        rows=self.trace.read_text().splitlines()
        parts=rows[0].split('\t'); parts[-1]='-1'; rows[0]='\t'.join(parts)
        self.trace.write_text('\n'.join(rows)+'\n')
        self.assertEqual(check(self.events,self.trace)['verdict'],'fail')

    def test_full_state_tamper(self):
        self.run_case(directed())
        rows=self.trace.read_text().splitlines()
        parts=rows[0].split('\t'); parts[7]='0,0,0,0,0,0,0,0'; rows[0]='\t'.join(parts)
        self.trace.write_text('\n'.join(rows)+'\n')
        self.assertEqual(check(self.events,self.trace)['verdict'],'fail')

    def test_empty_population(self):
        self.assertEqual(self.run_case([])['verdict'],'fail')

    def test_native_rejects_raw_bad_integer(self):
        raw=wire(make('MARKET',0,sequence=1,score=80)).replace('\t0\t1\t','\t-1\t1\t',1)
        r=subprocess.run([str(ROOT/'build/quantfabric')],input=raw,text=True,capture_output=True)
        self.assertEqual(r.returncode,2)

    def test_native_rejects_unknown_kind(self):
        r=subprocess.run([str(ROOT/'build/quantfabric')],input=wire(make('ADVANCE',0)).replace('ADVANCE','UNKNOWN'),text=True,capture_output=True)
        self.assertEqual(r.returncode,2)

    def test_native_rejects_regressed_time(self):
        raw=wire(make('ADVANCE',2))+wire(make('ADVANCE',1))
        r=subprocess.run([str(ROOT/'build/quantfabric')],input=raw,text=True,capture_output=True)
        self.assertEqual(r.returncode,2)

    def test_verifier_rejects_altered_bundle(self):
        report={'positive':[], 'controls':[], 'source_sha256':{},'verdict':'pass'}
        (self.root/'report.json').write_text(json.dumps(report))
        manifest={'sha256':{'report.json':digest(self.root/'report.json')}}
        (self.root/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'aggregate'):
            verify(self.root)
        (self.root/'report.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'altered'):
            verify(self.root)

    def test_verifier_rejects_path_escape(self):
        (self.root/'manifest.json').write_text(json.dumps({'sha256':{'../outside':'fake'}}))
        with self.assertRaises(ValueError):
            verify(self.root)


class ContractTests(unittest.TestCase):
    def test_invalid_integer_types(self):
        for value in (-1,2147483648,True,1.5):
            with self.subTest(value=value),self.assertRaises(ValueError):
                make('ADVANCE',value)

    def test_instrument_bounds(self):
        with self.assertRaises(ValueError):
            make('MARKET',0,instrument=8,sequence=1,score=80)

    def test_prediction_id_bounds(self):
        for identifier in (0,257):
            with self.assertRaises(ValueError):
                make('PREDICTION',0,id=identifier,quantity=1)

    def test_unused_fields(self):
        with self.assertRaises(ValueError):
            make('ADVANCE',0,model=1)

    def test_market_requires_integral_price(self):
        for score in ('nan',1.5,0):
            with self.assertRaises(ValueError):
                make('MARKET',0,sequence=1,score=score)

    def test_extra_fields(self):
        e=make('ADVANCE',0); e['surprise']=1
        with self.assertRaises(ValueError):
            validate(e)

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.jsonl'; p.write_text('{"kind":"ADVANCE","kind":"RESET"}\n')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                list(read_events(p))

    def test_queue_overflow_and_reordering(self):
        q=CompletionQueue(2)
        def e(i):
            return make('PREDICTION',0,id=i,quantity=1)
        self.assertIsNone(q.submit(e(1),3))
        self.assertIsNone(q.submit(e(2),2))
        self.assertEqual(q.submit(e(3),1)['kind'],'DROPPED')
        self.assertEqual([x['id'] for x in q.drain(4,reverse_ready=True)],[1,2])
        self.assertEqual(q.pending,[])

    def test_queue_time_regression(self):
        q=CompletionQueue(); q.drain(2)
        with self.assertRaises(ValueError):
            q.submit(make('PREDICTION',1,id=1,quantity=1),3)

    def test_queue_limits(self):
        for capacity in (0,9,True):
            with self.assertRaises(ValueError):
                CompletionQueue(capacity)

    def test_zero_accepted_cost_is_undefined(self):
        self.assertIsNone(accepted_cost(100,0))
        self.assertEqual(accepted_cost(100,20),5)

    def test_invalid_costs(self):
        for cost in (-1,math.inf,math.nan,True):
            with self.assertRaises(ValueError):
                accepted_cost(cost,10)

    def test_profile_identity(self):
        profile=json.loads((ROOT/'contracts/signal-reservation-v0.1.json').read_text())
        self.assertEqual(profile['profile'],'apex.quant.signal-reservation@0.1')
        self.assertEqual(profile['reservation_slots'],16)
        self.assertEqual(profile['instruments'],8)

    def test_acceptance_budget_can_reject_correct_candidate(self):
        result={'verdict':'pass','qualified_valid_signals':20,'kernel_call_ns':{'p99':100}}
        limits={'minimum_valid_signals':10,'maximum_kernel_p99_ns':50}
        self.assertEqual(evaluate(result,limits)['verdict'],'fail')
        limits['maximum_kernel_p99_ns']=200
        self.assertEqual(evaluate(result,limits)['verdict'],'pass')

    def test_acceptance_missing_evidence(self):
        self.assertEqual(evaluate({'verdict':'inconclusive'}, {})['verdict'],'inconclusive')


if __name__=='__main__':
    unittest.main()
