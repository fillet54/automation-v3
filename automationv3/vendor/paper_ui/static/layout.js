/* paper-ui's document layouts (ui.css: <html data-ui-layout="narrow|medium|full|tufte">).
 *
 * The page sets the layout before it is drawn (the Sphinx theme: a script in <head>, from ?layout=, the reader's
 * last choice or the docs' own). This script does the rest:
 *
 * - a <select data-ui-layout-switch> changes the layout and remembers the choice (localStorage
 *   "paper-ui-layout"), and every change is announced as a "ui-layout" event on the document (settings.js
 *   makes the select the Layout part of the header's settings menu);
 * - margin notes (.ui-margin) float into the margin from where they are written, so one written after its
 *   paragraph would start below it, leaving a gap. While they float, each is lifted beside the text blocks just
 *   before it, as many as its height covers; when they don't, everything goes back where it was written.
 */
(() => {
  const KEY = "paper-ui-layout";
  const root = document.documentElement;
  const TEXT = /^(P|UL|OL|DL|BLOCKQUOTE)$/;
  let moved = [];

  function place() {
    for (const { item, mark } of moved) {
      mark.replaceWith(item);
    }
    moved = [];
    for (const item of document.querySelectorAll(".ui-doc .ui-margin")) {
      if (getComputedStyle(item).float === "none") continue;
      const need = item.getBoundingClientRect().height;
      let covered = 0, before = null, prev = item.previousElementSibling;
      while (prev && covered < need && !prev.classList.contains("ui-margin")
             && (TEXT.test(prev.tagName) || prev.matches(".admonition"))
             && getComputedStyle(prev).float === "none") {
        covered += prev.getBoundingClientRect().height;
        before = prev;
        prev = prev.previousElementSibling;
      }
      if (!before) continue;
      const mark = document.createComment("ui-margin");
      item.replaceWith(mark);
      before.before(item);
      moved.push({ item, mark });
    }
  }

  function choose(layout, remember) {
    root.setAttribute("data-ui-layout", layout);
    if (remember) {
      try { localStorage.setItem(KEY, layout); } catch (e) { /* private window: this page only */ }
    }
    place();
    document.dispatchEvent(new CustomEvent("ui-layout", { detail: layout }));
  }

  function start() {
    for (const select of document.querySelectorAll("select[data-ui-layout-switch]")) {
      select.value = root.getAttribute("data-ui-layout") || select.value;
      select.addEventListener("change", () => choose(select.value, true));
    }
    place();
    // the margin comes and goes with the document's width (a container query), so look again when it changes
    const doc = document.querySelector(".ui-doc");
    if (doc && "ResizeObserver" in window) {
      let width = doc.clientWidth, timer = 0;
      new ResizeObserver(() => {
        if (doc.clientWidth === width) return;
        width = doc.clientWidth;
        clearTimeout(timer);
        timer = setTimeout(place, 120);
      }).observe(doc);
    }
    if (document.fonts) document.fonts.ready.then(place);   // heights change once the fonts are in
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
