"""Summarise a cohort file produced by collector_daemon / collect.py."""
import json
import sys
import time


def main(path):
    rows = [json.loads(l) for l in open(path)]
    now = time.time()
    filled = [p for p in rows if "candles" in p]
    live = [p for p in filled if len(p["candles"]) >= 30]
    print(f"registered={len(rows)}  filled={len(filled)}  with>=30 candles={len(live)}  "
          f"dead/empty={len(filled) - len(live)}  waiting(<3h)={len(rows) - len(filled)}")
    if rows:
        print(f"oldest registered {(now - min(p['created'] for p in rows)) / 3600:.1f}h ago")
    rc = [p["rugcheck"] for p in filled if p.get("rugcheck")]
    if rc:
        print(f"RugCheck: mint active {sum(not r['mint_revoked'] for r in rc)}/{len(rc)}, "
              f"freeze active {sum(not r['freeze_revoked'] for r in rc)}/{len(rc)}, rugged {sum(r['rugged'] for r in rc)}/{len(rc)}")
    both = [p for p in rows if p.get("helius_reg") and p.get("helius_fill")
            and p["helius_reg"].get("pool_sol") and p["helius_fill"].get("pool_sol") is not None]
    if both:
        drained = [p for p in both if p["helius_fill"]["pool_sol"] < 0.2 * p["helius_reg"]["pool_sol"]]
        print(f"Helius snapshots at registration AND fill: {len(both)} pools; "
              f"pool SOL fell >80% (liquidity pulled OR dumped; either way holders lose ~96%+): {len(drained)} ({len(drained)/len(both):.0%})")
    if filled:
        print(f"dead/illiquid: {len(filled) - len(live)}/{len(filled)} filled pools ({(len(filled) - len(live)) / len(filled):.0%}) "
              f"traded in fewer than 30 minutes of their first 3h+ -> most graduated memecoins die almost immediately")
    if filled:
        cohort_baseline(filled)
        realizable_baseline(rows)


def fixed_horizon_return(p, entry_delay_s=300, horizon_s=3 * 3600):
    """Buy at the open of the first candle >= created+5min, sell at the close of the last candle
    <= created+3h. Returns None if nothing traded in that window (no entry possible).
    Every pool that traded counts, dead or alive: no survivorship bias."""
    c = sorted(p.get("candles") or [])
    t0 = p["created"]
    window = [x for x in c if t0 + entry_delay_s <= x[0] <= t0 + horizon_s]
    if not window or window[0][1] <= 0:
        return None
    return window[-1][4] / window[0][1] - 1


def cohort_baseline(filled, cost=0.02):
    import statistics as st
    r = [x for x in (fixed_horizon_return(p) for p in filled) if x is not None]
    if len(r) < 4:
        return
    net = [(1 + x) * (1 - cost) - 1 for x in r]
    q = st.quantiles(net, n=4)
    print(f"[PRICE-BASED, UNRELIABLE: last trade price ignores whether exit liquidity still exists; drained pools "
          f"show absurd prices] buy 5min after migration, hold 3h, ALL pools that traded, "
          f"~{cost:.0%} round-trip cost: n={len(r)} of {len(filled)} filled "
          f"({len(filled) - len(r)} had no trade to enter)")
    print(f"   quartiles {q[0]:+.0%} / {q[1]:+.0%} / {q[2]:+.0%}; share>0 {sum(x > 0 for x in net)/len(net):.0%}; "
          f"share<-50% {sum(x < -0.5 for x in net)/len(net):.0%}; share>+100% {sum(x > 1 for x in net)/len(net):.0%}")
    eq = 1.0
    for x in net:          # equal stake on each pool: mean of returns, capped at +10x so one bogus candle can't dominate
        eq += min(x, 10) / len(net)
    print(f"   equal-stake average (gains capped at +1000%): {eq - 1:+.1%} per trade"
          f"  -> {'NEGATIVE: no edge' if eq < 1 else 'positive: check robustness before believing it'}")


def realizable_return(p, stake_sol=0.1, fee=0.01):
    """SOL you could actually get back. Buy `stake_sol` at the pool's spot price at registration
    (Helius reserves, minutes after migration), sell everything into the pool's REAL reserves at fill
    time (constant product: out = sol * q / (tokens + q)). A drained pool returns ~0 whatever its last
    trade price was. Returns None if a snapshot is missing/invalid."""
    r, f = p.get("helius_reg") or {}, p.get("helius_fill") or {}
    s0, t0 = r.get("pool_sol"), r.get("pool_tokens")
    s1, t1 = f.get("pool_sol"), f.get("pool_tokens")
    if not s0 or not t0 or s1 is None or t1 is None:
        return None
    q = stake_sol * (1 - fee / 2) * t0 / (s0 + stake_sol)     # tokens bought (with price impact)
    out = s1 * q / (t1 + q) * (1 - fee / 2)                   # SOL received selling into the real pool
    return out / stake_sol - 1


def realizable_baseline(rows, min_entry_sol=20.0):
    """Only pools you could actually have bought into: >= min_entry_sol SOL in the pool at registration.
    PumpSwap is permissionless, so the cohort mixes real pump.fun graduates (mint ends with 'pump')
    with pools created directly on PumpSwap; they are reported separately."""
    import statistics as st
    snap = [p for p in rows if (p.get("helius_reg") or {}).get("pool_sol") is not None and p.get("helius_fill")]
    if not snap:
        print("REALIZABLE baseline: needs pools with Helius snapshots at registration AND fill")
        return
    empty = [p for p in snap if (p["helius_reg"]["pool_sol"] or 0) < 1]
    thin = [p for p in snap if 1 <= (p["helius_reg"]["pool_sol"] or 0) < min_entry_sol]
    print(f"REALIZABLE (Helius reserves; buy 0.1 SOL at registration, sell into the REAL pool at fill, ~1% fees)")
    print(f"   {len(snap)} pools with both snapshots: {len(empty)} ({len(empty)/len(snap):.0%}) were ALREADY EMPTY (<1 SOL) "
          f"minutes after creation (untradable), {len(thin)} thin (<{min_entry_sol:.0f} SOL) excluded")
    tradable = [p for p in snap if (p["helius_reg"]["pool_sol"] or 0) >= min_entry_sol]
    for label, grp in (("pump.fun graduates (mint ...pump)", [p for p in tradable if p["mint"].endswith("pump")]),
                       ("other PumpSwap pools", [p for p in tradable if not p["mint"].endswith("pump")])):
        r = [x for x in (realizable_return(p) for p in grp) if x is not None]
        if len(r) < 4:
            print(f"   {label}: n={len(r)} (too few)")
            continue
        q = st.quantiles(r, n=4)
        avg = sum(min(x, 10) for x in r) / len(r)
        print(f"   {label}: n={len(r)} quartiles {q[0]:+.0%} / {q[1]:+.0%} / {q[2]:+.0%}; share>0 {sum(x > 0 for x in r)/len(r):.0%}; "
              f"share<-50% {sum(x < -0.5 for x in r)/len(r):.0%}; avg (cap +1000%) {avg:+.1%}"
              f" -> {'NEGATIVE' if avg < 0 else 'positive, verify'}")

if __name__ == "__main__":
    main(sys.argv[1])
