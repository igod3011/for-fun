import os
import tempfile
import unittest

from memebot.bot.telegram import Telegram
from memebot.pelluca import web
from memebot.pelluca.bot import CHECKS_PER_DAY, PellucaBot
from memebot.pelluca.limits import RateLimit
from memebot.pelluca.watch import Watches

MINT = "2cMcMEX3Eqo86tUrVe5dgHp5GZNwqQ6crqm22UeZpump"


def facts(**kw):
    f = {"mint": MINT, "checked_at": 1000.0, "pool": "P", "pool_sol": 80.0, "pool_tok": 2e8, "virt": 42.0,
         "lp_live": 0.0, "mint_auth": None, "freeze_auth": None, "top10": 0.3, "top1": 0.05, "dev_pct": 0.0,
         "history": {"n": 0, "drained": 0, "factory": False}, "dex": {"name": "LEO", "mcap": 5000.0}}
    f.update(kw)
    return f


class RateLimitTest(unittest.TestCase):
    def test_hour_then_day(self):
        t = [0.0]
        lim = RateLimit(per_hour=2, per_day=3, clock=lambda: t[0])
        self.assertIsNone(lim.take("a"))
        self.assertIsNone(lim.take("a"))
        self.assertEqual(lim.take("a"), "hour")
        self.assertIsNone(lim.take("b"))                     # per key
        t[0] = 3601
        self.assertIsNone(lim.take("a"))                     # new hour
        t[0] = 7300
        self.assertEqual(lim.take("a"), "day")               # 3 in 24 h
        t[0] = 86401
        self.assertIsNone(lim.take("a"))                     # first two expired


class BotDailyLimitTest(unittest.TestCase):
    def test_daily_limit(self):
        with tempfile.TemporaryDirectory() as d:
            t = [0.0]
            tg = Telegram("t", transport=lambda m, p: {"result": []})
            bot = PellucaBot(tg, Watches(os.path.join(d, "w.json")), gather=lambda m: facts(), clock=lambda: t[0])
            for i in range(CHECKS_PER_DAY):
                t[0] = i * 200.0                             # spread out: under the hourly limit
                self.assertNotIn("limit", bot.handle(5, f"/check {MINT}").lower())
            t[0] = CHECKS_PER_DAY * 200.0
            self.assertIn("Daily limit", bot.handle(5, f"/check {MINT}"))


class ReportJsonTest(unittest.TestCase):
    def test_clean(self):
        r = web.report_json(facts())
        self.assertEqual(r["verdict"], "NO MAJOR FLAGS FOUND")
        self.assertEqual((r["name"], r["pool_sol"], r["flags"]), ("LEO", 80.0, []))
        self.assertIn("round_trip_loss", r["exit"])

    def test_drained(self):
        r = web.report_json(facts(pool_sol=3.9))
        self.assertEqual(r["verdict"], "HIGH RISK")
        self.assertEqual(r["flags"][0]["level"], "red")
        self.assertNotIn("exit", r)

    def test_no_pool(self):
        r = web.report_json({"mint": MINT, "checked_at": 1.0, "pool": None, "dex": None})
        self.assertEqual(r["verdict"], "UNKNOWN")


class MarkdownTest(unittest.TestCase):
    def test_subset(self):
        h = web.md_to_html("# T\n\nA **b** and *c* and `d` <x>.\n\n- one\n  more\n- two\n\n## 2. Sec\ntext")
        self.assertIn('<h1 id="t">T</h1>', h)
        self.assertIn("<p>A <strong>b</strong> and <em>c</em> and <code>d</code> &lt;x&gt;.</p>", h)
        self.assertIn("<ul><li>one more</li><li>two</li></ul>", h)
        self.assertIn('<h2 id="2-sec">2. Sec</h2>', h)

    def test_real_terms_render(self):
        page = web.terms_page()
        self.assertNotIn("<!--TERMS-->", page)
        self.assertIn('id="6-pelluca-meme-studio"', page)     # linked from /studio
        self.assertNotIn("**", page)


class HttpPartsTest(unittest.TestCase):
    def test_static_path(self):
        self.assertTrue(web.static_path("style.css"))
        for bad in ("../web.py", ".env", "a/b.css", "web.py", "missing.css", ""):
            self.assertIsNone(web.static_path(bad), bad)

    def test_client_ip(self):
        self.assertEqual(web.client_ip("1.2.3.4", {"X-Forwarded-For": "9.9.9.9"}), "1.2.3.4")   # not from proxy
        self.assertEqual(web.client_ip("127.0.0.1", {"X-Forwarded-For": "8.8.8.8, 5.6.7.8"}), "5.6.7.8")
        self.assertEqual(web.client_ip("127.0.0.1", {}), "127.0.0.1")

    def test_api_check(self):
        app = web.App(gather=lambda m: facts(), limit=RateLimit(per_hour=1, per_day=5))
        self.assertEqual(app.api_check("nope", "ip")[0], 400)
        status, body = app.api_check(MINT, "ip")
        self.assertEqual((status, body["verdict"]), (200, "NO MAJOR FLAGS FOUND"))
        self.assertEqual(app.api_check(MINT, "ip")[0], 429)
        self.assertEqual(app.api_check(MINT, "other")[0], 200)

    def test_api_errors(self):
        def boom(m):
            raise RuntimeError("rpc down")
        app = web.App(gather=boom)
        self.assertEqual(app.api_check(MINT, "ip")[0], 502)
        app = web.App(gather=lambda m: facts())
        for _ in range(web.BUSY_SLOTS):
            app.slots.acquire()
        self.assertEqual(app.api_check(MINT, "ip")[0], 503)


if __name__ == "__main__":
    unittest.main()


class WrongPoolBugTest(unittest.TestCase):
    """19/11/2026: a live coin showed 'pool 0.00 SOL, mcap $132B, liquidity gone'."""
    WSOL = "So11111111111111111111111111111111111111112"

    def pair(self, addr, dex, quote, liq, mcap, base=MINT):
        return {"chainId": "solana", "pairAddress": addr, "dexId": dex, "priceUsd": "0.0001", "priceNative": "1e-6",
                "baseToken": {"address": base, "symbol": "DCTY"}, "quoteToken": {"address": quote},
                "liquidity": {"usd": liq}, "marketCap": mcap, "priceChange": {"h24": 500}}

    def test_parse_dex_skips_junk_quote_and_prefers_own_pool(self):
        from memebot.pelluca import check
        d = {"pairs": [self.pair("JUNK", "pumpswap", "JunkMint", 9e12, 1.3e11),
                       self.pair("BIG", "raydium", self.WSOL, 50000, 900000),
                       self.pair("OURS", "pumpswap", self.WSOL, 20000, 880000)]}
        x = check.parse_dex(d, mint=MINT, pool="OURS")
        self.assertEqual((x["pair"], x["mcap"], x["top_pair"]), ("OURS", 880000, "BIG"))
        self.assertEqual(check.parse_dex(d, mint=MINT)["pair"], "BIG")
        absurd = {"pairs": [self.pair("X", "pumpswap", self.WSOL, 10, 1.3e11)]}
        self.assertIsNone(check.parse_dex(absurd, mint=MINT)["mcap"])

    def test_empty_pumpswap_pool_but_trading_elsewhere_is_not_drained(self):
        from memebot.pelluca import check
        f = facts(pool="OURS", pool_sol=0.0, dex={"top_pair": "CURVE", "top_dex": "pumpfun", "top_liq_usd": 30000})
        flags, verdict = check.assess(f)
        self.assertNotIn("Liquidity is gone", " ".join(t for _, t in flags))
        self.assertIn("bonding curve", flags[0][1])
        self.assertEqual(flags[0][0], "amber")

    def test_unread_balance_is_not_zero(self):
        from unittest import mock
        from memebot.pelluca import chain, check
        pool = {"pool": "P", "sol_acc": "S", "tok_acc": "T", "virt_sol": 30.0, "coin_creator": None,
                "lp_mint": "L", "lp_supply": 100}
        with mock.patch.object(chain, "pools_for_mint", return_value=[dict(pool)]), \
             mock.patch.object(chain, "token_balances", return_value={}), \
             mock.patch.object(chain, "supply_raw", return_value=0), \
             mock.patch.object(chain, "supply", return_value=1e9), \
             mock.patch.object(chain, "largest_accounts", return_value=[]), \
             mock.patch.object(check.rpc, "mint_authorities", return_value=(None, None)):
            f = check.gather(MINT, _call=lambda *a: None, dex=lambda m: None, now=1.0, _sleep=lambda s: None)
        self.assertIsNone(f["pool_sol"])
        flags, verdict = check.assess(f)
        self.assertNotEqual(verdict, "HIGH RISK")
        self.assertIn("could not be read", flags[0][1])
        check.render(f)                                      # no crash on a missing balance
        web.report_json(f)


class MarketCapTest(unittest.TestCase):
    def test_from_pool_reserves(self):
        from memebot.pelluca import check
        # (80 + 20) SOL / 2e8 tokens = 5e-7 SOL; x 1e9 supply x $150 = $75,000
        f = facts(pool_sol=80.0, pool_tok=2e8, virt=20.0, supply=1e9, dex={"sol_usd": 150.0, "mcap": 17.7e6})
        mcap, src = check.market_cap(f)
        self.assertAlmostEqual(mcap, 75000.0)
        self.assertEqual(src, "chain")
        self.assertEqual(web.report_json(f)["mcap_source"], "chain")

    def test_falls_back_to_dexscreener(self):
        from memebot.pelluca import check
        self.assertEqual(check.market_cap(facts(supply=None, dex={"sol_usd": 150.0, "mcap": 5000.0})), (5000.0, "dex"))
        self.assertEqual(check.market_cap(facts(pool_sol=None, supply=1e9, dex={"mcap": 1.0})), (1.0, "dex"))


class DctyRegressionTest(unittest.TestCase):
    """Real DexScreener pairs of 9hjB...pump on 19/11/2026 (from check.py --debug on the VPS)."""
    WSOL = "So11111111111111111111111111111111111111112"

    def raw(self):
        def pr(addr, dex, quote, liq, mcap, price):
            return {"chainId": "solana", "pairAddress": addr, "dexId": dex, "priceUsd": price, "priceNative": "0.0002",
                    "baseToken": {"address": MINT, "symbol": "DCTY"}, "quoteToken": {"address": quote},
                    "liquidity": {"usd": liq}, "marketCap": mcap, "priceChange": {"h24": 10}}
        return {"pairs": [pr("DChX", "pumpswap", "TTWOmint", 487724.46, 13022266, "0.0137"),
                          pr("3gUa", "meteora", self.WSOL, 412546.14, 12730365, "0.01346"),
                          pr("D9Yy", "pumpswap", self.WSOL, 0, 17732250, "0.01875"),
                          pr("6Mpq", "meteora", "MMmint", 15287270.47, 132042015971, "139.6")]}

    def test_empty_own_pool_quotes_main_pair(self):
        from unittest import mock
        from memebot.pelluca import chain, check
        pool = {"pool": "D9Yy", "sol_acc": "S", "tok_acc": "T", "virt_sol": None, "coin_creator": None,
                "lp_mint": "L", "lp_supply": 100}
        with mock.patch.object(chain, "pools_for_mint", return_value=[dict(pool)]), \
             mock.patch.object(chain, "token_balances", return_value={"S": 3.4e-6, "T": 0.0002}), \
             mock.patch.object(chain, "supply_raw", return_value=0), \
             mock.patch.object(chain, "supply", return_value=945631721.98), \
             mock.patch.object(chain, "largest_accounts", return_value=[("A", 1.7e7)] + [("B", 1.27e7)] * 9), \
             mock.patch.object(check.rpc, "mint_authorities", return_value=(None, None)):
            f = check.gather(MINT, _call=lambda *a: None, dex=lambda m: self.raw(), now=1.0, _sleep=lambda s: None)
        self.assertEqual(f["dex"]["pair"], "3gUa")
        self.assertEqual(check.market_cap(f), (12730365, "dex"))
        r = web.report_json(f)
        self.assertEqual((r["venue"], r["liq_usd"]), ("meteora", 412546.14))
        flags, verdict = check.assess(f)
        self.assertNotIn("Liquidity is gone", " ".join(t for _, t in flags))
        self.assertEqual(verdict, "LIMITED CHECK")            # the Meteora pool's LP is not checked: say so
        self.assertIn("Main liquidity: ~$412,546 on meteora", check.render(f, html=False))


class CacheBustTest(unittest.TestCase):
    def test_versioned_links(self):
        h = web.versioned('<link href="/static/style.css"><script src="/static/app.js" defer></script><img src="/static/logo.svg">')
        self.assertRegex(h, r'/static/style\.css\?v=\d+"')
        self.assertRegex(h, r'/static/app\.js\?v=\d+"')
        self.assertIn('/static/logo.svg"', h)                  # images keep plain URLs
