"""Swap math for PumpSwap pools on REAL reserves (SOL side, token side).

A PumpSwap pool seeded by a pump.fun migration does NOT price swaps on its real SOL alone: the invariant is
    (real SOL + VIRTUAL quote reserve) x tokens = K        (K ~ 1.756e10 at migration, grows with LP fees)
The virtual amount is stored in the pool account (u64 lamports at byte offset 245) and was 17.584 SOL in every
pool checked on-chain (11/2026); 1,183 cohort pools give a median of 17.42 SOL from their reserves alone.
Consequences of ignoring it (the project did until 11/2026):
  * price = (S+V)/T, not S/T: every price move was overstated, by ~10% of the move at S=85 SOL;
  * tokens bought / SOL received were off by (S+V)/S when the price moved between entry and exit;
  * a holder dumping the whole supply leaves ~0.4 real SOL, which looked like "liquidity removed" (S x T falls
    ~97%) although the LP is burnt. It is a plain dump: nothing was pulled.
Pass virt=0 for pools that are not pump.fun migrations.
"""
PUMP_VIRTUAL_SOL = 17.584


def buy(sol_in, pool_sol, pool_tok, fee, virt=0.0):
    x = sol_in * (1 - fee)
    return pool_tok * x / (pool_sol + virt + x)


def sell(tok_in, pool_sol, pool_tok, fee, virt=0.0):
    out = (pool_sol + virt) * tok_in / (pool_tok + tok_in) * (1 - fee)
    return min(out, pool_sol)            # a pool can never pay more than the SOL it really holds


def price(pool_sol, pool_tok, virt=0.0):
    """Spot price in SOL per token."""
    return (pool_sol + virt) / pool_tok
