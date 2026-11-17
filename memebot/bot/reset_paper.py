"""Open a fresh paper ledger. The old decision log, reserve series and state are MOVED to archive/<stamp>/.

Run it only while the bot is STOPPED (a running bot rewrites bot_state.json every minute and would undo it):
  memebot\\reset_paper.bat                       stops the bot, then runs this
  python -m memebot.bot.reset_paper --bot-stopped
Then start the bot again with memebot\\start_bot.bat.
"""
import argparse
import json
import os
import sys
import time

from .config import BotConfig


def reset(cfg, stamp=None, out=print):
    """Archive cfg.log_path / series_path / state_path and write an empty state. Returns the archive folder."""
    stamp = stamp or time.strftime("%Y-%m-%d_%H%M%S")
    folder = os.path.join(os.path.dirname(os.path.abspath(cfg.state_path)), "archive", stamp)
    os.makedirs(folder, exist_ok=True)
    moved = []
    for path in (cfg.log_path, cfg.series_path, cfg.state_path):
        if os.path.exists(path):
            os.replace(path, os.path.join(folder, os.path.basename(path)))
            moved.append(os.path.basename(path))
    with open(cfg.state_path, "w") as f:
        json.dump({"balance": cfg.paper_balance_sol, "day": time.strftime("%Y-%m-%d"), "day_pnl": 0.0,
                   "total_pnl": 0.0, "paused": False, "seen": [], "positions": {}}, f)
    out(f"archived {', '.join(moved) or 'nothing'} -> {folder}")
    out(f"new paper ledger: balance {cfg.paper_balance_sol} SOL, no positions")
    return folder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="bot_config.json")
    ap.add_argument("--bot-stopped", action="store_true", help="confirm the bot is not running")
    a = ap.parse_args()
    cfg = BotConfig.load(a.config)
    if not a.bot_stopped and os.path.exists(cfg.state_path) and time.time() - os.path.getmtime(cfg.state_path) < 180:
        sys.exit(f"{cfg.state_path} was written in the last 3 minutes: the bot is probably running.\n"
                 "Use memebot\\reset_paper.bat (it stops the bot first), or pass --bot-stopped.")
    if os.path.exists(cfg.state_path):
        with open(cfg.state_path) as f:
            if json.load(f).get("positions"):
                sys.exit("open positions exist: close them first (/sellall in Telegram), then reset")
    reset(cfg)


if __name__ == "__main__":
    main()
