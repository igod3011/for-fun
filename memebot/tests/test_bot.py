import os
import tempfile
import time
import unittest
from dataclasses import replace

from memebot.bot.config import BotConfig
from memebot.bot.paper import Paper
from memebot.bot.runner import Bot
from memebot.bot.strategy import Position, entry_check, exit_decision
from memebot.bot.telegram import Telegram

NOW = time.time()


def row(mint="Abcpump", sol=85.0, tok=2.07e8, top10=0.2, age_s=300, **h):
    snap = {"pool_sol": sol, "pool_tokens": tok, "top10_pct": top10, "mint_authority": None, "freeze_authority": None}
    snap.update(h)
    return {"mint": mint, "pool": "POOL_" + mint, "name": mint[:3], "created": NOW - age_s - 60,
            "registered_at": NOW - 60, "helius_reg": snap}


def cfg_in(tmp, **kw):
    kw.setdefault("entry_delay_min", 0.0)               # most tests: buy at discovery
    kw.setdefault("virtual_quote_sol", 0.0)             # mechanics on plain constant product; virtual reserve: test_amm.py
    return replace(BotConfig(), state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"),
                   series_path=os.path.join(tmp, "series.jsonl"), **kw)


class EntryTests(unittest.TestCase):
    cfg = BotConfig()

    def test_canonical_pool_passes(self):
        self.assertEqual(entry_check(row(), self.cfg), (True, []))
        self.assertEqual(entry_check(row(top10=0.9, holders=300, top1_pct=0.3, virt_sol=17.58), self.cfg), (True, []))
        loose = replace(self.cfg, max_holders_reg=None, min_top10=None, max_top1=None)
        self.assertEqual(entry_check(row(top10=0.05, holders=5000, top1_pct=0.9), loose), (True, []))   # rules can be disabled

    def test_rejections(self):
        cases = {"not a pump.fun mint": row(mint="XYZabc"), "pool only": row(sol=5, tok=2e9),
                 "non-canonical": row(sol=559, tok=8.7e10), "top10 only": row(top10=0.05),
                 "wallet farm: 2500 holders": row(holders=2500), "no holder data": row(top10=None),
                 "one holder controls 80%": row(top10=0.8, top1_pct=0.7995),
                 "not a pump.fun migration": row(virt_sol=0.0),
                 "mint authority": row(mint_authority="X"), "too old": row(age_s=3600)}
        for want, r in cases.items():
            ok, why = entry_check(r, self.cfg)
            self.assertFalse(ok, want)
            self.assertTrue(any(want in w for w in why), (want, why))


class ExitTests(unittest.TestCase):
    # mechanics are tested with the old rule set (it exercises partial take-profits); new defaults tested below
    cfg = replace(BotConfig(), stop_loss=0.25, take_profit=[[0.5, 0.5], [1.0, 0.5]], trail_activate=0.3, trail=0.2,
                  max_hold_min=120.0, virtual_quote_sol=0.0)

    def pos(self):
        return Position("M", "P", "n", tokens=1.2e5, cost_sol=0.05, opened_at=NOW, entry_pool_sol=85, peak_pool_sol=85)

    def test_hold_when_flat(self):
        self.assertEqual(exit_decision(self.pos(), 85, 2.07e8, NOW, self.cfg)[0], 0.0)

    def test_dump_hits_stop_loss(self):
        frac, why = exit_decision(self.pos(), 50, 2.07e8 * 85 / 50, NOW, self.cfg)   # sellers dumped: price -65%
        self.assertEqual(frac, 1.0)
        self.assertIn("stop loss", why)

    def test_liquidity_pull_with_flat_price_hits_drain(self):
        p = self.pos()                                     # 0.05 SOL position: negligible impact on exit
        frac, why = exit_decision(p, 60, 2.07e8 * 60 / 85, NOW, self.cfg)   # both sides removed, price unchanged
        self.assertEqual(frac, 1.0)
        self.assertIn("drained", why)

    def test_take_profit_then_trailing(self):
        p = self.pos()
        frac, why = exit_decision(p, 85 * 1.3, 2.07e8 / 1.3, NOW, self.cfg)     # price x1.69 -> +50% TP hit
        self.assertEqual((frac, why.startswith("take profit")), (0.5, True))
        p.tokens *= 0.5
        p.realized_sol += 0.04
        frac, why = exit_decision(p, 85 * 0.95, 2.07e8 / 0.95, NOW, self.cfg)    # falls back hard -> trailing
        self.assertEqual(frac, 1.0)
        self.assertIn("trailing", why)

    def test_new_default_rules_tight_stop_and_trailing(self):
        cfg = BotConfig()
        self.assertEqual((cfg.entry_delay_min, cfg.stop_loss, cfg.take_profit, cfg.max_hold_min), (90.0, 0.10, [], 60.0))
        cfg = replace(cfg, virtual_quote_sol=0.0)
        p = self.pos()
        frac, why = exit_decision(p, 85 * 0.94, 2.07e8 / 0.94, NOW, cfg)           # price -12%
        self.assertEqual((frac, why.startswith("stop loss")), (1.0, True))
        p = self.pos()
        self.assertEqual(exit_decision(p, 85 * 1.12, 2.07e8 / 1.12, NOW, cfg)[0], 0.0)   # +25%: arm trailing
        frac, why = exit_decision(p, 85 * 1.04, 2.07e8 / 1.04, NOW, cfg)                 # back to ~+8%
        self.assertEqual((frac, "trailing" in why), (1.0, True))

    def test_max_hold(self):
        frac, why = exit_decision(self.pos(), 85, 2.07e8, NOW + 3 * 3600, self.cfg)
        self.assertEqual((frac, why), (1.0, "max hold time"))


class FakeTG:
    def __init__(self):
        self.sent, self.inbox, self.chat_id = [], [], "42"

    def send(self, text, html=False):
        self.sent.append(text)

    def poll(self):
        msgs, self.inbox = self.inbox, []
        return msgs

    def authorized(self, chat_id):
        return chat_id == "42"


class BotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.res = {"sol": 85.0, "tok": 2.07e8}
        self.rows = [row("Aaapump"), row("XYZnotpmp"), row("Bbbpump", top10=0.05)]
        self.tg = FakeTG()
        self.bot = Bot(cfg_in(self.tmp), self.tg, reserves=lambda pool, mint: (self.res["sol"], self.res["tok"]),
                       rows=lambda path, **kw: self.rows)

    def test_discover_buys_only_passing_rows_once(self):
        self.bot.discover()
        self.bot.discover()
        self.assertEqual(list(self.bot.p.positions), ["Aaapump"])
        self.assertAlmostEqual(self.bot.p.balance, 1 - 0.2 - 0.0003)         # stake + fixed tx fee

    def test_rug_drain_closes_position_and_reports(self):
        self.bot.discover()
        self.res.update(sol=10.0, tok=2.07e8 * 85 / 10)       # dumped to ~1/72 of the price
        self.bot.manage()
        self.assertEqual(self.bot.p.positions, {})
        self.assertLess(self.bot.p.total_pnl, -0.04)
        self.assertTrue(any("PAPER SELL" in m for m in self.tg.sent))

    def test_pause_blocks_new_entries_and_resume(self):
        self.assertIn("paused", self.bot.command("/pause"))
        before, pnl = self.bot.p.balance, self.bot.p.total_pnl
        self.assertIn("+5 paper SOL", self.bot.command("/topup 5"))
        self.assertAlmostEqual(self.bot.p.balance, before + 5)
        self.assertEqual(self.bot.p.total_pnl, pnl)                 # a deposit is not profit
        self.assertEqual(Paper(self.bot.cfg).deposited, 5)          # survives a restart
        for bad in ("/topup", "/topup abc", "/topup -3", "/topup 1000"):
            self.assertIn("usage", self.bot.command(bad))
        self.assertAlmostEqual(self.bot.p.balance, before + 5)
        self.assertIn('"deposit"', open(self.bot.cfg.log_path).read())
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})
        self.bot.command("/resume")
        self.rows.append(row("Cccpump"))
        self.bot.discover()
        self.assertEqual(list(self.bot.p.positions), ["Cccpump"])

    def test_review_and_series(self):
        self.bot.discover()
        self.bot.manage()                                       # flat: holds, but records a reserve point
        self.res.update(sol=10.0, tok=2.07e8 * 85 / 10)
        self.bot.manage()                                       # dumped: closes
        series = open(self.bot.cfg.series_path).read().splitlines()
        self.assertEqual(len(series), 2)
        text = self.bot.command("/review")
        self.assertIn("closed trades 1", text)
        self.assertIn("win rate 0%", text)
        self.assertIn("stop loss", text)
        self.assertIn("top skip reasons", text)

    def test_buy_and_sell_messages_carry_copyable_ca(self):
        self.bot.discover()
        self.res.update(sol=10.0, tok=2.07e8 * 85 / 10)
        self.bot.manage()
        buy = next(m for m in self.tg.sent if "PAPER BUY" in m)
        sell = next(m for m in self.tg.sent if "PAPER SELL" in m)
        for msg in (buy, sell):
            self.assertIn("CA: <code>Aaapump</code>", msg)
            self.assertIn("dexscreener.com/solana/Aaapump", msg)

    def test_html_failure_falls_back_to_plain_text(self):
        class Picky(FakeTG):
            def send(self, text, html=False):
                if html:
                    raise RuntimeError("telegram sendMessage: HTTP 400")
                self.sent.append(text)
        tg = Picky()
        self.bot.tg = tg
        self.bot.say("<b>x</b> CA: <code>M</code>", html=True)
        self.assertEqual(tg.sent, ["x CA: M"])

    def test_stop_sells_everything(self):
        self.bot.discover()
        msg = self.bot.command("/stop")
        self.assertFalse(self.bot.running)
        self.assertEqual(self.bot.p.positions, {})
        self.assertIn("stopping", msg)

    def test_falling_knife_and_low_liquidity_are_skipped(self):
        self.res.update(sol=60.0, tok=2.07e8 * 85 / 60)        # registered at 85 SOL, now 60: -29% SOL
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})
        log = open(self.bot.cfg.log_path).read()
        self.assertIn("falling knife", log)
        self.rows.append(row("Dddpump", sol=35, tok=2.07e8 * 85 / 35))   # under 40 SOL at registration
        self.res.update(sol=35.0, tok=2.07e8 * 85 / 35)
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})

    def test_delayed_entry_waits_then_buys_inside_window_only(self):
        self.bot.cfg = replace(self.bot.cfg, entry_delay_min=60.0, entry_window_min=30.0)
        young = row("Youngpump")                              # created ~6 min ago
        old = row("Oldpump")
        old["created"], old["registered_at"] = NOW - 65 * 60, NOW - 60 * 60
        late = row("Latepump")
        late["created"], late["registered_at"] = NOW - 200 * 60, NOW - 195 * 60
        self.rows[:] = [young, old, late]
        self.bot.discover()
        self.assertEqual(list(self.bot.p.positions), ["Oldpump"])
        self.assertNotIn("Youngpump", self.bot.p.seen)        # still watched, decided on a later pass
        self.assertIn("missed entry window", open(self.bot.cfg.log_path).read())
        young["created"] -= 60 * 60                            # an hour later (clock moves: shift both times)
        young["registered_at"] -= 60 * 60
        self.bot.discover()
        self.assertIn("Youngpump", self.bot.p.positions)

    def test_daily_loss_limit(self):
        self.bot.p.day_pnl = -0.65
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})

    def test_state_survives_restart(self):
        self.bot.discover()
        again = Paper(self.bot.cfg)
        self.assertEqual(list(again.positions), ["Aaapump"])
        self.assertIn("Aaapump", again.seen)


class TelegramTests(unittest.TestCase):
    def test_only_authorized_chat_and_offset(self):
        calls = []

        def transport(method, params, timeout=35):
            calls.append((method, params))
            if method == "getUpdates":
                return {"result": [{"update_id": 7, "message": {"chat": {"id": 42}, "text": "/status"}},
                                   {"update_id": 8, "message": {"chat": {"id": 99}, "text": "/stop"}}]}
            return {"ok": True}
        t = Telegram("TOKEN", "42", transport=transport)
        msgs = t.poll()
        self.assertEqual(t.offset, 9)
        self.assertEqual([t.authorized(c) for c, _ in msgs], [True, False])
        t.send("hi")
        self.assertEqual(calls[-1], ("sendMessage", {"chat_id": "42", "text": "hi", "disable_web_page_preview": True}))
        t.send("<b>x</b>", html=True)
        self.assertEqual(calls[-1][1]["parse_mode"], "HTML")


if __name__ == "__main__":
    unittest.main()
