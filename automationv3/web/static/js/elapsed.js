/* Running times that count up: a <span class="elapsed" data-since="ISO"
   data-now="ISO"> (documents/html.py) shows how long something still
   running has run. data-now is the server's time when it drew the span,
   so the count doesn't depend on this machine's clock being right. */
(function () {
  "use strict";

  function shown(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    var h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    function two(n) { return (n < 10 ? "0" : "") + n; }
    if (h) return h + ":" + two(m) + ":" + two(s);
    return m ? m + ":" + two(s) : s + " s";
  }

  function tick() {
    var spans = document.querySelectorAll(".elapsed[data-since]");
    for (var i = 0; i < spans.length; i++) {
      var span = spans[i], since = Date.parse(span.dataset.since);
      if (isNaN(since)) continue;
      if (span._offset === undefined) {  // the server's clock less this one's, when it was drawn
        var now = Date.parse(span.dataset.now);
        span._offset = isNaN(now) ? 0 : now - Date.now();
      }
      span.textContent = shown((Date.now() + span._offset - since) / 1000);
    }
  }

  setInterval(tick, 1000);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tick);
  else tick();
  document.addEventListener("htmx:afterSettle", tick);
})();
