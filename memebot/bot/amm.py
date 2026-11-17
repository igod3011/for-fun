"""Swap math for PumpSwap pools on REAL reserves (SOL side, token side).

A PumpSwap pool seeded by a pump.fun migration does NOT price swaps on its real SOL alone: the invariant is
    (real SOL + VIRTUAL quote reserve) x tokens = K        (K ~ 1.756e10 at migration, grows with LP fees)
The virtual amount is stored in the pool account (u64 lamports at byte offset 245, rpc.pool_virtual_sol). It is
PER POOL: ~17.56 SOL in most pools (11/2026), but 10-15% of pools hold less (seen: 15.3, 11.2, 2.9) and pools not
created by a migration hold 0. With the pool's own value K is 1.760e10 within 0.4% at registration, so always
prefer the value read on-chain (cohort: helius_reg.virt_sol; bot: Position.virt_sol) over PUMP_VIRTUAL_SOL, which
is only the fallback for rows collected before 11/2026.
Fee: quotes through these pools (memebot.quote_check, 11/11/2026) imply 1.20-1.25% per swap at market caps of
250-1,500 SOL, a little less above; the project had assumed 0.5%.
Consequences of ignoring it (the project did until 11/2026):
  * price = (S+V)/T, not S/T: every price move was overstated, by ~10% of the move at S=85 SOL;
  * tokens bought / SOL received were off by (S+V)/S when the price moved between entry and exit;
  * a holder dumping the whole supply leaves ~0.4 real SOL, which looked like "liquidity removed" (S x T falls
    ~97%) although the LP is burnt. It is a plain dump: nothing was pulled.
Pass virt=0 for pools that are not pump.fun migrations.
"""
PUMP_VIRTUAL_SOL = 17.584
PUMP_FEE = 0.012               # per swap, measured from real quotes (see above)


def row_virt(row, default=PUMP_VIRTUAL_SOL):
    """Virtual reserve of a cohort row: the value read on-chain at registration when it was recorded."""
    v = (row.get("helius_reg") or {}).get("virt_sol")
    return default if v is None else v


def buy(sol_in, pool_sol, pool_tok, fee, virt=0.0):
    x = sol_in * (1 - fee)
    return pool_tok * x / (pool_sol + virt + x)


def sell(tok_in, pool_sol, pool_tok, fee, virt=0.0):
    out = (pool_sol + virt) * tok_in / (pool_tok + tok_in) * (1 - fee)
    return min(out, pool_sol)            # a pool can never pay more than the SOL it really holds


def price(pool_sol, pool_tok, virt=0.0):
    """Spot price in SOL per token."""
    return (pool_sol + virt) / pool_tok
