# SPDX-License-Identifier: Apache-2.0
"""Produce reproducible native qualification, including unsafe controls."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from adapters.interchange import read_events, wire
from economics.cost import accepted_cost
from qualification.check import check
from qualification.acceptance import evaluate
from research.fixtures import directed, workload

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = ['stale_accept','expiry_accept','wrong_session','release_uncertain',
           'ignore_capacity','double_commit','threshold_shift','numerical_accept','late_result']


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def write_inputs(events, events_path, wire_path):
    with open(events_path,'w',encoding='utf-8') as jsonl, open(wire_path,'w',encoding='utf-8') as tsv:
        for event in events:
            jsonl.write(json.dumps(event,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n')
            tsv.write(wire(event))


def execute(binary, variant, events_path, wire_path, trace_path):
    started=time.perf_counter()
    with open(wire_path,'rb') as source, open(trace_path,'wb') as target:
        result=subprocess.run([str(binary),variant],stdin=source,stdout=target,stderr=subprocess.PIPE)
    wall=time.perf_counter()-started
    if result.returncode:
        return dict(verdict='inconclusive',native_returncode=result.returncode,
                    error=result.stderr.decode(errors='replace')[:2000],native_replay_wall_seconds=wall)
    checked=check(events_path,trace_path)
    checked['native_replay_wall_seconds']=wall
    checked['wall_boundary']='native process, TSV parse, step instrumentation, serialization and local file I/O; excludes fixture and independent checker'
    return checked


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events',type=int,default=5000,help='exact events per seed, including directed controls')
    parser.add_argument('--seeds',type=int,nargs='+',default=[7])
    parser.add_argument('--controls',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'evidence/runs/demo')
    parser.add_argument('--allocated-cost',type=float,default=None,help='total declared cost in user-defined currency for all positive experiments')
    parser.add_argument('--cost-currency',default='unspecified')
    parser.add_argument('--minimum-valid-signals',type=int,default=1)
    parser.add_argument('--maximum-kernel-p99-ns',type=int,default=None,help='instrumented step-only ceiling, not application or wire latency')
    args=parser.parse_args(argv)
    if args.events < len(directed()) or len(set(args.seeds))!=len(args.seeds):
        parser.error('population too small or repeated seeds')
    if args.minimum_valid_signals<0 or (args.maximum_kernel_p99_ns is not None and args.maximum_kernel_p99_ns<0):
        parser.error('invalid acceptance bounds')
    if args.allocated_cost is not None:
        accepted_cost(args.allocated_cost,0)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    binary=ROOT/'build/quantfabric'
    if not binary.exists():
        parser.error('build native kernel with make build first')
    source_ids={str(p.relative_to(ROOT)):digest(p) for folder in ['core','contracts','oracle','qualification','research','adapters','economics']
                for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.cpp','.json')}
    build_record=json.loads((ROOT/'build/metadata.json').read_text())
    if build_record['source_sha256']!=digest(ROOT/'core/main.cpp') or build_record['binary_sha256']!=digest(binary):
        raise ValueError('native source/binary changed; rebuild before qualification')
    report=dict(profile='apex.quant.signal-reservation@0.1',status='synthetic-native-qualification',
                environment=dict(os=platform.platform(),machine=platform.machine(),python=sys.version.split()[0],
                                 binary_sha256=digest(binary),build_record=build_record),
                source_sha256=source_ids,positive=[],controls=[],hardware={
                    'CPU':'native workstation only','CUDA':'unimplemented/unqualified','NIC_DPU':'unimplemented/unqualified',
                    'FPGA_ASIC':'unimplemented/unqualified','STAC':'not an official STAC workload'},
                authenticity='local digests and replay; no signatures or authenticated chain of custody')
    report['acceptance_limits']={'minimum_valid_signals':args.minimum_valid_signals,'maximum_kernel_p99_ns':args.maximum_kernel_p99_ns}
    for seed in args.seeds:
        directory=output/f'seed-{seed}'
        directory.mkdir()
        events_path=directory/'events.jsonl'
        wire_path=directory/'input.tsv'
        write_inputs(workload(args.events,seed),events_path,wire_path)
        for variant in ['baseline','equivalent']:
            trace_path=directory/f'{variant}.tsv'
            result=execute(binary,variant,events_path,wire_path,trace_path)
            result.update(seed=seed,variant=variant,events=str(events_path.relative_to(output)),trace=str(trace_path.relative_to(output)))
            result['release_acceptance']=evaluate(result,report['acceptance_limits'])
            report['positive'].append(result)
            print(f"seed={seed} variant={variant}: {result['verdict']} ({result.get('checked_events',0)} events)",flush=True)
    if args.controls:
        directory=output/'controls'
        directory.mkdir()
        events_path=directory/'events.jsonl'
        wire_path=directory/'input.tsv'
        write_inputs(directed(),events_path,wire_path)
        clean_trace=directory/'baseline.tsv'
        clean=execute(binary,'baseline',events_path,wire_path,clean_trace)
        if clean['verdict']!='pass':
            raise RuntimeError('control reference did not qualify')
        for variant in MUTANTS:
            trace_path=directory/f'{variant}.tsv'
            result=execute(binary,variant,events_path,wire_path,trace_path)
            result.update(control=variant,expected='fail',events=str(events_path.relative_to(output)),trace=str(trace_path.relative_to(output)))
            report['controls'].append(result)
        lines=clean_trace.read_text().splitlines(keepends=True)
        for name,mutated in [('trace_tamper',[lines[0].replace('\tMARKET\t','\tADMITTED\t')]+lines[1:]),
                             ('trace_missing',lines[:-1]),('trace_extra',lines+[lines[-1]])]:
            trace_path=directory/f'{name}.tsv'
            trace_path.write_text(''.join(mutated))
            result=check(events_path,trace_path)
            result.update(control=name,expected='fail',events=str(events_path.relative_to(output)),trace=str(trace_path.relative_to(output)))
            report['controls'].append(result)
        print('negative controls: '+', '.join(f"{r['control']}={r['verdict']}" for r in report['controls']),flush=True)
    qualified=all(r['verdict']=='pass' for r in report['positive'])
    controls_ok=all(r['verdict']=='fail' for r in report['controls'])
    report['verdict']='pass' if qualified and controls_ok else 'fail'
    report['release_verdict']='pass' if all(r['release_acceptance']['verdict']=='pass' for r in report['positive']) else 'fail'
    report['positive_checked_transitions']=sum(r.get('checked_events',0) for r in report['positive'])
    report['unique_fixture_events']=args.events*len(args.seeds)
    count=sum(r['qualified_valid_signals'] or 0 for r in report['positive']) if qualified else 0
    report['economics']=dict(allocated_cost=args.allocated_cost,currency=args.cost_currency,
                             qualified_valid_signals_across_positive_runs=count,
                             allocated_cost_per_valid_signal=accepted_cost(args.allocated_cost,count) if args.allocated_cost is not None and qualified else None,
                             note='No cash savings, revenue, alpha or hardware price is inferred. Repeated candidate runs are distinct experiments.')
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    manifest={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'manifest.json').write_text(json.dumps({'sha256':manifest,'trust':'unsigned local manifest'},indent=2)+'\n')
    print(f"qualification={report['verdict']} report={output/'report.json'}",flush=True)
    return 0 if report['verdict']=='pass' else 1


if __name__=='__main__':
    sys.exit(main())
