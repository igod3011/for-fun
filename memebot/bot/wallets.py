"""Step 3: follow wallets in (near) real time via Helius polling. Used by the bot when follow_enabled.

Cost warning: each watched wallet costs 1 Helius call per poll + 1 per new transaction. 20 wallets polled every
60 s is ~29k calls/day before transactions; check your Helius dashboard before enabling.
"""
import json
import os

from .data import WSOL

QUOTES = {WSOL, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}


def load_watchlist(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        d = json.load(f)
    if isinstance(d, dict):
        # wallet_scores writes the list even when its out-of-sample test FAILs; following those wallets would be
        # trading on a signal we measured to be worthless, so a FAIL verdict yields an empty watchlist.
        if str(d.get("verdict", "")).upper().startswith("FAIL"):
            return []
        return d.get("wallets", [])
    return d


def buys_in_tx(tx, wallet):
    """Mints whose balance owned by `wallet` went UP in this transaction (a buy), quote tokens excluded."""
    meta = (tx or {}).get("meta") or {}
    if meta.get("err"):
        return []
    pre, post = {}, {}
    for side, bal in ((pre, meta.get("preTokenBalances") or []), (post, meta.get("postTokenBalances") or [])):
        for b in bal:
            if b.get("owner") == wallet:
                amt = float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
                side[b["mint"]] = side.get(b["mint"], 0) + amt
    return [m for m in post if m not in QUOTES and post[m] > pre.get(m, 0)]


class WalletWatcher:
    def __init__(self, wallets, rpc):
        self.wallets, self.rpc = list(wallets), rpc
        self.last_sig = {}

    def poll(self):
        """Returns [(wallet, mint)] for buys seen since the previous poll. First poll only sets the baseline."""
        signals = []
        for w in self.wallets:
            sigs = self.rpc("getSignaturesForAddress", [w, {"limit": 10, "commitment": "confirmed"}]) or []
            if not sigs:
                continue
            newest = sigs[0]["signature"]
            if w not in self.last_sig:                     # baseline: do not replay old trades
                self.last_sig[w] = newest
                continue
            fresh = []
            for s in sigs:
                if s["signature"] == self.last_sig[w]:
                    break
                if not s.get("err"):
                    fresh.append(s["signature"])
            self.last_sig[w] = newest
            for sig in reversed(fresh):
                tx = self.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
                                                       "commitment": "confirmed"}])
                signals += [(w, m) for m in buys_in_tx(tx, w)]
        return signals
