import unittest
from dataclasses import replace

from memebot.anomaly import assess
from memebot.backtest import run, summarize
from memebot.broker import PaperBroker
from memebot.config import Config
from memebot.models import Candle, TokenMeta
from memebot.strategy import breakout_volume
from memebot.synthetic import generate_universe


def candle(ts, o, h, l, c, vol=1000, buys=30, sells=20, makers=40, liq=50_000):
    return Candle(ts, o, h, l, c, vol, buys, sells, makers, liq)


class AnomalyTests(unittest.TestCase):
    cfg = Config()

    def test_clean_token_has_no_flags(self):
        a = assess(TokenMeta("A", "A", 0), [candle(i, 1, 1.01, .99, 1) for i in range(10)], self.cfg)
        self.assertEqual(a.flags, [])

    def test_mint_authority_is_hard_block(self):
        a = assess(TokenMeta("A", "A", 0, mint_revoked=False), [candle(0, 1, 1, 1, 1)], self.cfg)
        self.assertTrue(a.hard)

    def test_liquidity_drain_detected(self):
        hist = [candle(i, 1, 1, 1, 1) for i in range(4)] + [candle(4, 1, 1, 1, 1, liq=10_000)]
        self.assertIn("liquidity_drain", assess(TokenMeta("A", "A", 0), hist, self.cfg).flags)

    def test_dump_detected(self):
        hist = [candle(0, 1, 1, 1, 1), candle(1, 1, 1, .1, .1, buys=5, sells=40)]
        self.assertIn("dump", assess(TokenMeta("A", "A", 0), hist, self.cfg).flags)

    def test_wash_trading_detected(self):
        hist = [candle(i, 1, 1, 1, 1, buys=100, sells=100, makers=5) for i in range(3)]
        self.assertIn("wash_trading", assess(TokenMeta("A", "A", 0), hist, self.cfg).flags)


class StrategyTests(unittest.TestCase):
    def test_breakout_needs_volume(self):
        cfg = Config()
        base = [candle(i, 1, 1.02, .98, 1.0) for i in range(cfg.lookback)]
        weak = base + [candle(99, 1, 1.2, 1, 1.15, vol=1000)]
        strong = base + [candle(99, 1, 1.2, 1, 1.15, vol=5000, buys=45, sells=5)]
        self.assertFalse(breakout_volume(weak, cfg))
        self.assertTrue(breakout_volume(strong, cfg))


class BrokerTests(unittest.TestCase):
    def test_round_trip_costs_money_at_flat_price(self):
        b = PaperBroker(1000, 0.005)
        b.buy("X", 100, 1.0, 50_000, 0)
        b.sell("X", 1.0, 50_000, 5, "t")
        self.assertLess(b.trades[0]["pnl"], 0)

    def test_rugged_pool_returns_almost_nothing(self):
        b = PaperBroker(1000, 0.005)
        b.buy("X", 100, 1.0, 50_000, 0)
        b.sell("X", 0.1, 2_500, 5, "rug")
        self.assertLess(b.trades[0]["ret"], -0.85)

    def test_cannot_overspend(self):
        b = PaperBroker(50, 0.0)
        b.buy("X", 100, 1.0, 50_000, 0)
        self.assertGreaterEqual(b.cash, 0)


class BacktestTests(unittest.TestCase):
    def test_deterministic_and_filter_blocks_entries(self):
        cfg = Config()
        toks = generate_universe(120, seed=3)
        s1 = summarize(run(toks, cfg, "breakout_volume", True), cfg)
        s2 = summarize(run(toks, cfg, "breakout_volume", True), cfg)
        self.assertEqual(s1, s2)
        self.assertGreater(sum(s1["entries_blocked"].values()), 0)
        self.assertGreater(s1["final_equity"], 0)


if __name__ == "__main__":
    unittest.main()
