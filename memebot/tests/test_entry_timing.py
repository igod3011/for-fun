import math
import unittest

from memebot.ml import entry_timing as et

K = 85 * 2.07e8
USD_PER_SOL = 150.0
T0 = 1_000_000


def pool(sol_path, fill_min=200, alive_until=None, reg_min=5):
    """sol_path(minute) -> pool SOL; candles priced from the constant product with k = K."""
    candles = []
    for m in range(0, fill_min):
        if alive_until is not None and m > alive_until:
            break
        s = sol_path(m)
        px = USD_PER_SOL * s * s / K
        candles.append([T0 + m * 60, px, px, px, px, 100.0])
    s_reg, s_fill = sol_path(reg_min), sol_path(fill_min)
    return {"mint": "Xpump", "created": T0, "registered_at": T0 + reg_min * 60, "fetched_at": T0 + fill_min * 60,
            "candles": candles,
            "helius_reg": {"pool_sol": s_reg, "pool_tokens": K / s_reg, "fetched_at": T0 + reg_min * 60},
            "helius_fill": {"pool_sol": s_fill, "pool_tokens": K / s_fill, "fetched_at": T0 + fill_min * 60}}


knife = lambda m: 85.0 if m <= 5 else max(20.0, 85 - (m - 5) * 13)          # 85 -> 20 SOL by minute 10
rocket = lambda m: 85.0 * (1 + min(m, 60) / 60)                             # 85 -> 170 SOL in an hour
flat = lambda m: 85.0


class EntryTimingTest(unittest.TestCase):
    def test_hold_value_matches_constant_product(self):
        S = et.setup(pool(flat))
        te, usd, s_e, t_e = et.entry(S, T0, 15, guard=False, momentum=False)
        self.assertAlmostEqual(s_e, 85.0, places=3)
        q = et.amm.buy(et.STAKE, s_e, t_e, et.FEE)
        self.assertAlmostEqual(et.exit_hold(S, q) / et.STAKE - 1, -0.0111, places=3)   # 2x0.5% fee + ~0.12% impact

    def test_guard_blocks_the_knife(self):
        S = et.setup(pool(knife))
        self.assertIsNotNone(et.entry(S, T0, 15, guard=False, momentum=False))
        self.assertIsNone(et.entry(S, T0, 15, guard=True, momentum=False))

    def test_dead_pool_cannot_be_entered_late(self):
        S = et.setup(pool(flat, alive_until=8))
        self.assertIsNotNone(et.entry(S, T0, 5, False, False))
        self.assertIsNone(et.entry(S, T0, 15, False, False))

    def test_bot_rules_take_profit_on_rocket(self):
        S = et.setup(pool(rocket))
        te, usd, s_e, t_e = et.entry(S, T0, 5, guard=True, momentum=False)
        q = et.amm.buy(et.STAKE, s_e, t_e, et.FEE)
        hold = et.exit_hold(S, q) / et.STAKE - 1
        bot = et.exit_bot(S, te, usd, s_e, q) / et.STAKE - 1
        self.assertGreater(hold, 2.0)                  # price x(170/~92)^2 by fill
        self.assertGreater(bot, 0.3)                   # partial take-profits, rest held
        self.assertLess(bot, hold)

    def test_run_reports_filters_and_halves(self):
        rows = [pool(knife) for _ in range(30)] + [pool(rocket) for _ in range(10)]
        lines = []
        res = et.run(rows, delays=(15,), out=lines.append)
        f0 = res[("F0 alive", 15, "hold")]
        f1 = res[("F1 +guard", 15, "hold")]
        self.assertEqual(len(f0["early"]) + len(f0["late"]), 40)
        self.assertEqual(len(f1["early"]) + len(f1["late"]), 10)        # knives filtered out
        self.assertTrue(any("F2" in l for l in lines))


if __name__ == "__main__":
    unittest.main()


class ExitFidelityTest(unittest.TestCase):
    def test_gap_through_stop_fills_at_open_not_at_stop(self):
        crash = lambda m: 85.0 if m <= 20 else 40.0                       # one-minute gap: price -78%
        S = et.setup(pool(crash))
        te, usd, s_e, t_e = et.entry(S, T0, 10, guard=False, momentum=False)
        q = et.amm.buy(et.STAKE, s_e, t_e, et.FEE)
        r = et.exit_bot(S, te, usd, s_e, q) / et.STAKE - 1
        self.assertLess(r, -0.7)                                          # not the idealised -25%

    def test_max_hold_sells_at_that_minute_not_at_fill(self):
        up_then_dump = lambda m: 85.0 * 1.1 if 10 < m < 150 else (85.0 if m <= 10 else 20.0)
        S = et.setup(pool(up_then_dump))
        te, usd, s_e, t_e = et.entry(S, T0, 10, guard=False, momentum=False)
        q = et.amm.buy(et.STAKE, s_e, t_e, et.FEE)
        rules = dict(et.DEFAULT_RULES, max_hold=60, tp=[], trail_on=None)
        r = et.exit_bot(S, te, usd, s_e, q, rules) / et.STAKE - 1
        self.assertGreater(r, 0.15)                                       # sold at +21% price before the dump

    def test_grid_search_is_walk_forward_and_fast_enough(self):
        import time
        import random
        rows = [pool(knife) for _ in range(500)] + [pool(rocket) for _ in range(150)] + [pool(flat) for _ in range(150)]
        random.Random(0).shuffle(rows)
        for i, r in enumerate(rows):                       # distinct creation times, mixed types
            r["created"] += i
        lines = []
        t = time.time()
        scored = et.grid_search(rows, out=lines.append)
        self.assertTrue(scored)
        self.assertTrue(any("TOP 5 BY TRAIN" in l for l in lines))
        self.assertTrue(any("TEST" in l for l in lines))
        self.assertLess(time.time() - t, 240)


class TxFeeTest(unittest.TestCase):
    def test_fixed_fee_costs_two_transactions_per_round_trip(self):
        S = et.setup(pool(flat))
        te, usd, s_e, t_e = et.entry(S, T0, 15, guard=False, momentum=False)
        q = et.amm.buy(et.STAKE, s_e, t_e, et.FEE)
        base = et.exit_hold(S, q)
        try:
            et.TX_FEE = 0.0003
            with_fee = et.exit_hold(S, q) - et.TX_FEE              # sell tx inside, buy tx at the caller
        finally:
            et.TX_FEE = 0.0
        self.assertAlmostEqual((base - with_fee) / et.STAKE, 2 * 0.0003 / 0.05, places=6)   # 1.2% at 0.05 SOL


class BootstrapTest(unittest.TestCase):
    def test_ci_contains_zero_for_noise_and_not_for_clear_edge(self):
        noise = [0.25, -0.25, 0.1, -0.1] * 15                 # mean exactly 0: CI must straddle 0
        edge = [0.15, 0.25, 0.2, 0.18] * 15                    # clearly positive
        lo, hi = et.bootstrap_ci(noise)
        self.assertTrue(lo < 0 < hi)
        lo, hi = et.bootstrap_ci(edge)
        self.assertGreater(lo, 0)
