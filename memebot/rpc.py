"""Solana RPC with a free-first policy: the public mainnet RPC for standard methods (0 Helius credits),
Helius only as a fallback (1 credit per standard call). DAS methods (holders) stay in helius.py (10 credits).
"""
import base64
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


VIRT_OFFSET = 245      # PumpSwap pool account: 8 disc + 1 bump + 2 index + 6 pubkeys + 8 lp_supply + 32 coin_creator + 2 flags


def pool_virtual_sol(pool, _call=call):
    """Virtual quote reserve (SOL) stored in a PumpSwap pool account: swaps price on real SOL + this (bot/amm.py).
    Returns None when the account is missing or shorter than the known layout. Free (public RPC)."""
    v = _call("getAccountInfo", [pool, {"encoding": "base64", "commitment": "confirmed"}])
    data = base64.b64decode((((v or {}).get("value") or {}).get("data") or [""])[0])
    if len(data) < VIRT_OFFSET + 8:
        return None
    sol = int.from_bytes(data[VIRT_OFFSET:VIRT_OFFSET + 8], "little") / 1e9
    return sol if sol < 1000 else None                    # anything larger means the layout changed


def mint_authorities(mint, _call=call):
    """(mint_authority, freeze_authority) of an SPL / Token-2022 mint. Free (public RPC); this replaced the
    Helius DAS getAsset call (10 credits per pool)."""
    v = _call("getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}])
    info = v["value"]["data"]["parsed"]["info"]
    return info.get("mintAuthority"), info.get("freezeAuthority")


def pool_reserves(pool, mint, _call=call):
    """(SOL, tokens) held by the AMM pool's own token accounts. "confirmed" ~1-2 s behind vs ~13 s for the
    default "finalized", so dumps and liquidity pulls are seen sooner."""
    res = []
    for m in (WSOL, mint):
        v = _call("getTokenAccountsByOwner", [pool, {"mint": m}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        res.append(sum(float(x["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
                       for x in (v or {}).get("value", [])))
    return res[0], res[1]
