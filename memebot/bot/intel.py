"""Pre-buy intelligence (free APIs, one call each, only for tokens that already passed every other check):
  * RugCheck: dev (creator) holding %, creator's rug history / launch count, insider ("bundle") share of top holders
  * DexScreener: price, market cap, 1h / 5m price change, liquidity
"""
import json
import time
import urllib.request

HDR = {"User-Agent": "memebot/0.1"}


def _get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=timeout) as r:
        return json.load(r)


def parse_rugcheck(rep):
    """Pure (unit-tested): RugCheck /report -> the few numbers our rules need."""
    supply = float((rep.get("token") or {}).get("supply") or 0)
    dev_bal = float(rep.get("creatorBalance") or 0)
    holders = rep.get("topHolders") or []
    risks = [r.get("name", "") for r in rep.get("risks") or []]
    return {
        "creator": rep.get("creator"),
        "dev_pct": dev_bal / supply if supply else None,
        "creator_rugs": any("rugged tokens" in r.lower() for r in risks),
        "creator_launches": len(rep.get("creatorTokens") or []),
        "insider_pct": sum(float(h.get("pct") or 0) for h in holders if h.get("insider")) / 100,
        "insiders_detected": int(rep.get("graphInsidersDetected") or 0),
        "risks": risks[:8],
    }


def parse_dex(d, pool=None):
    """Pure: DexScreener /tokens -> price/mcap/changes of OUR pool (or the most liquid Solana pair)."""
    pairs = [p for p in (d or {}).get("pairs") or [] if p.get("chainId") == "solana"]
    if not pairs:
        return None
    pick = next((p for p in pairs if pool and p.get("pairAddress") == pool), None)
    pick = pick or max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
    ch = pick.get("priceChange") or {}
    return {"price_usd": float(pick.get("priceUsd") or 0), "mcap": pick.get("marketCap") or pick.get("fdv"),
            "change_h1": (ch.get("h1") or 0) / 100, "change_m5": (ch.get("m5") or 0) / 100,
            "liq_usd": (pick.get("liquidity") or {}).get("usd"), "dex": pick.get("dexId")}


def fetch(mint, pool):
    """(rugcheck_info or None, dex_info or None). Never raises."""
    rc = dx = None
    try:
        rc = parse_rugcheck(_get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"))
    except Exception:
        pass
    time.sleep(0.3)
    try:
        dx = parse_dex(_get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}"), pool)
    except Exception:
        pass
    return rc, dx


def intel_check(rc, dx, cfg):
    """Pure: (ok, reasons). Rules from the reviewed prompt, thresholds in BotConfig."""
    bad = []
    if rc is None:
        bad.append("rugcheck unavailable")
    else:
        if rc["dev_pct"] is not None and rc["dev_pct"] > cfg.max_dev_pct:
            bad.append(f"dev holds {rc['dev_pct']:.1%}")
        if cfg.block_creator_rugs and rc["creator_rugs"]:
            bad.append(f"creator has rugged before ({rc['creator_launches']} launches)")
        # no insider rule: RugCheck's per-holder `insider` flag was 0% on all 348 pools checked (11/2026), so
        # "insiders > 10%" could never fire. insider_pct is still recorded for later study.
    if dx is None:
        bad.append("dexscreener unavailable")
    elif cfg.max_change_h1 is not None and dx["change_h1"] > cfg.max_change_h1:
        bad.append(f"already {dx['change_h1']:+.0%} in 1h")
    return (not bad), bad


def fmt_price(p):
    if not p:
        return "?"
    if p >= 1:
        return f"${p:,.4f}"
    s = f"{p:.12f}".rstrip("0")
    zeros = len(s.split(".")[1]) - len(s.split(".")[1].lstrip("0"))
    return f"${p:.{zeros + 4}f}"


def fmt_usd(x):
    if x is None:
        return "?"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= div:
            return f"${x / div:.1f}{suf}"
    return f"${x:,.0f}"
