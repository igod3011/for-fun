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
    return replace(BotConfig(), state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"), **kw)


class EntryTests(unittest.TestCase):
    cfg = BotConfig()

    def test_canonical_pool_passes(self):
        self.assertEqual(entry_check(row(), self.cfg), (True, []))

    def test_rejections(self):
        cases = {"not a pump.fun mint": row(mint="XYZabc"), "pool only": row(sol=5, tok=2e9),
                 "non-canonical": row(sol=559, tok=8.7e10), "top10": row(top10=0.9),
                 "mint authority": row(mint_authority="X"), "too old": row(age_s=3600)}
        for want, r in cases.items():
            ok, why = entry_check(r, self.cfg)
            self.assertFalse(ok, want)
            self.assertTrue(any(want in w for w in why), (want, why))


class ExitTests(unittest.TestCase):
    cfg = BotConfig()

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

    def test_max_hold(self):
        frac, why = exit_decision(self.pos(), 85, 2.07e8, NOW + 3 * 3600, self.cfg)
        self.assertEqual((frac, why), (1.0, "max hold time"))


class FakeTG:
    def __init__(self):
        self.sent, self.inbox, self.chat_id = [], [], "42"

    def send(self, text):
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
        self.rows = [row("Aaapump"), row("XYZnotpmp"), row("Bbbpump", top10=0.95)]
        self.tg = FakeTG()
        self.bot = Bot(cfg_in(self.tmp), self.tg, reserves=lambda pool, mint: (self.res["sol"], self.res["tok"]),
                       rows=lambda path: self.rows)

    def test_discover_buys_only_passing_rows_once(self):
        self.bot.discover()
        self.bot.discover()
        self.assertEqual(list(self.bot.p.positions), ["Aaapump"])
        self.assertAlmostEqual(self.bot.p.balance, 0.95)

    def test_rug_drain_closes_position_and_reports(self):
        self.bot.discover()
        self.res.update(sol=10.0, tok=2.07e8 * 85 / 10)       # dumped to ~1/72 of the price
        self.bot.manage()
        self.assertEqual(self.bot.p.positions, {})
        self.assertLess(self.bot.p.total_pnl, -0.04)
        self.assertTrue(any("PAPER SELL" in m for m in self.tg.sent))

    def test_pause_blocks_new_entries_and_resume(self):
        self.assertIn("paused", self.bot.command("/pause"))
        self.bot.discover()
        self.assertEqual(self.bot.p.positions, {})
        self.bot.command("/resume")
        self.rows.append(row("Cccpump"))
        self.bot.discover()
        self.assertEqual(list(self.bot.p.positions), ["Cccpump"])

    def test_stop_sells_everything(self):
        self.bot.discover()
        msg = self.bot.command("/stop")
        self.assertFalse(self.bot.running)
        self.assertEqual(self.bot.p.positions, {})
        self.assertIn("stopping", msg)

    def test_daily_loss_limit(self):
        self.bot.p.day_pnl = -0.25
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
        self.assertEqual(calls[-1], ("sendMessage", {"chat_id": "42", "text": "hi"}))


if __name__ == "__main__":
    unittest.main()
