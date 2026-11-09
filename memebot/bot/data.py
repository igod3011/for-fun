"""Data access: newest pools from the collector's cohort file (tail only) + live reserves via Helius."""
import json
import os
import time

WSOL = "So11111111111111111111111111111111111111112"


def recent_cohort_rows(path, max_age_s=1800, tail_bytes=2_000_000):
    """Read only the end of cohort.jsonl (it grows to 100+ MB; newest registrations are appended last)."""
    if not os.path.exists(path):
        return []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - tail_bytes))
        chunk = f.read().decode("utf-8", "replace")
    lines = chunk.splitlines()
    if size > tail_bytes:
        lines = lines[1:]                    # first line is probably cut in half
    now, out = time.time(), []
    for l in lines:
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if now - r.get("registered_at", 0) <= max_age_s:
            out.append(r)
    return out


def pool_reserves(pool, mint):
    """(pool_sol, pool_tokens); free public RPC first, Helius only as fallback."""
    from ..rpc import pool_reserves as _pr
    return _pr(pool, mint)


def find_pumpswap_pool(mint, cohort_path, max_age_s=3 * 86400):
    """Pool address for a mint: our own cohort first (no API call), else GeckoTerminal's token->pools."""
    for r in reversed(recent_cohort_rows(cohort_path, max_age_s=max_age_s, tail_bytes=8_000_000)):
        if r.get("mint") == mint:
            return r["pool"]
    from ..collect import GT, get
    d = get(f"{GT}/tokens/{mint}/pools?page=1")
    for p in (d or {}).get("data", []):
        if (p.get("relationships", {}).get("dex", {}).get("data", {}) or {}).get("id") == "pumpswap":
            return p["attributes"]["address"]
    return None
