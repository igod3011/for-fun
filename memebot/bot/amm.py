"""Constant-product swap math on REAL pool reserves (SOL side, token side)."""


def buy(sol_in, pool_sol, pool_tok, fee):
    x = sol_in * (1 - fee)
    return pool_tok * x / (pool_sol + x)


def sell(tok_in, pool_sol, pool_tok, fee):
    return pool_sol * tok_in / (pool_tok + tok_in) * (1 - fee)
