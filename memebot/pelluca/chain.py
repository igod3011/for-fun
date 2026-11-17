"""On-chain reads for Pelluca, all through memebot.rpc (free public RPC first, Helius only as a fallback).

PumpSwap pool account layout (verified on mainnet 17/11/2026, 301 bytes):
    0  discriminator (8)      8  bump (1)          9  index (u16)
   11  pool creator           43  base mint         75  quote mint        107  lp mint
  139  pool base token acct  171  pool quote token acct                   203  lp supply (u64)
  211  coin creator (the token's creator; all zeros for pools not created by a pump.fun migration)
  245  virtual quote reserve (u64 lamports, see bot/amm.py)
Because the base mint and the coin creator sit at fixed offsets, getProgramAccounts with a memcmp filter finds
the pool(s) of a token and every pool of a creator without any third-party API.
"""
import base64

from .. import rpc

PUMPSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = rpc.WSOL
NULL = "11111111111111111111111111111111"
OFF = {"creator": 11, "base_mint": 43, "quote_mint": 75, "lp_mint": 107, "base_acc": 139, "quote_acc": 171,
       "coin_creator": 211}
VIRT = 245
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def is_address(s):
    return isinstance(s, str) and 32 <= len(s) <= 44 and all(c in B58 for c in s)


def parse_pool(raw):
    """Pure (unit-tested): PumpSwap pool account bytes -> dict of addresses + virtual reserve (SOL)."""
    if len(raw) < VIRT + 8:
        return None
    out = {k: b58(raw[o:o + 32]) for k, o in OFF.items()}
    out["lp_supply"] = int.from_bytes(raw[203:211], "little")
    v = int.from_bytes(raw[VIRT:VIRT + 8], "little") / 1e9
    out["virt_sol"] = v if v < 1000 else None
    if out["coin_creator"] == NULL:
        out["coin_creator"] = None
    return out


def _gpa(offset, value, slice_=None, _call=rpc.call):
    cfg = {"encoding": "base64", "filters": [{"memcmp": {"offset": offset, "bytes": value}}]}
    if slice_:
        cfg["dataSlice"] = {"offset": slice_[0], "length": slice_[1]}
    return _call("getProgramAccounts", [PUMPSWAP, cfg]) or []


def pools_for_mint(mint, _call=rpc.call):
    """Every PumpSwap token/SOL pool of `mint`, parsed, with `sol_acc` / `tok_acc` set whichever side SOL is on.
    pump.fun graduations put the token as base and SOL as quote. Pools created by hand can be reversed (SOL as
    base); those are never migrations, so their virtual reserve is 0."""
    out = []
    for side in ("base_mint", "quote_mint"):
        for a in _gpa(OFF[side], mint, _call=_call):
            p = parse_pool(base64.b64decode(a["account"]["data"][0]))
            if not p:
                continue
            p["pool"] = a["pubkey"]
            if side == "base_mint" and p["quote_mint"] == WSOL:
                p["sol_acc"], p["tok_acc"] = p["quote_acc"], p["base_acc"]
            elif side == "quote_mint" and p["base_mint"] == WSOL:
                p["sol_acc"], p["tok_acc"], p["virt_sol"], p["coin_creator"] = p["base_acc"], p["quote_acc"], 0.0, None
            else:
                continue                                          # token/token pool: not covered
            out.append(p)
    return out


def creator_pools(creator, limit=200, _call=rpc.call):
    """[(pool, base_mint, quote_acc)] of every PumpSwap pool whose coin creator is `creator` (graduated launches).
    Only the 64 bytes we need are downloaded. More than `limit` pools means a launch factory; the caller is told
    so by getting limit+1 rows back."""
    rows = _gpa(OFF["coin_creator"], creator, slice_=(OFF["base_mint"], 160), _call=_call)
    out = []
    for a in rows[:limit + 1]:
        raw = base64.b64decode(a["account"]["data"][0])         # starts at base_mint
        out.append((a["pubkey"], b58(raw[0:32]), b58(raw[128:160])))
    return out


def token_balances(accounts, _call=rpc.call):
    """{token account: uiAmount} for up to 100 accounts per call (getMultipleAccounts)."""
    out = {}
    for i in range(0, len(accounts), 100):
        chunk = accounts[i:i + 100]
        v = _call("getMultipleAccounts", [chunk, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        for acc, val in zip(chunk, (v or {}).get("value") or []):
            try:
                out[acc] = float(val["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
            except (TypeError, KeyError):
                out[acc] = 0.0
    return out


def supply(mint, _call=rpc.call):
    v = _call("getTokenSupply", [mint, {"commitment": "confirmed"}])
    return float(v["value"]["uiAmount"] or 0)


def supply_raw(mint, _call=rpc.call):
    """Supply in base units (comparable with the pool's lp_supply field)."""
    v = _call("getTokenSupply", [mint, {"commitment": "confirmed"}])
    return int(v["value"]["amount"])


def largest_accounts(mint, _call=rpc.call):
    """[(token account, amount)] of the 20 largest token accounts (free; owners are not resolved)."""
    v = _call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
    return [(x["address"], float(x["uiAmount"] or 0)) for x in (v or {}).get("value") or []]


def owner_balance(owner, mint, _call=rpc.call):
    v = _call("getTokenAccountsByOwner", [owner, {"mint": mint}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
    return sum(float(x["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
               for x in (v or {}).get("value") or [])
