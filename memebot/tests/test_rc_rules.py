import unittest

from memebot.ml import rc_rules as rr
from memebot.tests.test_entry_timing import flat, pool

RC_CLEAN = {"creator": "A", "dev_pct": 0.0, "creator_rugs": False, "creator_launches": 0, "insider_pct": 0.0,
            "insiders_detected": 0, "risks": []}
rugged = lambda m: 85.0 if m <= 5 else 1.0          # drained right after registration


def cohort(n_each, flag_predicts_rug=True):
    """Half the pools are rugs. The 'creator rugged before' flag either marks exactly the rugs, or alternates."""
    rows = []
    for i in range(4 * n_each):
        is_rug = i % 2 == 0
        flag = is_rug if flag_predicts_rug else (i // 2) % 2 == 0
        p = pool(rugged if is_rug else flat)
        p["created"] += i
        p["rc_reg"] = dict(RC_CLEAN, creator_rugs=flag, risks=["Creator history of rugged tokens"] if flag else [])
        rows.append(p)
    return rows


class RcRulesTest(unittest.TestCase):
    def test_bot_rule_predicates_match_bot_thresholds(self):
        self.assertTrue(rr.RULES["bot: dev holds >3%"](dict(RC_CLEAN, dev_pct=0.031)))
        self.assertFalse(rr.RULES["bot: dev holds >3%"](dict(RC_CLEAN, dev_pct=0.03)))
        self.assertTrue(rr.RULES["bot: insiders >10% (top holders)"](dict(RC_CLEAN, insider_pct=0.11)))
        self.assertTrue(rr.RULES["bot: any of the three"](dict(RC_CLEAN, creator_rugs=True)))
        self.assertFalse(rr.RULES["bot: any of the three"](RC_CLEAN))
        self.assertFalse(rr.RULES["bot: dev holds >3%"](dict(RC_CLEAN, dev_pct=None)))

    def test_informative_rule_is_kept(self):
        res = rr.run(cohort(15), out=lambda *_: None)
        r = res[("hold", "bot: creator rugged before")]
        self.assertEqual(r["verdict"], "KEEP")
        self.assertLess(r["flagged"], -0.9)
        self.assertGreater(r["kept"], -0.05)
        self.assertGreater(r["ci"][0], 0)

    def test_uninformative_rule_is_not_kept(self):
        res = rr.run(cohort(15, flag_predicts_rug=False), out=lambda *_: None)
        self.assertNotEqual(res[("hold", "bot: creator rugged before")]["verdict"], "KEEP")

    def test_small_groups_get_no_verdict(self):
        res = rr.run(cohort(15), out=lambda *_: None)
        self.assertEqual(res[("hold", "bot: dev holds >3%")]["verdict"], "too few")     # nobody flagged
        self.assertEqual(res[("hold", "bot: dev holds >3%")]["n_flagged"], 0)

    def test_holder_rules_are_judged_on_the_holder_snapshot(self):
        rows = cohort(15)
        for i, p in enumerate(rows):                       # the rugs are wallet farms: 2000 holders, flat top-10
            farm = i % 2 == 0
            p["helius_reg"].update(holders=2000 if farm else 300, top10_pct=0.10 if farm else 0.30)
            del p["rc_reg"]                                # holder rules do not need RugCheck data
        lines = []
        res = rr.run(rows, out=lines.append)
        self.assertEqual(res[("hold", "x: holders >=1000")]["verdict"], "KEEP")
        self.assertEqual(res[("hold", "x: top10 <15%")]["verdict"], "KEEP")
        self.assertEqual(res[("hold", "bot: top10 >50%")]["verdict"], "too few")      # nobody above 50%
        self.assertNotIn(("hold", "bot: creator rugged before"), res)                 # RugCheck section skipped
        self.assertTrue(any("holder data" in l and "60" in l for l in lines))

    def test_pools_without_rc_reg_or_with_error_are_ignored(self):
        rows = cohort(15)
        rows[0]["rc_reg"] = {"error": "HTTPError"}
        del rows[1]["rc_reg"]
        lines = []
        rr.run(rows, out=lines.append)
        self.assertIn("58", lines[0])


if __name__ == "__main__":
    unittest.main()
