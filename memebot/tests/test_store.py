"""Append-only cohort storage, the collector passes that use it, and the free on-chain reads."""
import base64
import json
import os
import tempfile
import time
import unittest

from memebot import collect, rpc, store
from memebot.bot.runner import Bot
from memebot.tests.test_bot import FakeTG, cfg_in, row

NOW = int(time.time())


def reg(pool, age_h=5.0, **extra):
    r = {"pool": pool, "mint": pool + "pump", "name": pool, "created": NOW - int(age_h * 3600),
         "registered_at": NOW - int(age_h * 3600) + 300, "helius_reg": {"pool_sol": 85.0, "pool_tokens": 2.07e8}}
    r.update(extra)
    return r


def write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "cohort.jsonl")

    def test_fill_rows_are_merged_and_inline_rows_still_work(self):
        inline = reg("OLD", candles=[[1, 1, 1, 1, 1, 9]], rugcheck={"rugged": False},
                     helius_fill={"pool_sol": 1.0, "pool_tokens": 9e8}, fetched_at=NOW - 10)
        write(self.path, [inline, reg("NEW"), reg("WAIT", age_h=1)])
        store.append_fill(self.path, "NEW", {"candles": [[2, 1, 1, 1, 1, 5], [3, 1, 1, 1, 1, 5]], "rugcheck": None,
                                             "helius_fill": {"pool_sol": 2.0, "pool_tokens": 8e8}, "fetched_at": NOW,
                                             "junk": "not stored"})
        rows = {r["pool"]: r for r in store.load(self.path)}
        self.assertEqual([rows[k].get("filled", False) for k in ("OLD", "NEW", "WAIT")], [True, True, False])
        self.assertEqual(len(rows["NEW"]["candles"]), 2)
        self.assertEqual(rows["NEW"]["helius_fill"]["pool_sol"], 2.0)
        self.assertNotIn("junk", rows["NEW"])
        self.assertEqual(rows["NEW"]["helius_reg"]["pool_sol"], 85.0)          # registration data untouched
        self.assertEqual([r["pool"] for r in store.load(self.path, filled_only=True)], ["OLD", "NEW"])
        slim = {r["pool"]: r for r in store.load(self.path, candles=False)}
        self.assertEqual((slim["OLD"]["n_candles"], slim["NEW"]["n_candles"]), (1, 2))
        self.assertNotIn("candles", slim["NEW"])
        self.assertEqual(store.filled_pools(self.path), {"NEW"})

    def test_index_is_rebuilt_from_the_fills_file(self):
        write(self.path, [reg("A"), reg("B")])
        store.append_fill(self.path, "A", {"candles": []})
        os.remove(store.index_path(self.path))
        self.assertEqual(store.filled_pools(self.path), {"A"})
        self.assertTrue(os.path.exists(store.index_path(self.path)))

    def test_tail_skips_the_cut_first_line_and_a_half_written_last_line(self):
        write(self.path, [reg(f"P{i:03d}") for i in range(200)])
        with open(self.path, "a") as f:
            f.write('{"pool": "HALF", "mint": ')                               # a registration being appended
        tail = store.tail_rows(self.path, tail_bytes=3000)
        self.assertTrue(0 < len(tail) < 200)
        self.assertEqual(tail[-1]["pool"], "P199")
        self.assertEqual(len(store.tail_rows(self.path)), 200)                  # whole file fits: nothing dropped
        bad = [0]
        self.assertEqual(sum(1 for _ in store.iter_jsonl(self.path, bad)), 200)
        self.assertEqual(bad[0], 1)

    def test_migrate_moves_inline_fills_out_and_changes_nothing_else(self):
        rows = [reg(f"F{i}", candles=[[i, 1, 1, 1, 1, 5]] * 50, rugcheck={"rugged": False},
                    helius_fill={"pool_sol": float(i), "pool_tokens": 9e8}, fetched_at=NOW - i) for i in range(5)]
        rows += [reg("W1", age_h=1), reg("W2", age_h=0.5)]
        write(self.path, rows)
        store.append_fill(self.path, "F0", {"candles": [[0, 1, 1, 1, 1, 5]] * 50, "fetched_at": NOW})   # already split
        before = store.load(self.path)
        size = os.path.getsize(self.path)
        lines = []
        self.assertEqual(store.migrate(self.path, out=lines.append), 5)
        after = store.load(self.path)
        strip = lambda rs: [{k: v for k, v in r.items()} for r in rs]
        self.assertEqual([r["pool"] for r in after], [r["pool"] for r in before])
        for a, b in zip(strip(after), strip(before)):
            if a["pool"] != "F0":                                               # F0 keeps the newer side record
                self.assertEqual(a, b)
        self.assertLess(os.path.getsize(self.path), size / 3)
        self.assertEqual(os.path.getsize(self.path + ".before-split"), size)   # original kept
        self.assertFalse(any("candles" in r for r in store.iter_jsonl(self.path)))
        self.assertEqual(store.filled_pools(self.path), {f"F{i}" for i in range(5)})
        self.assertEqual(store.migrate(self.path, out=lines.append), 0)        # running it twice is harmless
        self.assertEqual(len(store.load(self.path, filled_only=True)), 5)

    def test_migrate_refuses_a_damaged_file(self):
        write(self.path, [reg("A", candles=[])])
        with open(self.path, "a") as f:
            f.write("garbage\n" * 5)
        size = os.path.getsize(self.path)
        with self.assertRaises(SystemExit):
            store.migrate(self.path, out=lambda *_: None)
        self.assertEqual(os.path.getsize(self.path), size)
        self.assertFalse(os.path.exists(self.path + ".before-split"))


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "cohort.jsonl")
        self.saved = {n: getattr(collect, n) for n in ("candidate_pools", "helius_snapshot", "get", "rugcheck")}
        collect.SPAN_MIN["v"] = 7.0

    def tearDown(self):
        for n, f in self.saved.items():
            setattr(collect, n, f)

    def test_register_appends_new_pools_once(self):
        write(self.path, [reg("A", age_h=1)])
        fresh = lambda *a: [{"pool": p, "mint": "Xnotpmp", "name": p, "created": NOW - 60} for p in ("A", "B", "C")]
        collect.candidate_pools = fresh
        collect.helius_snapshot = lambda p, with_holders=True: {"pool_sol": 0.0, "pool_tokens": 0.0}
        size = os.path.getsize(self.path)
        self.assertEqual(collect.register(self.path, 100, 0, 3), 2)
        with open(self.path, "rb") as f:
            self.assertEqual(len(f.read(size)), size)                           # appended, never rewritten
        self.assertEqual([r["pool"] for r in store.iter_jsonl(self.path)], ["A", "B", "C"])
        self.assertEqual(collect.register(self.path, 100, 0, 3), 0)
        self.assertNotIn("rc_reg", list(store.iter_jsonl(self.path))[-1])       # RugCheck only for canonical pools

    def organic(self, pool, age_min, **h):
        r = row(mint=pool + "pump", holders=150, virt_sol=17.5, top1_pct=0.03, **h)
        r.update(pool=pool, created=NOW - int(age_min * 60), registered_at=NOW - int(age_min * 60) + 240)
        return r

    def test_pools_the_bot_would_accept_get_one_holder_snapshot_at_90_minutes(self):
        write(self.path, [self.organic("OLD", 130), self.organic("DUE", 90), self.organic("YOUNG", 40),
                          self.organic("FARM", 90, top10=0.05), reg("JUNK", age_h=1.5)])
        calls = []
        collect.helius_snapshot = lambda p, with_holders=True: calls.append(p["pool"]) or {
            "pool_sol": 70.0, "pool_tokens": 2.4e8, "holders": 900, "top10_pct": 0.06}
        size = os.path.getsize(self.path)
        self.assertEqual(collect.snap90(self.path, now=NOW), 1)
        self.assertEqual(calls, ["DUE"])                    # not the farm, not the too young/old, not the junk pool
        self.assertEqual(collect.snap90(self.path, now=NOW + 120), 0)           # once per pool
        self.assertEqual(os.path.getsize(self.path), size)                      # cohort.jsonl untouched
        rows = {r["pool"]: r for r in store.load(self.path)}
        self.assertEqual(rows["DUE"]["helius_90"]["top10_pct"], 0.06)
        self.assertEqual(rows["DUE"]["helius_90"]["age_min"], 90.0)
        self.assertNotIn("helius_90", rows["FARM"])

    def test_snapshot_pass_is_bounded_retries_rpc_errors_and_never_breaks_registration(self):
        write(self.path, [self.organic(f"P{i}", 90) for i in range(8)])
        collect.helius_snapshot = lambda p, with_holders=True: {"error": "timeout"}
        self.assertEqual(collect.snap90(self.path, now=NOW), 0)                 # retried next pass, nothing recorded
        collect.helius_snapshot = lambda p, with_holders=True: {"pool_sol": 70.0, "pool_tokens": 2.4e8}
        self.assertEqual(collect.snap90(self.path, max_snaps=5, now=NOW), 5)
        self.assertEqual(collect.snap90(self.path, max_snaps=5, now=NOW), 3)
        collect.candidate_pools = lambda *a: [{"pool": "NEW", "mint": "Xnotpmp", "name": "n", "created": NOW - 60}]
        boom = collect.snap90
        collect.snap90 = lambda path: 1 / 0
        try:
            self.assertEqual(collect.register(self.path, 100, 0, 3), 1)
        finally:
            collect.snap90 = boom

    def test_fill_appends_outcomes_and_never_touches_the_cohort_file(self):
        write(self.path, [reg("OLD1"), reg("OLD2"), reg("OLD3"), reg("YOUNG", age_h=1),
                          reg("INLINE", candles=[[1, 1, 1, 1, 1, 1]])])
        with open(self.path, "rb") as f:
            original = f.read()
        asked = []

        def get(url, **kw):
            asked.append(url)
            return {"data": {"attributes": {"ohlcv_list": [[3, 1, 1, 1, 1, 5], [2, 1, 1, 1, 1, 5]]}}}
        collect.get, collect.rugcheck = get, lambda mint: {"rugged": False}
        collect.helius_snapshot = lambda p, with_holders=True: {"pool_sol": 1.5, "pool_tokens": 9e8, "holders_asked": with_holders}
        self.assertEqual(collect.fill(self.path, 3, max_fill=2), 2)
        self.assertEqual(collect.fill(self.path, 3, max_fill=2), 1)             # the third one on the next pass
        self.assertEqual(collect.fill(self.path, 3, max_fill=2), 0)             # nothing is fetched twice
        self.assertEqual(len(asked), 3)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), original)
        rows = {r["pool"]: r for r in store.load(self.path)}
        self.assertEqual(rows["OLD2"]["candles"][0][0], 2)                      # sorted by time
        self.assertEqual(rows["OLD2"]["helius_fill"], {"pool_sol": 1.5, "pool_tokens": 9e8, "holders_asked": False})
        self.assertFalse(rows["YOUNG"].get("filled"))

    def test_fill_survives_a_bad_pool_and_keeps_dead_pools(self):
        write(self.path, [reg("BAD"), reg("DEAD")])
        collect.rugcheck = lambda mint: None
        collect.helius_snapshot = lambda p, with_holders=True: {"pool_sol": 0.0, "pool_tokens": 0.0}
        collect.get = lambda url, **kw: {"unexpected": 1} if "BAD" in url else None     # None = nothing ever traded
        self.assertEqual(collect.fill(self.path, 3), 1)
        rows = {r["pool"]: r for r in store.load(self.path)}
        self.assertEqual(rows["DEAD"]["candles"], [])                           # dead pools count (no survivorship bias)
        self.assertFalse(rows["BAD"].get("filled"))                             # retried on a later pass

    def test_canonical_pools_get_free_onchain_fields(self):
        calls = []

        def fake(method, params):
            calls.append(method)
            if method == "getTokenAccountsByOwner":
                amt = 85.0 if params[1]["mint"] == rpc.WSOL else 2.07e8
                return {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": amt}}}}}}]}
            if params[1]["encoding"] == "base64":
                data = bytearray(301)
                data[rpc.VIRT_OFFSET:rpc.VIRT_OFFSET + 8] = (17_584_000_000).to_bytes(8, "little")
                return {"value": {"data": [base64.b64encode(bytes(data)).decode(), "base64"]}}
            return {"value": {"data": {"parsed": {"info": {"mintAuthority": None, "freezeAuthority": "FRZ"}}}}}
        old_call, old_key = rpc.call, os.environ.pop("HELIUS_API_KEY", None)
        rpc.call = fake
        rpc.pool_reserves.__defaults__, rpc.pool_virtual_sol.__defaults__, rpc.mint_authorities.__defaults__ = (fake,), (fake,), (fake,)
        try:
            snap = collect.helius_snapshot({"pool": "P", "mint": "Xpump"})
            self.assertEqual((snap["virt_sol"], snap["mint_authority"], snap["freeze_authority"]), (17.584, None, "FRZ"))
            self.assertNotIn("holders", snap)                                   # no Helius key: no DAS call, no error
            n = len(calls)
            other = collect.helius_snapshot({"pool": "P", "mint": "Xnotpmp"})
            self.assertEqual((len(calls) - n, "virt_sol" in other), (2, False)) # non-canonical: reserves only
            self.assertEqual(len(calls) - n, 2)
            self.assertNotIn("virt_sol", collect.helius_snapshot({"pool": "P", "mint": "Xpump"}, with_holders=False))
        finally:
            rpc.call = old_call
            for f in (rpc.pool_reserves, rpc.pool_virtual_sol, rpc.mint_authorities):
                f.__defaults__ = (old_call,)
            if old_key:
                os.environ["HELIUS_API_KEY"] = old_key

    def test_virtual_reserve_of_an_unknown_layout_is_none(self):
        short = {"value": {"data": [base64.b64encode(b"\0" * 211).decode(), "base64"]}}
        self.assertIsNone(rpc.pool_virtual_sol("P", _call=lambda m, p: short))
        self.assertIsNone(rpc.pool_virtual_sol("P", _call=lambda m, p: {"value": None}))
        huge = bytearray(301)
        huge[rpc.VIRT_OFFSET:rpc.VIRT_OFFSET + 8] = (2 ** 63).to_bytes(8, "little")
        self.assertIsNone(rpc.pool_virtual_sol("P", _call=lambda m, p: {"value": {"data": [base64.b64encode(bytes(huge)).decode(), "base64"]}}))


class EntrySnapshotTest(unittest.TestCase):
    """A5: a second holder snapshot right before the buy decision, recorded with the decision."""

    def bot(self, holders, intel=None):
        self.tg = FakeTG()
        return Bot(cfg_in(tempfile.mkdtemp()), self.tg, reserves=lambda pool, mint: (90.0, 1.9e8),
                   rows=lambda path, **kw: [row("Aaapump", holders=320, top10=0.3)], holders=holders, intel=intel)

    def events(self, bot):
        return [json.loads(l) for l in open(bot.cfg.log_path)]

    def test_snapshot_is_logged_with_the_buy_and_shown_in_the_message(self):
        bot = self.bot(lambda r: {"holders": 410, "top10_pct": 0.27, "top1_pct": 0.05, "accounts_fetched": 430})
        bot.discover()
        buy = next(e for e in self.events(bot) if e["action"] == "buy")
        self.assertEqual((buy["holders_reg"], buy["holders_entry"], buy["top10_entry"]), (320, 410, 0.27))
        self.assertEqual((buy["pool_sol"], buy["pool_tokens"]), (90.0, 1.9e8))   # enough to replay the trade later
        self.assertTrue(any("Holder 320 → 410" in m for m in self.tg.sent))

    def test_a_failing_snapshot_never_blocks_the_decision(self):
        def boom(r):
            raise SystemExit("HELIUS_API_KEY is not set")
        bot = self.bot(boom)
        bot.discover()
        buy = next(e for e in self.events(bot) if e["action"] == "buy")
        self.assertIn("HELIUS_API_KEY", buy["holders_entry_error"])
        self.assertNotIn("holders_entry", buy)

    def test_candidates_rejected_by_intel_keep_their_snapshot(self):
        rc = {"creator": "D", "dev_pct": 0.2, "creator_rugs": False, "creator_launches": 0, "insider_pct": 0.0,
              "insiders_detected": 0, "risks": []}
        dx = {"price_usd": 1e-5, "mcap": 1e4, "change_h1": 0.1, "change_m5": 0.0, "liq_usd": 1e4, "dex": "pumpswap"}
        bot = self.bot(lambda r: {"holders": 5000, "top10_pct": 0.05}, intel=lambda m, p: (rc, dx))
        bot.discover()
        self.assertEqual(bot.p.positions, {})
        skip = next(e for e in self.events(bot) if e["action"] == "skip")
        self.assertIn("dev holds", skip["reason"])
        self.assertEqual(skip["holders_entry"], 5000)


if __name__ == "__main__":
    unittest.main()
