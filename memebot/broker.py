"""Paper broker modelling AMM price impact: a trade of value v against a pool with
liquidity L (L/2 per side) moves price roughly by v / (L/2). Rugged pools therefore
return almost nothing on exit, as in real life."""
from dataclasses import dataclass


@dataclass
class Position:
    token_id: str
    qty: float
    entry_mid: float
    cost: float          # USD paid incl. fee
    entry_ts: int
    peak: float


class PaperBroker:
    def __init__(self, cash, fee):
        self.cash = cash
        self.fee = fee
        self.positions = {}
        self.trades = []     # closed trades: dict(token, pnl, ret, reason, hold)

    def buy(self, token_id, usd, mid, liquidity, ts):
        usd = min(usd, self.cash)
        if usd <= 0 or mid <= 0:
            return None
        eff = mid * (1 + usd / (liquidity / 2))
        qty = usd * (1 - self.fee) / eff
        self.cash -= usd
        self.positions[token_id] = Position(token_id, qty, mid, usd, ts, mid)
        return self.positions[token_id]

    def sell(self, token_id, mid, liquidity, ts, reason):
        pos = self.positions.pop(token_id)
        v = pos.qty * mid
        half = max(liquidity / 2, 1e-9)
        proceeds = v * half / (half + v) * (1 - self.fee)
        self.cash += proceeds
        self.trades.append({
            "token": token_id, "pnl": proceeds - pos.cost,
            "ret": proceeds / pos.cost - 1, "reason": reason, "hold": ts - pos.entry_ts,
        })
        return proceeds

    def equity(self, marks):
        return self.cash + sum(p.qty * marks.get(t, p.entry_mid) for t, p in self.positions.items())
