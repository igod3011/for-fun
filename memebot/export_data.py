"""Pack everything the collector and the paper bot recorded into ONE zip file (stdlib only; nothing is deleted).

  python -m memebot.export_data                 -> export/memebot-data-<date>.zip in the project folder
  python -m memebot.export_data --out D:\\x.zip

Contents: cohort.jsonl (one registration row per pool), cohort.fills.jsonl (candles + outcome), cohort.snaps.jsonl
(holder snapshot at ~90 min), cohort.filled.txt, the paper ledger (bot_trades.jsonl, bot_series.jsonl,
bot_state.json), archive/ (older ledgers), smart_wallets.json, daemon.log, and the reports in memebot/research.
No secrets are stored in any of these files (keys live only in environment variables).
"""
import argparse
import os
import time
import zipfile

FILES = ["cohort.jsonl", "cohort.fills.jsonl", "cohort.snaps.jsonl", "cohort.filled.txt", "bot_trades.jsonl",
         "bot_series.jsonl", "bot_state.json", "smart_wallets.json", "daemon.log",
         "memebot/research/RANKING.md", "memebot/research/SCOREBOARD.md", "memebot/research/PHASE1_AUDIT.md",
         "memebot/RESULTS.md", "memebot/PROJECT.md"]
FOLDERS = ["archive"]


def export(out, root=".", log=print):
    """Write the zip; returns [(name, bytes)] of what went in. Files that do not exist are skipped."""
    names = [f for f in FILES if os.path.exists(os.path.join(root, f))]
    for folder in FOLDERS:
        for base, _, files in os.walk(os.path.join(root, folder)):
            names += [os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/") for f in files]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    packed = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in names:
            path = os.path.join(root, name)
            z.write(path, name)
            packed.append((name, os.path.getsize(path)))
            log(f"  {name:42} {os.path.getsize(path) / 1e6:8.1f} MB")
    log(f"wrote {out}: {len(packed)} files, {sum(s for _, s in packed) / 1e6:.1f} MB -> {os.path.getsize(out) / 1e6:.1f} MB")
    return packed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("export", f"memebot-data-{time.strftime('%Y-%m-%d')}.zip"))
    a = ap.parse_args()
    export(a.out)


if __name__ == "__main__":
    main()
