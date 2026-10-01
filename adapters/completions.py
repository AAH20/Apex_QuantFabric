# SPDX-License-Identifier: Apache-2.0
"""Bounded logical-time completion queue. No wall-clock deadline claim."""
from adapters.interchange import validate


class CompletionQueue:
    def __init__(self, capacity=8):
        if type(capacity) is not int or not 1 <= capacity <= 8:
            raise ValueError('completion capacity must be 1..8')
        self.capacity = capacity
        self.pending = []
        self.now = -1

    def submit(self, prediction, ready_time):
        validate(prediction)
        if prediction['kind'] != 'PREDICTION' or type(ready_time) is not int or not prediction['time'] <= ready_time <= 2147483647:
            raise ValueError('invalid completion submission')
        if prediction['time'] < self.now:
            raise ValueError('submission time regressed')
        self.now = prediction['time']
        if len(self.pending) == self.capacity:
            dropped = dict(prediction, kind='DROPPED')
            return dropped
        self.pending.append((ready_time,dict(prediction)))
        return None

    def drain(self, now, reverse_ready=False):
        if type(now) is not int or not self.now <= now <= 2147483647:
            raise ValueError('completion time regressed or out of bounds')
        self.now = now
        ready = [item for item in self.pending if item[0] <= now]
        self.pending = [item for item in self.pending if item[0] > now]
        ready.sort(key=lambda item: (item[0],item[1]['id']),reverse=reverse_ready)
        return [dict(event,time=now) for _,event in ready]
