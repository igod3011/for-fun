"""Research Engine: the scorer and its gates, the data cache, the hypotheses' accounting, the ranking. No network."""
import os
import random
import tempfile
import unittest

from memebot.research import hypotheses as hyp
from memebot.research import run, score
from memebot.research.data import Data, Missing

DAY = 86400


def series(rets):
    return [(i * 3600, r) for i, r in enumerate(rets)]


class ScoreTest(unittest.TestCase):
    def test_a_steady_edge_passes_and_a_steady_loss_is_rejected(self):
        rng = random.Random(1)
        good = series([0.03 + rng.uniform(-0.05, 0.05) for _ in range(200)])
        m = score.metrics(good)
        self.assertEqual(score.verdict(m)[0], score.PASS)
        self.assertGreater(m["ci"][0], 0)
        bad = series([-0.03 + rng.uniform(-0.05, 0.05) for _ in range(200)])
        self.assertEqual(score.verdict(score.metrics(bad))[0], score.REJECTED)

    def test_gates_catch_few_trades_one_good_half_and_a_handful_of_winners(self):
        self.assertEqual(score.verdict(score.metrics(series([0.5] * 20)))[0], score.NO_DATA)
        self.assertEqual(score.verdict(score.metrics([]))[0], score.NO_DATA)
        status, why = score.verdict(score.metrics(series([0.05] * 60)))
        self.assertEqual(status, score.UNPROVEN)                      # positive, but fewer than 100 trades
        self.assertIn("< 100", why)
        status, why = score.verdict(score.metrics(series([0.30] * 100 + [-0.05] * 100)))
        self.assertEqual(status, score.UNPROVEN)
        self.assertIn("both halves", why)
        lottery = series(([-0.10] * 49 + [9.0]) * 4)                  # mean > 0 only thanks to 4 huge winners
        m = score.metrics(lottery)
        self.assertGreater(m["mean"], 0)
        status, why = score.verdict(m)
        self.assertEqual(status, score.UNPROVEN)
        self.assertIn("best trades", why)

    def test_more_variants_tried_means_a_wider_interval(self):
        rng = random.Random(2)
        t = series([0.01 + rng.uniform(-0.2, 0.2) for _ in range(150)])
        one, many = score.metrics(t, 1), score.metrics(t, 50)
        self.assertLess(many["ci"][0], one["ci"][0])
        self.assertGreater(many["ci"][1], one["ci"][1])
        self.assertAlmostEqual(many["ci_level"], 0.998)

    def test_a_single_trade_is_capped_and_recent_trades_are_reported(self):
        m = score.metrics(series([0.0] * 9 + [500.0]))
        self.assertAlmostEqual(m["mean"], 1.0)                        # +50000% counts as +1000%
        m = score.metrics(series([0.1] * 80 + [-0.1] * 20))
        self.assertAlmostEqual(m["recent"], -0.1)                     # the newest 20% lose: the edge is fading
        self.assertAlmostEqual(score.max_drawdown([0.1, -0.2, -0.1, 0.5]), -0.3)

    def test_monte_carlo_is_reproducible_and_knows_ruin(self):
        self.assertEqual(score.monte_carlo([-0.5] * 20, 10, 50)["p_ruin"], 1.0)
        self.assertEqual(score.monte_carlo([0.1] * 20, 10, 50)["p_ruin"], 0.0)
        rets = [0.2, -0.1, 0.05, -0.3, 0.1, 0.0, -0.05, 0.15]
        a, b = score.monte_carlo(rets, 10, 100), score.monte_carlo(rets, 10, 100)
        self.assertEqual(a, b)
        self.assertLessEqual(a["p5"], a["p50"])
        self.assertIsNone(score.monte_carlo([0.1] * 3, 10, 50))


class FakeData:
    """Stands in for Data: daily candles and funding given directly."""
    def __init__(self, daily, funding=None):
        self._daily, self._funding = daily, funding or {}

    def daily(self):
        return self._daily

    def funding(self, symbols, since=0):
        return {s: self._funding.get(s, []) for s in symbols}


def candles(start, closes, volume=50e6, high=None):
    return [[start + i * DAY, c, (high or {}).get(i, c), c, c, volume] for i, c in enumerate(closes)]


class HypothesisTest(unittest.TestCase):
    T0 = 1704067200 + 10 * DAY

    def test_registry_entries_state_mechanism_and_kill_criterion(self):
        ids = [h["id"] for h in hyp.REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))
        for h in hyp.REGISTRY:
            self.assertTrue(h["mechanism"] and h["kill"] and h["stake_usd"] > 0 and h["variants"] >= 1, h["id"])

    def test_listing_short_gains_when_the_coin_falls_and_stops_at_plus_50(self):
        btc = candles(self.T0, [100.0] * 60)
        fall = candles(self.T0, [1.0] * 8 + [0.6] * 52)                # entry at the day-7 close (1.0), exit at 0.6
        squeeze = candles(self.T0, [1.0] * 60, high={12: 1.8})         # spikes through the +50% stop on day 12
        daily = {"BTCUSDT": {"onboard": 0, "d": btc}, "FALLUSDT": {"onboard": self.T0, "d": fall},
                 "SQZUSDT": {"onboard": self.T0, "d": squeeze}}
        fund = {"FALLUSDT": [[self.T0 + 20 * DAY, 0.01]]}              # shorts receive +1% once while holding
        trades, _ = hyp.f5(FakeData(daily, fund))
        rets = sorted(r for _, r in trades)
        self.assertEqual(len(rets), 2)
        self.assertAlmostEqual(rets[0], -0.5 - 4 * hyp.PERP_COST)      # stopped out: never better than the stop
        self.assertAlmostEqual(rets[1], 0.4 + 0.01 - 4 * hyp.PERP_COST)

    def test_carry_collects_funding_and_pays_both_legs_once(self):
        days = 60
        daily = {"BTCUSDT": {"onboard": 0, "d": candles(self.T0, [100.0] * days)},
                 "AAAUSDT": {"onboard": 0, "d": candles(self.T0, [1.0] * days)}}
        rate = 0.0003                                                  # every 8 hours -> 0.63% a week
        fund = {"BTCUSDT": [[self.T0 + i * 28800, 0.0] for i in range(days * 3)],
                "AAAUSDT": [[self.T0 + i * 28800, rate] for i in range(days * 3)]}
        trades, _ = hyp.c1(FakeData(daily, fund))
        rets = [r for _, r in trades]
        self.assertGreater(len(rets), 4)
        week = 21 * rate
        self.assertAlmostEqual(rets[0], (week - 2 * hyp.PERP_COST - 2 * hyp.SPOT_COST) / 2)    # first week pays the costs
        self.assertAlmostEqual(rets[1], week / 2)                                            # later weeks: funding only
        none, _ = hyp.c1(FakeData(daily, {s: [[t, 0.0] for t, _ in rows] for s, rows in fund.items()}))
        self.assertEqual(none, [])                                     # no funding to earn: no position

    def test_trend_following_profits_from_a_trend_and_is_floored_at_liquidation(self):
        up = [[i * 3600, p, p * 1.001, p * 0.999, p * 1.002, 1.0] for i, p in
              enumerate([100 * 0.999 ** i for i in range(150)] + [86 * 1.004 ** i for i in range(300)] + [280 * 0.99 ** i for i in range(80)])]
        trades = hyp.ema_trades(up, [], fast=10, slow=50, lev=5)
        self.assertTrue(trades)
        self.assertGreater(max(r for _, r in trades), 1.0)             # the long through the rally, 5x on margin
        self.assertGreaterEqual(min(r for _, r in trades), -1.0)       # never worse than losing the margin
        self.assertAlmostEqual(hyp._funding_sum([[10, 0.1], [20, 0.2], [30, 0.4]], 10, 30), 0.6)


class DataAndRunTest(unittest.TestCase):
    def test_cache_is_used_and_offline_never_downloads(self):
        tmp = tempfile.mkdtemp()
        calls = []

        def get(url):
            calls.append(url)
            return [{"fundingTime": 1000_000, "fundingRate": "0.0001"}]
        d = Data(cache=tmp, get=get, pace=0)
        self.assertEqual(d.funding(["XUSDT"])["XUSDT"], [[1000, 0.0001]])
        self.assertEqual(Data(cache=tmp, get=get, pace=0).funding(["XUSDT"])["XUSDT"], [[1000, 0.0001]])
        self.assertEqual(len(calls), 1)                                # the second object read the file
        with self.assertRaises(Missing):
            Data(cache=tmp, offline=True, get=get).funding(["YUSDT"])
        with self.assertRaises(Missing):
            Data(cache=tmp, get=lambda url: None, pace=0).funding(["ZUSDT"])
        self.assertTrue(os.path.exists(os.path.join(tmp, "funding.json")))

    def test_a_missing_source_or_a_broken_hypothesis_becomes_a_row_not_a_crash(self):
        def missing(data):
            raise Missing("daily.json")

        def broken(data):
            return 1 / 0
        rng = random.Random(3)
        good = lambda data: (series([0.04 + rng.uniform(-0.05, 0.05) for _ in range(150)]), "ghi chú")
        base = {"name": "n", "family": "f", "mechanism": "m", "kill": "k", "stake_usd": 10, "variants": 1}
        rows = [run.evaluate({**base, "id": i, "fn": fn}, None) for i, fn in (("A", missing), ("B", broken), ("C", good))]
        self.assertEqual([r["status"] for r in rows], [score.NO_DATA, score.NO_DATA, score.PASS])
        text = run.render(rows, "2026-11-13 20:00")
        self.assertLess(text.index("| 1 | C |"), text.index("| A |"))  # the one that passed is ranked first
        self.assertIn("thiếu dữ liệu: daily.json", text)
        self.assertIn("ZeroDivisionError", text)
        self.assertIn("ĐẠT, chuyển sang paper", text)

    def test_a_passing_hypothesis_whose_recent_trades_lose_is_flagged(self):
        fading = lambda data: (series([0.2] * 100 + [0.02] * 60 + [-0.01] * 40), "")
        base = {"id": "X", "name": "n", "family": "f", "mechanism": "m", "kill": "k", "stake_usd": 10, "variants": 1}
        row = run.evaluate({**base, "fn": fading}, None)
        self.assertEqual(row["status"], score.PASS)
        self.assertIn("Cảnh báo", run.render([row], "now"))


if __name__ == "__main__":
    unittest.main()
