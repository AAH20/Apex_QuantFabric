# SPDX-License-Identifier: Apache-2.0
import math


def accepted_cost(allocated_cost, accepted_signals):
    if type(allocated_cost) not in (int, float) or not math.isfinite(allocated_cost) or allocated_cost < 0:
        raise ValueError('allocated cost must be finite and nonnegative')
    if type(accepted_signals) is not int or accepted_signals < 0:
        raise ValueError('invalid accepted signal count')
    return allocated_cost / accepted_signals if accepted_signals else None
