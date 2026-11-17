import unittest

from memebot import quote_check as qc
from memebot.bot import amm

POOL, MINT, V = "POOLaddr", "Mintpump", 17.5


def fake_quote(fee, pool=POOL, sellable=True, s=100.0, t=1.5e8):
    """A market that charges `fee` per swap on a pool with reserves (s, t) and virtual reserve V."""
    def quote(inp, out, amount):
        if inp == qc.rpc.WSOL:
            raw = amm.buy(amount / 1e9, s, t, fee, V) * 10 ** qc.TOKEN_DECIMALS
        elif not sellable:
            return None
        else:
            raw = amm.sell(amount / 10 ** qc.TOKEN_DECIMALS, s, t, fee, V) * 1e9
        return {"outAmount": str(int(raw)), "routePlan": [{"swapInfo": {"ammKey": pool}}]}
    return quote


class QuoteCheckTest(unittest.TestCase):
    def check(self, quote):
        return qc.check(POOL, MINT, 0.2, quote=quote, reserves=lambda p, m: (100.0, 1.5e8), virt=lambda p: V)

    def test_implied_fee_recovers_what_the_market_charges(self):
        r = self.check(fake_quote(0.012))
        self.assertAlmostEqual(r["buy_fee"], 0.012, places=4)
        self.assertAlmostEqual(r["sell_fee"], 0.012, places=4)
        self.assertAlmostEqual(r["mcap_sol"], (100 + V) / 1.5e8 * 1e9, places=3)
        self.assertEqual(r["moved"], 0)

    def test_a_quote_routed_elsewhere_is_not_trusted(self):
        self.assertIn("no direct buy quote", self.check(fake_quote(0.012, pool="OTHER"))["error"])
        self.assertIsNone(qc.routed_out({"outAmount": "5", "routePlan": [{"swapInfo": {"ammKey": POOL}}] * 2}, POOL))
        self.assertIsNone(qc.routed_out(None, POOL))

    def test_unsellable_token_is_flagged(self):
        self.assertIn("NO SELL QUOTE", self.check(fake_quote(0.012, sellable=False))["error"])

    def test_unreadable_pool(self):
        r = qc.check(POOL, MINT, 0.2, quote=fake_quote(0.012), reserves=lambda p, m: (100.0, 1.5e8), virt=lambda p: None)
        self.assertIn("unreadable", r["error"])


if __name__ == "__main__":
    unittest.main()
