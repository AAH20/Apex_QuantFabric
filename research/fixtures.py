# SPDX-License-Identifier: Apache-2.0
"""Deterministic synthetic prices and delivery faults; no licensed data."""
import random
from adapters.interchange import make
from adapters.completions import CompletionQueue


def model(price):
    return ((price % 101) - 50) / 50


def directed():
    events = []
    session = 1
    clock = 0

    def add(kind, **fields):
        nonlocal clock
        override = fields.pop('session', session)
        clock += 1
        e = make(kind, clock, override, **fields)
        events.append(e)
        return e

    def market(instrument=0, sequence=1, price=80):
        return add('MARKET', instrument=instrument, sequence=sequence, score=price)

    def prediction(identifier, instrument=0, watermark=1, price=80, **changes):
        fields = dict(id=identifier, instrument=instrument, watermark=watermark, model=1,
                      policy=1, config=1, expiry=clock+20, score=model(price), quantity=1)
        fields.update(changes)
        return add('PREDICTION', **fields)

    def reset():
        nonlocal session
        session += 1
        add('RESET')

    market()
    prediction(1, quantity=8)
    prediction(1, quantity=8)  # duplicate cannot reserve twice
    prediction(2, quantity=10)
    add('UNCERTAIN', action=1)
    add('RESET', session=session+1)
    add('RELEASE', action=1)
    add('RELEASE', action=1)
    add('RESET', session=session)
    reset()
    market()
    market(sequence=2)
    prediction(1, watermark=1)
    prediction(2, watermark=2, expiry=clock)  # expires before arrival
    prediction(3, watermark=2, model=2)
    prediction(4, watermark=2, policy=2)
    prediction(5, watermark=2, config=2)
    prediction(6, watermark=2, session=session+1)
    prediction(7, watermark=2, score='nan')
    prediction(8, watermark=2, score='inf')
    prediction(9, watermark=2, score=0.9)
    prediction(10, watermark=2)
    add('RELEASE', action=10)
    add('DROPPED', id=11, quantity=1)
    prediction(11, watermark=2)
    market(sequence=2)
    market(sequence=4)
    prediction(12, watermark=2)
    market(sequence=3)
    reset()
    prediction(1)
    market(price=75)
    prediction(2, price=75, expiry=clock+1)  # exactly at deadline
    add('RELEASE', action=2)
    market(sequence=2, price=74)
    prediction(3, watermark=2, price=74)
    reset()
    for i in range(8):
        market(i)
    for identifier in range(1, 17):
        prediction(identifier, instrument=(identifier-1)%8)
    prediction(17)
    for identifier in range(1, 17):
        add('RELEASE', action=identifier)
    reset()
    add('ADVANCE')
    market()
    queue = CompletionQueue(capacity=2)
    for identifier in (1,2,3):
        submitted = make('PREDICTION',clock,session,id=identifier,watermark=1,model=1,
                         policy=1,config=1,expiry=clock+20,score=model(80),quantity=1)
        dropped = queue.submit(submitted,clock+3)
        if dropped is not None:
            events.append(dropped)
    market(sequence=2)
    clock += 3
    events.extend(queue.drain(clock,reverse_ready=True))
    reset()
    return events


def workload(count, seed):
    if count < len(directed()):
        raise ValueError('event count must include the complete directed controls')
    prefix = directed()
    yield from prefix
    produced = len(prefix)
    session = prefix[-1]['session']
    clock = prefix[-1]['time']
    rng = random.Random(seed)
    # All random episodes close their reservations before reset. Stream truncation
    # may leave live obligations; those remain explicit in the final state.
    while produced < count:
        session += 1
        clock += 1
        yield make('RESET', clock, session)
        produced += 1
        steps = []
        for instrument in range(8):
            price = rng.choice([60, 74, 75, 76, 80, 90, 100])
            steps.append(('MARKET', dict(instrument=instrument, sequence=1, score=price)))
            for offset in range(3):
                identifier = instrument*3+offset+1
                case = rng.randrange(10)
                steps.append(('DROPPED' if case==0 else 'PREDICTION', dict(
                    id=identifier, instrument=instrument, watermark=0 if case==1 else 1,
                    model=2 if case==2 else 1, policy=1, config=1, expiry_offset=-1 if case==3 else 8,
                    score='nan' if case==4 else model(price), quantity=rng.randint(1,10))))
                if offset==1:
                    steps.append(('UNCERTAIN', dict(action=identifier)))
                steps.append(('RELEASE', dict(action=identifier)))
        # Arrival ordering is deliberately independent of prediction identifier.
        rng.shuffle(steps)
        # Releases can precede admission; a terminal sweep closes only known IDs.
        steps.extend(('RELEASE', dict(action=i)) for i in range(1,25))
        for kind, fields in steps:
            if produced >= count:
                break
            clock += rng.choice([0, 1, 1, 4])
            if 'expiry_offset' in fields:
                fields['expiry'] = max(0,clock+fields.pop('expiry_offset'))
            yield make(kind, clock, session, **fields)
            produced += 1
