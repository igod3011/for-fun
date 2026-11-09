import os
import unittest
from unittest import mock

from memebot import collect, rpc


def acct(amount):
    return {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": amount}}}}}}


class RpcFallbackTest(unittest.TestCase):
    def test_public_first_helius_only_on_failure(self):
        calls = []
        ok = lambda m, p: calls.append("public") or {"value": [acct(85)]}
        self.assertEqual(rpc.call("x", [], _public=ok, _helius=lambda m, p, pace: calls.append("helius")),
                         {"value": [acct(85)]})
        self.assertEqual(calls, ["public"])

        def broken(m, p):
            raise RuntimeError("429")
        out = rpc.call("x", [], _public=broken, _helius=lambda m, p, pace: {"value": [acct(1)]})
        self.assertEqual(out, {"value": [acct(1)]})

    def test_reserves_sum_accounts(self):
        fake = lambda m, p: {"value": [acct(80), acct(5)]} if p[1]["mint"] == rpc.WSOL else {"value": [acct(2.07e8)]}
        self.assertEqual(rpc.pool_reserves("POOL", "Mpump", _call=fake), (85.0, 2.07e8))


class StagedSnapshotTest(unittest.TestCase):
    def run_snap(self, mint, sol, tok, key=True, with_holders=True):
        env = {"HELIUS_API_KEY": "x"} if key else {}
        holders = mock.Mock(return_value={"top10_pct": 0.2, "top_holders": [["A", 0.1]]})
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("memebot.rpc.pool_reserves", return_value=(sol, tok)), \
                mock.patch("memebot.helius.holder_snapshot", holders):
            snap = collect.helius_snapshot({"pool": "P", "mint": mint}, with_holders=with_holders)
        return snap, holders.called

    def test_das_only_for_canonical_pump_pools_at_registration(self):
        snap, das = self.run_snap("Mpump", 85, 2.07e8)
        self.assertTrue(das)
        self.assertEqual(snap["top10_pct"], 0.2)
        for mint, sol, tok, kw in (("Mpump", 0.0, 1e8, {}),            # empty pool
                                   ("Mxyz", 85, 2.07e8, {}),          # not pump.fun
                                   ("Mpump", 559, 8.7e10, {}),        # copycat pool
                                   ("Mpump", 85, 2.07e8, {"with_holders": False}),   # fill snapshot
                                   ("Mpump", 85, 2.07e8, {"key": False})):           # no key
            snap, das = self.run_snap(mint, sol, tok, **kw)
            self.assertFalse(das, (mint, sol, kw))
            self.assertEqual(snap["pool_sol"], sol)


if __name__ == "__main__":
    unittest.main()


class HealthcheckSmokeTest(unittest.TestCase):
    def test_runs_and_flags_missing_holder_data(self):
        import json
        import subprocess
        import sys
        import tempfile
        import time
        d = tempfile.mkdtemp()
        now = int(time.time())
        row = {"mint": "Apump", "pool": "p", "name": "a", "created": now - 600, "registered_at": now - 120,
               "helius_reg": {"pool_sol": 85, "pool_tokens": 2.07e8}}
        open(os.path.join(d, "cohort.jsonl"), "w").write(json.dumps(row) + "\n")
        open(os.path.join(d, "daemon.log"), "w").write("x | registered 1 pools | pages cover 7 min of new pools\n")
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        r = subprocess.run([sys.executable, "-m", "memebot.healthcheck"], cwd=d, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": root})
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("NO holder data", r.stdout)
