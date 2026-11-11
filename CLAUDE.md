# CLAUDE.md

This repo's active project is `memebot/`: a Solana memecoin research pipeline and a 24/7 PAPER-trading bot
controlled over Telegram. Read `memebot/PROJECT.md` first: architecture, data schema, results so far, evaluation
method and the go/no-go gates for real money. `App.js`/`package.json` at the root are an unrelated old app.

## Hard rules
- **Paper only.** Do not add real order execution, wallet handling or private-key code unless the user explicitly asks
  AND the gates in `memebot/PROJECT.md` section 7 are met. Never ask the user to paste keys/tokens into chat; secrets
  live only in environment variables (`HELIUS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- **Stdlib only** for `memebot/` runtime code (bot, collector, rpc, helius, report, healthcheck): it must run on the
  user's Windows machine and a Linux VPS with no `pip install`. `ml/train_rug_model.py` (lightgbm) is the exception.
- **Returns are what the pool would really pay** (constant product on real reserves via `bot/amm.py`), never the last
  trade price: GeckoTerminal prices are absurd once a pool is drained.
- **No look-ahead.** Only use information available at decision time. Past mistakes: filtering on collection-time
  liquidity (fake +250%), selection bias from "top pools" lists, first candle = pool-init price.
- **Evaluate walk-forward with confidence intervals** (`ml/entry_timing.py --grid`). A rule is kept only if it beats
  its absence on the SAME data, in both time halves. Report uncertainty honestly; do not oversell.
- **Helius credits are scarce** (free plan, 1M/month; DAS = 10 credits). Standard RPC goes to the public endpoint first
  (`rpc.py`); DAS only for canonical pump.fun pools at registration.
- Untrusted downloads (pickles, archives) are never loaded directly; see `ml/melt_data.py`.

## Workflow
- Tests: `python3 -m unittest discover -s memebot/tests -t .` (all must pass). Commit only when green; with pipes use
  `set -o pipefail`.
- Windows users update by downloading the branch zip and extracting over the folder (data files are not in git), then
  `memebot\restart_collector.bat` (collector) and/or `memebot\start_bot.bat` (bot) in a window that has the env vars.
- User-facing messages and docs are in Vietnamese; code, comments and commit messages in English.

## Key entry points
`collector_daemon.py` → `collect.py` → `cohort.jsonl` · `report.py` · `healthcheck.py` · `ml/entry_timing.py` ·
`ml/wallet_scores.py` · `bot/runner.py` (uses `strategy.py`, `paper.py`, `intel.py`, `telegram.py`, `config.py`).
