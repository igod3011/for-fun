"""Paper portfolio with persistent state and a decision log (every action + its reason)."""
import json
import os
import time
from dataclasses import asdict

from . import amm
from .strategy import Position


class Paper:
    def __init__(self, cfg):
        self.cfg = cfg
        self.balance = cfg.paper_balance_sol
        self.positions = {}
        self.day = time.strftime("%Y-%m-%d")
        self.day_pnl = 0.0
        self.total_pnl = 0.0
        self.paused = False
        self.seen = set()
        self._load()

    # persistence -------------------------------------------------------------------------------
    def _load(self):
        if not os.path.exists(self.cfg.state_path):
            return
        s = json.load(open(self.cfg.state_path))
        self.balance, self.day, self.day_pnl = s["balance"], s["day"], s["day_pnl"]
        self.total_pnl, self.paused = s.get("total_pnl", 0.0), s.get("paused", False)
        self.seen = set(s.get("seen", []))
        self.positions = {m: Position(**p) for m, p in s["positions"].items()}

    def save(self):
        tmp = self.cfg.state_path + ".tmp"
        json.dump({"balance": self.balance, "day": self.day, "day_pnl": self.day_pnl, "total_pnl": self.total_pnl,
                   "paused": self.paused, "seen": sorted(self.seen)[-5000:],
                   "positions": {m: asdict(p) for m, p in self.positions.items()}}, open(tmp, "w"))
        os.replace(tmp, self.cfg.state_path)

    def log(self, **event):
        event["ts"] = int(time.time())
        with open(self.cfg.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    # risk gate ---------------------------------------------------------------------------------
    def roll_day(self):
        today = time.strftime("%Y-%m-%d")
        if today != self.day:
            self.day, self.day_pnl = today, 0.0

    def can_open(self, stake):
        stake += self.cfg.tx_fee_sol
        self.roll_day()
        if self.paused:
            return False, "paused"
        if len(self.positions) >= self.cfg.max_positions:
            return False, "max positions"
        if self.balance < stake:
            return False, "insufficient balance"
        if -self.day_pnl >= self.cfg.max_daily_loss_sol:
            return False, "daily loss limit reached"
        return True, ""

    # trades --------------------------------------------------------------------------------------
    def buy(self, row, pool_sol, pool_tok, stake, reason, add_to=None, price_usd=0.0, mcap=0.0):
        tokens = amm.buy(stake, pool_sol, pool_tok, self.cfg.fee)
        stake_paid = stake + self.cfg.tx_fee_sol          # the fixed transaction fee is part of the cost
        self.balance -= stake_paid
        if add_to:
            add_to.tokens += tokens
            add_to.cost_sol += stake_paid
            add_to.chased = True
            pos = add_to
        else:
            pos = Position(row["mint"], row["pool"], row.get("name", "?"), tokens, stake_paid, time.time(),
                           pool_sol, peak_pool_sol=pool_sol, entry_pool_tok=pool_tok,
                           entry_price_usd=price_usd or 0.0, entry_mcap=mcap or 0.0)
            self.positions[row["mint"]] = pos
        self.log(action="buy", mint=pos.mint, name=pos.name, sol=stake, tokens=tokens, pool_sol=pool_sol, reason=reason,
                 price_usd=price_usd, mcap=mcap)
        self.save()
        return pos

    def sell(self, mint, fraction, pool_sol, pool_tok, reason):
        pos = self.positions[mint]
        q = pos.tokens * min(max(fraction, 0), 1)
        out = amm.sell(q, pool_sol, pool_tok, self.cfg.fee) if pool_tok > 0 else 0.0
        out = max(out - self.cfg.tx_fee_sol, 0.0)         # fixed fee per sell transaction
        pos.tokens -= q
        pos.realized_sol += out
        self.balance += out
        closed = fraction >= 1 or pos.tokens <= 1e-9
        pnl = None
        if closed:
            pnl = pos.realized_sol - pos.cost_sol
            self.day_pnl += pnl
            self.total_pnl += pnl
            del self.positions[mint]
        self.log(action="sell", mint=mint, name=pos.name, fraction=fraction, sol_out=out, pool_sol=pool_sol,
                 reason=reason, closed=closed, pnl=pnl)
        self.save()
        return out, pnl
