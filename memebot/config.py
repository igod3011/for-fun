from dataclasses import dataclass


@dataclass
class Config:
    # portfolio
    capital: float = 1000.0
    position_pct: float = 0.05      # fraction of equity per trade
    max_positions: int = 5
    max_liq_frac: float = 0.02      # never trade more than 2% of pool liquidity
    fee: float = 0.005              # 0.5% per swap (DEX fee + priority fee approx)

    # universe filters
    min_liquidity: float = 15_000
    min_age_min: int = 5
    max_age_min: int = 240

    # anomaly / rug detection
    max_top10: float = 0.45
    min_lp_locked: float = 0.5
    drain_pct: float = 0.25         # liquidity drop vs 5-candle max that counts as a drain
    dump_pct: float = 0.35          # one-candle price drop with sell pressure
    wash_makers_ratio: float = 0.15  # unique makers / txns below this => wash trading
    max_score: int = 60             # entry blocked at or above this score

    # strategy: breakout + volume
    lookback: int = 15
    vol_mult: float = 3.0
    min_buy_ratio: float = 0.6
    max_run: float = 4.0            # skip if price already >4x over last 10 candles

    # exits
    stop_loss: float = 0.15
    trail_activate: float = 0.30
    trail: float = 0.20
    max_hold_min: int = 120
