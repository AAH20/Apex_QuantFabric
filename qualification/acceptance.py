# SPDX-License-Identifier: Apache-2.0
"""Declared workstation acceptance; distinct from checker integrity."""


def evaluate(result, limits):
    reasons=[]
    if result['verdict']!='pass':
        return {'verdict':'inconclusive' if result['verdict']=='inconclusive' else 'fail',
                'reasons':['semantic qualification unavailable or failed']}
    if result['qualified_valid_signals'] < limits['minimum_valid_signals']:
        reasons.append('valid-signal population below declared minimum')
    ceiling=limits['maximum_kernel_p99_ns']
    if ceiling is not None and (result['kernel_call_ns']['p99'] is None or result['kernel_call_ns']['p99']>ceiling):
        reasons.append('instrumented kernel p99 exceeds declared ceiling')
    return {'verdict':'fail' if reasons else 'pass','reasons':reasons}
