"""Add paper SOL to the bot's balance (the P&L figures do not change; the deposit is written to the decision log).

Run it only while the bot is STOPPED (a running bot rewrites bot_state.json and would undo it):
  memebot/topup_paper.bat 5                     stops the bot, adds 5 SOL, starts the bot again
  python -m memebot.bot.topup 5 --bot-stopped
While the bot runs, send it  /topup 5  in Telegram instead.
"""
import argparse
import os
import sys
import time

from .config import BotConfig
from .paper import Paper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sol", type=float)
    ap.add_argument("--config", default="bot_config.json")
    ap.add_argument("--bot-stopped", action="store_true", help="confirm the bot is not running")
    a = ap.parse_args()
    cfg = BotConfig.load(a.config)
    if not a.bot_stopped and os.path.exists(cfg.state_path) and time.time() - os.path.getmtime(cfg.state_path) < 180:
        sys.exit(f"{cfg.state_path} was written in the last 3 minutes: the bot is probably running. "
                 "Use memebot/topup_paper.bat, or send /topup in Telegram, or pass --bot-stopped.")
    p = Paper(cfg)
    try:
        bal = p.deposit(a.sol)
    except ValueError as e:
        sys.exit(str(e))
    print(f"added {a.sol:g} paper SOL: balance {bal:.4f} SOL, {len(p.positions)} open positions, "
          f"P&L unchanged ({p.total_pnl:+.4f} SOL)")


if __name__ == "__main__":
    main()
