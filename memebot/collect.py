"""Collect REAL post-migration data for graduated pump.fun tokens (PumpSwap pools).

Per pool: GeckoTerminal 1-minute OHLCV (up to ~16h) + pool reserve snapshot, plus a
RugCheck static snapshot of the token. Output: JSONL, one pool per line.
GeckoTerminal's free tier is ~30 req/min and the proxy IP is shared, so calls are paced
and retried with backoff.

Usage: python -m memebot.collect --out DATA.jsonl --max-pools 150
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

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


def candidate_pools(max_pools, min_age_h, max_age_h, source="top"):
    now = time.time()
    out, seen = [], set()
    oldest = now
    for page in range(1, 11):
        url = (f"{GT}/new_pools?page={page}&include=base_token" if source == "new"
               else f"{GT}/dexes/pumpswap/pools?page={page}&include=base_token")
        d = get(url)
        if not d or not d.get("data"):
            break
        for p in d["data"]:
            a = p["attributes"]
            addr = a["address"]
            oldest = min(oldest, parse_ts(a["pool_created_at"]))
            if source == "new" and p["relationships"]["dex"]["data"]["id"] != "pumpswap":
                continue
            if addr in seen:
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
    SPAN_MIN["v"] = (now - oldest) / 60 if source == "new" else None
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


def helius_snapshot(p):
    """Pool/holder snapshot via Helius if HELIUS_API_KEY is set; never raises."""
    if not os.environ.get("HELIUS_API_KEY"):
        return None
    try:
        from .helius import enrich_one
        return enrich_one(p)
    except BaseException as e:      # SystemExit from a missing key, network errors, ...
        return {"error": str(e)[:120]}


def _save(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:          # json.dumps is ASCII-only, so no encoding problems on Windows
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def fill(path, min_age_h, max_fill=10):
    rows = [json.loads(l) for l in open(path)]
    now, n = time.time(), 0
    for p in rows:
        if "candles" in p or (now - p["created"]) / 3600 < min_age_h:
            continue
        if n >= max_fill:      # bounded pass: fill must not starve registration (they share one file)
            break
        try:
            o = get(f"{GT}/pools/{p['pool']}/ohlcv/minute?aggregate=1&limit=1000&currency=usd")
            p["candles"] = sorted(o["data"]["attributes"]["ohlcv_list"]) if o else []   # keep empty: dead pools count!
            p["rugcheck"] = rugcheck(p["mint"])
            snap = helius_snapshot(p)
            if snap:
                p["helius_fill"] = snap
            p["fetched_at"] = int(time.time())
        except Exception as e:                      # one bad pool must not kill the pass
            p.pop("candles", None)
            print(f"skip pool {p.get('mint', '?')[:8]}: {type(e).__name__}", flush=True)
            continue
        n += 1
        print(f"filled {p['name'].encode('ascii', 'replace').decode()} candles={len(p['candles'])}", flush=True)
        if n % 10 == 0:
            _save(path, rows)   # rewrite the whole file only every 10 pools: it grows to ~100+ MB (disk wear / CPU)
    _save(path, rows)
    print(f"filled {n} pools; {sum('candles' not in p for p in rows)} still waiting", flush=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pools", type=int, default=150)
    ap.add_argument("--min-age-h", type=float, default=2.0)
    ap.add_argument("--max-age-h", type=float, default=15.5)
    ap.add_argument("--source", choices=["top", "new"], default="top",
                    help="top = biased toward tokens that did well (DON'T backtest on it); new = unbiased cohort")
    ap.add_argument("--register-only", action="store_true",
                    help="store the cohort (no candles yet); fill later with --fill")
    ap.add_argument("--fill", action="store_true", help="fetch candles for registered pools older than --min-age-h")
    ap.add_argument("--max-fill", type=int, default=10, help="max pools per --fill pass")
    a = ap.parse_args()
    done = set()
    try:
        done = {json.loads(l)["pool"] for l in open(a.out)}
    except FileNotFoundError:
        pass
    if a.fill:
        return fill(a.out, a.min_age_h, a.max_fill)
    pools = [p for p in candidate_pools(a.max_pools, a.min_age_h, a.max_age_h, a.source) if p["pool"] not in done]
    if a.register_only:
        with open(a.out, "a") as f:
            for p in pools:
                p["registered_at"] = int(time.time())
                snap = helius_snapshot(p)
                if snap:
                    p["helius_reg"] = snap
                f.write(json.dumps(p) + "\n")
        span = SPAN_MIN["v"]
        print(f"registered {len(pools)} pools | pages cover {span:.0f} min of new pools"
              + (" -> GAP risk: run more often than this!" if span is not None and span < 6 else ""), flush=True)
        return
    print(f"{len(pools)} new pools to fetch", flush=True)
    with open(a.out, "a") as f:
        for i, p in enumerate(pools, 1):
            o = get(f"{GT}/pools/{p['pool']}/ohlcv/minute?aggregate=1&limit=1000&currency=usd")
            if not o:
                continue
            candles = sorted(o["data"]["attributes"]["ohlcv_list"])
            if len(candles) < 30:
                continue
            p["candles"] = candles                      # [ts, o, h, l, c, volume_usd]
            p["rugcheck"] = rugcheck(p["mint"])
            p["fetched_at"] = int(time.time())
            f.write(json.dumps(p) + "\n"); f.flush()
            print(f"[{i}/{len(pools)}] {p['name']} candles={len(candles)}", flush=True)


if __name__ == "__main__":
    main()
