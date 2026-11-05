"""Entry signals. Each takes the candle history (last element = just-closed candle)."""


def _buy_ratio(c):
    t = c.buys + c.sells
    return c.buys / t if t else 0.0


def breakout_volume(candles, cfg):
    """Close breaks the highest high of the last N candles on a volume surge with buyer dominance."""
    n = cfg.lookback
    if len(candles) < n + 1:
        return False
    prior, cur = candles[-n - 1:-1], candles[-1]
    avg_vol = sum(x.volume for x in prior) / n
    if avg_vol <= 0:
        return False
    return (
        cur.close > max(x.high for x in prior)
        and cur.volume >= cfg.vol_mult * avg_vol
        and _buy_ratio(cur) >= cfg.min_buy_ratio
    )


def pullback_reclaim(candles, cfg):
    """After a run-up, buy the reclaim of the 10-candle EMA following a 25-50% pullback."""
    if len(candles) < 25:
        return False
    win = candles[-40:]
    peak_i = max(range(len(win)), key=lambda i: win[i].high)
    if peak_i >= len(win) - 3:
        return False
    peak = win[peak_i].high
    trough = min(x.low for x in win[peak_i:])
    dd = (peak - trough) / peak
    if not 0.25 <= dd <= 0.50:
        return False
    closes = [x.close for x in candles[-12:]]
    k, ema = 2 / 11, closes[0]
    emas = []
    for p in closes:
        ema = p * k + ema * (1 - k)
        emas.append(ema)
    cur = candles[-1]
    return closes[-2] <= emas[-2] and closes[-1] > emas[-1] and _buy_ratio(cur) >= 0.55


STRATEGIES = {"breakout_volume": breakout_volume, "pullback_reclaim": pullback_reclaim}
