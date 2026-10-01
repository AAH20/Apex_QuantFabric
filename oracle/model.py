# SPDX-License-Identifier: Apache-2.0
"""Dictionary/set reference model, authored independently from fixed-slot C++."""
import math


class Reference:
    def __init__(self):
        self.session = 1
        self.markets = {i: {'sequence': 0, 'price': 0, 'blocked': False} for i in range(8)}
        self.seen = set()
        self.reservations = {}

    def apply(self, e, index):
        kind = e['kind']
        score = None
        valid = False
        action = 0
        if kind == 'RESET':
            if e['session'] <= self.session:
                code = 'RESET_OLD'
            elif self.reservations:
                code = 'RESET_BLOCKED'
            else:
                self.__init__()
                self.session = e['session']
                code = 'RESET'
        elif e['session'] != self.session:
            code = 'WRONG_SESSION'
        elif kind == 'ADVANCE':
            code = 'ADVANCE'
        elif kind == 'MARKET':
            market = self.markets[e['instrument']]
            if market['blocked']:
                code = 'FEED_BLOCKED'
            elif e['sequence'] <= market['sequence']:
                code = 'MARKET_DUPLICATE'
            elif e['sequence'] != market['sequence'] + 1:
                market['blocked'] = True
                code = 'FEED_GAP'
            else:
                market.update(sequence=e['sequence'], price=int(e['score']))
                code = 'MARKET'
        elif kind in ('UNCERTAIN', 'RELEASE'):
            if e['action'] not in self.reservations:
                code = 'UNKNOWN_ACTION'
            elif kind == 'UNCERTAIN':
                self.reservations[e['action']]['uncertain'] = True
                code = 'UNRESOLVED'
            else:
                del self.reservations[e['action']]
                code = 'RELEASED'
        elif e['id'] in self.seen:
            code = 'DUPLICATE'
        else:
            self.seen.add(e['id'])
            if kind == 'DROPPED':
                code = 'QUEUE_DROPPED'
            else:
                score = float(e['score'])
                market = self.markets[e['instrument']]
                reference_score = ((market['price'] % 101) - 50) / 50
                if (e['model'], e['policy'], e['config']) != (1, 1, 1):
                    code = 'WRONG_VERSION'
                elif market['blocked']:
                    code = 'FEED_BLOCKED'
                elif not market['sequence'] or e['watermark'] != market['sequence']:
                    code = 'STALE_WATERMARK'
                elif e['time'] > e['expiry']:
                    code = 'EXPIRED'
                elif not math.isfinite(score) or abs(score-reference_score) > 0.000001:
                    code = 'NUMERICAL'
                else:
                    valid = True
                    units = sum(r['quantity'] for r in self.reservations.values() if r['instrument'] == e['instrument'])
                    if score < 0.5:
                        code = 'NO_SIGNAL'
                    elif units + e['quantity'] > 16:
                        code = 'CAPACITY_UNITS'
                    elif len(self.reservations) >= 16:
                        code = 'CAPACITY_SLOTS'
                    else:
                        action = e['id']
                        self.reservations[action] = dict(instrument=e['instrument'], quantity=e['quantity'], uncertain=False)
                        code = 'ADMITTED'
        bitmap = sum(1 << (x-1) for x in self.seen)
        reservations = ';'.join(f"{k}:{v['instrument']}:{v['quantity']}:{int(v['uncertain'])}"
                                for k, v in sorted(self.reservations.items())) or '-'
        return [str(index), code, str(int(valid)), str(action), score, str(self.session),
                ','.join(str(self.markets[i]['sequence']) for i in range(8)),
                ','.join(str(self.markets[i]['price']) for i in range(8)),
                str(sum(1 << i for i in range(8) if self.markets[i]['blocked'])),
                f'{bitmap:064x}', reservations]
