import random
import tempfile
import unittest
from dataclasses import replace

from memebot.bot.config import BotConfig
from memebot.bot.runner import Bot
from memebot.bot.wallets import WalletWatcher, buys_in_tx
from memebot.helius import top_owners
from memebot.ml.wallet_scores import evaluate, score_wallets
from memebot.tests.test_bot import FakeTG, cfg_in

WSOL = "So11111111111111111111111111111111111111112"


class TopOwnersTest(unittest.TestCase):
    def test_sorted_pool_excluded_shares_of_total(self):
        accs = [{"owner": "POOL", "amount": "600"}, {"owner": "A", "amount": "100"}, {"owner": "B", "amount": "250"},
                {"owner": "B", "amount": "50"}]
        self.assertEqual(top_owners(accs, ["POOL"], 10), [["B", 0.3], ["A", 0.1]])


def cohort(rng, n, smart_edge):
    """SMART is an early holder in some pools; its pools win with prob 0.6 if smart_edge else base 0.12."""
    out = []
    for i in range(n):
        holders = [[f"rnd{rng.randrange(400)}", 0.01] for _ in range(9)]
        has_smart = rng.random() < 0.2
        if has_smart:
            holders.append(["SMART", 0.02])
        if i % 7 == 0:
            holders.append(["DEV", 0.4])                    # big holder: must be ignored
        p_win = 0.6 if (has_smart and smart_edge) else 0.12
        out.append((holders, 0.5 if rng.random() < p_win else -0.95))
    return out


class WalletScoreTest(unittest.TestCase):
    def test_persistent_wallet_is_found_and_passes_out_of_sample(self):
        data = cohort(random.Random(1), 1200, smart_edge=True)
        base, scored = score_wallets(data[:720])
        top = [w for *_, w in scored[:5]]
        self.assertEqual(top[0], "SMART")
        self.assertNotIn("DEV", [w for *_, w in scored])
        hit, miss, dh, dm = evaluate(data[720:], {"SMART"})
        self.assertGreater(sum(v > 0 for v in hit) / len(hit), sum(v > 0 for v in miss) / len(miss) + 0.2)

    def test_lucky_wallets_do_not_carry_over(self):
        data = cohort(random.Random(2), 1200, smart_edge=False)
        _, scored = score_wallets(data[:720])
        sel = {w for *_, w in scored[:30]}
        hit, miss, _, _ = evaluate(data[720:], sel)
        diff = sum(v > 0 for v in hit) / max(len(hit), 1) - sum(v > 0 for v in miss) / max(len(miss), 1)
        self.assertLess(diff, 0.1)


def tx(wallet, pre, post, err=None):
    bal = lambda d: [{"owner": wallet, "mint": m, "uiTokenAmount": {"uiAmount": v}} for m, v in d.items()]
    return {"meta": {"err": err, "preTokenBalances": bal(pre), "postTokenBalances": bal(post)}}


class TxParseTest(unittest.TestCase):
    def test_buy_detected_quote_and_sells_ignored(self):
        self.assertEqual(buys_in_tx(tx("W", {WSOL: 5}, {WSOL: 1, "Mpump": 1000}), "W"), ["Mpump"])
        self.assertEqual(buys_in_tx(tx("W", {"Mpump": 1000}, {"Mpump": 0, WSOL: 4}), "W"), [])
        self.assertEqual(buys_in_tx(tx("W", {}, {"Mpump": 5}, err={"x": 1}), "W"), [])
        self.assertEqual(buys_in_tx(tx("OTHER", {}, {"Mpump": 5}), "W"), [])


class WatcherTest(unittest.TestCase):
    def test_baseline_then_new_buys(self):
        state = {"sigs": [{"signature": "s1"}]}
        txs = {"s2": tx("W", {}, {"Npump": 9}), "s3": tx("W", {"Npump": 9}, {"Npump": 0})}

        def rpc(method, params):
            return state["sigs"] if method == "getSignaturesForAddress" else txs[params[0]]
        w = WalletWatcher(["W"], rpc)
        self.assertEqual(w.poll(), [])                              # baseline only
        state["sigs"] = [{"signature": "s3"}, {"signature": "s2"}, {"signature": "s1"}]
        self.assertEqual(w.poll(), [("W", "Npump")])                # buy in s2; s3 is a sell
        self.assertEqual(w.poll(), [])                              # nothing new


class FakeWatcher:
    def __init__(self):
        self.queue = []

    def poll(self):
        out, self.queue = self.queue, []
        return out


class FollowBotTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.w = FakeWatcher()
        self.tg = FakeTG()
        self.bot = Bot(cfg_in(tmp, follow_enabled=True, follow_min_wallets=2), self.tg,
                       reserves=lambda pool, mint: (85.0, 2.07e8), rows=lambda p: [],
                       watcher=self.w, find_pool=lambda mint: "POOL_" + mint)

    def test_needs_two_wallets_and_pump_mint(self):
        self.w.queue = [("W1", "Xpump"), ("W1", "notpmp")]
        self.bot.follow_step()
        self.assertEqual(self.bot.p.positions, {})
        self.w.queue = [("W2", "Xpump")]
        self.bot.follow_step()
        self.assertEqual(list(self.bot.p.positions), ["Xpump"])
        self.assertTrue(any("FOLLOW BUY" in m for m in self.tg.sent))
        self.w.queue = [("W3", "Xpump")]                            # no double entry
        self.bot.follow_step()
        self.assertAlmostEqual(self.bot.p.balance, 0.95)


if __name__ == "__main__":
    unittest.main()
