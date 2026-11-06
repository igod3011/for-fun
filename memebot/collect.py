"""Collect REAL post-migration data for graduated pump.fun tokens (PumpSwap pools).

Per pool: GeckoTerminal 1-minute OHLCV (up to ~16h) + pool reserve snapshot, plus a
RugCheck static snapshot of the token. Output: JSONL, one pool per line.
GeckoTerminal's free tier is ~30 req/min and the proxy IP is shared, so calls are paced
and retried with backoff.

Usage: python -m memebot.collect --out DATA.jsonl --max-pools 150
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

GT = "https://api.geckoterminal.com/api/v2/networks/solana"
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
    now = time.time()
    out, seen = [], set()
    for page in range(1, 11):
        d = get(f"{GT}/dexes/pumpswap/pools?page={page}&include=base_token")
        if not d or not d.get("data"):
            break
        for p in d["data"]:
            a = p["attributes"]
            addr = a["address"]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pools", type=int, default=150)
    ap.add_argument("--min-age-h", type=float, default=2.0)
    ap.add_argument("--max-age-h", type=float, default=15.5)
    a = ap.parse_args()
    done = set()
    try:
        done = {json.loads(l)["pool"] for l in open(a.out)}
    except FileNotFoundError:
        pass
    pools = [p for p in candidate_pools(a.max_pools, a.min_age_h, a.max_age_h) if p["pool"] not in done]
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
