import tempfile
import unittest
from dataclasses import replace

from memebot.bot.config import BotConfig
from memebot.bot.intel import fmt_price, fmt_usd, intel_check, parse_dex, parse_rugcheck
from memebot.bot.runner import Bot
from memebot.ml import entry_timing as et
from memebot.tests.test_bot import FakeTG, cfg_in, row
from memebot.tests.test_entry_timing import T0, pool

REP = {"creator": "DEV", "creatorBalance": 50_000_000_000_000, "token": {"supply": 1_000_000_000_000_000},
       "creatorTokens": [{"mint": "a"}, {"mint": "b"}],
       "risks": [{"name": "Creator history of rugged tokens"}, {"name": "Low Liquidity"}],
       "topHolders": [{"pct": 6.0, "insider": True}, {"pct": 5.5, "insider": True}, {"pct": 9.0, "insider": False}]}
DEX = {"pairs": [{"chainId": "solana", "pairAddress": "OTHER", "priceUsd": "0.1", "marketCap": 1, "liquidity": {"usd": 9e9}},
                 {"chainId": "solana", "pairAddress": "POOL", "priceUsd": "0.0000397", "marketCap": 39788.66,
                  "priceChange": {"h1": 567, "m5": 31.8}, "liquidity": {"usd": 12000}, "dexId": "pumpswap"}]}
CLEAN_RC = {"creator": "D", "dev_pct": 0.0, "creator_rugs": False, "creator_launches": 0, "insider_pct": 0.02,
            "insiders_detected": 0, "risks": []}
CLEAN_DX = {"price_usd": 0.0000397, "mcap": 39788.66, "change_h1": 0.12, "change_m5": 0.01, "liq_usd": 12000,
            "dex": "pumpswap"}


class ParseTest(unittest.TestCase):
    def test_rugcheck(self):
        rc = parse_rugcheck(REP)
        self.assertAlmostEqual(rc["dev_pct"], 0.05)
        self.assertTrue(rc["creator_rugs"])
        self.assertEqual(rc["creator_launches"], 2)
        self.assertAlmostEqual(rc["insider_pct"], 0.115)

    def test_dex_picks_our_pool(self):
        dx = parse_dex(DEX, pool="POOL")
        self.assertEqual((dx["mcap"], dx["change_h1"]), (39788.66, 5.67))

    def test_rules(self):
        cfg = BotConfig()
        ok, why = intel_check(parse_rugcheck(REP), parse_dex(DEX, "POOL"), cfg)
        self.assertFalse(ok)
        for want in ("dev holds 5.0%", "creator has rugged", "already +567% in 1h"):
            self.assertTrue(any(want in w for w in why), (want, why))
        self.assertEqual(intel_check(CLEAN_RC, CLEAN_DX, cfg), (True, []))
        self.assertFalse(intel_check(None, CLEAN_DX, cfg)[0])           # no RugCheck data: do not buy blind

    def test_format(self):
        self.assertEqual(fmt_usd(39788.66), "$39.8K")
        self.assertEqual(fmt_usd(2_500_000), "$2.5M")
        self.assertEqual(fmt_price(0.0000397), "$0.00003970")
        self.assertEqual(fmt_price(1.5), "$1.5000")


class BotIntelTest(unittest.TestCase):
    def setUp(self):
        self.res = {"sol": 85.0, "tok": 2.07e8}
        self.intel = {"rc": CLEAN_RC, "dx": CLEAN_DX}
        self.tg = FakeTG()
        self.bot = Bot(cfg_in(tempfile.mkdtemp()), self.tg, reserves=lambda p, m: (self.res["sol"], self.res["tok"]),
                       rows=lambda p, **kw: [row("Aaapump")], intel=lambda m, p: (self.intel["rc"], self.intel["dx"]))

    def test_buy_message_has_price_and_mcap_and_sell_shows_change(self):
        self.bot.discover()
        buy = self.tg.sent[-1]
        self.assertIn("MC $39.8K", buy)
        self.assertIn("Giá $0.00003970", buy)
        self.assertIn("Dev 0.0%", buy)
        self.assertNotIn("Insider", buy)                                    # the dead insider rule is gone
        self.res.update(sol=60.0, tok=2.07e8 * 85 / 60)                    # dump -> stop loss
        self.bot.manage()
        sell = self.tg.sent[-1]
        self.assertIn("PAPER SELL", sell)
        self.assertIn("MC $39.8K → $19.8K", sell)                           # price x(60/85)^2 ~ 0.498

    def test_creator_rug_history_blocks_entry(self):
        self.intel["rc"] = dict(CLEAN_RC, creator_rugs=True, creator_launches=7)
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})
        self.assertIn("creator has rugged before (7 launches)", open(self.bot.cfg.log_path).read())


class BacktestH1Test(unittest.TestCase):
    def test_already_pumped_entries_are_skipped(self):
        pumped = lambda m: 85.0 if m < 30 else (85.0 + (m - 30) * 85 / 60 if m < 90 else 170.0)   # price x4 in 1h
        S = et.setup(pool(pumped))
        self.assertIsNotNone(et.entry(S, T0, 90, guard=True, momentum=False))
        self.assertIsNone(et.entry(S, T0, 90, guard=True, momentum=False, max_h1=0.8))
        flat = et.setup(pool(lambda m: 85.0))
        self.assertIsNotNone(et.entry(flat, T0, 90, guard=True, momentum=False, max_h1=0.8))


if __name__ == "__main__":
    unittest.main()
