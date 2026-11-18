"""Pelluca /check: a read-only risk report for one Solana token (contract address), in English.

  python -m memebot.pelluca.check <CA>          # prints the report (plain text)

Everything is read from the chain through memebot.rpc (free public RPC, Helius only as a fallback) plus one
DexScreener call (commercial use allowed by its API terms; credited in the footer). No RugCheck, no GeckoTerminal:
their terms do not cover a paid product (Notion "Tuần 1", 17/11/2026).

The base rates quoted come from the project's own 10-day study (memebot/RESULTS.md, 16/11/2026). They describe
what happened to pools like this one; they are not a prediction and never a recommendation to buy.
"""
import json
import sys
import time
import urllib.request

from .. import rpc
from ..bot import amm
from . import chain

DEX = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
DEAD_SOL = 5.0            # a graduated pump.fun pool starts with ~85 SOL; under 5 SOL it is drained
GRAD_SOL = 85.0           # real SOL in a PumpSwap pool right after a pump.fun graduation (cohort, 11/2026)
STUDY = "2,890 graduated pump.fun pools tracked 6-16 Nov 2026"
BASE_RATE = 0.71          # share of those pools left with <10% of their SOL 3 hours later (RESULTS.md)
HOLDER_TRIES = 3          # the public RPC rate-limits getTokenLargestAccounts often; retry before giving up


def _retry(fn, tries=HOLDER_TRIES, wait=2.0, sleep=time.sleep):
    """fn() with a few spaced retries; re-raises the last error."""
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            sleep(wait * (i + 1))


def dex_info(mint, get=None):
    """Price, market cap, changes and SOL/USD from DexScreener's most liquid Solana pair, or None."""
    try:
        if get:
            d = get(DEX.format(mint=mint))
        else:
            req = urllib.request.Request(DEX.format(mint=mint), headers={"User-Agent": "pelluca/0.1"})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.load(r)
    except Exception:
        return None
    return parse_dex(d)


def parse_dex(d):
    """Pure (unit-tested)."""
    pairs = [p for p in (d or {}).get("pairs") or [] if p.get("chainId") == "solana"]
    if not pairs:
        return None
    p = max(pairs, key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
    usd, native = float(p.get("priceUsd") or 0), float(p.get("priceNative") or 0)
    ch = p.get("priceChange") or {}
    return {"name": (p.get("baseToken") or {}).get("symbol"), "price_usd": usd, "mcap": p.get("marketCap") or p.get("fdv"),
            "change_h1": (ch.get("h1") or 0) / 100, "change_h24": (ch.get("h24") or 0) / 100,
            "volume_h24": (p.get("volume") or {}).get("h24"), "created_ms": p.get("pairCreatedAt"),
            "sol_usd": usd / native if native else None}


def gather(mint, _call=rpc.call, dex=dex_info, now=None, _sleep=time.sleep):
    """All facts for one token. Never raises for missing optional parts; a missing pool is a fact too."""
    now = now or time.time()
    f = {"mint": mint, "checked_at": now}
    pools = chain.pools_for_mint(mint, _call=_call)
    f["dex"] = dex(mint)
    if not pools:
        f["pool"] = None
        return f
    bal = chain.token_balances([x for p in pools for x in (p["sol_acc"], p["tok_acc"])], _call=_call)
    for p in pools:
        p["sol"], p["tok"] = bal.get(p["sol_acc"], 0.0), bal.get(p["tok_acc"], 0.0)
    p = max(pools, key=lambda x: x["sol"])
    f.update(pool=p["pool"], pool_sol=p["sol"], pool_tok=p["tok"], virt=p["virt_sol"], creator=p["coin_creator"],
             n_pools=len(pools), tok_acc=p["tok_acc"], sol_acc=p["sol_acc"])
    try:                                   # share of the pool's LP tokens still in existence (0 = all burnt)
        f["lp_live"] = chain.supply_raw(p["lp_mint"], _call=_call) / p["lp_supply"] if p.get("lp_supply") else None
    except Exception:
        f["lp_live"] = None
    try:
        f["mint_auth"], f["freeze_auth"] = rpc.mint_authorities(mint, _call=_call)
    except Exception:
        f["mint_auth"] = f["freeze_auth"] = "unknown"
    try:
        sup = _retry(lambda: chain.supply(mint, _call=_call), sleep=_sleep)
        top = [a for a in _retry(lambda: chain.largest_accounts(mint, _call=_call), sleep=_sleep)
               if a[0] != p["tok_acc"]]
        f["supply"] = sup
        f["top1"] = top[0][1] / sup if sup and top else None
        f["top10"] = sum(a[1] for a in top[:10]) / sup if sup else None
        f["top10_tokens"] = sum(a[1] for a in top[:10])
    except Exception:
        f["supply"] = None
    if p["coin_creator"]:
        try:
            f["dev_pct"] = chain.owner_balance(p["coin_creator"], mint, _call=_call) / f["supply"] if f.get("supply") else None
        except Exception:
            f["dev_pct"] = None
        f["history"] = creator_history(p["coin_creator"], p["pool"], _call=_call)
    return f


def creator_history(creator, this_pool, limit=200, _call=rpc.call):
    """Other graduated launches of the same creator and how many are drained now (replaces RugCheck's
    'creator history of rugged tokens', from chain data only)."""
    try:
        rows = [r for r in chain.creator_pools(creator, limit=limit, _call=_call) if r[0] != this_pool]
    except Exception:
        return None
    if len(rows) > limit:
        return {"n": len(rows), "factory": True}
    sol = chain.token_balances([r[2] for r in rows], _call=_call) if rows else {}
    return {"n": len(rows), "drained": sum(1 for r in rows if sol.get(r[2], 0) < DEAD_SOL), "factory": False}


def assess(f):
    """Pure (unit-tested): [(level, text)] with level 'red' | 'amber' | 'info', plus the verdict string."""
    flags = []
    add = lambda lvl, txt: flags.append((lvl, txt))
    if not f.get("pool"):
        add("red", "No PumpSwap pool found. Pelluca currently covers Solana tokens trading on PumpSwap.")
        return flags, "UNKNOWN"
    sol = f["pool_sol"]
    if sol < DEAD_SOL:
        add("red", f"Liquidity is gone: the pool holds {sol:.2f} SOL. You may not be able to sell.")
    elif f.get("virt") and sol < GRAD_SOL * 0.35:
        add("red", f"The pool has lost {1 - sol / GRAD_SOL:.0%} of the ~{GRAD_SOL:.0f} SOL it started with at graduation.")
    lp = f.get("lp_live")
    if lp is not None and lp > 0.05:
        add("red", f"{min(lp, 1):.0%} of the pool's LP tokens are not burnt: whoever holds them can withdraw the "
                   "liquidity at any time.")
    elif lp is None and f.get("virt") == 0:
        add("red", "Not created by a pump.fun graduation and the LP lock could not be verified "
                   "(126 of 127 such pools in our study were drained).")
    if f.get("virt") == 0 and lp is not None and lp > 0.05:
        add("info", "Not created by a pump.fun graduation: in our study 126 of 127 such pools were drained.")
    if f.get("mint_auth") not in (None, "unknown"):
        add("red", "Mint authority is active: more tokens can be created at any time.")
    if f.get("freeze_auth") not in (None, "unknown"):
        add("red", "Freeze authority is active: your tokens can be frozen.")
    t1, t10 = f.get("top1"), f.get("top10")
    if t1 is not None and t1 >= 0.5:
        add("red", f"One wallet holds {t1:.0%} of the supply.")
    elif t10 is not None and t10 > 0.5:
        add("amber", f"The 10 largest holders own {t10:.0%} of the supply.")
    if t10 is not None and t10 < 0.15:
        add("amber", f"Supply is spread unusually thin (top 10 hold {t10:.0%}): a pattern of wallet farms and bundles.")
    dev = f.get("dev_pct")
    if dev is not None and dev > 0.03:
        add("amber", f"The creator still holds {dev:.1%} of the supply.")
    h = f.get("history")
    if h and h.get("factory"):
        add("red", f"The creator has launched more than {h['n'] - 1} graduated tokens: a launch factory.")
    elif h and h["n"] >= 3 and h["drained"] / h["n"] >= 0.8:
        add("red", f"The creator launched {h['n']} other graduated tokens; {h['drained']} are now drained.")
    elif h and h["n"] >= 1:
        add("info", f"The creator launched {h['n']} other graduated token(s); {h['drained']} drained now.")
    if f.get("top10") is None:
        add("info", "Holder concentration could not be read right now (RPC busy); try again in a minute.")
    dx = f.get("dex") or {}
    if dx.get("change_h1", 0) > 0.8:
        add("amber", f"Already {dx['change_h1']:+.0%} in the last hour.")
    elif dx.get("change_h1", 0) <= -0.5:
        add("red", f"The price fell {-dx['change_h1']:.0%} in the last hour.")
    if dx.get("created_ms"):
        age_min = (f["checked_at"] - dx["created_ms"] / 1000) / 60
        if 0 <= age_min < 180:
            add("info", f"The pool is {age_min:.0f} minutes old: most collapses happen in the first 3 hours.")
    reds = sum(1 for l, _ in flags if l == "red")
    ambers = sum(1 for l, _ in flags if l == "amber")
    verdict = "HIGH RISK" if reds else "ELEVATED RISK" if ambers >= 2 else "NO MAJOR FLAGS FOUND"
    return flags, verdict


def exit_math(f, stake=0.5):
    """Pure: what a round trip costs now, and what the top 10 holders selling would leave in the pool."""
    sol, tok, v = f.get("pool_sol") or 0, f.get("pool_tok") or 0, f.get("virt") or 0
    if sol < DEAD_SOL or tok <= 0:
        return None
    got = amm.buy(stake, sol, tok, amm.PUMP_FEE, v)
    back = amm.sell(got, sol + stake * (1 - amm.PUMP_FEE), tok - got, amm.PUMP_FEE, v)
    out = {"stake": stake, "round_trip_loss": 1 - back / stake}
    if f.get("top10_tokens"):
        paid = amm.sell(f["top10_tokens"], sol, tok, amm.PUMP_FEE, v)
        out["top10_drain"] = paid / sol
    return out


def render(f, html=True):
    from html import escape
    flags, verdict = assess(f)
    b = (lambda s: f"<b>{s}</b>") if html else (lambda s: s)
    c = (lambda s: f"<code>{s}</code>") if html else (lambda s: s)
    dx = f.get("dex") or {}
    name = escape(str(dx.get("name") or "Token"))
    icon = {"HIGH RISK": "🔴", "ELEVATED RISK": "🟠", "NO MAJOR FLAGS FOUND": "🟢"}.get(verdict, "⚪")
    lines = [f"{icon} {b(name + ': ' + verdict)}", f"CA: {c(escape(f['mint']))}"]
    if dx.get("price_usd"):
        mc = f" | MC ${dx['mcap']:,.0f}" if dx.get("mcap") else ""
        lines.append(f"Price ${dx['price_usd']:.8g}{mc} | 1h {dx.get('change_h1', 0):+.0%} | 24h {dx.get('change_h24', 0):+.0%}")
    if f.get("pool"):
        lines.append(f"Pool: {f['pool_sol']:.1f} SOL" + (f" (~${f['pool_sol'] * dx['sol_usd']:,.0f})" if dx.get("sol_usd") else ""))
    facts = []
    if f.get("top10") is not None:
        facts.append(f"top 10 accounts hold {f['top10']:.0%}")
    if f.get("dev_pct") is not None:
        facts.append(f"creator holds {f['dev_pct']:.1%}")
    if facts:
        lines.append("Holders: " + ", ".join(facts))
    lines.append("")
    for lvl, txt in flags:
        lines.append({"red": "⛔", "amber": "⚠️", "info": "ℹ️"}[lvl] + " " + escape(txt))
    if not flags:
        lines.append("No red flags in the on-chain checks.")
    ex = exit_math(f)
    if ex:
        lines.append("")
        lines.append(f"Exit check: buying {ex['stake']} SOL and selling right away loses {ex['round_trip_loss']:.1%} "
                     "to fees and price impact.")
        if ex.get("top10_drain") is not None:
            lines.append(f"If the top 10 holders sold now, they would take {ex['top10_drain']:.0%} of the pool's SOL.")
    lines += ["", f"Base rate: {BASE_RATE:.0%} of {STUDY} lost over 90% of their SOL within 3 hours.",
              "Data: Solana RPC, DexScreener. Not financial advice."]
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2 or not chain.is_address(sys.argv[1]):
        sys.exit("usage: python -m memebot.pelluca.check <token contract address>")
    print(render(gather(sys.argv[1]), html=False))


if __name__ == "__main__":
    main()
