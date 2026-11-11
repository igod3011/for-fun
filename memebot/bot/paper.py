"""Paper portfolio with persistent state and a decision log (every action + its reason)."""
import json
import os
import time
from dataclasses import asdict

from . import amm
from .strategy import Position, pos_virt


class Seen(dict):
    """Mints already decided, in insertion order, so that pruning drops the OLDEST ones. (It used to be a set
    saved as sorted(...)[-5000:], which threw away mints by alphabet: after a restart those could be bought again.)"""

    def add(self, mint):
        self.setdefault(mint, None)

    def discard(self, mint):
        self.pop(mint, None)


SEEN_KEEP = 5000


class Paper:
    def __init__(self, cfg):
        self.cfg = cfg
        self.balance = cfg.paper_balance_sol
        self.positions = {}
        self.day = time.strftime("%Y-%m-%d")
        self.day_pnl = 0.0
        self.total_pnl = 0.0
        self.paused = False
        self.seen = Seen()
        self._load()

    # persistence -------------------------------------------------------------------------------
    def _load(self):
        if not os.path.exists(self.cfg.state_path):
            return
        with open(self.cfg.state_path) as f:
            s = json.load(f)
        self.balance, self.day, self.day_pnl = s["balance"], s["day"], s["day_pnl"]
        self.total_pnl, self.paused = s.get("total_pnl", 0.0), s.get("paused", False)
        self.seen = Seen.fromkeys(s.get("seen", []))
        self.positions = {m: Position.from_state(p) for m, p in s["positions"].items()}

    def save(self):
        tmp = self.cfg.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"balance": self.balance, "day": self.day, "day_pnl": self.day_pnl, "total_pnl": self.total_pnl,
                       "paused": self.paused, "seen": list(self.seen)[-SEEN_KEEP:],
                       "positions": {m: asdict(p) for m, p in self.positions.items()}}, f)
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
    def buy(self, row, pool_sol, pool_tok, stake, reason, price_usd=0.0, mcap=0.0, virt=None, **extra):
        """virt: the pool's virtual reserve read on-chain (None = cfg fallback).
        extra: fields recorded with the decision (e.g. the holder snapshot taken right before buying)."""
        virt = self.cfg.virtual_quote_sol if virt is None else virt
        tokens = amm.buy(stake, pool_sol, pool_tok, self.cfg.fee, virt)
        stake_paid = stake + self.cfg.tx_fee_sol          # the fixed transaction fee is part of the cost
        self.balance -= stake_paid
        pos = Position(row["mint"], row["pool"], row.get("name", "?"), tokens, stake_paid, time.time(),
                       pool_sol, peak_pool_sol=pool_sol, entry_pool_tok=pool_tok,
                       entry_price_usd=price_usd or 0.0, entry_mcap=mcap or 0.0, virt_sol=virt)
        self.positions[row["mint"]] = pos
        self.log(action="buy", mint=pos.mint, name=pos.name, sol=stake, tokens=tokens, pool_sol=pool_sol,
                 pool_tokens=pool_tok, virt_sol=virt, reason=reason, price_usd=price_usd, mcap=mcap, **extra)
        self.save()
        return pos

    def sell(self, mint, fraction, pool_sol, pool_tok, reason):
        pos = self.positions[mint]
        q = pos.tokens * min(max(fraction, 0), 1)
        out = amm.sell(q, pool_sol, pool_tok, self.cfg.fee, pos_virt(pos, self.cfg)) if pool_tok > 0 else 0.0
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
                 pool_tokens=pool_tok, virt_sol=pos.virt_sol,
                 reason=reason, closed=closed, pnl=pnl)
        self.save()
        return out, pnl
