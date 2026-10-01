# SPDX-License-Identifier: Apache-2.0
import math
from collections import Counter
from itertools import zip_longest
from adapters.interchange import read_events
from oracle.model import Reference


def percentile(histogram, fraction):
    count = sum(histogram.values())
    if not count:
        return None
    target = max(1,math.ceil(count*fraction))
    cumulative = 0
    for value, frequency in sorted(histogram.items()):
        cumulative += frequency
        if cumulative >= target:
            return value


def invariant(row):
    entries = [] if row[10] == '-' else [tuple(map(int, x.split(':'))) for x in row[10].split(';')]
    if len(entries)>16 or len({x[0] for x in entries})!=len(entries):
        raise ValueError('slot or unique action invariant')
    units = Counter()
    for identifier, instrument, quantity, uncertain in entries:
        if not 1<=identifier<=256 or not 0<=instrument<8 or not 1<=quantity<=16 or uncertain not in (0,1):
            raise ValueError('reservation bounds')
        units[instrument] += quantity
    if any(x>16 for x in units.values()):
        raise ValueError('instrument capacity invariant')


def check(events_path, trace_path, max_examples=8):
    oracle = Reference()
    counts = Counter()
    timings = Counter()
    failures = []
    mismatches = 0
    total = 0
    predictions = 0
    duplicates = 0
    valid_signals = 0
    score_error_max = 0.0
    sentinel = object()
    with open(trace_path, encoding='utf-8') as trace:
        for index, pair in enumerate(zip_longest(read_events(events_path), trace, fillvalue=sentinel)):
            event, line = pair
            total += 1
            reason = None
            if event is sentinel or line is sentinel:
                reason = 'missing input disposition or extra trace row'
            else:
                expected = oracle.apply(event,index)
                counts[expected[1]] += 1
                if event['kind'] in ('PREDICTION','DROPPED'):
                    predictions += 1
                    duplicates += expected[1]=='DUPLICATE'
                valid_signals += expected[2]=='1'
                row = line.rstrip('\n').split('\t')
                try:
                    if len(row)!=12:
                        raise ValueError('trace columns')
                    ns=int(row[11])
                    if ns<0:
                        raise ValueError('negative timing')
                    invariant(row)
                    if any(row[k]!=expected[k] for k in range(11) if k!=4):
                        raise ValueError('disposition, authority or full-state mismatch')
                    if expected[4] is None:
                        if row[4]!='-':
                            raise ValueError('unexpected score')
                    else:
                        score=float(row[4])
                        ref=expected[4]
                        if math.isfinite(ref):
                            if not math.isfinite(score) or abs(score-ref)>1e-6:
                                raise ValueError('score tolerance')
                            score_error_max=max(score_error_max,abs(score-ref))
                        elif not (math.isnan(ref) and math.isnan(score)) and ref!=score:
                            raise ValueError('nonfinite score mismatch')
                    timings[ns]+=1
                except (ValueError,OverflowError) as error:
                    reason=str(error)
            if reason:
                mismatches+=1
                if len(failures)<max_examples:
                    failures.append({'index':index,'reason':reason,'event':None if event is sentinel else event})
    if total==0:
        mismatches+=1
        failures.append({'reason':'empty qualification population'})
    return dict(verdict='pass' if mismatches==0 else 'fail', checked_events=total,
                mismatches=mismatches, failure_examples=failures, reference_dispositions=dict(sorted(counts.items())),
                offered_prediction_deliveries=predictions, duplicate_prediction_deliveries=duplicates,
                qualified_valid_signals=valid_signals if mismatches==0 else None,
                reference_valid_signals=valid_signals, reference_admitted_actions=counts['ADMITTED'],
                reference_unresolved_reservations_at_end=len(oracle.reservations),
                maximum_absolute_score_difference=score_error_max,
                kernel_call_ns={'population':sum(timings.values()),'p50':percentile(timings,.5),
                                'p99':percentile(timings,.99),'p99_9':percentile(timings,.999),
                                'observed_max':max(timings) if timings else None,
                                'boundary':'instrumented step call only; excludes parse, queue, I/O, prediction and report; no wire latency'})
