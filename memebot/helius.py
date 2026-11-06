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


def enrich_one(row):
    mint = row["mint"]
    accs = token_accounts(mint)
    f = holder_features(accs, exclude_owners=[row.get("pool")])
    f["accounts_fetched"] = len(accs)
    try:
        asset = rpc("getAsset", {"id": mint})
        ti = asset.get("token_info") or {}
        f["mint_authority"] = ti.get("mint_authority")
        f["freeze_authority"] = ti.get("freeze_authority")
        f["supply_raw"] = ti.get("supply")
    except RuntimeError as e:
        f["asset_error"] = str(e)[:120]
    f["fetched_at"] = int(time.time())
    return f


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
    a = ap.parse_args()
    if a.selftest:
        selftest(a.data)
    elif a.enrich:
        enrich_file(a.enrich, a.max)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
