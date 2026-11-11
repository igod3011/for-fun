"""Collect REAL post-migration data for graduated pump.fun tokens (PumpSwap pools). Run by collector_daemon.

  register   python -m memebot.collect --out cohort.jsonl --max-pools 100 --max-age-h 3
             newest PumpSwap pools from GeckoTerminal, whatever their later fate (unbiased cohort): reserve
             snapshot (free RPC); for canonical pump.fun pools also the pool's virtual reserve and mint authorities
             (free RPC), holders (Helius DAS) and RugCheck. One row per pool is APPENDED to cohort.jsonl.
  fill       python -m memebot.collect --out cohort.jsonl --fill --min-age-h 3 --max-fill 8
             for pools older than 3 h: 1-minute candles (GeckoTerminal), RugCheck, reserve snapshot = the real
             outcome. One row per pool is APPENDED to cohort.fills.jsonl (see store.py). Nothing is rewritten.

GeckoTerminal's free tier is ~30 req/min, so calls are paced and retried with backoff.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import store

GT = "https://api.geckoterminal.com/api/v2/networks/solana"
SPAN_MIN = {"v": None}   # minutes of history covered by the newest-pools pages of the last discovery
HDR = {"User-Agent": "memebot-research/0.1", "accept": "application/json;version=20230302"}


def get(url, pace=2.3, tries=5):
    for i in range(tries):
        time.sleep(pace)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(6 * (i + 1))
        except Exception:
            time.sleep(4 * (i + 1))
    return None


def parse_ts(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def candidate_pools(max_pools, min_age_h, max_age_h):
    """Newest pools on Solana (all DEXes, 10 pages of 20), PumpSwap ones kept. Unbiased: no ranking by success."""
    now = time.time()
    out, seen = [], set()
    oldest = now
    for page in range(1, 11):
        d = get(f"{GT}/new_pools?page={page}&include=base_token")
        if not d or not d.get("data"):
            break
        for p in d["data"]:
            a = p["attributes"]
            addr = a["address"]
            oldest = min(oldest, parse_ts(a["pool_created_at"]))
            if p["relationships"]["dex"]["data"]["id"] != "pumpswap" or addr in seen:
                continue
            seen.add(addr)
            age_h = (now - parse_ts(a["pool_created_at"])) / 3600
            if not (min_age_h <= age_h <= max_age_h):
                continue
            mint = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
            out.append({"pool": addr, "mint": mint, "name": a["name"],
                        "created": parse_ts(a["pool_created_at"]),
                        "reserve_usd": float(a.get("reserve_in_usd") or 0),
                        "fdv_usd": float(a.get("fdv_usd") or 0)})
        print(f"page {page}: candidates={len(out)}", flush=True)
        if len(out) >= max_pools:
            break
    SPAN_MIN["v"] = (now - oldest) / 60
    return out[:max_pools]


def rugcheck(mint):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", headers=HDR), timeout=20) as r:
            rep = json.load(r)
    except Exception:
        return None
    markets = rep.get("markets") or []
    pool = set()
    for m in markets:
        pool |= {m.get("pubkey"), m.get("liquidityA"), m.get("liquidityB")}
    holders = [h for h in (rep.get("topHolders") or [])
               if h.get("owner") not in pool and h.get("address") not in pool]
    lp = [(m.get("lp") or {}).get("lpLockedPct") for m in markets]
    lp = [x for x in lp if x is not None]
    return {"mint_revoked": rep.get("mintAuthority") is None,
            "freeze_revoked": rep.get("freezeAuthority") is None,
            "rugged": bool(rep.get("rugged")),
            "top10_pct": sum(h.get("pct", 0) for h in holders[:10]) / 100 if holders else None,
            "lp_locked_pct": max(lp) / 100 if lp else None,
            "score_norm": rep.get("score_normalised"),
            "creator": rep.get("creator"), "total_holders": rep.get("totalHolders")}


def is_canonical(mint, sol, tok):
    """Loose check for a real pump.fun graduation pool (k = SOL*tokens ~ 1-2.6e10; window kept wider here)."""
    return mint.endswith("pump") and sol >= 1 and 0.5e10 <= sol * tok <= 5e10


def helius_snapshot(p, with_holders=True):
    """Reserves for every pool via the FREE public RPC. For canonical pump.fun pools at registration also: the
    pool's virtual quote reserve and the mint/freeze authorities (free RPC), and holder data (Helius DAS, 10
    credits per 1000 accounts, needs HELIUS_API_KEY). Never raises."""
    from . import rpc
    try:
        sol, tok = rpc.pool_reserves(p["pool"], p["mint"])
    except BaseException as e:
        return {"error": str(e)[:120]}
    snap = {"pool_sol": sol, "pool_tokens": tok, "fetched_at": int(time.time())}
    if not (with_holders and is_canonical(p["mint"], sol, tok)):
        return snap
    try:
        snap["virt_sol"] = rpc.pool_virtual_sol(p["pool"])
    except Exception as e:
        snap["virt_error"] = str(e)[:120]
    try:
        snap["mint_authority"], snap["freeze_authority"] = rpc.mint_authorities(p["mint"])
    except Exception as e:
        snap["authority_error"] = str(e)[:120]
    if os.environ.get("HELIUS_API_KEY"):
        try:
            from .helius import holder_snapshot
            snap.update(holder_snapshot(p, max_pages=2))
        except BaseException as e:                       # helius._key() exits when the key is unusable
            snap["holders_error"] = str(e)[:120]
    return snap


def register(path, max_pools, min_age_h, max_age_h):
    """Append one row per newly seen PumpSwap pool. Duplicates are avoided against the tail of the file: a pool
    this young can only have been registered in the last few hours."""
    done = {r.get("pool") for r in store.tail_rows(path)}
    pools = [p for p in candidate_pools(max_pools, min_age_h, max_age_h) if p["pool"] not in done]
    with open(path, "a", encoding="utf-8") as f:
        for p in pools:
            p["registered_at"] = int(time.time())
            snap = helius_snapshot(p)
            p["helius_reg"] = snap
            if snap.get("pool_tokens") and is_canonical(p["mint"], snap.get("pool_sol") or 0, snap["pool_tokens"]):
                try:
                    from .bot.intel import _get, parse_rugcheck
                    p["rc_reg"] = parse_rugcheck(_get(f"https://api.rugcheck.xyz/v1/tokens/{p['mint']}/report"))
                except Exception as e:
                    p["rc_reg"] = {"error": type(e).__name__}
            f.write(json.dumps(p) + "\n")
            f.flush()
    span = SPAN_MIN["v"]
    print(f"registered {len(pools)} pools | pages cover {span:.0f} min of new pools"
          + (" -> GAP risk: run more often than this!" if span is not None and span < 6 else ""), flush=True)
    return len(pools)


def fill(path, min_age_h, max_fill=8):
    """Fetch the outcome of registered pools older than min_age_h and APPEND it to the fills file."""
    done = store.filled_pools(path)
    waiting = [p for p in store.tail_rows(path) if "candles" not in p and p.get("pool") not in done]
    now, n = time.time(), 0
    for p in waiting:
        if (now - p["created"]) / 3600 < min_age_h:
            continue
        if n >= max_fill:      # bounded pass: fill must not delay registration (they run one after the other)
            break
        try:
            o = get(f"{GT}/pools/{p['pool']}/ohlcv/minute?aggregate=1&limit=1000&currency=usd")
            rec = {"candles": sorted(o["data"]["attributes"]["ohlcv_list"]) if o else [],   # keep empty: dead pools count!
                   "rugcheck": rugcheck(p["mint"]),
                   "helius_fill": helius_snapshot(p, with_holders=False),      # outcome only needs reserves (free)
                   "fetched_at": int(time.time())}
            store.append_fill(path, p["pool"], rec)
        except Exception as e:                      # one bad pool must not kill the pass
            print(f"skip pool {p.get('mint', '?')[:8]}: {type(e).__name__}", flush=True)
            continue
        n += 1
        print(f"filled {p['name'].encode('ascii', 'replace').decode()} candles={len(rec['candles'])}", flush=True)
    print(f"filled {n} pools; {len(waiting) - n} still waiting", flush=True)
    return n


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pools", type=int, default=100)
    ap.add_argument("--min-age-h", type=float, default=0.0)
    ap.add_argument("--max-age-h", type=float, default=3.0)
    ap.add_argument("--fill", action="store_true", help="fetch outcomes for registered pools older than --min-age-h")
    ap.add_argument("--max-fill", type=int, default=8, help="max pools per --fill pass")
    # accepted and ignored: a collector_daemon started before 11/2026 still passes them
    ap.add_argument("--source", choices=["new"], default="new", help=argparse.SUPPRESS)
    ap.add_argument("--register-only", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.fill:
        fill(a.out, a.min_age_h, a.max_fill)
    else:
        register(a.out, a.max_pools, a.min_age_h, a.max_age_h)


if __name__ == "__main__":
    main()
