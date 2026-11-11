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
from .strategy import entry_check, exit_decision, pos_virt
from .review import load as load_log
from .review import summary
from .intel import fetch as fetch_intel
from .intel import fmt_price, fmt_usd, intel_check
from .telegram import HELP, Telegram, token_block
from .wallets import WalletWatcher, load_watchlist


class Bot:
    def __init__(self, cfg, tg, reserves=pool_reserves, rows=recent_cohort_rows, watcher=None, find_pool=None,
                 intel=None, holders=None, virt=None):
        self.cfg, self.tg, self.reserves, self.rows = cfg, tg, reserves, rows
        self.intel = intel                 # callable(mint, pool) -> (rugcheck_info, dex_info); None = skip
        self.holders = holders             # callable(cohort_row) -> holder snapshot (Helius DAS); None = skip
        self.virt = virt                   # callable(pool) -> the pool's virtual reserve in SOL (free RPC); None = cfg value
        self.watcher, self.find_pool = watcher, find_pool
        self.follow_hits = {}            # mint -> {wallet: ts}
        self.followed = set()
        self.p = Paper(cfg)
        self.lock = threading.Lock()
        self.running = True
        self.last_err = 0.0
        self.summary_day = None
        self.warned_balance = False

    def say(self, text, html=False):
        try:
            self.tg.send(text, html=html)
        except Exception as e:
            if html:                                   # malformed HTML must never lose an alert: retry as plain text
                import re
                return self.say(re.sub(r"<[^>]+>", "", text))
            print("telegram send failed:", e, flush=True)

    # --- trading ------------------------------------------------------------------------------
    def discover(self):
        """Static checks as soon as a pool is registered; the buy decision waits until the pool is
        entry_delay_min old (then the falling-knife guard is applied to the reserves at that moment)."""
        horizon = (self.cfg.entry_delay_min + self.cfg.entry_window_min + 20) * 60
        now = time.time()
        for r in self.rows(self.cfg.cohort_path, max_age_s=max(horizon, 1800)):
            mint = r.get("mint")
            if not mint or mint in self.p.seen:
                continue
            ok, why = entry_check(r, self.cfg)
            if not ok:
                self.p.seen.add(mint)
                self.p.log(action="skip", mint=mint, name=r.get("name"), reason="; ".join(why))
                continue
            age_min = (now - r.get("created", now)) / 60
            if age_min < self.cfg.entry_delay_min:
                continue                                       # not yet: check again on a later pass
            self.p.seen.add(mint)
            if age_min > self.cfg.entry_delay_min + self.cfg.entry_window_min:
                self.p.log(action="skip", mint=mint, name=r.get("name"),
                           reason=f"missed entry window ({age_min:.0f} min old)")
                continue
            try:
                self.consider(r, mint)
            except Exception as e:
                # a failed RPC/API call must not silently drop the candidate for good (it used to: the mint was
                # already in `seen` and nothing was logged). Retry on the next pass while it is inside its window.
                self.p.seen.discard(mint)
                self.error(f"discover {mint[:8]}", e)
        self.p.save()

    def pool_virt(self, pool, last=None):
        """The pool's own virtual reserve, read on-chain; on any failure the last known value (None = cfg fallback)."""
        if not self.virt:
            return last
        try:
            v = self.virt(pool)
        except Exception:
            return last
        return last if v is None else v

    def consider(self, r, mint):
        """Risk gate + live reserves + intel for one candidate that is inside its entry window; buys if all pass."""
        with self.lock:
            can, why_not = self.p.can_open(self.cfg.stake_sol)
            if not can:
                self.p.log(action="skip", mint=mint, name=r.get("name"), reason=f"risk gate: {why_not}")
                if why_not == "insufficient balance" and not self.warned_balance:
                    self.warned_balance = True             # the bot once sat idle for a day without saying so
                    self.say(f"⚠️ Hết vốn paper: số dư {self.p.balance:.4f} SOL < lệnh {self.cfg.stake_sol} SOL. "
                             f"Bot KHÔNG mở lệnh mới nữa cho đến khi nạp lại vốn (bot_state.json).")
                return
            sol, tok = self.reserves(r["pool"], mint)          # price NOW, not at registration
            if sol < self.cfg.min_pool_sol:
                self.p.log(action="skip", mint=mint, name=r.get("name"), reason=f"pool now {sol:.1f} SOL")
                return
            reg_sol = (r.get("helius_reg") or {}).get("pool_sol") or 0
            if reg_sol and sol < (1 - self.cfg.max_drop_since_reg) * reg_sol:
                self.p.log(action="skip", mint=mint, name=r.get("name"),
                           reason=f"falling knife: pool SOL {reg_sol:.0f} -> {sol:.0f} since registration")
                return
            snap = self.entry_snapshot(r, sol, tok)
            ok, info, price, mcap = self.check_intel(mint, r["pool"], r.get("name"), **snap)
            if not ok:
                return
            pos = self.p.buy(r, sol, tok, self.cfg.stake_sol, "entry filter passed", price_usd=price, mcap=mcap,
                             virt=self.pool_virt(r["pool"]), **snap)
        grew = f"Holder {snap['holders_reg']} → {snap['holders_entry']}\n" if snap.get("holders_entry") is not None else ""
        self.say(f"🟢 PAPER BUY\n{token_block(pos.name, mint)}\n{info}{grew}{self.cfg.stake_sol} SOL, pool {sol:.0f} SOL",
                 html=True)

    def entry_snapshot(self, r, sol, tok):
        """Second holder snapshot, taken right before the buy decision (the first one is ~5 min after creation; we
        buy at ~90 min). Only for candidates that passed every free check: a few dozen a day, 10-20 Helius credits
        each. RECORDED with the decision, not yet used as a rule: there is no data to validate a threshold on."""
        h0 = r.get("helius_reg") or {}
        snap = {"holders_reg": h0.get("holders"), "top10_reg": h0.get("top10_pct"), "pool_sol_reg": h0.get("pool_sol"),
                "pool_tokens_entry": tok}
        if self.holders:
            try:
                h = self.holders(r)
                snap.update(holders_entry=h.get("holders"), top10_entry=h.get("top10_pct"),
                            top1_entry=h.get("top1_pct"), accounts_entry=h.get("accounts_fetched"))
            except BaseException as e:                     # helius exits on a bad key; never block a decision on it
                if isinstance(e, KeyboardInterrupt):
                    raise
                snap["holders_entry_error"] = str(e)[:80]
        return snap

    def check_intel(self, mint, pool, name, **extra):
        """RugCheck + DexScreener rules right before buying. Returns (ok, message_lines, price_usd, mcap).
        extra: fields recorded with a skip (so rejected candidates can be studied like bought ones)."""
        if not (self.intel and self.cfg.use_intel):
            return True, "", 0.0, 0.0
        rc, dx = self.intel(mint, pool)
        ok, why = intel_check(rc, dx, self.cfg)
        if not ok:
            self.p.log(action="skip", mint=mint, name=name, reason="; ".join(why), **extra)
            return False, "", 0.0, 0.0
        info = (f"Giá {fmt_price(dx['price_usd'])} | MC {fmt_usd(dx['mcap'])} | 1h {dx['change_h1']:+.0%}\n"
                f"Dev {(rc['dev_pct'] or 0):.1%}\n")
        return True, info, dx["price_usd"], float(dx["mcap"] or 0)

    def price_line(self, pos, sol, tok):
        """Entry vs current price/market cap, from the pool's real reserves (no extra API call)."""
        if not (pos.entry_price_usd and pos.entry_pool_tok and tok):
            return ""
        v = pos_virt(pos, self.cfg)
        ratio = amm.price(sol, tok, v) / amm.price(pos.entry_pool_sol, pos.entry_pool_tok, v)
        return (f"Giá {fmt_price(pos.entry_price_usd)} → {fmt_price(pos.entry_price_usd * ratio)}"
                f" | MC {fmt_usd(pos.entry_mcap)} → {fmt_usd(pos.entry_mcap * ratio)}\n")

    def manage(self):
        now = time.time()
        for mint in list(self.p.positions):
            pos = self.p.positions.get(mint)
            if not pos:
                continue
            try:
                sol, tok = self.reserves(pos.pool, mint)
            except Exception as e:                         # one unreadable pool must not stop the exits of the others
                self.error(f"manage {mint[:8]}", e)
                continue
            pos.virt_sol = self.pool_virt(pos.pool, pos.virt_sol)
            self.record_series(mint, sol, tok, now, pos.virt_sol)
            with self.lock:
                frac, reason = exit_decision(pos, sol, tok, now, self.cfg)
                if frac > 0:
                    out, pnl = self.p.sell(mint, frac, sol, tok, reason)
                    tail = f"closed, PnL {pnl:+.4f} SOL" if pnl is not None else f"sold {frac:.0%}"
                    from html import escape
                    self.say(f"🔴 PAPER SELL: {escape(reason)}\n{token_block(pos.name, mint)}\n"
                             f"{self.price_line(pos, sol, tok)}+{out:.4f} SOL, {tail}", html=True)
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
            ok, info, price, mcap = self.check_intel(mint, pool, mint[:6])
            if not ok:
                return
            pos = self.p.buy({"mint": mint, "pool": pool, "name": mint[:6]}, sol, tok, self.cfg.stake_sol,
                             f"follow {len(wallets)} wallet(s): {who}", price_usd=price, mcap=mcap,
                             virt=self.pool_virt(pool))
        self.say(f"🐋 PAPER FOLLOW BUY\n{token_block(pos.name, mint)}\n{info}{len(wallets)} watched wallet(s) bought: {who}\n"
                 f"{self.cfg.stake_sol} SOL, pool {sol:.0f} SOL", html=True)

    def record_series(self, mint, sol, tok, now, virt=None):
        """Reserve time series of held pools: lets us replay other exit rules on real data later."""
        with open(self.cfg.series_path, "a") as f:
            f.write(json.dumps({"ts": int(now), "mint": mint, "pool_sol": sol, "pool_tokens": tok, "virt_sol": virt}) + "\n")

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
            msgs.append(f"{pos.name}: +{out:.4f} SOL (PnL {pnl:+.4f})\nCA: {mint}")
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
            mc = f", MC vào {fmt_usd(pos.entry_mcap)}" if pos.entry_mcap else ""
            out.append(f"{pos.name}: cost {pos.cost_sol:.3f} SOL{mc}, peak x{pos.peak_mult:.2f}, {age:.0f} min\nCA: {m}")
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
        from ..rpc import call as rpc_call
        wallets = load_watchlist(cfg.wallets_path)[: cfg.follow_max_wallets]
        if not wallets:
            sys.exit(f"follow_enabled but no wallets in {cfg.wallets_path} (run memebot.ml.wallet_scores first)")
        watcher = WalletWatcher(wallets, rpc_call)        # standard RPC: public first, Helius fallback
    from ..helius import holder_snapshot
    from ..rpc import pool_virtual_sol
    bot = Bot(cfg, tg, watcher=watcher, find_pool=lambda mint: find_pumpswap_pool(mint, cfg.cohort_path),
              intel=fetch_intel, holders=lambda row: holder_snapshot(row, max_pages=2), virt=pool_virtual_sol)
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
