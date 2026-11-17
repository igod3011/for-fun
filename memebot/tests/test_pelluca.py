import base64
import os
import tempfile
import unittest

from memebot.bot.telegram import Telegram
from memebot.pelluca import chain, check, drain_eval
from memebot.pelluca.bot import CHECKS_PER_HOUR, PellucaBot
from memebot.pelluca.watch import Watches, drain_alert

MINT = "2cMcMEX3Eqo86tUrVe5dgHp5GZNwqQ6crqm22UeZpump"
CREATOR = "JBMCwSKt2Zt3jL9zKaQtbk3HHB15jYrmGZLhUaEMMQGn"


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + chain.B58.index(ch)
    raw = n.to_bytes(32, "big")
    return raw


def pool_bytes(mint=MINT, creator=CREATOR, virt_lamports=17_584_000_000):
    raw = bytearray(301)
    raw[43:75] = b58decode(mint)
    raw[75:107] = b58decode(chain.WSOL)
    raw[139:171] = b58decode("DYniKwL55zofpNwZi75TBx2sJnKJarAAuiS9UWtprpXy")
    raw[171:203] = b58decode("HSM68DESjoTzMJDVeUdVLb1qHZd7zMh648ihrJZKaDQj")
    raw[211:243] = b58decode(creator) if creator else bytes(32)
    raw[245:253] = virt_lamports.to_bytes(8, "little")
    return bytes(raw)


def healthy(**kw):
    f = {"mint": MINT, "checked_at": 1e9, "pool": "P", "pool_sol": 85.0, "pool_tok": 2.0e8, "virt": 17.58,
         "mint_auth": None, "freeze_auth": None, "lp_live": 0.0, "top1": 0.04, "top10": 0.25, "top10_tokens": 2.5e7, "dev_pct": 0.0,
         "history": {"n": 0, "drained": 0, "factory": False}, "dex": {"change_h1": 0.1}}
    f.update(kw)
    return f


class ChainTest(unittest.TestCase):
    def test_parse_pool_roundtrip(self):
        p = chain.parse_pool(pool_bytes())
        self.assertEqual(p["base_mint"], MINT)
        self.assertEqual(p["quote_mint"], chain.WSOL)
        self.assertEqual(p["coin_creator"], CREATOR)
        self.assertAlmostEqual(p["virt_sol"], 17.584)

    def test_parse_pool_null_creator_and_short(self):
        self.assertIsNone(chain.parse_pool(pool_bytes(creator=None))["coin_creator"])
        self.assertIsNone(chain.parse_pool(b"\0" * 100))

    def test_is_address(self):
        self.assertTrue(chain.is_address(MINT))
        self.assertFalse(chain.is_address("hello"))
        self.assertFalse(chain.is_address("0OIl" * 10))

    def test_pools_for_mint_uses_memcmp(self):
        offsets = []
        normal = base64.b64encode(pool_bytes()).decode()
        raw = bytearray(pool_bytes())
        raw[43:75], raw[75:107] = b58decode(chain.WSOL), b58decode(MINT)        # SOL as base: hand-made pool
        reversed_ = base64.b64encode(bytes(raw)).decode()

        def fake(method, params):
            self.assertEqual(method, "getProgramAccounts")
            off = params[1]["filters"][0]["memcmp"]["offset"]
            offsets.append(off)
            data = normal if off == 43 else reversed_
            return [{"pubkey": f"POOL{off}", "account": {"data": [data]}}]
        out = chain.pools_for_mint(MINT, _call=fake)
        self.assertEqual(offsets, [43, 75])
        self.assertEqual([p["pool"] for p in out], ["POOL43", "POOL75"])
        self.assertEqual(out[0]["sol_acc"], out[0]["quote_acc"])
        self.assertEqual(out[1]["sol_acc"], out[1]["base_acc"])
        self.assertEqual(out[1]["virt_sol"], 0.0)                                  # never a migration


class CheckTest(unittest.TestCase):
    def test_parse_dex_sol_usd(self):
        d = {"pairs": [{"chainId": "solana", "priceUsd": "0.002", "priceNative": "0.00001", "liquidity": {"usd": 5},
                        "priceChange": {"h1": -50}, "baseToken": {"symbol": "X"}}]}
        x = check.parse_dex(d)
        self.assertAlmostEqual(x["sol_usd"], 200)
        self.assertAlmostEqual(x["change_h1"], -0.5)
        self.assertIsNone(check.parse_dex({"pairs": []}))

    def test_healthy_has_no_flags(self):
        flags, verdict = check.assess(healthy())
        self.assertEqual([l for l, _ in flags if l != "info"], [])
        self.assertEqual(verdict, "NO MAJOR FLAGS FOUND")

    def test_red_flags(self):
        for kw in ({"pool_sol": 2.0}, {"virt": 0, "lp_live": None}, {"lp_live": 1.0}, {"mint_auth": "X"}, {"freeze_auth": "X"}, {"top1": 0.6},
                   {"history": {"n": 5, "drained": 5, "factory": False}}, {"history": {"n": 201, "factory": True}},
                   {"pool_sol": 20.0}, {"dex": {"change_h1": -0.9}}):
            flags, verdict = check.assess(healthy(**kw))
            self.assertEqual(verdict, "HIGH RISK", kw)

    def test_handmade_pool_with_burnt_lp_is_not_red(self):
        self.assertEqual(check.assess(healthy(virt=0, lp_live=0.0))[1], "NO MAJOR FLAGS FOUND")

    def test_no_pool(self):
        self.assertEqual(check.assess({"mint": MINT, "pool": None})[1], "UNKNOWN")

    def test_amber_needs_two(self):
        self.assertEqual(check.assess(healthy(dev_pct=0.05))[1], "NO MAJOR FLAGS FOUND")
        self.assertEqual(check.assess(healthy(dev_pct=0.05, top10=0.1))[1], "ELEVATED RISK")

    def test_exit_math(self):
        ex = check.exit_math(healthy())
        self.assertTrue(0.02 < ex["round_trip_loss"] < 0.05)          # two 1.2% fees + impact
        self.assertTrue(0 < ex["top10_drain"] < 1)
        self.assertIsNone(check.exit_math(healthy(pool_sol=1.0)))

    def test_render_mentions_base_rate_and_disclaimer(self):
        text = check.render(healthy(dex={"name": "<b>X", "price_usd": 0.001, "mcap": 5000, "change_h1": 0.1}))
        self.assertIn("Not financial advice", text)
        self.assertIn("&lt;b&gt;X", text)                              # token names are escaped


class WatchTest(unittest.TestCase):
    def test_drain_alert(self):
        h = [(0, 80.0), (60, 78.0), (120, 50.0)]
        self.assertTrue(drain_alert(h, 120)[0])                        # -37% within 10 min
        self.assertFalse(drain_alert([(0, 80.0), (60, 70.0)], 60)[0])  # -12.5%
        self.assertFalse(drain_alert([(0, 80.0), (1200, 50.0)], 1200)[0])   # slow bleed outside the window
        self.assertTrue(drain_alert([(0, 4.0)], 0)[0])

    def test_watches_alert_once_then_rearm(self):
        with tempfile.TemporaryDirectory() as d:
            w = Watches(os.path.join(d, "w.json"))
            self.assertTrue(w.add(1, MINT, "P", "Q", "X"))
            self.assertEqual(w.step({"Q": 80.0}, 0), [])
            self.assertEqual(len(w.step({"Q": 50.0}, 60)), 1)
            self.assertEqual(w.step({"Q": 30.0}, 120), [])                # same episode: no repeat
            w.step({"Q": 81.0}, 4000)                                       # recovered -> re-armed
            self.assertTrue(w.of(1)[MINT]["armed"])
            self.assertEqual(Watches(os.path.join(d, "w.json")).of(1)[MINT]["name"], "X")   # persisted

    def test_watch_limit(self):
        with tempfile.TemporaryDirectory() as d:
            w = Watches(os.path.join(d, "w.json"))
            for i in range(10):
                self.assertTrue(w.add(1, f"M{i}", "P", f"Q{i}", "X"))
            self.assertFalse(w.add(1, "M10", "P", "Q10", "X"))


class BotTest(unittest.TestCase):
    def make(self, d):
        sent = []
        tg = Telegram("t", transport=lambda m, p: sent.append(p) or {"result": []})
        bot = PellucaBot(tg, Watches(os.path.join(d, "w.json")),
                         gather=lambda mint: healthy(mint=mint, sol_acc="Q", dex={"name": "X"}),
                         balances=lambda accs: {a: 10.0 for a in accs}, clock=lambda: 1000.0)
        return bot, sent

    def test_commands(self):
        with tempfile.TemporaryDirectory() as d:
            bot, _ = self.make(d)
            self.assertIn("/check", bot.handle(5, "/start"))
            self.assertIn("NO MAJOR FLAGS", bot.handle(5, MINT))            # bare address = /check
            self.assertIn("Send it like this", bot.handle(5, "/check abc"))
            self.assertIn("Watching", bot.handle(5, f"/watch {MINT}"))
            self.assertIn(MINT, bot.handle(5, "/list"))
            self.assertIn("Stopped", bot.handle(5, f"/unwatch {MINT}"))

    def test_rate_limit(self):
        with tempfile.TemporaryDirectory() as d:
            bot, _ = self.make(d)
            for _ in range(CHECKS_PER_HOUR):
                bot.handle(5, f"/check {MINT}")
            self.assertIn("Limit reached", bot.handle(5, f"/check {MINT}"))
            self.assertIn("NO MAJOR FLAGS", bot.handle(6, f"/check {MINT}"))   # per chat

    def test_watch_pass_sends_alert(self):
        with tempfile.TemporaryDirectory() as d:
            bot, sent = self.make(d)
            bot.handle(5, f"/watch {MINT}")
            self.assertEqual(bot.watch_pass(), 0)                           # 10 SOL, nothing happened yet
            bot.balances = lambda accs: {a: 3.0 for a in accs}
            self.assertEqual(bot.watch_pass(), 1)                           # under 5 SOL: drained
            self.assertEqual(str(sent[-1]["chat_id"]), "5")
            self.assertIn("liquidity is gone", sent[-1]["text"])


class DrainEvalTest(unittest.TestCase):
    def item(self, sols, s1, s0=80.0):
        S = {"s0": s0, "s1": s1}
        return (S, [(i * 60, s) for i, s in enumerate(sols)], drain_eval.outcome(S))

    def test_evaluate(self):
        items = [self.item([80, 79, 50, 20, 1], 1.0),        # dead, alerted at 50 (>= 40): caught
                 self.item([80, 80, 80, 79], 2.0),            # dead, never alerted: missed
                 self.item([80, 50, 75, 80], 79.0)]           # survived but alerted: false alarm
        r = drain_eval.evaluate(items, 0.3, 10)
        self.assertEqual(r["dead"], 2)
        self.assertAlmostEqual(r["caught"], 0.5)
        self.assertEqual(r["alerts"], 2)
        self.assertAlmostEqual(r["false"], 0.5)

    def test_pick_prefers_low_false(self):
        rs = [{"caught": 0.9, "false": 0.5}, {"caught": 0.6, "false": 0.1}, {"caught": 0.4, "false": 0.05}]
        self.assertEqual(drain_eval.pick(rs)["caught"], 0.6)


if __name__ == "__main__":
    unittest.main()
