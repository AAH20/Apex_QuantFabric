# SPDX-License-Identifier: Apache-2.0
"""Recheck hashes and replay verdicts. An unsigned manifest is not custody."""
import argparse
import json
from itertools import zip_longest
from pathlib import Path
from adapters.interchange import read_events, wire
from qualification.check import check
from qualification.acceptance import evaluate
from qualification.run import digest


def verify(directory):
    root=Path(directory).resolve()
    manifest=json.loads((root/'manifest.json').read_text())
    for name,expected in manifest['sha256'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path)!=expected:
            raise ValueError(f'file missing, outside bundle or altered: {name}')
    if 'report.json' not in manifest['sha256']:
        raise ValueError('report missing from manifest')
    report=json.loads((root/'report.json').read_text())
    # Source drift changes the checker being trusted for reproduction.
    source_root=Path(__file__).resolve().parents[1]
    for name,expected in report['source_sha256'].items():
        path=(source_root/name).resolve()
        if not path.is_relative_to(source_root) or not path.is_file() or digest(path)!=expected:
            raise ValueError(f'source unavailable or changed: {name}')
    checked_inputs=set()
    for entry in report['positive']+report['controls']:
        for field in ('events','trace'):
            if entry[field] not in manifest['sha256']:
                raise ValueError('unregistered evidence reference')
        if entry['events'] not in checked_inputs:
            input_path=(root/entry['events']).with_name('input.tsv')
            if str(input_path.relative_to(root)) not in manifest['sha256']:
                raise ValueError('native input is not registered')
            with open(input_path,encoding='utf-8') as native_input:
                for expected_wire,actual_wire in zip_longest((wire(e) for e in read_events(root/entry['events'])),native_input):
                    if expected_wire!=actual_wire:
                        raise ValueError('JSON events differ from native input')
            checked_inputs.add(entry['events'])
        actual=check(root/entry['events'],root/entry['trace'])
        # Replay checks semantic result and populations, not remeasured host time.
        for field in ('verdict','checked_events','mismatches','qualified_valid_signals','reference_dispositions'):
            if actual[field]!=entry[field]:
                raise ValueError(f'report mismatch: {field}')
        if entry in report['positive'] and evaluate(actual,report['acceptance_limits'])!=entry['release_acceptance']:
            raise ValueError('release acceptance mismatch')
    expected='pass' if report['positive'] and all(r['verdict']=='pass' for r in report['positive']) and all(r['verdict']=='fail' for r in report['controls']) else 'fail'
    if report['verdict']!=expected:
        raise ValueError('aggregate verdict mismatch')
    release='pass' if all(r['release_acceptance']['verdict']=='pass' for r in report['positive']) else 'fail'
    if report['release_verdict']!=release:
        raise ValueError('aggregate release mismatch')
    if report['positive_checked_transitions']!=sum(r['checked_events'] for r in report['positive']):
        raise ValueError('aggregate transition count mismatch')
    return {'verdict':expected,'checked_runs':len(report['positive'])+len(report['controls']),
            'authenticity':'unsigned manifest; no origin authentication'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.directory),indent=2))


if __name__=='__main__':
    main()
