import random
import unittest

from memebot.ml import select_model as sm
from memebot.tests.test_entry_timing import flat, pool
from memebot.tests.test_rc_rules import rugged


class SelectModelTest(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(sm.auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1.0)
        self.assertEqual(sm.auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]), 0.0)
        self.assertEqual(sm.auc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]), 0.5)          # ties count half
        self.assertIsNone(sm.auc([0.1, 0.2], [1, 1]))                               # one class only

    def test_fit_learns_a_separable_rule_and_ignores_noise(self):
        rng = random.Random(0)
        X = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(400)]
        y = [1 if x[0] > 0.2 else 0 for x in X]
        model = sm.fit(X, y)
        self.assertGreater(sm.auc([model(x) for x in X], y), 0.98)
        w = list(model.weights.values())
        self.assertGreater(abs(w[0]), 5 * abs(w[1]))

    def test_features_need_holder_data_and_use_no_outcome_field(self):
        p = pool(flat)
        self.assertIsNone(sm.features(p))                                          # no holder snapshot
        p["helius_reg"].update(holders=300, top1_pct=0.05, top5_pct=0.2, top10_pct=0.3, top20_pct=0.4, pool_pct=0.2)
        x = sm.features(p)
        self.assertEqual(len(x), len(sm.FEATURES))
        for k in ("helius_fill", "candles", "rugcheck", "fetched_at"):             # outcome data must not matter
            p.pop(k, None)
        self.assertEqual(sm.features(p), x)

    def test_run_is_time_split_and_reports_money_next_to_ranking(self):
        rng = random.Random(1)
        rows = []
        for i in range(300):
            farm = rng.random() < 0.6
            p = pool(rugged if farm else flat)
            p["created"] += i
            p["helius_reg"].update(holders=2000 if farm else 300, top1_pct=0.01 if farm else 0.05,
                                   top5_pct=0.05 if farm else 0.2, top10_pct=0.1 if farm else 0.3,
                                   top20_pct=0.2 if farm else 0.4, pool_pct=0.2, accounts_fetched=2000 if farm else 300)
            rows.append(p)
        lines = []
        res = sm.run(rows, out=lines.append)
        self.assertGreater(res["auc"], 0.95)
        self.assertEqual(res["n_test"], 120)                                        # the later 40% only
        self.assertTrue(any("TEST money" in l for l in lines))
        self.assertIsNone(sm.run(rows[:50], out=lines.append))                      # too few pools: no model


if __name__ == "__main__":
    unittest.main()
