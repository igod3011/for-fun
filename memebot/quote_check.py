"""Does our swap math match what the market would really quote? (quotes only: no wallet, no key, no order)

For each pool: read real reserves + the pool's virtual reserve on-chain, ask Jupiter for a quote routed through
THAT pool for a buy of --stake SOL and for selling the tokens straight back, and compare with bot/amm.py at fee 0.
The gap is the fee really charged (pool + protocol + creator). Also catches tokens that cannot be sold.

  python -m memebot.quote_check                         # 8 recent canonical pools from cohort.jsonl
  python -m memebot.quote_check --pool POOL --mint MINT
"""
import argparse
import json
import statistics as st
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import rpc, store
from .bot import amm
from .bot.config import BotConfig

JUP = "https://lite-api.jup.ag/swap/v1/quote"
HDR = {"User-Agent": "memebot-research/0.1", "accept": "application/json"}
TOKEN_DECIMALS = 6          # every pump.fun mint


def jup_quote(input_mint, output_mint, amount_raw, timeout=20):
    """Raw Jupiter quote restricted to a single direct hop, or None."""
    q = urllib.parse.urlencode({"inputMint": input_mint, "outputMint": output_mint, "amount": int(amount_raw),
                                "slippageBps": 100, "onlyDirectRoutes": "true"})
    time.sleep(1.1)                                        # free tier: ~1 request per second
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{JUP}?{q}", headers=HDR), timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, ValueError, OSError):
        return None


def routed_out(quote, pool):
    """outAmount (raw units) if the quote is a single hop through `pool`, else None."""
    plan = (quote or {}).get("routePlan") or []
    if len(plan) != 1 or (plan[0].get("swapInfo") or {}).get("ammKey") != pool:
        return None
    return int(quote["outAmount"])


def implied_fee(quoted, model_at_zero_fee):
    """Fee fraction that explains the gap between a real quote and our fee-less math."""
    return 1 - quoted / model_at_zero_fee if model_at_zero_fee > 0 else None


def check(pool, mint, stake=0.2, quote=jup_quote, reserves=rpc.pool_reserves, virt=rpc.pool_virtual_sol):
    """One pool -> dict with implied buy / sell fee, or {"error": ...}."""
    s, t = reserves(pool, mint)
    v = virt(pool)
    if v is None or t <= 0:
        return {"error": "pool account unreadable or empty"}
    out = {"pool_sol": s, "virt_sol": v, "mcap_sol": amm.price(s, t, v) * 1e9}
    q_buy = routed_out(quote(rpc.WSOL, mint, stake * 1e9), pool)
    if q_buy is None:
        return dict(out, error="no direct buy quote through this pool")
    tokens = q_buy / 10 ** TOKEN_DECIMALS
    out["buy_fee"] = implied_fee(tokens, amm.buy(stake, s, t, 0.0, v))
    q_sell = routed_out(quote(mint, rpc.WSOL, q_buy), pool)
    if q_sell is None:
        return dict(out, error="NO SELL QUOTE: token may not be sellable (honeypot?)")
    # sell quote is against the pool as it is now (our buy never happened), so compare on the same reserves
    out["sell_fee"] = implied_fee(q_sell / 1e9, amm.sell(tokens, s, t, 0.0, v))
    s2, t2 = reserves(pool, mint)
    out["moved"] = abs(amm.price(s2, t2, v) / amm.price(s, t, v) - 1)     # pool traded meanwhile: reading is noisy
    return out


def recent_pools(path, n, min_sol=40.0):
    """Newest canonical pools (still liquid at registration) from the cohort tail."""
    out = []
    for r in reversed(store.tail_rows(path, 1_500_000)):
        h = r.get("helius_reg") or {}
        if r.get("mint", "").endswith("pump") and h.get("virt_sol") and (h.get("pool_sol") or 0) >= min_sol:
            out.append((r["pool"], r["mint"], r.get("name", "?")))
        if len(out) >= 3 * n:
            break
    return out


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--pool")
    ap.add_argument("--mint")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--stake", type=float, default=0.2)
    a = ap.parse_args()
    todo = [(a.pool, a.mint, a.mint[:6])] if a.pool and a.mint else recent_pools(a.data, a.n)
    cfg, fees, done = BotConfig(), [], 0
    print(f"{'token':16} {'pool SOL':>9} {'virt':>7} {'mcap SOL':>9} {'buy fee':>8} {'sell fee':>9}")
    for pool, mint, name in todo:
        if done >= a.n:
            break
        try:
            r = check(pool, mint, a.stake)
        except Exception as e:
            r = {"error": type(e).__name__}
        label = name.encode("ascii", "replace").decode()[:16]
        if "error" in r:
            print(f"{label:16} {r.get('pool_sol', 0):9.1f} {'':7} {'':9}  {r['error']}")
            continue
        if r["pool_sol"] < 20:
            continue                                       # dumped since registration: nothing to learn from it
        noisy = "  (pool moved, noisy)" if r["moved"] > 0.003 else ""
        print(f"{label:16} {r['pool_sol']:9.1f} {r['virt_sol']:7.3f} {r['mcap_sol']:9.0f} {r['buy_fee']:8.2%} {r['sell_fee']:9.2%}{noisy}")
        done += 1
        if not noisy:
            fees += [r["buy_fee"], r["sell_fee"]]
    if len(fees) >= 4:
        med = st.median(fees)
        print(f"\nmedian implied fee per swap: {med:.2%} over {len(fees)} quotes; the bot and backtest assume {cfg.fee:.2%}")
        if abs(med - cfg.fee) > 0.002:
            print("-> MISMATCH: fix BotConfig.fee / entry_timing.FEE, or find what the model is missing")
        else:
            print("-> our swap math matches real quotes")
    else:
        print("\ntoo few clean quotes to conclude")


if __name__ == "__main__":
    main()
