"""Run the PAPER bot 24/7 (Windows now, Linux VPS later; stdlib only).

Needs, in the same window:  HELIUS_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
and the collector running (it writes cohort.jsonl, which is where new pools come from).
  python -m memebot.bot.runner              # run forever
  python -m memebot.bot.runner --once       # one discovery + one position check, then exit (smoke test)
"""
import argparse
import json
import os
import sys
import threading
import time
import traceback

from . import amm
from .config import BotConfig
from .data import find_pumpswap_pool, pool_reserves, recent_cohort_rows
from .paper import Paper
from .strategy import chase_check, entry_check, exit_decision
from .review import load as load_log
from .review import summary
from .telegram import HELP, Telegram
from .wallets import WalletWatcher, load_watchlist


class Bot:
    def __init__(self, cfg, tg, reserves=pool_reserves, rows=recent_cohort_rows, watcher=None, find_pool=None):
        self.cfg, self.tg, self.reserves, self.rows = cfg, tg, reserves, rows
        self.watcher, self.find_pool = watcher, find_pool
        self.follow_hits = {}            # mint -> {wallet: ts}
        self.followed = set()
        self.p = Paper(cfg)
        self.lock = threading.Lock()
        self.running = True
        self.last_err = 0.0
        self.summary_day = None

    def say(self, text):
        try:
            self.tg.send(text)
        except Exception as e:
            print("telegram send failed:", e, flush=True)

    # --- trading ------------------------------------------------------------------------------
    def discover(self):
        for r in self.rows(self.cfg.cohort_path):
            mint = r.get("mint")
            if not mint or mint in self.p.seen:
                continue
            self.p.seen.add(mint)
            ok, why = entry_check(r, self.cfg)
            if not ok:
                self.p.log(action="skip", mint=mint, name=r.get("name"), reason="; ".join(why))
                continue
            with self.lock:
                can, why_not = self.p.can_open(self.cfg.stake_sol)
                if not can:
                    self.p.log(action="skip", mint=mint, name=r.get("name"), reason=f"risk gate: {why_not}")
                    continue
                sol, tok = self.reserves(r["pool"], mint)          # price NOW, not at registration
                if sol < self.cfg.min_pool_sol:
                    self.p.log(action="skip", mint=mint, name=r.get("name"), reason=f"pool now {sol:.1f} SOL")
                    continue
                pos = self.p.buy(r, sol, tok, self.cfg.stake_sol, "entry filter passed")
            self.say(f"🟢 PAPER BUY {pos.name}\n{self.cfg.stake_sol} SOL, pool {sol:.0f} SOL\nmint {mint}")
        self.p.save()

    def manage(self):
        now = time.time()
        for mint in list(self.p.positions):
            pos = self.p.positions.get(mint)
            if not pos:
                continue
            sol, tok = self.reserves(pos.pool, mint)
            self.record_series(mint, sol, tok, now)
            with self.lock:
                frac, reason = exit_decision(pos, sol, tok, now, self.cfg)
                if frac > 0:
                    out, pnl = self.p.sell(mint, frac, sol, tok, reason)
                    tail = f"closed, PnL {pnl:+.4f} SOL" if pnl is not None else f"sold {frac:.0%}"
                    self.say(f"🔴 PAPER SELL {pos.name}: {reason}\n+{out:.4f} SOL, {tail}")
                elif chase_check(pos, sol, tok, now, self.cfg):
                    can, _ = self.p.can_open(0)
                    if can and self.p.balance >= self.cfg.chase_stake_sol:
                        self.p.buy({"mint": mint}, sol, tok, self.cfg.chase_stake_sol, "chase", add_to=pos)
                        self.say(f"🟡 PAPER ADD {pos.name}: +{self.cfg.chase_stake_sol} SOL (chase)")
                self.p.save()

    def follow_step(self):
        """Poll watched wallets; enter when enough of them bought the same pump.fun mint recently."""
        now = time.time()
        for wallet, mint in self.watcher.poll():
            if not mint.endswith("pump"):
                continue
            self.follow_hits.setdefault(mint, {})[wallet] = now
        for mint, hits in list(self.follow_hits.items()):
            recent = {w: t for w, t in hits.items() if now - t <= self.cfg.follow_window_min * 60}
            self.follow_hits[mint] = recent
            if not recent:
                del self.follow_hits[mint]
                continue
            if len(recent) < self.cfg.follow_min_wallets or mint in self.followed or mint in self.p.positions:
                continue
            self.followed.add(mint)
            self.enter_follow(mint, sorted(recent))

    def enter_follow(self, mint, wallets):
        who = ", ".join(w[:6] for w in wallets)
        pool = self.find_pool(mint) if self.find_pool else None
        if not pool:
            self.p.log(action="skip", mint=mint, reason=f"follow {who}: no PumpSwap pool found")
            return
        sol, tok = self.reserves(pool, mint)
        if sol < self.cfg.min_pool_sol or not (self.cfg.k_min <= sol * tok <= self.cfg.k_max):
            self.p.log(action="skip", mint=mint, reason=f"follow {who}: pool {sol:.1f} SOL / non-canonical")
            return
        with self.lock:
            can, why_not = self.p.can_open(self.cfg.stake_sol)
            if not can:
                self.p.log(action="skip", mint=mint, reason=f"follow {who}: risk gate: {why_not}")
                return
            pos = self.p.buy({"mint": mint, "pool": pool, "name": mint[:6]}, sol, tok, self.cfg.stake_sol,
                             f"follow {len(wallets)} wallet(s): {who}")
        self.say(f"🐋 PAPER FOLLOW BUY {pos.name}\n{len(wallets)} watched wallet(s) bought: {who}\n"
                 f"{self.cfg.stake_sol} SOL, pool {sol:.0f} SOL\nmint {mint}")

    def record_series(self, mint, sol, tok, now):
        """Reserve time series of held pools: lets us replay other exit rules on real data later."""
        with open(self.cfg.series_path, "a") as f:
            f.write(json.dumps({"ts": int(now), "mint": mint, "pool_sol": sol, "pool_tokens": tok}) + "\n")

    def daily_summary(self):
        today = time.strftime("%Y-%m-%d")
        if self.summary_day is None:
            self.summary_day = today
        elif today != self.summary_day:
            self.summary_day = today
            self.say(summary(load_log(self.cfg.log_path, time.time() - 86400), "last 24h") + "\n\n" + self.status())

    def sellall(self, reason):
        msgs = []
        for mint in list(self.p.positions):
            pos = self.p.positions[mint]
            try:
                sol, tok = self.reserves(pos.pool, mint)
            except Exception:
                sol, tok = 0.0, 0.0
            with self.lock:
                out, pnl = self.p.sell(mint, 1.0, sol, tok, reason)
            msgs.append(f"{pos.name}: +{out:.4f} SOL (PnL {pnl:+.4f})")
        return msgs

    # --- telegram -----------------------------------------------------------------------------
    def status(self):
        p = self.p
        return (f"{'⏸ PAUSED' if p.paused else '▶️ RUNNING'} (PAPER)\nbalance {p.balance:.4f} SOL\n"
                f"today PnL {p.day_pnl:+.4f} SOL, total {p.total_pnl:+.4f} SOL\nopen positions: {len(p.positions)}")

    def positions_text(self):
        if not self.p.positions:
            return "no open positions"
        out = []
        for m, pos in self.p.positions.items():
            age = (time.time() - pos.opened_at) / 60
            out.append(f"{pos.name}: cost {pos.cost_sol:.3f} SOL, peak x{pos.peak_mult:.2f}, {age:.0f} min\n{m}")
        return "\n\n".join(out)

    def command(self, text):
        cmd = text.split()[0].split("@")[0].lower()
        if cmd in ("/start", "/help"):
            return HELP
        if cmd == "/status":
            return self.status()
        if cmd == "/positions":
            return self.positions_text()
        if cmd == "/review":
            hours = 24
            parts = text.split()
            if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit():
                hours = float(parts[1])
            return summary(load_log(self.cfg.log_path, time.time() - hours * 3600), f"last {hours:g}h")
        if cmd == "/pause":
            self.p.paused = True
            self.p.save()
            return "⏸ paused: no new positions; open ones are still managed"
        if cmd == "/resume":
            self.p.paused = False
            self.p.save()
            return "▶️ resumed"
        if cmd == "/sellall":
            return "\n".join(self.sellall("manual /sellall")) or "nothing to sell"
        if cmd == "/stop":
            r = self.sellall("manual /stop")
            self.running = False
            return "🛑 stopping.\n" + ("\n".join(r) if r else "no open positions")
        return "unknown command\n" + HELP

    def telegram_loop(self):
        while self.running:
            try:
                for chat_id, text in self.tg.poll():
                    if not self.tg.authorized(chat_id):
                        print(f"ignored message from unauthorized chat {chat_id}", flush=True)
                        continue
                    self.say(self.command(text))
            except Exception as e:
                print("telegram poll error:", e, flush=True)
                time.sleep(5)

    def error(self, where, e):
        print(time.strftime("%F %T"), where, "error:", type(e).__name__, str(e)[:200], flush=True)
        traceback.print_exc()
        if time.time() - self.last_err > 600:          # at most one Telegram alert per 10 minutes
            self.last_err = time.time()
            self.say(f"⚠️ {where} error: {type(e).__name__}: {str(e)[:150]}")

    def loop(self, once=False):
        nxt_disc = nxt_follow = 0.0
        while self.running:
            if self.watcher and time.time() >= nxt_follow:
                try:
                    self.follow_step()
                except Exception as e:
                    self.error("follow", e)
                nxt_follow = time.time() + self.cfg.follow_poll_s
            if time.time() >= nxt_disc:
                try:
                    self.discover()
                except Exception as e:
                    self.error("discover", e)
                nxt_disc = time.time() + self.cfg.discover_every_s
            try:
                self.manage()
            except Exception as e:
                self.error("manage", e)
            try:
                self.daily_summary()
            except Exception as e:
                self.error("daily summary", e)
            if once:
                return
            time.sleep(self.cfg.poll_positions_s)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--config", default="bot_config.json")
    a = ap.parse_args()
    missing = [k for k in ("HELIUS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(k)]
    if missing:
        sys.exit("missing environment variables: " + ", ".join(missing))
    cfg = BotConfig.load(a.config)
    if cfg.mode != "paper":
        sys.exit("only paper mode exists")
    tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
    watcher = None
    if cfg.follow_enabled:
        from ..helius import rpc
        wallets = load_watchlist(cfg.wallets_path)[: cfg.follow_max_wallets]
        if not wallets:
            sys.exit(f"follow_enabled but no wallets in {cfg.wallets_path} (run memebot.ml.wallet_scores first)")
        watcher = WalletWatcher(wallets, lambda m, p: rpc(m, p, pace=0.3))
    bot = Bot(cfg, tg, watcher=watcher, find_pool=lambda mint: find_pumpswap_pool(mint, cfg.cohort_path))
    if a.once:
        bot.loop(once=True)
        print(bot.status())
        return
    mode = f" + following {len(watcher.wallets)} wallets" if watcher else ""
    bot.say(f"🤖 bot started (PAPER mode{mode})\n" + bot.status() + "\n\n" + HELP)
    threading.Thread(target=bot.telegram_loop, daemon=True).start()
    try:
        bot.loop()
    finally:
        bot.say("🛑 bot stopped")


if __name__ == "__main__":
    main()
