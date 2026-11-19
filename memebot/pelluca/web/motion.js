// Pelluca: scroll reveals, count-up numbers and the typing demo. Pure progressive enhancement: without JS (or
// with reduced motion) everything is simply visible.
(function () {
  "use strict";
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (still || !("IntersectionObserver" in window)) return;
  document.documentElement.classList.add("js");

  var targets = document.querySelectorAll(".block .head, .block>div:first-child, .rows .row, .panel, .studio-teaser, " +
    ".chat, details, .numbers .n, .legal h2, .studio .out>*");
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      io.unobserve(e.target);
      var c = e.target.querySelector("[data-count]");
      if (c) count(c);
    });
  }, { rootMargin: "0px 0px -8% 0px" });
  Array.prototype.forEach.call(targets, function (el, i) {
    el.classList.add("reveal");
    el.style.transitionDelay = (el.matches(".rows .row, details, .numbers .n") ? (i % 6) * 60 : 0) + "ms";
    io.observe(el);
  });

  function count(el) {
    var to = +el.getAttribute("data-count"), suf = el.getAttribute("data-suffix") || "", t0 = null;
    function step(t) {
      if (!t0) t0 = t;
      var k = Math.min(1, (t - t0) / 1100), v = Math.round(to * (1 - Math.pow(1 - k, 3)));
      el.textContent = v.toLocaleString("en-US") + suf;
      if (k < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  var prompt = document.querySelector(".studio-teaser .prompt");
  if (prompt) {
    var ideas = ["a frog who works night shifts at a 24h ramen shop", "a cat that only trades on Mondays",
                 "a jellyfish who checks every pool before swimming in"], n = 0;
    var text = prompt.firstChild, caret = prompt.querySelector(".accent");
    (function loop() {
      var s = ideas[n++ % ideas.length], i = 0;
      (function type() {
        text.nodeValue = s.slice(0, ++i);
        if (i < s.length) setTimeout(type, 38); else setTimeout(loop, 2600);
      })();
    })();
    if (caret) prompt.appendChild(caret);
  }
})();
