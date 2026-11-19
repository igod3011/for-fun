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
