# SPDX-License-Identifier: Apache-2.0
"""Strict full-field JSONL to TSV interchange. No hardware emulation."""
import json
import math

FIELDS = ('kind', 'time', 'session', 'id', 'instrument', 'sequence', 'watermark',
          'model', 'policy', 'config', 'expiry', 'score', 'quantity', 'action')
KINDS = {'MARKET', 'PREDICTION', 'DROPPED', 'UNCERTAIN', 'RELEASE', 'RESET', 'ADVANCE'}


def validate(event):
    if not isinstance(event, dict) or set(event) != set(FIELDS):
        raise ValueError('event fields must exactly match the frozen profile')
    if event['kind'] not in KINDS:
        raise ValueError('unknown event kind')
    for field in FIELDS:
        if field in {'kind', 'score'}:
            continue
        if type(event[field]) is not int or not 0 <= event[field] <= 2147483647:
            raise ValueError(f'invalid integer: {field}')
    raw_score = event['score']
    if type(raw_score) not in (int, float) and raw_score not in ('nan', 'inf', '-inf'):
        raise ValueError('invalid score')
    score = float(raw_score)
    if not event['session'] or event['instrument'] >= 8:
        raise ValueError('session or instrument bounds')
    kind = event['kind']
    if kind in ('PREDICTION', 'DROPPED'):
        if not 1 <= event['id'] <= 256 or not 1 <= event['quantity'] <= 16:
            raise ValueError('prediction bounds')
        if event['sequence'] or event['action']:
            raise ValueError('unused prediction fields')
    elif kind == 'MARKET':
        if not event['sequence'] or not math.isfinite(score) or not 1 <= score <= 2147483647 or score != int(score):
            raise ValueError('market bounds')
        if any(event[x] for x in ('id', 'watermark', 'model', 'policy', 'config', 'expiry', 'quantity', 'action')):
            raise ValueError('unused market fields')
    else:
        if any(event[x] for x in ('id', 'instrument', 'sequence', 'watermark', 'model', 'policy', 'config', 'expiry', 'quantity')) or score != 0:
            raise ValueError('unused control fields')
        if kind in ('UNCERTAIN', 'RELEASE'):
            if not 1 <= event['action'] <= 256:
                raise ValueError('action bounds')
        elif event['action']:
            raise ValueError('unused action')
    return event


def make(kind, time, session=1, **fields):
    e = dict.fromkeys(FIELDS, 0)
    e.update(kind=kind, time=time, session=session)
    e.update(fields)
    return validate(e)


def wire(event):
    validate(event)
    return '\t'.join(str(event[x]) for x in FIELDS) + '\n'


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_events(path):
    previous = -1
    with open(path, encoding='utf-8') as stream:
        for line in stream:
            e = validate(json.loads(line, object_pairs_hook=no_duplicate_keys,
                                    parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'JSON constant {x}'))))
            if e['time'] < previous:
                raise ValueError('logical time regressed')
            previous = e['time']
            yield e
