"""Score every registered hypothesis and write the ranking. Research only: nothing here trades.

  python -m memebot.research.run                 all hypotheses (downloads missing public data once)
  python -m memebot.research.run --offline       only data already on disk
  python -m memebot.research.run --only F5,C1    some of them (the ranking file is not rewritten)
"""
import argparse
import sys
import time

from . import hypotheses, score
from .data import Data, Missing

CAPITAL, MAX_LOSS = 100.0, 50.0
LABEL = {score.PASS: "ĐẠT, chuyển sang paper", score.UNPROVEN: "Chưa chứng minh", score.REJECTED: "Loại",
         score.NO_DATA: "Thiếu dữ liệu"}
REASON = {"all gates passed": "qua mọi ngưỡng", "the whole confidence interval is below 0": "cả khoảng tin cậy nằm dưới 0",
          "interval contains 0": "khoảng tin cậy chứa 0", "not positive in both halves": "không dương ở cả hai nửa",
          "no trades": "không có lệnh nào"}


def evaluate(h, data):
    """Run one hypothesis. Never raises: missing data or a bug in a hypothesis becomes a NO_DATA row."""
    row = {k: h[k] for k in ("id", "name", "family", "mechanism", "kill", "stake_usd", "variants")}
    try:
        trades, note = h["fn"](data)
    except Missing as e:
        return {**row, "m": {"n": 0}, "status": score.NO_DATA, "reason": f"thiếu dữ liệu: {e}", "note": "", "mc": None}
    except Exception as e:
        return {**row, "m": {"n": 0}, "status": score.NO_DATA, "reason": f"lỗi khi chạy: {type(e).__name__}: {e}", "note": "", "mc": None}
    m = score.metrics(trades, h["variants"])
    status, reason = score.verdict(m)
    mc = score.monte_carlo([r for _, r in trades], h["stake_usd"], m["per_year"], CAPITAL, MAX_LOSS) if m.get("n") else None
    return {**row, "m": m, "status": status, "reason": reason, "note": note, "mc": mc}


def vi_reason(reason):
    parts = []
    for part in reason.split("; "):
        if part in REASON:
            parts.append(REASON[part])
        elif part.startswith("only "):
            parts.append("mới có " + part[5:].replace("trades", "lệnh"))
        elif "trades <" in part:
            parts.append(part.replace("trades <", "lệnh, cần"))
        elif part.startswith("negative without"):
            parts.append(f"âm nếu bỏ {score.TOP_DROP} lệnh thắng lớn nhất")
        else:
            parts.append(part)
    return "; ".join(parts)


def pct(v):
    return "—" if v is None else f"{v:+.1%}"


def render(rows, stamp):
    rows = sorted(rows, key=lambda r: score.rank_key(r["m"], r["status"], r["stake_usd"]) if r["m"].get("n") else (9, 0))
    out = ["# Bảng xếp hạng giả thuyết (tự sinh)", "",
           f"Tạo lúc {stamp} bằng `python -m memebot.research.run`. Đừng sửa tay: chạy lại lệnh đó.",
           f"Tài khoản nghiên cứu {CAPITAL:.0f} USD, mức lỗ tối đa chấp nhận {MAX_LOSS:.0f} USD. Mọi con số là sau phí.",
           "Xếp theo: đã qua ngưỡng trước, rồi tới cận dưới của lãi ròng một năm (không xếp theo trung bình).", "",
           "| Hạng | Mã | Giả thuyết | Kết luận | Số lệnh | Kỳ vọng mỗi lệnh | Khoảng tin cậy | Nửa đầu / nửa sau | Thắng | Lãi ròng 1 năm (cận dưới .. trung bình) | Xác suất lỗ quá 50 USD trong 1 năm |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        m = r["m"]
        if not m.get("n"):
            out.append(f"| {i} | {r['id']} | {r['name']} | {LABEL[r['status']]}: {vi_reason(r['reason'])} | 0 | — | — | — | — | — | — |")
            continue
        ci = m["ci"]
        year = lambda v: v * r["stake_usd"] * m["per_year"]
        usd = lambda v: f"{v:+.0f}" if v > -MAX_LOSS else f"chạm mức dừng -{MAX_LOSS:.0f}"
        out.append(
            f"| {i} | {r['id']} | {r['name']} | {LABEL[r['status']]} | {m['n']} | {pct(m['mean'])} | "
            + (f"{pct(ci[0])} .. {pct(ci[1])} ({m['ci_level']:.1%})" if ci else "—")
            + f" | {pct(m['half1'])} / {pct(m['half2'])} | {m['win']:.0%} | "
            + (f"{usd(year(ci[0]))} .. {usd(year(m['mean']))} USD" if ci else "—")
            + " | " + (f"{r['mc']['p_ruin']:.0%}" if r["mc"] else "—") + " |")
    out += ["", "## Chi tiết từng giả thuyết", ""]
    for r in rows:
        m = r["m"]
        out += [f"### {r['id']}. {r['name']}",
                f"- Cơ chế: {r['mechanism']}",
                f"- Điều kiện loại bỏ (viết trước): {r['kill']}",
                f"- Kết luận: **{LABEL[r['status']]}** ({vi_reason(r['reason'])})."]
        if m.get("n") and r["status"] == score.PASS and m["recent"] <= 0:
            out.append(f"- **Cảnh báo:** 20% lệnh gần nhất có kỳ vọng {pct(m['recent'])}: lợi thế có thể đang mất dần.")
        if m.get("n"):
            out.append(f"- Cỡ lệnh {r['stake_usd']:g} USD, khoảng {m['per_year']:.0f} lệnh mỗi năm, dữ liệu {m['days']:.0f} ngày, "
                       f"đã thử {r['variants']} biến thể. Trung vị {pct(m['median'])}, lệnh tệ nhất {pct(m['worst'])}, "
                       f"profit factor {m['profit_factor']:.2f}, bỏ {score.TOP_DROP} lệnh thắng lớn nhất còn {pct(m['ex_top'])}, "
                       f"20% lệnh gần nhất {pct(m['recent'])}.")
        if r["mc"]:
            mc = r["mc"]
            out.append(f"- Mô phỏng 1 năm ({mc['trades']} lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất {mc['p5']:+.0f} USD, "
                       f"trung vị {mc['p50']:+.0f} USD, 5% tốt nhất {mc['p95']:+.0f} USD.")
        if r["note"]:
            out.append(f"- Lưu ý: {r['note']}.")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--cache", default="research_data")
    ap.add_argument("--offline", action="store_true", help="do not download anything")
    ap.add_argument("--only", default="", help="comma-separated hypothesis ids")
    ap.add_argument("--out", default="memebot/research/RANKING.md")
    a = ap.parse_args(argv)
    only = {x.strip().upper() for x in a.only.split(",") if x.strip()}
    data = Data(a.data, a.cache, a.offline)
    rows = []
    for h in hypotheses.REGISTRY:
        if only and h["id"] not in only:
            continue
        r = evaluate(h, data)
        rows.append(r)
        m = r["m"]
        print(f"{r['id']:3} {LABEL[r['status']]:24} n={m.get('n', 0):5} "
              + (f"avg {pct(m['mean'])} CI {pct(m['ci'][0])}..{pct(m['ci'][1])} halves {pct(m['half1'])}/{pct(m['half2'])}"
                 if m.get("ci") else vi_reason(r["reason"])), flush=True)
    text = render(rows, time.strftime("%Y-%m-%d %H:%M"))
    if not only:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        print(f"wrote {a.out}")
    return rows


if __name__ == "__main__":
    main()
