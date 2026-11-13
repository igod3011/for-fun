# CLAUDE.md

This repo's active project is `memebot/`: a Solana memecoin research pipeline and a 24/7 PAPER-trading bot
controlled over Telegram. Read `memebot/PROJECT.md` first (architecture, data schema, how to evaluate, go/no-go
gates for real money); numbers and history are in `memebot/RESULTS.md`. The strategy research track (Research
Engine: every hypothesis tried and its verdict) is in `memebot/research/SCOREBOARD.md` and `PHASE1_AUDIT.md`.

## Hard rules
- **Paper only.** Do not add real order execution, wallet handling or private-key code unless the user explicitly asks
  AND the gates in `memebot/PROJECT.md` section 7 are met. Never ask the user to paste keys/tokens into chat; secrets
  live only in environment variables (`HELIUS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- **Stdlib only** for `memebot/` runtime code (bot, collector, store, rpc, helius, report, healthcheck, quote_check):
  it must run on the user's Windows machine and a Linux VPS with no `pip install`. `ml/train_rug_model.py` is the
  exception.
- **Returns are what the pool would really pay** (`bot/amm.py` on real reserves), never the last trade price.
  pump.fun-migrated pools price on `(real SOL + virtual SOL) x tokens`; the virtual reserve is PER POOL (read
  on-chain: `helius_reg.virt_sol`, `Position.virt_sol`), `PUMP_VIRTUAL_SOL` is only a fallback. Swap fee is 1.2%
  (measured with `quote_check`); re-measure before trusting any new number.
- **No look-ahead.** Only use information available at decision time. Past mistakes: filtering on collection-time
  liquidity (fake +250%), "top pools" lists, first candle = pool-init price, stop losses filled at the stop level
  inside a candle (fake +3%).
- **Evaluate walk-forward with confidence intervals** (`ml/entry_timing.py --grid --bot-filter`, `ml/rc_rules.py`).
  A rule is kept only if it beats its absence on the SAME data, in both time halves. Report uncertainty honestly.
- **Helius credits are scarce** (free plan, 1M/month; DAS = 10 credits per 1000 accounts). Everything that the free
  public RPC can answer goes there (`rpc.py`); DAS only for canonical pump.fun pools.
- **Data files are append-only** (`store.py`): never rewrite `cohort.jsonl` in place; the collector is running.
- Untrusted downloads (pickles, archives) are never loaded directly; see `ml/melt_data.py`.

## Workflow
- Tests: `python -m unittest discover -s memebot/tests -t .` (all must pass). Commit only when green.
- The collector runs each pass as a fresh subprocess: edits to `collect.py`, `store.py`, `rpc.py`, `helius.py`,
  `bot/intel.py` are LIVE within 2 minutes. The daemon itself and the bot only change when the user restarts them
  (`memebot\restart_collector.bat`, `memebot\start_bot.bat`) in a window that has the env vars.
- The folder is a git checkout of `igod3011/for-fun`, branch `claude/mql5-market-product-5p7wht`. The user's
  Command Prompt has no `git`; data files are gitignored.
- User-facing messages and docs are in Vietnamese; code, comments and commit messages in English. The user works in
  Windows Command Prompt: give one copyable command at a time, with how to check it worked.
- Weekly evaluation: the `weekly-eval` skill.

## Key entry points
`collector_daemon.py` → `collect.py` → `store.py` (`cohort.jsonl`, `cohort.fills.jsonl`, `cohort.snaps.jsonl`) · `report.py` ·
`healthcheck.py` · `quote_check.py` · `ml/entry_timing.py` · `ml/rc_rules.py` · `ml/select_model.py` ·
`ml/wallet_scores.py` · `bot/runner.py` (uses `strategy.py`, `paper.py`, `intel.py`, `telegram.py`, `config.py`).
