"""Candle-driven trading engine shared by the backtester and the live paper runner."""
from .anomaly import HARD, assess
from .broker import PaperBroker


class Engine:
    def __init__(self, cfg, strategy, use_filter=True):
        self.cfg = cfg
        self.strategy = strategy
        self.use_filter = use_filter
        self.broker = PaperBroker(cfg.capital, cfg.fee)
        self.pending = set()      # tokens with a signal, to be filled at next candle open
        self.marks = {}
        self.skipped = {}         # flag -> count of entries blocked
        self.curve = []

    def on_candle(self, meta, hist):
        cfg, b, c = self.cfg, self.broker, hist[-1]
        self.marks[meta.id] = c.close
        pos = b.positions.get(meta.id)

        if pos:
            self._manage(meta, hist, pos)
        elif meta.id in self.pending:
            self.pending.discard(meta.id)
            self._enter(meta, c)
        elif len(hist) > 1:
            self._signal(meta, hist)
        self.curve.append((c.ts, b.equity(self.marks)))

    def _manage(self, meta, hist, pos):
        cfg, c = self.cfg, hist[-1]
        a = assess(meta, hist, cfg)
        if a.hard:
            reason = "+".join(f for f in a.flags if f in HARD)
            self.broker.sell(meta.id, c.close, c.liquidity, c.ts, reason)
            return
        stop = pos.entry_mid * (1 - cfg.stop_loss)
        if pos.peak >= pos.entry_mid * (1 + cfg.trail_activate):
            stop = max(stop, pos.peak * (1 - cfg.trail))
        if c.open <= stop:
            self.broker.sell(meta.id, c.open, c.liquidity, c.ts, "stop_gap")
        elif c.low <= stop:
            self.broker.sell(meta.id, stop, c.liquidity, c.ts, "stop")
        elif c.ts - pos.entry_ts >= cfg.max_hold_min:
            self.broker.sell(meta.id, c.close, c.liquidity, c.ts, "time")
        else:
            pos.peak = max(pos.peak, c.high)

    def _signal(self, meta, hist):
        cfg, c = self.cfg, hist[-1]
        age = c.ts - meta.created_ts
        if not (cfg.min_age_min <= age <= cfg.max_age_min):
            return
        if len(self.broker.positions) + len(self.pending) >= cfg.max_positions:
            return
        if c.liquidity < cfg.min_liquidity or not self.strategy(hist, cfg):
            return
        if self.use_filter:
            a = assess(meta, hist, cfg)
            if a.blocked(cfg):
                for f in a.flags:
                    self.skipped[f] = self.skipped.get(f, 0) + 1
                return
        self.pending.add(meta.id)

    def _enter(self, meta, c):
        cfg, b = self.cfg, self.broker
        usd = min(b.equity(self.marks) * cfg.position_pct, c.liquidity * cfg.max_liq_frac)
        b.buy(meta.id, usd, c.open, c.liquidity, c.ts)
