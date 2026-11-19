"""Pelluca public Telegram bot (English, read-only): /check and /watch for anyone who messages it.

  set PELLUCA_BOT_TOKEN=...            (a NEW bot from @BotFather, not the paper bot's token)
  python -m memebot.pelluca.bot        # run forever
  python -m memebot.pelluca.bot --once # answer pending messages + one watch pass, then exit (smoke test)

Limits per chat: CHECKS_PER_HOUR checks, watch.MAX_PER_CHAT watched tokens. Watched pools are read every
POLL_S seconds with one getMultipleAccounts call per 100 pools (free public RPC).
"""
import os
import sys
import threading
import time
import traceback
from html import escape

from ..bot.telegram import Telegram
from . import chain, check
from .watch import DROP, MAX_PER_CHAT, WINDOW_MIN, Watches

CHECKS_PER_HOUR = 20
POLL_S = 30
WORKERS = 4               # chats served in parallel; a /check takes 10-40 s on the free public RPC

HELP = ("Pelluca checks Solana tokens before you buy.\n\n"
        "/check <CA> - risk report for a token (or just paste the address)\n"
        f"/watch <CA> - alert me if its liquidity drops {DROP:.0%} within {WINDOW_MIN} min\n"
        "/unwatch <CA> - stop watching\n"
        "/list - tokens you watch\n"
        "/terms - terms of service\n"
        "/help - this message\n\n"
        "Read-only: Pelluca never asks for your wallet, seed phrase or keys. Not financial advice. "
        "18+ only. By using Pelluca you accept the /terms.")

TERMS_URL = "https://pelluca.com/terms"
TERMS = ("<b>Pelluca terms, in short</b>\n"
         "• Information only, not financial advice. Memecoins are extremely risky; you can lose everything.\n"
         "• You must be 18+ and not in a sanctioned country.\n"
         "• Read-only: we never hold funds or ask for your seed phrase or keys. Anyone who does is a scammer.\n"
         "• Data (Solana chain, DexScreener) can be late or wrong; alerts are best effort.\n"
         "• Payments are in SOL and cannot be reversed; pay the exact invoice before it expires.\n"
         "• We store only your chat ID, the tokens you check or watch, and payment records.\n\n"
         f"Full terms: {TERMS_URL}")


class PellucaBot:
    def __init__(self, tg, watches, gather=check.cached_gather, balances=chain.token_balances, clock=time.time):
        self.tg, self.w, self.gather, self.balances, self.clock = tg, watches, gather, balances, clock
        self.calls = {}                      # chat -> [timestamps of checks]
        self.lock = threading.Lock()

    def say(self, chat, text, html=True):
        try:
            self.tg.send_to(chat, text, html)
        except Exception as e:
            if html:
                import re
                return self.say(chat, re.sub(r"<[^>]+>", "", text), html=False)
            print("telegram send failed:", e, flush=True)

    def is_lookup(self, text):
        """True when the message will trigger a slow chain lookup (/check, /watch or a bare address)."""
        parts = text.split()
        if not parts:
            return False
        if chain.is_address(parts[0]):
            return True
        cmd = parts[0].split("@")[0].lower()
        return cmd in ("/check", "/watch") and len(parts) > 1 and chain.is_address(parts[1])

    def serve(self, chat, text):
        """Answer one message; slow lookups get an immediate 'checking' note first."""
        try:
            if self.is_lookup(text):
                self.say(chat, "🔎 Checking on-chain data… this takes 10-40 seconds.", html=False)
            self.say(chat, self.handle(chat, text))
        except Exception as e:
            print("handle failed:", type(e).__name__, e, flush=True)
            self.say(chat, "Sorry, the check failed (network). Please try again in a minute.", html=False)

    def allowed(self, chat):
        with self.lock:
            return self._allowed(chat)

    def _allowed(self, chat):
        now = self.clock()
        c = [t for t in self.calls.get(chat, []) if now - t < 3600]
        if len(c) >= CHECKS_PER_HOUR:
            self.calls[chat] = c
            return False
        self.calls[chat] = c + [now]
        return True

    def handle(self, chat, text):
        """Returns the reply (HTML) for one message."""
        parts = text.split()
        cmd = parts[0].split("@")[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if parts and chain.is_address(parts[0]):           # a bare pasted address (case matters: no .lower())
            cmd, arg = "/check", parts[0]
        if cmd in ("/start", "/help"):
            return HELP
        if cmd == "/terms":
            return TERMS
        if cmd == "/list":
            ws = self.w.of(chat)
            if not ws:
                return "You are not watching any token. Use /watch <CA>."
            return "Watching:\n" + "\n".join(f"• {escape(str(v.get('name') or '?'))} <code>{m}</code>" for m, v in ws.items())
        if cmd in ("/check", "/watch", "/unwatch") and not chain.is_address(arg):
            return f"Send it like this: {cmd} <token contract address>"
        if cmd == "/unwatch":
            return "Stopped watching." if self.w.remove(chat, arg) else "You were not watching that token."
        if cmd in ("/check", "/watch"):
            if not self.allowed(chat):
                return f"Limit reached ({CHECKS_PER_HOUR} checks per hour). Try again later."
            f = self.gather(arg)
            report = check.render(f)
            if cmd == "/check":
                return report
            if not f.get("pool"):
                return report
            name = (f.get("dex") or {}).get("name")
            with self.lock:
                ok = self.w.add(chat, arg, f["pool"], f["sol_acc"], name)
            if not ok:
                return f"You already watch {MAX_PER_CHAT} tokens. /unwatch one first."
            return report + f"\n\n👁 Watching. I will alert you if the pool loses {DROP:.0%} of its SOL within {WINDOW_MIN} min."
        return "Unknown command.\n\n" + HELP

    def watch_pass(self):
        accs = self.w.accounts()
        if not accs:
            return 0
        bal = self.balances(accs)
        with self.lock:
            alerts = self.w.step(bal, self.clock())
        for chat, mint, w, text in alerts:
            self.say(chat, f"🚨 <b>{escape(str(w.get('name') or 'Token'))}</b>: {escape(text)}\nCA: <code>{mint}</code>\n"
                           "Check it now: /check " + mint)
        return len(alerts)

    def telegram_loop(self):
        slots = threading.BoundedSemaphore(WORKERS)

        def run(chat, text):
            try:
                self.serve(chat, text)
            finally:
                slots.release()
        while True:
            try:
                for chat, text in self.tg.poll():
                    slots.acquire()                     # at most WORKERS lookups at once; others wait their turn
                    threading.Thread(target=run, args=(chat, text), daemon=True).start()
            except Exception as e:
                print("telegram poll failed:", e, flush=True)
                time.sleep(5)


def main():
    tok = os.environ.get("PELLUCA_BOT_TOKEN")
    if not tok:
        sys.exit("set PELLUCA_BOT_TOKEN first (a new bot from @BotFather)")
    bot = PellucaBot(Telegram(tok), Watches(os.environ.get("PELLUCA_WATCH_FILE", "pelluca_watch.json")))
    if "--once" in sys.argv:
        for chat, text in bot.tg.poll(timeout=1):
            bot.say(chat, bot.handle(chat, text))
        print("watch alerts:", bot.watch_pass())
        return
    threading.Thread(target=bot.telegram_loop, daemon=True).start()
    print("Pelluca bot running", flush=True)
    while True:
        try:
            bot.watch_pass()
        except Exception:
            traceback.print_exc()
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
