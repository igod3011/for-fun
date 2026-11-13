"""Cohort storage (stdlib only).

  cohort.jsonl         one REGISTRATION row per pool, append-only (the bot reads its tail for new pools)
  cohort.fills.jsonl   one row per pool with everything fetched >=3 h later: candles, RugCheck, reserve snapshot
  cohort.filled.txt    pool addresses that have a fill row (cheap "already done?" index)
  cohort.snaps.jsonl   one row per pool the bot's static filter accepts: a second holder snapshot taken when the
                       pool is ~90 minutes old, i.e. when the bot decides (row["helius_90"] after load())

Until 11/2026 the fill step wrote candles INTO cohort.jsonl and therefore rewrote the whole file (50 MB, growing
10 MB/day) several times every 5 minutes. Rows written that way ("inline") are still understood everywhere;
`python -m memebot.store --migrate cohort.jsonl` moves them out once, with the collector stopped.

  python -m memebot.store --stats cohort.jsonl
"""
import argparse
import json
import os
import sys
import time

FILL_KEYS = ("candles", "rugcheck", "helius_fill", "fetched_at")


def _base(path):
    return path[:-6] if path.endswith(".jsonl") else path


def fills_path(path):
    return _base(path) + ".fills.jsonl"


def index_path(path):
    return _base(path) + ".filled.txt"


def snaps_path(path):
    return _base(path) + ".snaps.jsonl"


def snapped_pools(path):
    """Pools that already have a decision-time snapshot. Only the tail is read: a pool is snapshotted once, at
    ~90 minutes, so anything older than the tail can never be a candidate again."""
    return {r.get("pool") for r in tail_rows(snaps_path(path), 2_000_000)}


def append_snap(path, pool, snap):
    with open(snaps_path(path), "a", encoding="utf-8") as f:
        f.write(json.dumps({"pool": pool, "helius_90": snap}) + "\n")


def iter_jsonl(path, bad=None):
    """Rows of a JSONL file. Unparsable lines (one being appended right now, or damaged) are skipped and counted
    in bad[0] when a list is given."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except ValueError:
                if bad is not None:
                    bad[0] += 1


def tail_rows(path, tail_bytes=8_000_000):
    """Rows from the end of a JSONL file. Registrations are appended in time order, so the tail holds every pool
    that is recent or still waiting for its fill; reading it avoids parsing the whole file every 2 minutes."""
    if not os.path.exists(path):
        return []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - tail_bytes))
        lines = f.read().decode("utf-8", "replace").splitlines()
    if size > tail_bytes:
        lines = lines[1:]                                  # the first line is probably cut in half
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def filled_pools(path):
    """Pool addresses that already have a fill row (from the index; rebuilt from the fills file if it is missing)."""
    ip = index_path(path)
    if os.path.exists(ip):
        with open(ip) as f:
            return {line.strip() for line in f if line.strip()}
    pools = {r["pool"] for r in iter_jsonl(fills_path(path)) if r.get("pool")}
    if pools:
        with open(ip, "w") as f:
            f.write("\n".join(sorted(pools)) + "\n")
    return pools


def append_fill(path, pool, record):
    """Append one pool's fill data. Never rewrites anything."""
    rec = {"pool": pool}
    rec.update((k, record[k]) for k in FILL_KEYS if k in record)
    with open(fills_path(path), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    with open(index_path(path), "a") as f:
        f.write(pool + "\n")


def load(path, candles=True, filled_only=False):
    """Registration rows merged with their fill data, oldest first. row["filled"] is True when the fill exists.
    candles=False drops the candle arrays (85% of the bytes) and leaves row["n_candles"] instead."""
    fills = {}
    for r in iter_jsonl(fills_path(path)):
        if not candles:
            r["n_candles"] = len(r.pop("candles", None) or [])
        fills[r.get("pool")] = r
    snaps = {r.get("pool"): r.get("helius_90") for r in iter_jsonl(snaps_path(path))}
    out = []
    for r in iter_jsonl(path):
        if r.get("pool") in snaps:
            r["helius_90"] = snaps[r["pool"]]
        if "candles" in r:                                 # filled inline, before the split
            r["filled"] = True
            if not candles:
                r["n_candles"] = len(r.pop("candles") or [])
        else:
            f = fills.get(r.get("pool"))
            if f:
                r.update((k, v) for k, v in f.items() if k != "pool")
                r["filled"] = True
        if r.get("filled") or not filled_only:
            out.append(r)
    return out


def migrate(path, out=print):
    """One-off, collector STOPPED: move inline fill data out of cohort.jsonl. The original is kept as
    cohort.jsonl.before-split until you delete it."""
    done, bad, moved, kept = filled_pools(path), [0], 0, 0
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as slim:
        for r in iter_jsonl(path, bad):
            if "candles" in r:
                if r["pool"] not in done:
                    append_fill(path, r["pool"], r)
                    done.add(r["pool"])
                moved += 1
                r = {k: v for k, v in r.items() if k not in FILL_KEYS}
            slim.write(json.dumps(r) + "\n")
            kept += 1
    if bad[0] > 3:                     # a single cut-off last line (collector killed mid-write) is expected and dropped
        os.remove(tmp)
        raise SystemExit(f"{bad[0]} unreadable lines in {path}: nothing was changed (is the collector still running?)")
    if bad[0]:
        out(f"dropped {bad[0]} unreadable line(s) (a row cut off when the collector was stopped)")
    backup = path + ".before-split"
    before = os.path.getsize(path)
    if not os.path.exists(backup):
        os.replace(path, backup)
    os.replace(tmp, path)
    out(f"migrated: {kept} rows kept, fill data of {moved} pools moved to {os.path.basename(fills_path(path))}; "
        f"{os.path.basename(path)} {before / 1e6:.1f} MB -> {os.path.getsize(path) / 1e6:.1f} MB "
        f"(original kept as {os.path.basename(backup)})")
    return moved


def stats(path, out=print):
    rows = load(path, candles=False)
    filled = sum(bool(r.get("filled")) for r in rows)
    out(f"{len(rows)} pools registered, {filled} filled, {len(rows) - filled} waiting")
    for p in (path, fills_path(path), index_path(path), snaps_path(path)):
        out(f"  {os.path.basename(p):28} {os.path.getsize(p) / 1e6:8.1f} MB" if os.path.exists(p) else f"  {os.path.basename(p):28} (absent)")
    return len(rows), filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--migrate", metavar="COHORT")
    ap.add_argument("--stats", metavar="COHORT")
    ap.add_argument("--collector-stopped", action="store_true", help="confirm the collector is not running")
    a = ap.parse_args()
    if a.migrate:
        log = os.path.join(os.path.dirname(os.path.abspath(a.migrate)), "daemon.log")
        if not a.collector_stopped and os.path.exists(log) and time.time() - os.path.getmtime(log) < 360:
            sys.exit("daemon.log was written in the last 6 minutes: the collector is probably running.\n"
                     "Use memebot\\migrate_store.bat (it stops the collector first), or pass --collector-stopped.")
        migrate(a.migrate)
    elif a.stats:
        stats(a.stats)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
