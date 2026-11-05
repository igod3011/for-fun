# memebot — memecoin paper-trading & backtest framework

Paper trading only: no wallet, no private keys, no real orders.

## Run
```bash
python3 -m memebot.backtest --strategy breakout_volume --n 600 --seed 11   # synthetic backtest
python3 -m unittest memebot.tests.test_memebot                             # tests
python3 -m memebot.live --once    # live paper run (needs access to dexscreener/rugcheck; UNTESTED)
```

## How it works
1. **Universe** – new Solana pairs (DexScreener token profiles; pump.fun tokens show up here once they have a pool).
2. **Anomaly / rug detection** (`anomaly.py`)
   - Hard blocks (also force-exit open positions): mint authority active, freeze authority active, liquidity drain (>25% vs 5-candle max), dump (>35% one-candle drop with sell majority).
   - Scored: top-10 holders >45%, LP not locked, wash trading (unique makers / txns <15%), sell pressure (>65% sells), parabolic (>4x in 10 candles), low liquidity.
3. **Strategies** (`strategy.py`)
   - `breakout_volume`: close above N-candle high, volume ≥3x average, ≥60% buys.
   - `pullback_reclaim`: 25–50% pullback after a run, buy the EMA-10 reclaim.
4. **Risk** – 5% of equity per trade, ≤2% of pool liquidity, ≤5 positions, 15% stop, trailing stop after +30%, 120-min time stop.
5. **Execution model** (`broker.py`) – AMM price impact + 0.5% fee. A rugged pool returns almost nothing on exit.

## Honest limitations
- Backtest data is **synthetic** (hand-made generator). It proves the plumbing and shows the filter blocks bad tokens; it does **not** prove an edge. Next step: record real candles + RugCheck results for a few weeks, then re-run.
- `live.py` is untested against the real APIs. DexScreener has no OHLC, so live candles are approximated.
- Not modelled: MEV/sniper front-running, failed transactions, Jito tips, honeypots that block sells (RugCheck only partly catches them), pump.fun bonding-curve phase (before graduation to a DEX pool).
- Most memecoin trades lose money. Expect a large share of tokens to be rugs; filters reduce, not remove, that.

## Ideas to extend (not implemented)
- Bonding-curve sniping on pump.fun (needs RPC/websocket, very competitive).
- Smart-money wallet copy-trading (track wallets with a history of early entries).
- Dev-wallet tracking: flag creators who launched previous rugs.
- Sell simulation via Jupiter quote API before entry (honeypot check).
- Social/volume divergence filters.
