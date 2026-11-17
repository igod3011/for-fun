"""Data sources for the Research Engine (stdlib only). Everything fetched is public and needs no key; it is cached in
research_data/ (gitignored) so that a hypothesis can be re-scored without downloading again.

  cohort      the collector's own pools (cohort.jsonl + fills), via store / entry_timing
  futures     Binance USDT perpetuals: daily candles of every listed contract, funding history, hourly candles
              NOTE: the contract list is today's list, so contracts already delisted are missing (survivorship).
"""
import json
import os
import time
import urllib.request

FAPI = "https://fapi.binance.com"


class Missing(Exception):
    """The data a hypothesis needs is not on disk and fetching is not allowed (--offline) or failed."""


def http_json(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research/0.1"}), timeout=25) as r:
                return json.load(r)
        except Exception:
            time.sleep(3 * (i + 1))
    return None


class Data:
    def __init__(self, cohort_path="cohort.jsonl", cache="research_data", offline=False, get=http_json, pace=0.15):
        self.cohort_path, self.cache, self.offline, self.get, self.pace = cohort_path, cache, offline, get, pace
        self._mem = {}

    # cache ---------------------------------------------------------------------------------------------
    def _load(self, name):
        if name in self._mem:
            return self._mem[name]
        path = os.path.join(self.cache, name + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self._mem[name] = json.load(f)
            return self._mem[name]
        return None

    def _save(self, name, value):
        os.makedirs(self.cache, exist_ok=True)
        tmp = os.path.join(self.cache, name + ".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(tmp, os.path.join(self.cache, name + ".json"))
        self._mem[name] = value

    def _fetch(self, path):
        if self.offline:
            raise Missing("not on disk and --offline was given")
        time.sleep(self.pace)
        out = self.get(FAPI + path)
        if out is None:
            raise Missing("download failed: " + path.split("?")[0])
        return out

    # the collector's pools --------------------------------------------------------------------------------
    def cohort_pools(self):
        """[(row, setup)] for canonical pump.fun pools with candles and both reserve snapshots, oldest first."""
        if "cohort" not in self._mem:
            from .. import store
            from ..ml import entry_timing as et
            if not os.path.exists(self.cohort_path):
                raise Missing(self.cohort_path + " not found")
            rows = store.load(self.cohort_path, filled_only=True)
            self._mem["cohort"] = sorted(((p, S) for p in rows for S in [et.setup(p)] if S), key=lambda x: x[0]["created"])
        return self._mem["cohort"]

    def sol_usd(self):
        """Median SOL price implied by the registration snapshots (pool USD value / 2 / pool SOL)."""
        px = sorted(p["reserve_usd"] / 2 / p["helius_reg"]["pool_sol"] for p, _ in self.cohort_pools()
                    if p.get("reserve_usd") and p["helius_reg"].get("pool_sol", 0) > 1)
        return px[len(px) // 2] if px else 150.0

    # Binance futures ----------------------------------------------------------------------------------------
    def daily(self):
        """{symbol: {"onboard": ts, "d": [[ts, open, high, low, close, quote_volume]]}} for every USDT perpetual."""
        d = self._load("daily")
        if d is None:
            info = self._fetch("/fapi/v1/exchangeInfo")
            d = {}
            for s in info["symbols"]:
                if s["quoteAsset"] != "USDT" or s["contractType"] != "PERPETUAL":
                    continue
                k = self._fetch(f"/fapi/v1/klines?symbol={s['symbol']}&interval=1d&limit=1500")
                if k:
                    d[s["symbol"]] = {"onboard": s["onboardDate"] // 1000,
                                      "d": [[x[0] // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])] for x in k]}
            self._save("daily", d)
        return d

    def funding(self, symbols, since=0):
        """{symbol: [[ts, rate]]}; missing symbols are downloaded (all pages from `since`) and added to the cache."""
        f = self._load("funding") or {}
        todo = [s for s in symbols if s not in f]
        for s in todo:
            rows, start = [], since * 1000
            while True:
                r = self._fetch(f"/fapi/v1/fundingRate?symbol={s}&startTime={start}&limit=1000")
                rows += [[x["fundingTime"] // 1000, float(x["fundingRate"])] for x in r]
                if len(r) < 1000:
                    break
                start = r[-1]["fundingTime"] + 1
            f[s] = rows
        if todo:
            self._save("funding", f)
        return {s: f[s] for s in symbols}

    def hourly(self, symbol, pages=9):
        """[[ts, open, high, low, close, volume]] hourly candles, oldest first (about 1.5 years)."""
        name = symbol + "_1h"
        c = self._load(name)
        if c is None:
            out, end = [], None
            for _ in range(pages):
                k = self._fetch(f"/fapi/v1/klines?symbol={symbol}&interval=1h&limit=1500" + (f"&endTime={end}" if end else ""))
                if not k:
                    break
                out, end = k + out, k[0][0] - 1
                if len(k) < 1500:
                    break
            c = [[x[0] // 1000] + [float(v) for v in x[1:6]] for x in out]
            self._save(name, c)
        return c
