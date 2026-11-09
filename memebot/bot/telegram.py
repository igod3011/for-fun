"""Minimal Telegram Bot API client (stdlib only) + command handling.

Only messages from TELEGRAM_CHAT_ID are obeyed; everything else is ignored.
  python -m memebot.bot.telegram --whoami     # send any message to your bot first, this prints your chat id
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"

HELP = ("/status - balance, PnL, open positions\n"
        "/positions - details of open positions\n"
        "/pause - stop opening new positions (exits still managed)\n"
        "/resume - allow new positions again\n"
        "/sellall - close every open position now\n"
        "/stop - close everything and shut the bot down\n"
        "/help - this list")


class Telegram:
    def __init__(self, token, chat_id=None, transport=None):
        self.token, self.chat_id, self.offset = token, str(chat_id) if chat_id else None, 0
        self._transport = transport or self._http

    def _http(self, method, params, timeout=35):
        url = API.format(token=self.token, method=method)
        data = json.dumps(params).encode()
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:      # never echo the URL: it contains the token
            raise RuntimeError(f"telegram {method}: HTTP {e.code}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"telegram {method}: network error {type(e.reason).__name__}") from None

    def send(self, text):
        if self.chat_id:
            self._transport("sendMessage", {"chat_id": self.chat_id, "text": text[:4000]})

    def poll(self, timeout=25):
        r = self._transport("getUpdates", {"offset": self.offset, "timeout": timeout}, )
        msgs = []
        for u in r.get("result", []):
            self.offset = max(self.offset, u["update_id"] + 1)
            m = u.get("message") or {}
            if m.get("text"):
                msgs.append((str(m["chat"]["id"]), m["text"].strip()))
        return msgs

    def authorized(self, chat_id):
        return self.chat_id is not None and chat_id == self.chat_id


def whoami():
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        sys.exit("set TELEGRAM_BOT_TOKEN first")
    t = Telegram(tok)
    msgs = t.poll(timeout=1)
    if not msgs:
        print("no messages yet: open your bot in Telegram, send it any text (e.g. hi), then run this again")
    for chat_id, text in msgs:
        print(f"chat id: {chat_id}   (message: {text[:30]!r})")


if __name__ == "__main__":
    if "--whoami" in sys.argv:
        whoami()
    else:
        print(__doc__)
