"""Solana RPC with a free-first policy: the public mainnet RPC for standard methods (0 Helius credits),
Helius only as a fallback (1 credit per standard call). DAS methods (holders) stay in helius.py (10 credits).
"""
import json
import os
import time
import urllib.error
import urllib.request

PUBLIC = "https://api.mainnet-beta.solana.com"
WSOL = "So11111111111111111111111111111111111111112"
USAGE = {"public": 0, "helius_fallback": 0}


def public_rpc(method, params, tries=2, pace=0.15):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for i in range(tries):
        time.sleep(pace * (i + 1))
        try:
            req = urllib.request.Request(PUBLIC, data=body, headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                out = json.load(r)
            if "error" in out:
                raise RuntimeError(f"{method}: {out['error']}")
            USAGE["public"] += 1
            return out["result"]
        except (urllib.error.URLError, RuntimeError, ValueError) as e:   # 429 is an HTTPError (URLError subclass)
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"public RPC {method} failed: {type(last).__name__}")


def call(method, params, _public=public_rpc, _helius=None):
    try:
        return _public(method, params)
    except RuntimeError:
        if not os.environ.get("HELIUS_API_KEY") and _helius is None:
            raise
        if _helius is None:
            from .helius import rpc as _helius
        USAGE["helius_fallback"] += 1
        return _helius(method, params, pace=0.3)


def pool_reserves(pool, mint, _call=call):
    """(SOL, tokens) held by the AMM pool's own token accounts."""
    res = []
    for m in (WSOL, mint):
        v = _call("getTokenAccountsByOwner", [pool, {"mint": m}, {"encoding": "jsonParsed"}])
        res.append(sum(float(x["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
                       for x in (v or {}).get("value", [])))
    return res[0], res[1]
