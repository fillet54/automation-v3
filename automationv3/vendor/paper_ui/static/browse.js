/* paper-ui: a resizable side column on browse pages (.ui-browse).
 *
 * Adds a handle on the rule between the side column and the page: drag it, or focus it and use the arrow keys
 * (Shift: bigger steps), Home and End; double-click it to go back to the default width. The page moves over as
 * the side column grows. The width is kept per browser, under the browse element's data-ui-side-key (one width
 * for the docs, another for an app's file tree). Without this script the side column keeps its CSS width.
 */
(function () {
  "use strict";

  var MIN = 200, MAX = 640, STEP = 16, BIG_STEP = 64;

  function load(key) { try { return parseFloat(localStorage.getItem(key)) || null; } catch (e) { return null; } }
  function save(key, v) { try { if (v == null) localStorage.removeItem(key); else localStorage.setItem(key, String(v)); } catch (e) {} }

  function setup(browse) {
    var side = browse.querySelector(":scope > .ui-browse__side");
    if (!side || browse.querySelector(":scope > .ui-browse__handle")) return;
    var key = "ui-side:" + (browse.getAttribute("data-ui-side-key") || "default");

    var handle = document.createElement("div");
    handle.className = "ui-browse__handle";
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-label", "Resize the side column");
    handle.setAttribute("aria-valuemin", MIN);
    handle.setAttribute("tabindex", "0");
    handle.title = "Drag to resize · double-click to reset";
    side.after(handle);
    browse.classList.add("ui-browse--resizable");

    function max() {
      // never more than half the row: the page keeps the larger share
      return Math.max(MIN, Math.min(MAX, browse.getBoundingClientRect().width / 2));
    }
    function width() { return side.getBoundingClientRect().width; }
    function set(w, keep) {
      if (w == null) {
        browse.style.removeProperty("--ui-side");
      } else {
        w = Math.round(Math.max(MIN, Math.min(max(), w)));
        browse.style.setProperty("--ui-side", w + "px");
      }
      handle.setAttribute("aria-valuemax", Math.round(max()));
      handle.setAttribute("aria-valuenow", Math.round(width()));
      if (keep) save(key, w);
    }

    set(load(key), false);

    // dragging
    var start = null;
    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      start = { x: e.clientX, w: width() };
      document.documentElement.classList.add("ui-resizing");
    });
    handle.addEventListener("pointermove", function (e) {
      if (start) set(start.w + e.clientX - start.x, false);
    });
    function end() {
      if (!start) return;
      start = null;
      document.documentElement.classList.remove("ui-resizing");
      set(width(), true);
    }
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
    handle.addEventListener("dblclick", function () { set(null, true); });

    // keys
    handle.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? BIG_STEP : STEP, w = width();
      if (e.key === "ArrowLeft") set(w - step, true);
      else if (e.key === "ArrowRight") set(w + step, true);
      else if (e.key === "Home") set(MIN, true);
      else if (e.key === "End") set(max(), true);
      else if (e.key === "Enter") set(null, true);
      else return;
      e.preventDefault();
    });

    // a narrower window can make a kept width too wide
    window.addEventListener("resize", function () {
      var kept = load(key);
      if (kept != null) set(kept, false);
    });
  }

  function init() { document.querySelectorAll(".ui-browse").forEach(setup); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
