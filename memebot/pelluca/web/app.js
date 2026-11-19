// Pelluca home page: runs a check through /api/check and draws the report card. No trackers, no wallet code.
(function () {
  "use strict";
  var form = document.getElementById("checkform");
  var input = document.getElementById("ca");
  var card = document.getElementById("report-card");
  if (!form || !card) return;
  var ADDR = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function pct(x, digits) { return (x * 100).toFixed(digits || 0) + "%"; }
  function signed(x) { return (x > 0 ? "+" : x < 0 ? "−" : "") + pct(Math.abs(x)); }
  function short(a) { return a.slice(0, 4) + "…" + a.slice(-4); }
  function money(x) { return "$" + Math.round(x).toLocaleString("en-US"); }

  function message(text, busy) {
    card.textContent = "";
    card.classList.remove("fresh");
    card.classList.toggle("scan", !!busy);
    card.appendChild(el("div", "msg" + (busy ? " pulse mono" : ""), text));
    if (busy) {
      var l = el("div", "lines"); l.appendChild(el("i")); l.appendChild(el("i")); l.appendChild(el("i"));
      card.appendChild(l);
    }
  }

  function draw(r) {
    card.textContent = "";
    card.classList.remove("scan");
    card.classList.remove("fresh"); void card.offsetWidth; card.classList.add("fresh");
    var bar = el("div", "bar mono");
    bar.appendChild(el("span", null, "report"));
    bar.appendChild(el("span", null, "/"));
    var ca = el("a", null, short(r.mint));
    ca.href = "https://solscan.io/token/" + encodeURIComponent(r.mint);
    ca.rel = "noopener";
    ca.style.color = "var(--text)";
    bar.appendChild(ca);
    bar.appendChild(el("span", "when", new Date((r.checked_at || Date.now() / 1000) * 1000).toUTCString().slice(5, 22) + " UTC"));
    card.appendChild(bar);

    var title = el("div", "title");
    title.appendChild(el("b", null, r.name || "Token"));
    var VENUES = { pumpswap: "PumpSwap", meteora: "Meteora", raydium: "Raydium", orca: "Orca", pumpfun: "pump.fun curve" };
    if (r.venue) title.appendChild(el("span", "mono", VENUES[r.venue] || r.venue));
    var cls = { "HIGH RISK": "v-red", "ELEVATED RISK": "v-amber", "NO MAJOR FLAGS FOUND": "v-green" }[r.verdict] || "v-grey";
    title.appendChild(el("span", "verdict " + cls, r.verdict));
    card.appendChild(title);

    var stats = el("div", "stats mono");
    function stat(label, value, color) {
      var d = el("div"); d.appendChild(el("span", null, label));
      var s = el("strong", null, value); if (color) s.style.color = color;
      d.appendChild(s); stats.appendChild(d);
    }
    if (r.liq_usd) stat("liquidity", money(r.liq_usd));
    else if (r.pool_sol != null) stat("pool", r.pool_sol.toFixed(2) + " SOL");
    if (r.change_h24 != null) stat("24h", signed(r.change_h24), r.change_h24 <= -0.5 ? "var(--red)" : null);
    if (r.mcap) stat(r.mcap_source === "chain" ? "mcap (on-chain)" : "mcap", money(r.mcap));
    if (r.top10 != null) stat("top 10", pct(r.top10));
    if (stats.childNodes.length) card.appendChild(stats);

    var ul = el("ul", "flags");
    var names = { red: "RED", amber: "WATCH", info: "INFO" };
    (r.flags || []).forEach(function (f) {
      var li = el("li");
      li.appendChild(el("span", "lv lv-" + f.level, names[f.level] || "INFO"));
      li.appendChild(el("span", null, f.text));
      ul.appendChild(li);
    });
    if (!r.flags || !r.flags.length) {
      var ok = el("li"); ok.appendChild(el("span", "lv lv-ok", "OK"));
      ok.appendChild(el("span", null, "No red flags in the on-chain checks. That does not mean safe."));
      ul.appendChild(ok);
    }
    if (r.exit) {
      var ex = el("li"); ex.appendChild(el("span", "lv lv-info", "EXIT"));
      var t = "Buying " + r.exit.stake + " SOL and selling right away loses " + pct(r.exit.round_trip_loss, 1) + ".";
      if (r.exit.top10_drain != null) t += " If the top 10 sold now they would take " + pct(r.exit.top10_drain) + " of the pool's SOL.";
      ex.appendChild(el("span", null, t)); ul.appendChild(ex);
    }
    card.appendChild(ul);
    card.appendChild(el("div", "foot mono", "Base rate: " + pct(r.base_rate) + " of " + r.study +
      " lost over 90% of their SOL within 3 hours. Data: Solana RPC, DexScreener. Not financial advice."));
  }

  function run(ca) {
    if (!ADDR.test(ca)) { message("That is not a Solana token address."); return; }
    message("Reading the chain…", true);
    fetch("/api/check?ca=" + encodeURIComponent(ca), { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json().then(function (j) { return [res.status, j]; }); })
      .then(function (x) {
        if (x[0] !== 200) { message(x[1].error || "Something went wrong. Try again."); return; }
        draw(x[1]);
        if (history.replaceState) history.replaceState(null, "", "/?ca=" + encodeURIComponent(ca));
      })
      .catch(function () { message("Could not reach Pelluca. Check your connection and try again."); });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    run(input.value.trim());
  });
  var q = new URLSearchParams(location.search).get("ca");
  if (q) { input.value = q; run(q.trim()); }
})();
