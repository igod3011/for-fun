"""Per-key usage limits shared by the Telegram bot (key = chat id) and the website (key = client IP).

Plan limits approved by the owner 19/11/2026, sized to the Helius free plan (1M credits/month):
Free: 20 checks per hour and 100 per day, 3 watched tokens. Pro (pay.py, Week 4): 300 checks per day, 25 watched.
"""
import threading
import time

FREE_PER_HOUR = 20
FREE_PER_DAY = 100
PRO_PER_DAY = 300
FREE_WATCH = 3
PRO_WATCH = 25


class RateLimit:
    def __init__(self, per_hour=FREE_PER_HOUR, per_day=FREE_PER_DAY, clock=time.time):
        self.per_hour, self.per_day, self.clock = per_hour, per_day, clock
        self.calls = {}
        self.lock = threading.Lock()

    def take(self, key):
        """Records one use and returns None, or returns 'hour' / 'day' when that limit is reached."""
        now = self.clock()
        with self.lock:
            c = [t for t in self.calls.get(key, []) if now - t < 86400]
            if self.per_day and len(c) >= self.per_day:
                self.calls[key] = c
                return "day"
            if self.per_hour and sum(1 for t in c if now - t < 3600) >= self.per_hour:
                self.calls[key] = c
                return "hour"
            self.calls[key] = c + [now]
            if len(self.calls) > 50000:                      # forget idle keys so memory stays bounded
                self.calls = {k: v for k, v in self.calls.items() if v and now - v[-1] < 86400}
            return None
