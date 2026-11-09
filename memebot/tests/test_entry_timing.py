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
