"""The virtual quote reserve of pump.fun-migrated PumpSwap pools, and the robustness fixes of the 11/2026 audit."""
import json
import os
import tempfile
import unittest
from dataclasses import replace

from memebot import helius
from memebot.bot import amm
from memebot.bot.config import BotConfig
from memebot.bot.paper import SEEN_KEEP, Paper
from memebot.bot.runner import Bot
from memebot.bot.strategy import Position, exit_decision
from memebot.bot.wallets import load_watchlist
from memebot.ml import entry_timing as et
from memebot.report import realizable_return
from memebot.tests.test_bot import NOW, FakeTG, cfg_in, row
from memebot.tests.test_entry_timing import T0, pool

V = amm.PUMP_VIRTUAL_SOL


class VirtualReserveTest(unittest.TestCase):
    def test_real_dump_recorded_by_the_bot_is_reproduced(self):
        # ANSEM, 09/11/2026, two consecutive 15 s polls: 245.81 SOL x 6.7155e7 -> 0.43 SOL x 9.8549e8 tokens
        s0, t0, t1, s1_seen = 245.81, 6.7155e7, 9.8549e8, 0.43
        left = s0 - amm.sell(t1 - t0, s0, t0, 0.0, V)
        self.assertLess(abs(left - s1_seen), 0.5)                    # the virtual reserve explains the drain ...
        self.assertGreater(s0 - amm.sell(t1 - t0, s0, t0, 0.0), 15)  # ... plain constant product leaves ~17 SOL

    def test_round_trip_costs_fees_only_and_never_pays_more_than_real_sol(self):
        q = amm.buy(0.2, 85.0, 2.07e8, 0.005, V)
        self.assertAlmostEqual(amm.sell(q, 85.0 + 0.2, 2.07e8 - q, 0.005, V), 0.2 * 0.995 ** 2, places=4)
        self.assertEqual(amm.sell(5e9, 0.4, 9.8e8, 0.0, V), 0.4)     # clamp: only real SOL can leave the pool

    def test_price_moves_were_overstated_without_it(self):
        k = (85 + V) * 2.07e8
        tok = lambda s: k / (s + V)
        true_move = amm.price(60, tok(60), V) / amm.price(85, tok(85), V) - 1
        naive_move = amm.price(60, tok(60)) / amm.price(85, tok(85)) - 1
        self.assertAlmostEqual(true_move, ((60 + V) / (85 + V)) ** 2 - 1, places=9)       # -42.9%
        self.assertLess(naive_move, true_move - 0.03)                                    # -46.6%: too pessimistic

    def test_bot_values_positions_with_the_virtual_reserve(self):
        cfg = BotConfig()
        self.assertEqual(cfg.virtual_quote_sol, V)
        k = (85 + V) * 2.07e8
        tok = lambda s: k / (s + V)
        tokens = amm.buy(0.2, 85, tok(85), cfg.fee, V)
        pos = Position("M", "P", "n", tokens=tokens, cost_sol=0.2003, opened_at=NOW, entry_pool_sol=85, peak_pool_sol=85)
        self.assertEqual(exit_decision(pos, 82, tok(82), NOW, cfg)[0], 0.0)      # price -5.8%, value -6.8%: hold
        frac, why = exit_decision(pos, 79, tok(79), NOW, cfg)                    # price -11%: stop loss
        self.assertEqual((frac, why.startswith("stop loss")), (1.0, True))

    def test_backtest_recovers_the_real_pool_sol_at_entry(self):
        S = et.setup(pool(lambda m: 85.0 if m <= 5 else 120.0))
        te, usd, s_e, t_e = et.entry(S, T0, 30, guard=True, momentum=False)
        self.assertAlmostEqual(s_e, 120.0, places=3)                             # what the live bot would read
        self.assertAlmostEqual((s_e + V) * t_e, S["k"], delta=S["k"] * 1e-9)

    def test_realizable_return_uses_it_for_canonical_pools(self):
        k = (85 + V) * 2.07e8
        p = {"helius_reg": {"pool_sol": 85.0, "pool_tokens": k / (85 + V)},
             "helius_fill": {"pool_sol": 170.0, "pool_tokens": k / (170 + V)}}
        true = ((170 + V) / (85 + V)) ** 2 - 1                                   # price x3.34
        self.assertAlmostEqual(realizable_return(p, virt=V), true, delta=0.10)   # minus 2.4% fees and impact
        self.assertGreater(realizable_return(p), true + 0.2)                     # the old formula overstated winners


class PerPoolVirtualReserveTest(unittest.TestCase):
    """The virtual reserve differs between pools (seen on-chain: 17.58, 15.3, 11.2, 2.9, 0): use the pool's own."""

    def bot(self, virt):
        self.tg = FakeTG()
        return Bot(cfg_in(tempfile.mkdtemp(), virtual_quote_sol=V), self.tg, reserves=lambda pool, mint: (85.0, 2.07e8),
                   rows=lambda path, **kw: [row("Aaapump")], virt=virt)

    def test_bot_buys_and_values_with_the_pools_own_value(self):
        bot = self.bot(lambda pool: 11.158)
        bot.discover()
        pos = bot.p.positions["Aaapump"]
        self.assertEqual(pos.virt_sol, 11.158)
        self.assertAlmostEqual(pos.tokens, amm.buy(0.2, 85.0, 2.07e8, bot.cfg.fee, 11.158))
        buy = json.loads(open(bot.cfg.log_path).read().splitlines()[-1])
        self.assertEqual((buy["action"], buy["virt_sol"]), ("buy", 11.158))
        bot.manage()
        self.assertEqual(json.loads(open(bot.cfg.series_path).read().splitlines()[-1])["virt_sol"], 11.158)

    def test_rpc_failure_falls_back_to_the_last_known_then_the_default(self):
        def broken(pool):
            raise RuntimeError("429")
        bot = self.bot(broken)
        bot.discover()
        pos = bot.p.positions["Aaapump"]
        self.assertEqual(pos.virt_sol, V)                                         # nothing read: cfg fallback is used
        self.assertAlmostEqual(pos.tokens, amm.buy(0.2, 85.0, 2.07e8, bot.cfg.fee, V))
        pos.virt_sol = 16.9
        bot.manage()
        self.assertEqual(bot.p.positions["Aaapump"].virt_sol, 16.9)                # kept when the read fails

    def test_backtest_uses_the_value_recorded_at_registration(self):
        p = pool(lambda m: 85.0)
        self.assertEqual(et.setup(p)["v"], V)                                     # old rows: fallback
        p["helius_reg"]["virt_sol"] = 11.158
        S = et.setup(p)
        self.assertEqual(S["v"], 11.158)
        self.assertAlmostEqual(S["k"], (85.0 + 11.158) * p["helius_reg"]["pool_tokens"])

    def test_fee_default_is_the_measured_one(self):
        self.assertEqual((BotConfig().fee, et.FEE, amm.PUMP_FEE), (0.012, 0.012, 0.012))


class RobustnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fail = set()
        self.rows = [row("Aaapump"), row("Bbbpump")]
        self.tg = FakeTG()

        def reserves(pool, mint):
            if mint in self.fail:
                raise RuntimeError("public RPC getTokenAccountsByOwner failed")
            return 85.0, 2.07e8
        self.bot = Bot(cfg_in(self.tmp), self.tg, reserves=reserves, rows=lambda path, **kw: self.rows)

    def test_seen_is_pruned_by_age_not_by_alphabet(self):
        p = Paper(cfg_in(self.tmp))
        for i in range(SEEN_KEEP + 10):
            p.seen.add(f"z{i:05d}")                       # old mints sort last alphabetically ...
        p.seen.add("aNEWESTpump")                         # ... the newest one sorts first
        p.save()
        again = Paper(cfg_in(self.tmp))
        self.assertIn("aNEWESTpump", again.seen)
        self.assertNotIn("z00000", again.seen)
        self.assertEqual(len(again.seen), SEEN_KEEP)

    def test_old_state_file_with_a_plain_list_still_loads(self):
        cfg = cfg_in(self.tmp)
        with open(cfg.state_path, "w") as f:
            json.dump({"balance": 0.5, "day": "2026-11-11", "day_pnl": 0.0, "seen": ["b", "a"], "positions": {}}, f)
        p = Paper(cfg)
        self.assertEqual((p.balance, list(p.seen)), (0.5, ["b", "a"]))

    def test_failed_rpc_does_not_drop_the_candidate_for_good(self):
        self.fail = {"Aaapump"}
        self.bot.discover()
        self.assertEqual(list(self.bot.p.positions), ["Bbbpump"])    # the other candidate is unaffected
        self.assertNotIn("Aaapump", self.bot.p.seen)
        self.fail = set()
        self.bot.discover()                                          # next pass: RPC works again
        self.assertIn("Aaapump", self.bot.p.positions)

    def test_one_unreadable_pool_does_not_block_other_exits(self):
        self.bot.discover()
        self.fail = {"Aaapump"}
        for pos in self.bot.p.positions.values():
            pos.opened_at -= 3 * 3600                                # both are past max hold
        self.bot.manage()
        self.assertEqual(list(self.bot.p.positions), ["Aaapump"])    # Bbb was sold, Aaa waits for its pool

    def test_running_out_of_paper_balance_is_announced_once(self):
        self.bot.p.balance = 0.01
        self.rows.append(row("Cccpump"))
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})
        self.assertEqual(sum("Hết vốn paper" in m for m in self.tg.sent), 1)

    def test_a_silent_collector_is_announced_once_and_its_return_too(self):
        old = row("Oldpump")
        old["registered_at"] = NOW - 40 * 60                         # nothing registered for 40 minutes
        self.rows[:] = [old]
        self.bot.discover()
        self.bot.discover()
        self.assertEqual(sum("Bộ thu thập không ghi pool mới" in m for m in self.tg.sent), 1)
        self.rows.append(row("Newpump"))
        self.bot.discover()
        self.assertEqual(sum("đã chạy lại" in m for m in self.tg.sent), 1)
        self.rows[:] = []                                            # an empty cohort tail is also "down"
        self.bot.discover()
        self.assertEqual(sum("Bộ thu thập không ghi pool mới" in m for m in self.tg.sent), 2)

    def test_watchlist_with_a_fail_verdict_is_empty(self):
        path = os.path.join(self.tmp, "w.json")
        for verdict, want in (("FAIL: no reliable out-of-sample edge", []), ("PASS: kept an edge", ["W1", "W2"])):
            with open(path, "w") as f:
                json.dump({"verdict": verdict, "wallets": ["W1", "W2"]}, f)
            self.assertEqual(load_watchlist(path), want)
        with open(path, "w") as f:
            json.dump(["W3"], f)                                     # a hand-written list has no verdict
        self.assertEqual(load_watchlist(path), ["W3"])

    def test_helius_inspect_helper_no_longer_crashes(self):
        old = helius.rpc
        try:
            helius.rpc = lambda method, params: {"value": {"owner": helius.SYSTEM_PROGRAM}}
            self.assertEqual(helius.owner_kind("Wallet111"), "wallet")
            helius.rpc = lambda method, params: {"value": None}
            self.assertIn("no-account", helius.owner_kind("Pda111"))
        finally:
            helius.rpc = old



class ResetPaperTest(unittest.TestCase):
    def test_old_ledger_is_archived_and_a_clean_one_opened(self):
        from memebot.bot.reset_paper import reset
        tmp = tempfile.mkdtemp()
        cfg = cfg_in(tmp)
        p = Paper(cfg)
        p.balance, p.total_pnl = 0.0016, -0.9984
        p.seen.add("Oldpump")
        p.log(action="skip", mint="Oldpump", reason="x")
        p.save()
        folder = reset(cfg, stamp="T", out=lambda *_: None)
        self.assertEqual(sorted(os.listdir(folder)), ["l.jsonl", "s.json"])        # nothing is deleted
        with open(os.path.join(folder, "s.json")) as f:
            self.assertEqual(json.load(f)["balance"], 0.0016)
        fresh = Paper(cfg)
        self.assertEqual((fresh.balance, fresh.total_pnl, len(fresh.seen), fresh.positions), (1.0, 0.0, 0, {}))
        self.assertFalse(os.path.exists(cfg.log_path))


if __name__ == "__main__":
    unittest.main()
