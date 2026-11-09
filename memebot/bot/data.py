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
    """(pool_sol, pool_tokens) from the pool's own token accounts, via Helius RPC."""
    from ..helius import rpc
    res = []
    for m in (WSOL, mint):
        v = rpc("getTokenAccountsByOwner", [pool, {"mint": m}, {"encoding": "jsonParsed"}], pace=0.3)
        res.append(sum(float(x["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
                       for x in v.get("value", [])))
    return res[0], res[1]
