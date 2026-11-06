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
              f"pool SOL fell >80% (likely liquidity pulled / rug): {len(drained)} ({len(drained)/len(both):.0%})")
    if live:
        import statistics as st
        # entry = open of the 6th candle (5 min after first trade); exit = close of the last candle
        r = [p["candles"][-1][4] / sorted(p["candles"])[5][1] - 1 for p in live if len(p["candles"]) > 6]
        if r:
            print(f"naive buy@candle6, hold to end of data: n={len(r)} median {st.median(r):+.0%}, "
                  f"mean {st.mean(r):+.0%}, share>0 {sum(x > 0 for x in r)/len(r):.0%}  (no costs/slippage)")


if __name__ == "__main__":
    main(sys.argv[1])
