"""The hypothesis registry. Each entry states HOW it is supposed to make money and WHEN it is dropped, before it is
scored. A hypothesis is a function(data) -> (trades, note): trades = [(timestamp, net return as a fraction of the
stake)], every cost already deducted. `variants` is the number of parameter sets that were tried for that idea
(including discarded ones): the scorer widens the confidence interval accordingly.

stake_usd is the position size on the 100 USD research account (max acceptable loss 50 USD).
Nothing here places orders. Texts shown to the user are Vietnamese; code and comments are English.
"""
import bisect
import math

from ..bot.config import BotConfig
from ..bot.strategy import entry_check

REGISTRY = []
DAY = 86400
PERP_COST = 0.0007          # taker fee 0.05% + slippage 0.02% per side (Binance USDT perpetuals)
SPOT_COST = 0.0012          # taker fee 0.10% + slippage 0.02% per side


def hypothesis(id, name, family, mechanism, kill, stake_usd, variants=1):
    def wrap(fn):
        REGISTRY.append({"id": id, "name": name, "family": family, "mechanism": mechanism, "kill": kill,
                         "stake_usd": stake_usd, "variants": variants, "fn": fn})
        return fn
    return wrap


# ---------------------------------------------------------------------------------------------------------
# Memecoin: pump.fun pools after migration (the collector's cohort). Returns are what the pool really pays.
# ---------------------------------------------------------------------------------------------------------
BOT_EXITS = {"sl": 0.10, "tp": [], "trail_on": 0.2, "trail": 0.1, "max_hold": 60}


def _meme_trades(data, stake_usd, pick, when, guard=True):
    """pick(row) -> bool chooses pools; when(row, setup) -> entry timestamp or None. Bot exits, stop filled no
    better than the candle close, 0.0003 SOL fixed fee per transaction, stake converted to SOL at the cohort's
    median SOL price. guard = the bot's falling-knife rule (pool SOL not more than 20% below registration)."""
    from ..ml import entry_timing as et
    saved = et.STAKE, et.TX_FEE, et.STOP_FILL
    et.STAKE, et.TX_FEE, et.STOP_FILL = stake_usd / data.sol_usd(), 0.0003, "close"
    try:
        out = []
        for p, S in data.cohort_pools():
            if not pick(p):
                continue
            te = when(p, S)
            e = et.entry(S, p["created"], (te - p["created"]) / 60, guard=False, momentum=False, max_h1=0.8) if te else None
            if not e:
                continue
            te, usd, s_e, t_e = e
            if s_e < 40 or (guard and te >= S["t_reg"] and s_e < 0.8 * S["s0"]):
                continue
            q = et.buy_at(s_e, t_e, S["v"])
            out.append((te, (et.exit_bot(S, te, usd, s_e, q, BOT_EXITS) - et.TX_FEE) / et.STAKE - 1))
        return out
    finally:
        et.STAKE, et.TX_FEE, et.STOP_FILL = saved


def _at(minutes):
    return lambda p, S: p["created"] + minutes * 60


def _organic(p, _cfg=BotConfig()):
    return entry_check(p, _cfg)[0]


@hypothesis("M1", "Mua mọi pool chuẩn pump.fun lúc 90 phút tuổi", "memecoin",
            "Pool sống sót 90 phút được cho là đã qua giai đoạn xả hàng.",
            "Loại nếu cả khoảng tin cậy nằm dưới 0.", stake_usd=5)
def m1(data):
    return _meme_trades(data, 5, lambda p: True, _at(90)), "mọi pool chuẩn, không lọc holder"


@hypothesis("M2", "Chỉ pool tự nhiên (lọc dàn ví, loại ví giữ từ 50%) lúc 90 phút", "memecoin",
            "Loại bỏ pool do dàn ví hoặc một ví kiểm soát; phần còn lại có người mua thật.",
            "Loại nếu sau 100 lệnh paper kỳ vọng vẫn không dương, hoặc tới cuối 11/2026 khoảng tin cậy còn chứa 0.",
            stake_usd=5, variants=4)
def m2(data):
    return _meme_trades(data, 5, _organic, _at(90)), "đây là cấu hình bot paper đang chạy"


@hypothesis("M3", "Mua nhanh: 5 phút sau khi lên sàn", "memecoin",
            "Vào sớm hơn người khác ngay sau khi token tốt nghiệp.",
            "Loại nếu cả khoảng tin cậy nằm dưới 0.", stake_usd=5, variants=5)
def m3(data):
    return _meme_trades(data, 5, lambda p: True, _at(5), guard=False), "đã thử 2, 3, 5, 10, 20 phút"


def _first_dip(depth):
    def when(p, S):
        c = S["c"]
        lo_t, hi_t = p["created"] + 30 * 60, p["created"] + 120 * 60
        for j, x in enumerate(c):
            if x[0] < lo_t or x[0] > hi_t:
                continue
            win = [y for y in c[max(0, j - 40):j + 1] if y[0] >= x[0] - 1800]
            if len(win) >= 5 and x[4] <= (1 - depth) * max(y[2] for y in win):
                nxt = c[j + 1] if j + 1 < len(c) else None      # decided on this close, filled on the next candle
                return nxt[0] if nxt and nxt[0] - x[0] <= 180 else None
        return None
    return when


@hypothesis("M4", "Mua sau cú giảm từ 35% so với đỉnh 30 phút (pool tự nhiên)", "memecoin",
            "Giá giảm quá đà sẽ hồi lại.",
            "Loại nếu cả khoảng tin cậy nằm dưới 0.", stake_usd=5, variants=9)
def m4(data):
    return _meme_trades(data, 5, _organic, _first_dip(0.35), guard=False), "đã thử 3 độ sâu x 3 kiểu chờ bật lại"


# ---------------------------------------------------------------------------------------------------------
# Futures (Binance USDT perpetuals, public data)
# ---------------------------------------------------------------------------------------------------------
def _ema(x, n):
    k, e = 2 / (n + 1), [x[0]]
    for v in x[1:]:
        e.append(e[-1] + k * (v - e[-1]))
    return e


def _atr(c, n=14):
    tr = [c[0][2] - c[0][3]] + [max(c[i][2] - c[i][3], abs(c[i][2] - c[i - 1][4]), abs(c[i][3] - c[i - 1][4]))
                                 for i in range(1, len(c))]
    return _ema(tr, 2 * n - 1)


def _funding_sum(rows, t0, t1):
    """Sum of funding rates with t0 < ts <= t1 (rows sorted by time)."""
    ts = [r[0] for r in rows]
    return sum(r[1] for r in rows[bisect.bisect_right(ts, t0):bisect.bisect_right(ts, t1)])


def ema_trades(c, fund, fast=20, slow=100, lev=5, stop_atr=2.5):
    """Always follow the EMA cross; enter at the next bar's open, ATR stop, return on MARGIN (lev x), -100% floor
    (liquidation). After a stop-out it waits for the next cross."""
    cl = [x[4] for x in c]
    a, b, A = _ema(cl, fast), _ema(cl, slow), _atr(c)
    sig = [0] * len(c)
    for i in range(slow, len(c)):
        sig[i] = 1 if a[i] > b[i] else -1
    trades, cur, entry, stop, t_in = [], 0, 0.0, 0.0, 0
    for i in range(slow + 2, len(c)):
        o, want, prev = c[i][1], sig[i - 1], sig[i - 2]
        hit = None
        if cur and want != cur:
            hit = o                                             # cross against us: out at the open
        if cur and hit is None:
            if cur == 1 and c[i][3] <= stop:
                hit = min(stop, o)
            elif cur == -1 and c[i][2] >= stop:
                hit = max(stop, o)
        if hit is not None:
            ret = cur * (hit / entry - 1) - 2 * PERP_COST - cur * _funding_sum(fund, t_in, c[i][0])
            trades.append((c[i][0], max(-1.0, lev * ret)))
            cur = 0
        if cur == 0 and want != 0 and want != prev and hit in (None, o):
            cur, entry, stop, t_in = want, o, o - want * stop_atr * A[i - 1], c[i][0]
    return trades


@hypothesis("F1", "Theo xu hướng EMA 20/100 nến 1h trên PEPE và PUMP (10 USD x5)", "futures",
            "Xu hướng giá kéo dài; chỉ báo trung bình động bắt được nó.",
            "Loại nếu cả khoảng tin cậy nằm dưới 0, hoặc lãi lúc chọn tham số nhưng lỗ lúc kiểm tra.",
            stake_usd=10, variants=24)
def f1(data):
    out = []
    for sym in ("1000PEPEUSDT", "PUMPUSDT"):
        out += ema_trades(data.hourly(sym), data.funding([sym])[sym])
    return out, "lợi nhuận tính trên ký quỹ; đã thử 24 cấu hình của 4 loại chỉ báo"


def _btc(daily):
    return {r[0]: r[4] for r in daily["BTCUSDT"]["d"]}


@hypothesis("F5", "Bán khống coin mới niêm yết từ ngày 7, giữ 30 ngày, cắt lỗ +50%, kèm mua BTC", "futures",
            "Coin mới được niêm yết ở đỉnh chú ý; người giữ từ trước bán dần trong các tuần sau.",
            "Loại nếu kỳ vọng âm ở nửa sau thêm một quý nữa, hoặc funding của bên bán âm hơn 3% mỗi lệnh.",
            stake_usd=5, variants=15)
def f5(data, d0=7, hold=30, stop=0.5, since=1704067200):
    daily = data.daily()
    btc = _btc(daily)
    new = sorted((v["onboard"], s) for s, v in daily.items() if v["onboard"] >= since and len(v["d"]) > d0 + hold)
    fund = data.funding([s for _, s in new])
    out = []
    for _, s in new:
        d = daily[s]["d"]
        e, x = d[d0], d[d0 + hold]
        pe, exit_px, exit_t = e[4], x[4], x[0]
        for r in d[d0 + 1:d0 + hold + 1]:
            if r[2] >= pe * (1 + stop):
                exit_px, exit_t = max(pe * (1 + stop), r[1]), r[0]      # gapped through the stop: filled at the open
                break
        b0, b1 = btc.get(e[0]), btc.get(exit_t)
        if not (b0 and b1):
            continue
        fr = _funding_sum(fund[s], e[0] + DAY, exit_t + DAY)             # shorts receive positive funding
        out.append((exit_t, 1 - exit_px / pe + fr + (b1 / b0 - 1) - 4 * PERP_COST))
    return out, ("thiếu các hợp đồng đã hủy niêm yết; đòn bẩy x1, không dùng được x5 vì cắt lỗ ở +50%; khoảng 13 vị thế mở "
                 "cùng lúc nên mỗi lệnh chỉ 5 USD; các lệnh chồng thời gian và cùng chịu một cú tăng của altcoin, "
                 "nên xác suất lỗ lớn thực tế cao hơn con số mô phỏng")


@hypothesis("F6", "Động lượng 1 tuần: mua nhóm 20% tăng mạnh nhất, bán nhóm 20% giảm mạnh nhất", "futures",
            "Coin đang mạnh tiếp tục mạnh hơn coin đang yếu trong tuần kế tiếp.",
            "Loại nếu cả khoảng tin cậy nằm dưới 0.", stake_usd=50, variants=4)
def f6(data, look=1, min_volume=20e6):
    daily = data.daily()
    closes = {s: {r[0]: (r[4], r[5]) for r in v["d"]} for s, v in daily.items()}
    days = sorted(_btc(daily))
    weeks, out = days[::7], []
    for i in range(4, len(weeks) - 1):
        t0, t, t1 = weeks[i - look], weeks[i], weeks[i + 1]
        k = days.index(t)
        rows = []
        for c in closes.values():
            if t0 in c and t in c and t1 in c and weeks[i - 4] in c:
                vol = sum(c[d][1] for d in days[k - 7:k] if d in c) / 7
                if vol >= min_volume:
                    rows.append((c[t][0] / c[t0][0] - 1, c[t1][0] / c[t][0] - 1))
        if len(rows) < 30:
            continue
        rows.sort()
        q = len(rows) // 5
        spread = (sum(r[1] for r in rows[-q:]) - sum(r[1] for r in rows[:q])) / q / 2      # per 1 USD gross
        out.append((t1, spread - 2 * PERP_COST))
    return out, "mỗi tuần là một lệnh trên tổng vị thế 50 USD; coi như đổi toàn bộ danh mục hằng tuần"


@hypothesis("C1", "Ăn funding trung lập giá: mua spot, bán perp ở coin có funding cao", "carry",
            "Người long dùng đòn bẩy trả funding cho người short; giữ spot để triệt tiêu biến động giá.",
            "Loại nếu lợi suất ròng sau phí dưới 5% một năm trên vốn sử dụng, hoặc khoảng tin cậy chứa 0.",
            stake_usd=30, variants=2)
def c1(data, universe=40, top=3, keep=10, min_week=0.001):
    """Weekly: enter the `top` symbols by trailing 7-day funding (at least min_week), keep a position while the
    symbol stays in the top `keep` with positive trailing funding. One trade = one position-week; the return is
    (funding received that week - entry and exit costs of both legs, charged in the first week) on the capital used (spot + 1x perp margin = 2x the
    notional). Basis drift between spot and perp is ignored, and a spot market is assumed to exist."""
    daily = data.daily()
    last = max(r[0] for r in daily["BTCUSDT"]["d"])
    liquid = sorted(daily, key=lambda s: -sum(r[5] for r in daily[s]["d"][-30:]) if daily[s]["d"][-1][0] >= last - 3 * DAY else 0)
    syms = liquid[:universe]
    fund = data.funding(syms)
    start = min(rows[0][0] for rows in fund.values() if rows)
    held, out = {}, []
    t = start + 7 * DAY
    while t <= last:
        trail = {s: _funding_sum(rows, t - 7 * DAY, t) for s, rows in fund.items() if rows and rows[0][0] <= t - 7 * DAY and rows[-1][0] >= t - DAY}
        ranked = sorted(trail, key=lambda s: -trail[s])
        stay = {s for s in ranked[:keep] if trail[s] > 0}
        for s in list(held):                                    # one "trade" = one position-week
            cost = (2 * PERP_COST + 2 * SPOT_COST) if held[s] else 0.0      # both legs, in and out, charged up front
            out.append((t, (_funding_sum(fund[s], t - 7 * DAY, t) - cost) / 2))
            held[s] = False
            if s not in stay:
                del held[s]
        for s in ranked[:top]:
            if len(held) < top and s not in held and trail[s] >= min_week:
                held[s] = True                                  # True = entry week, costs not charged yet
        t += 7 * DAY
    return out, "bỏ qua chênh lệch spot-perp và giả định coin nào cũng có thị trường spot; vốn dùng gấp đôi vị thế"
