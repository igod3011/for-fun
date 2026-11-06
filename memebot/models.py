from dataclasses import dataclass, field


@dataclass(frozen=True)
class Candle:
    ts: int          # minutes since epoch (or since start of simulation)
    open: float
    high: float
    low: float
    close: float
    volume: float    # USD
    buys: int
    sells: int
    makers: int      # unique wallets that traded in this candle
    liquidity: float  # pool liquidity in USD at candle close


@dataclass
class TokenMeta:
    id: str
    symbol: str
    created_ts: int
    mint_revoked: bool = True
    freeze_revoked: bool = True
    top10_pct: float = 0.0       # share of supply held by top 10 wallets (0..1)
    lp_locked_pct: float = 1.0   # share of LP burned/locked (0..1)
    rugged: bool = False         # flagged as rugged by an external checker (RugCheck)


@dataclass
class Token:
    meta: TokenMeta
    candles: list = field(default_factory=list)
