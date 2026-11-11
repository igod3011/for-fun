"""Is the collector alive and doing its job? One command, PASS/WARN/FAIL per check.

  python -m memebot.healthcheck                     # reads cohort.jsonl / daemon.log / daemon.err in cwd
  python -m memebot.healthcheck --live              # ALSO makes real API calls right now (~1 min) into a temp file
Exit code 0 = no FAIL, 1 = at least one FAIL.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from . import store
from .bot.amm import PUMP_VIRTUAL_SOL


def _age_min(ts):
    return (time.time() - ts) / 60


def main():
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--log", default="daemon.log")
    ap.add_argument("--err", default="daemon.err")
    ap.add_argument("--state", default="bot_state.json")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    res = []

    def out(level, msg):
        res.append(level)
        print(f"{level:4} {msg}")

    # 1) process (Windows only; elsewhere rely on freshness checks below)
    if os.name == "nt":
        t = subprocess.run("tasklist", capture_output=True, text=True, shell=True).stdout.lower()
        n = t.count("python.exe")
        out("PASS" if n >= 1 else "FAIL", f"python.exe processes running: {n}" + ("" if n else "  -> collector is not running"))

    # 2) daemon.log freshness + recent content
    if os.path.exists(a.log):
        age = _age_min(os.path.getmtime(a.log))
        out("PASS" if age < 6 else "FAIL", f"{a.log} last written {age:.1f} min ago" + ("" if age < 6 else "  -> daemon stopped or stuck"))
        tail = open(a.log, encoding="utf-8", errors="replace").read().splitlines()[-40:]
        bad = [l for l in tail if re.search(r"Traceback|Error|skip pool|HTTP 4|HTTP 5", l)]
        out("PASS" if not bad else "WARN", f"errors in last 40 log lines: {len(bad)}" + (f"  e.g. {bad[-1][:110]}" if bad else ""))
        cov = [int(m.group(1)) for l in tail for m in [re.search(r"pages cover (\d+) min", l)] if m]
        gaps = sum("GAP risk" in l for l in tail)
        if cov:
            out("PASS" if gaps <= len(cov) // 3 else "WARN", f"new-pool window covers {min(cov)}-{max(cov)} min; GAP-risk warnings: {gaps}/{len(cov)} recent runs")
    else:
        out("FAIL", f"{a.log} not found (wrong folder, or daemon never started)")

    # 3) cohort growth
    if os.path.exists(a.data):
        bad = [0]
        sum(1 for _ in store.iter_jsonl(a.data, bad))      # count damaged lines
        bad_lines = bad[0]
        rows = store.load(a.data, candles=False)
        reg =[r["registered_at"] for r in rows if r.get("registered_at")]
        if reg:
            age = _age_min(max(reg))
            out("PASS" if age < 8 else ("WARN" if age < 20 else "FAIL"),
                f"{len(rows)} pools registered; newest registered {age:.1f} min ago")
        else:
            out("FAIL", f"{a.data} has no registered pools")
        if bad_lines:
            out("WARN", f"{bad_lines} unreadable lines in {a.data}")
        # 4) fill progress
        waiting_old = [r for r in rows if not r.get("filled") and (time.time() - r["created"]) / 3600 >= 3.5]
        fetched = [r["fetched_at"] for r in rows if r.get("filled") and r.get("fetched_at")]
        last = _age_min(max(fetched)) if fetched else None
        if waiting_old and (last is None or last > 30):
            out("WARN", f"{len(waiting_old)} pools older than 3.5h still waiting for candles; last fill "
                        + ("never" if last is None else f"{last:.0f} min ago") + "  -> fill may be failing")
        else:
            out("PASS", f"fill OK: {len(fetched)} pools have candles; {len(waiting_old)} overdue")
        # 5) snapshots: reserves (free public RPC) for every pool; Helius holder data only for canonical pools
        recent = [r for r in rows if r.get("registered_at") and _age_min(r["registered_at"]) < 45]
        if recent:
            snapped = [r for r in recent if (r.get("helius_reg") or {}).get("pool_sol") is not None]
            out("PASS" if snapped else "FAIL", f"reserve snapshots (free RPC): {len(snapped)}/{len(recent)} recent pools")
            canon = [r for r in snapped if r["mint"].endswith("pump") and r["helius_reg"].get("pool_tokens")
                     and 0.5e10 <= r["helius_reg"]["pool_sol"] * r["helius_reg"]["pool_tokens"] <= 5e10]
            holders = [r for r in canon if r["helius_reg"].get("top_holders") is not None]
            errs = [r["helius_reg"]["holders_error"] for r in canon if r["helius_reg"].get("holders_error")]
            virt = [r["helius_reg"]["virt_sol"] for r in canon if r["helius_reg"].get("virt_sol") is not None]
            if virt:
                med = sorted(virt)[len(virt) // 2]
                ok = abs(med - PUMP_VIRTUAL_SOL) <= 0.02 * PUMP_VIRTUAL_SOL
                out("PASS" if ok else "WARN", f"virtual reserve read on-chain for {len(virt)}/{len(canon)} recent canonical pools, "
                    f"median {med:.3f} SOL" + ("" if ok else f"  -> the fallback {PUMP_VIRTUAL_SOL} in bot/amm.py is out of date"))
            elif canon:
                out("WARN", "no virtual reserve recorded for recent canonical pools (public RPC failing, or layout changed)")
            if canon and holders:
                out("PASS", f"Helius holder data on canonical pools: {len(holders)}/{len(canon)}")
            elif errs:
                out("FAIL", f"Helius holder errors: {errs[-1]}")
            elif canon:
                out("WARN", "canonical pools have NO holder data -> daemon started without HELIUS_API_KEY "
                            "(set the key in this window, then run memebot\\restart_collector.bat)")
    else:
        out("FAIL", f"{a.data} not found")

    if os.path.exists(a.err) and os.path.getsize(a.err) > 0:
        e = open(a.err, encoding="utf-8", errors="replace").read().strip().splitlines()
        out("WARN", f"{a.err} is not empty ({len(e)} lines); last: {e[-1][:110] if e else ''}")

    # 5b) the paper bot (only if it has ever run here): alive, and able to open positions?
    if os.path.exists(a.state):
        try:
            with open(a.state) as f:
                state = json.load(f)
            from .bot.config import BotConfig
            cfg = BotConfig.load()
            age = _age_min(os.path.getmtime(a.state))
            out("PASS" if age < 10 else "WARN", f"bot state saved {age:.1f} min ago" + ("" if age < 10 else "  -> bot is not running"))
            need = cfg.stake_sol + cfg.tx_fee_sol
            if state.get("paused"):
                out("WARN", "bot is PAUSED: no new positions")
            elif state.get("balance", 0) < need:
                out("WARN", f"bot paper balance {state.get('balance', 0):.4f} SOL < {need:.4f} needed per entry"
                            "  -> it opens NO new positions (measurement has stopped)")
            else:
                out("PASS", f"bot paper balance {state['balance']:.4f} SOL, {len(state.get('positions') or {})} open positions")
        except (ValueError, OSError) as e:
            out("WARN", f"{a.state} unreadable: {type(e).__name__}")

    # 6) live probe: real calls into a TEMP file (never touches cohort.jsonl)
    if a.live:
        tmp = os.path.join(tempfile.gettempdir(), "memebot_health.jsonl")
        if os.path.exists(tmp):
            os.remove(tmp)
        r = subprocess.run([sys.executable, "-m", "memebot.collect", "--out", tmp, "--source", "new", "--register-only",
                            "--min-age-h", "0", "--max-age-h", "3", "--max-pools", "3"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=300)
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        out("PASS" if r.returncode == 0 and "registered" in last else "FAIL", f"live register probe: {last[:120]}")
        if os.environ.get("HELIUS_API_KEY"):
            r2 = subprocess.run([sys.executable, "-m", "memebot.helius", "--selftest"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120)
            out("PASS" if "ALL OK" in r2.stdout else "FAIL", "live Helius selftest: " + ("ALL OK" if "ALL OK" in r2.stdout else r2.stdout.strip()[-120:]))
        else:
            out("WARN", "HELIUS_API_KEY not set in THIS window: Helius probe skipped")

    print(f"\nsummary: {res.count('PASS')} pass, {res.count('WARN')} warn, {res.count('FAIL')} fail")
    sys.exit(1 if "FAIL" in res else 0)


if __name__ == "__main__":
    main()
