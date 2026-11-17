"""Pelluca /watch: liquidity-drain alerts for tokens a user follows.

Rule (pure, unit-tested; thresholds measured with memebot.pelluca.drain_eval on the 10-day cohort):
  alert when the pool's real SOL falls by at least DROP within WINDOW_MIN minutes (from the highest value seen in
  that window), or falls under DEAD_SOL. One alert per episode: the rule re-arms once the pool recovers to the
  level it had before the alert.
State lives in a small JSON file (watches only, no history) written atomically.
"""
import json
import os
import time

DROP = 0.30
WINDOW_MIN = 10
DEAD_SOL = 5.0
MAX_PER_CHAT = 10


def drain_alert(hist, now, drop=DROP, window_min=WINDOW_MIN, dead=DEAD_SOL):
    """hist: [(t, sol)] oldest first, last item = current reading. Returns (fire, text) for the newest reading."""
    if not hist:
        return False, ""
    t, sol = hist[-1]
    if sol < dead:
        return True, f"pool down to {sol:.2f} SOL: liquidity is gone"
    recent = [s for (ts, s) in hist if now - ts <= window_min * 60]
    peak = max(recent) if recent else sol
    if peak > 0 and sol <= (1 - drop) * peak:
        return True, f"pool SOL fell {1 - sol / peak:.0%} in {window_min} min ({peak:.1f} → {sol:.1f} SOL)"
    return False, ""


class Watches:
    """{chat_id: {mint: {pool, sol_acc, name, added, armed, alert_level}}} persisted to `path`."""

    def __init__(self, path="pelluca_watch.json"):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except ValueError:
                self.data = {}
        self.hist = {}                       # sol_acc -> [(t, sol)] in memory only (last hour)

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)

    def add(self, chat, mint, pool, sol_acc, name):
        w = self.data.setdefault(str(chat), {})
        if mint not in w and len(w) >= MAX_PER_CHAT:
            return False
        w[mint] = {"pool": pool, "sol_acc": sol_acc, "name": name, "added": time.time(), "armed": True}
        self.save()
        return True

    def remove(self, chat, mint):
        ok = self.data.get(str(chat), {}).pop(mint, None) is not None
        if ok:
            self.save()
        return ok

    def of(self, chat):
        return self.data.get(str(chat), {})

    def accounts(self):
        return sorted({w["sol_acc"] for ws in self.data.values() for w in ws.values()})

    def step(self, balances, now):
        """Feed new pool SOL readings; returns [(chat, mint, watch, text)] alerts to send."""
        for acc, sol in balances.items():
            h = self.hist.setdefault(acc, [])
            h.append((now, sol))
            while h and now - h[0][0] > 3600:
                h.pop(0)
        out, changed = [], False
        for chat, ws in self.data.items():
            for mint, w in ws.items():
                h = self.hist.get(w["sol_acc"])
                if not h:
                    continue
                fire, text = drain_alert(h, now)
                if fire and w.get("armed", True):
                    peak = max(s for ts, s in h if now - ts <= WINDOW_MIN * 60)
                    w["armed"], w["alert_level"], changed = False, peak, True
                    out.append((chat, mint, w, text))
                elif not w.get("armed", True) and h[-1][1] >= w.get("alert_level", 0) and h[-1][1] >= DEAD_SOL:
                    w["armed"], changed = True, True
        if changed:
            self.save()
        return out
