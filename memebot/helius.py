"""Helius enrichment: real on-chain holder data for cohort tokens (stdlib only).

Runs where HELIUS_API_KEY is set as an ENVIRONMENT VARIABLE (your own machine). Helius reads the
key from the URL (?api-key=), which the cloud sandbox's header-injecting proxy cannot do, so this
does not work inside the Claude cloud container. The key is never printed or written to disk.

  python -m memebot.helius --selftest [--data cohort.jsonl]     # check each endpoint, prints OK/FAIL
  python -m memebot.helius --enrich cohort.jsonl [--max 50]     # adds a "helius" field per pool

Adds per token: holders (distinct owners), top1/5/10/20 % of supply EXCLUDING the AMM pool, and
authority info from DAS getAsset. All endpoints used are Helius RPC/DAS methods; if one fails the
selftest says which, instead of silently dropping features.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

RPC = "https://mainnet.helius-rpc.com/?api-key={key}"
WSOL = "So11111111111111111111111111111111111111112"


def _key():
    k = os.environ.get("HELIUS_API_KEY", "").strip()
    if not k:
        sys.exit("HELIUS_API_KEY is not set (PowerShell: $env:HELIUS_API_KEY='...'; cmd: set HELIUS_API_KEY=...)")
    return k


def rpc(method, params, pace=0.6, tries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": "memebot", "method": method, "params": params}).encode()
    url = RPC.format(key=_key())
    for i in range(tries):
        time.sleep(pace)
        req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.load(r)
            if "error" in out:
                raise RuntimeError(f"{method}: {out['error']}")
            return out["result"]
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(f"{method}: HTTP {e.code} (key invalid or lacks access)")
            time.sleep(3 * (i + 1))      # 429/5xx: back off
        except urllib.error.URLError:
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{method}: failed after {tries} tries")


def token_accounts(mint, max_pages=3):
    """All token accounts for a mint via DAS getTokenAccounts (1000/page)."""
    out = []
    for page in range(1, max_pages + 1):
        r = rpc("getTokenAccounts", {"mint": mint, "limit": 1000, "page": page})
        accs = r.get("token_accounts") or []
        out += accs
        if len(accs) < 1000:
            break
    return out


def holder_features(accounts, exclude_owners=()):
    """Pure function (unit-tested): concentration stats from DAS token accounts."""
    by_owner = {}
    for a in accounts:
        amt = int(a.get("amount") or 0)
        if amt > 0:
            by_owner[a["owner"]] = by_owner.get(a["owner"], 0) + amt
    total = sum(by_owner.values())
    ex = set(exclude_owners)
    ranked = sorted((v for o, v in by_owner.items() if o not in ex), reverse=True)
    f = {"holders": len(by_owner), "pool_pct": (sum(v for o, v in by_owner.items() if o in ex) / total) if total else None}
    for n in (1, 5, 10, 20):
        f[f"top{n}_pct"] = sum(ranked[:n]) / total if total else None
    return f


def top_owners(accounts, exclude_owners=(), n=10):
    """[[owner, share_of_supply], ...] for the n largest holders, AMM pool excluded (unit-tested)."""
    by_owner = {}
    for a in accounts:
        amt = int(a.get("amount") or 0)
        if amt > 0:
            by_owner[a["owner"]] = by_owner.get(a["owner"], 0) + amt
    total = sum(by_owner.values()) or 1
    ex = set(exclude_owners)
    ranked = sorted(((o, v) for o, v in by_owner.items() if o not in ex), key=lambda kv: -kv[1])[:n]
    return [[o, round(v / total, 5)] for o, v in ranked]


def holder_snapshot(row, max_pages=1):
    """DAS-only part (10 credits per call): holder stats, top-10 addresses, mint/freeze authority."""
    mint = row["mint"]
    accs = token_accounts(mint, max_pages=max_pages)
    f = holder_features(accs, exclude_owners=[row.get("pool")])
    f["top_holders"] = top_owners(accs, [row.get("pool")], 10)   # addresses: lets us study "smart" wallets
    f["accounts_fetched"] = len(accs)
    try:
        ti = rpc("getAsset", {"id": mint}).get("token_info") or {}
        f["mint_authority"] = ti.get("mint_authority")
        f["freeze_authority"] = ti.get("freeze_authority")
        f["supply_raw"] = ti.get("supply")
    except RuntimeError as e:
        f["asset_error"] = str(e)[:120]
    return f


def enrich_one(row):
    """Full snapshot: free reserves (public RPC) + DAS holder data."""
    from .rpc import pool_reserves
    f = holder_snapshot(row, max_pages=3)
    try:
        f["pool_sol"], f["pool_tokens"] = pool_reserves(row["pool"], row["mint"])
    except (RuntimeError, KeyError, TypeError) as e:
        f["pool_error"] = str(e)[:120]
    f["fetched_at"] = int(time.time())
    return f


def owner_kind(addr):
    """wallet = system-owned account; program-owned = a program/PDA account; no-account = never funded (often a PDA)."""
    r = rpc("getAccountInfo", [addr, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}])
    v = r.get("value")
    if v is None:
        return "no-account (PDA or empty wallet)"
    return "wallet" if v.get("owner") == SYSTEM_PROGRAM else f"program-owned ({v.get('owner')[:8]}..)"


def inspect(path, key):
    rows = [json.loads(l) for l in open(path)]
    row = next((r for r in rows if key == r.get("mint") or key.lower() in (r.get("name") or "").lower()), None)
    if not row:
        sys.exit(f"no row matching {key!r}")
    rc = row.get("rugcheck") or {}
    print(f"{row['name']}  mint={row['mint']}\n  pool={row['pool']}  reserve_usd@registration={row.get('reserve_usd')}")
    print(f"  rugcheck: lp_locked={rc.get('lp_locked_pct')} rugged={rc.get('rugged')} top10(excl. pool)={rc.get('top10_pct')}")
    accs = token_accounts(row["mint"])
    by_owner = {}
    for a in accs:
        by_owner[a["owner"]] = by_owner.get(a["owner"], 0) + int(a.get("amount") or 0)
    total = sum(by_owner.values()) or 1
    print(f"  total supply in accounts={total}, owners={len(by_owner)}")
    for o, v in sorted(by_owner.items(), key=lambda kv: -kv[1])[:5]:
        tag = " <== THE POOL" if o == row["pool"] else ""
        print(f"   {v/total*100:6.2f}%  {o[:10]}..  {owner_kind(o)}{tag}")
    pool_accs = rpc("getTokenAccountsByOwner", [row["pool"], {"mint": row["mint"]}, {"encoding": "jsonParsed"}])
    bal = [x["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"] for x in pool_accs.get("value", [])]
    print(f"  pool address token balances (getTokenAccountsByOwner): {bal or 'none'}")
    sol = rpc("getTokenAccountsByOwner", [row["pool"], {"mint": WSOL}, {"encoding": "jsonParsed"}])
    print("  pool wSOL balance:", [x["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"] for x in sol.get("value", [])] or "none")


def selftest(data=None):
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            print(f"OK   {name}: {fn()}")
        except Exception as e:
            ok = False
            print(f"FAIL {name}: {e}")

    check("getHealth/getSlot", lambda: rpc("getSlot", []))
    check("DAS getAsset(wSOL)", lambda: (rpc("getAsset", {"id": WSOL}).get("id")))
    mint = WSOL
    if data and os.path.exists(data):
        for l in open(data):
            mint = json.loads(l)["mint"]
            break
    check(f"DAS getTokenAccounts({mint[:6]}...)",
          lambda: f"{len(rpc('getTokenAccounts', {'mint': mint, 'limit': 5, 'page': 1}).get('token_accounts') or [])} accounts")
    print("ALL OK" if ok else "SOME CHECKS FAILED - send me the FAIL lines (they contain no key)")


def enrich_file(path, max_n):
    rows = [json.loads(l) for l in open(path)]
    n = 0
    for r in rows:
        if "helius" in r or n >= max_n:
            continue
        try:
            r["helius"] = enrich_one(r)
            n += 1
            h = r["helius"]
            print(f"{r.get('name','?')[:18]:18} holders={h['holders']} top10={h['top10_pct'] and round(h['top10_pct']*100,1)}%", flush=True)
        except RuntimeError as e:
            print("skip", r.get("name"), e, flush=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"enriched {n} pools")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--enrich")
    ap.add_argument("--data")
    ap.add_argument("--max", type=int, default=50)
    ap.add_argument("--inspect", help="token name or mint to inspect (uses --data)")
    a = ap.parse_args()
    if a.selftest:
        selftest(a.data)
    elif a.inspect:
        inspect(a.data, a.inspect)
    elif a.enrich:
        enrich_file(a.enrich, a.max)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
