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
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .. import rpc
from ..bot import amm
from . import chain

DEX = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
DEAD_SOL = 5.0            # a graduated pump.fun pool starts with ~85 SOL; under 5 SOL it is drained
GRAD_SOL = 85.0           # real SOL in a PumpSwap pool right after a pump.fun graduation (cohort, 11/2026)
STUDY = "2,890 graduated pump.fun pools tracked 6-16 Nov 2026"
BASE_RATE = 0.71          # share of those pools left with <10% of their SOL 3 hours later (RESULTS.md)
PARALLEL = 6              # concurrent RPC reads per check (public RPC allows ~40 per IP)
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


QUOTES = {rpc.WSOL, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}
MAX_MCAP = 1e10           # no memecoin pair is worth more; above this a DexScreener pair is priced against junk


def dex_raw(mint, get=None):
    """DexScreener's raw answer for a token, or None. Parsed later by parse_dex, once our own pool is known."""
    try:
        if get:
            return get(DEX.format(mint=mint))
        req = urllib.request.Request(DEX.format(mint=mint), headers={"User-Agent": "pelluca/0.1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception:
        return None


def dex_info(mint, get=None):
    """Price, market cap, changes and SOL/USD from DexScreener's most liquid Solana pair, or None."""
    return parse_dex(dex_raw(mint, get), mint=mint)


def parse_dex(d, mint=None, pool=None):
    """Pure (unit-tested). Picks the pair to quote: our own PumpSwap pool if DexScreener lists it, else the most
    liquid pair that prices the token in SOL/USDC/USDT. Pairs against other tokens are skipped: anyone can create
    a pool against a worthless token and its price makes nonsense market caps (19/11/2026: $132B on a 3-hour-old
    coin). Also returns where the main liquidity is (dex_id, pair, liq_usd) so a check can tell a drained pool
    from a token that simply trades elsewhere."""
    pairs = [p for p in (d or {}).get("pairs") or [] if p.get("chainId") == "solana"]
    if mint:
        pairs = [p for p in pairs if (p.get("baseToken") or {}).get("address") in (None, mint)]
    priced = [p for p in pairs if (p.get("quoteToken") or {}).get("address") in QUOTES | {None}]
    if not priced:
        return None
    liq = lambda x: (x.get("liquidity") or {}).get("usd") or 0
    own = [p for p in priced if pool and p.get("pairAddress") == pool]
    p = own[0] if own else max(priced, key=liq)
    top = max(priced, key=liq)
    usd, native = float(p.get("priceUsd") or 0), float(p.get("priceNative") or 0)
    ch = p.get("priceChange") or {}
    mcap = p.get("marketCap") or p.get("fdv")
    return {"name": (p.get("baseToken") or {}).get("symbol"), "price_usd": usd,
            "mcap": mcap if mcap and mcap < MAX_MCAP else None,
            "change_h1": (ch.get("h1") or 0) / 100, "change_h24": (ch.get("h24") or 0) / 100,
            "volume_h24": (p.get("volume") or {}).get("h24"), "created_ms": p.get("pairCreatedAt"),
            "sol_usd": usd / native if native and (p.get("quoteToken") or {}).get("address") in (None, rpc.WSOL) else None,
            "pair": p.get("pairAddress"), "dex_id": p.get("dexId"),
            "top_pair": top.get("pairAddress"), "top_dex": top.get("dexId"), "top_liq_usd": liq(top)}


def _all_read(bal, accs):
    if any(a not in bal for a in accs):
        raise RuntimeError("balances not read")
    return bal


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def gather(mint, _call=rpc.call, dex=dex_raw, now=None, _sleep=time.sleep):
    """All facts for one token. Never raises for missing optional parts; a missing pool is a fact too.
    Independent reads run in parallel (two rounds: by mint, then by pool) so a check takes seconds, not tens."""
    now = now or time.time()
    f = {"mint": mint, "checked_at": now}
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        j_pools = ex.submit(chain.pools_for_mint, mint, _call=_call)
        j_dex = ex.submit(_safe, lambda: dex(mint))
        j_auth = ex.submit(_safe, lambda: rpc.mint_authorities(mint, _call=_call), ("unknown", "unknown"))
        j_sup = ex.submit(_safe, lambda: _retry(lambda: chain.supply(mint, _call=_call), sleep=_sleep))
        # the free public RPC refuses getTokenLargestAccounts almost always (measured on the VPS 19/11/2026:
        # 3 of 3 tries failed, 15 s lost); retry only when Helius can answer it
        top_tries = HOLDER_TRIES if rpc._has_helius(None) else 1
        j_top = ex.submit(_safe, lambda: _retry(lambda: chain.largest_accounts(mint, _call=_call), tries=top_tries,
                                                sleep=_sleep))
        pools = j_pools.result()
        raw = j_dex.result()
        # tests and --timing pass an already parsed dict; the real fetch returns DexScreener's raw answer
        parse = (lambda pool: parse_dex(raw, mint=mint, pool=pool)) if isinstance(raw, dict) and "pairs" in raw \
            else (lambda pool: raw)
        if not pools:
            f["pool"], f["dex"] = None, parse(None)
            return f
        accs = [x for p in pools for x in (p["sol_acc"], p["tok_acc"])]
        # a failed read must never look like an empty pool (19/11/2026: "0.00 SOL, liquidity gone" on a live coin)
        bal = _safe(lambda: _retry(lambda: _all_read(chain.token_balances(accs, _call=_call), accs), tries=2,
                                   sleep=_sleep), {})
        read = [p for p in pools if p["sol_acc"] in bal]
        if not read:
            f.update(pool=pools[0]["pool"], pool_sol=None, pool_unread=True, dex=parse(pools[0]["pool"]))
            return f
        for p in read:
            p["sol"], p["tok"] = bal[p["sol_acc"]], bal.get(p["tok_acc"], 0.0)
        p = max(read, key=lambda x: x["sol"])
        f["dex"] = parse(p["pool"])
        f.update(pool=p["pool"], pool_sol=p["sol"], pool_tok=p["tok"], virt=p["virt_sol"], creator=p["coin_creator"],
                 n_pools=len(pools), tok_acc=p["tok_acc"], sol_acc=p["sol_acc"])
        # share of the pool's LP tokens still in existence (0 = all burnt)
        j_lp = ex.submit(_safe, lambda: chain.supply_raw(p["lp_mint"], _call=_call) / p["lp_supply"]
                         if p.get("lp_supply") else None)
        j_dev = j_hist = None
        if p["coin_creator"]:
            j_dev = ex.submit(_safe, lambda: chain.owner_balance(p["coin_creator"], mint, _call=_call))
            j_hist = ex.submit(creator_history, p["coin_creator"], p["pool"], _call=_call)
        f["lp_live"] = j_lp.result()
        f["mint_auth"], f["freeze_auth"] = j_auth.result()
        sup, top = j_sup.result(), j_top.result()
        if sup is not None and top is not None:
            top = [a for a in top if a[0] != p["tok_acc"]]
            f["supply"] = sup
            f["top1"] = top[0][1] / sup if sup and top else None
            f["top10"] = sum(a[1] for a in top[:10]) / sup if sup else None
            f["top10_tokens"] = sum(a[1] for a in top[:10])
        else:
            f["supply"] = None
        if j_dev:
            dev = j_dev.result()
            f["dev_pct"] = dev / f["supply"] if dev is not None and f.get("supply") else None
            f["history"] = j_hist.result()
    return f


CHECK_TTL = 60            # seconds a full report is reused: most users check the same trending tokens
HISTORY_TTL = 3600        # a creator's launch history changes slowly
_cache = {}               # key -> (expires_at, value)
_cache_lock = threading.Lock()


def _cached(key, ttl, fn, now=time.time):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now():
            return hit[1]
    value = fn()
    if value is None:                                     # a failed read is retried next time, never cached
        return value
    with _cache_lock:
        if len(_cache) > 5000:                            # keep memory bounded on a 1 GB VPS
            t = now()
            for k in [k for k, (exp, _) in _cache.items() if exp <= t]:
                del _cache[k]
            if len(_cache) > 5000:
                _cache.clear()
        _cache[key] = (now() + ttl, value)
    return value


def cached_gather(mint, now=time.time, **kw):
    """gather() reused for CHECK_TTL seconds per token (the bot's entry point). A report whose pool balance could
    not be read is not reused."""
    f = _cached(("check", mint), CHECK_TTL, lambda: gather(mint, **kw), now=now)
    if f and f.get("pool_unread"):
        with _cache_lock:
            _cache.pop(("check", mint), None)
    return f


def creator_history(creator, this_pool, limit=200, _call=rpc.call):
    return _cached(("history", creator, this_pool), HISTORY_TTL,
                   lambda: _creator_history(creator, this_pool, limit, _call))


def _creator_history(creator, this_pool, limit=200, _call=rpc.call):
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
    sol = f.get("pool_sol")
    dx = f.get("dex") or {}
    elsewhere = dx.get("top_pair") and dx["top_pair"] != f["pool"] and (dx.get("top_liq_usd") or 0) >= 1000
    if sol is None:
        add("info", "The pool's balance could not be read right now (RPC busy); try again in a minute.")
    elif sol < DEAD_SOL and elsewhere:
        venue = "the pump.fun bonding curve (not graduated yet)" if dx.get("top_dex") == "pumpfun" else \
            f"another pool ({dx.get('top_dex') or 'other DEX'}, ~${dx['top_liq_usd']:,.0f} liquidity)"
        add("amber", f"This PumpSwap pool holds only {sol:.2f} SOL, but the token mainly trades on {venue}. "
                     "Pelluca's pool checks do not cover that venue yet: check its liquidity there.")
    elif sol < DEAD_SOL:
        add("red", f"Liquidity is gone: the pool holds {sol:.2f} SOL. You may not be able to sell.")
    elif f.get("virt") and sol < GRAD_SOL * 0.35 and not elsewhere:
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
    if f.get("pool") and f.get("pool_sol") is not None:
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
        sys.exit("usage: python -m memebot.pelluca.check <token contract address> [--timing | --debug]")
    if "--debug" in sys.argv:                            # what the report is built from, for bug reports
        raw = dex_raw(sys.argv[1])
        for p in (raw or {}).get("pairs") or []:
            print("dex pair:", p.get("dexId"), p.get("pairAddress"), (p.get("quoteToken") or {}).get("symbol"),
                  "liq", (p.get("liquidity") or {}).get("usd"), "mcap", p.get("marketCap"))
        f = gather(sys.argv[1], dex=lambda m: raw)
        print(json.dumps({k: v for k, v in f.items() if k != "dex"}, default=str, indent=1))
        print("chosen dex:", json.dumps(f.get("dex"), default=str))
        print(render(f, html=False))
        return
    if "--timing" not in sys.argv:
        print(render(gather(sys.argv[1]), html=False))
        return
    log, lock = [], threading.Lock()                     # where does a check spend its time?

    def timed_call(method, params):
        t = time.time()
        ok = "ok"
        try:
            return rpc.call(method, params)
        except Exception as e:
            ok = type(e).__name__
            raise
        finally:
            with lock:
                log.append((time.time() - t, method, ok))

    def timed_dex(mint):
        t = time.time()
        out = dex_raw(mint)
        log.append((time.time() - t, "DexScreener", "ok" if out else "none"))
        return out
    t0 = time.time()
    gather(sys.argv[1], _call=timed_call, dex=timed_dex)
    print(f"total {time.time() - t0:.1f} s   (Helius configured: {'yes' if rpc._has_helius(None) else 'no'})")
    for sec, what, ok in sorted(log, reverse=True):
        print(f"  {sec:5.1f} s  {what}  {ok}")
    print("route:", rpc.USAGE)


if __name__ == "__main__":
    main()
