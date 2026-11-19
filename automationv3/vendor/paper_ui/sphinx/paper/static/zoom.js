/* paper-ui: open a diagram or an image in a viewer to zoom and pan it.
 *
 * Clicking (or Enter on) a diagram (mermaid-diag's .mermaid-diag__canvas, or any figure's SVG) or an image on a
 * docs page opens it in a modal dialog:
 *   wheel or pinch: zoom at the pointer       drag: pan
 *   double-click: zoom in (Shift: out)        + / - / 0: zoom in, out, fit      arrows: pan
 *   Esc or the close button: back to the page, focus where it was.
 * Images inside links are left alone (the link wins), except Sphinx's link from a scaled image to its own file.
 * No dependencies.
 */
(function () {
  "use strict";

  var MIN = 0.1, MAX = 12, STEP = 1.25;
  var TARGETS = ".ui-doc .mermaid-diag__canvas, .ui-doc figure > svg, .ui-doc img";

  var dialog, stage, content, titleEl, levelEl;
  var view = { scale: 1, x: 0, y: 0, w: 0, h: 0 };
  var opener = null;

  function icon(path) {
    return '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + path + "</svg>";
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "ui-zoom";
    dialog.setAttribute("aria-label", "Enlarged view");
    dialog.innerHTML =
      '<div class="ui-zoom__bar">' +
        '<p class="ui-zoom__title"></p>' +
        '<div class="ui-zoom__tools" role="toolbar" aria-label="Zoom">' +
          '<button type="button" class="ui-zoom__btn" data-zoom="out" aria-label="Zoom out" title="Zoom out (−)">' + icon('<path d="M3.5 8h9"/>') + "</button>" +
          '<button type="button" class="ui-zoom__level" data-zoom="fit" title="Fit (0)">100%</button>' +
          '<button type="button" class="ui-zoom__btn" data-zoom="in" aria-label="Zoom in" title="Zoom in (+)">' + icon('<path d="M3.5 8h9M8 3.5v9"/>') + "</button>" +
          '<button type="button" class="ui-zoom__btn" data-zoom="actual" aria-label="Actual size" title="Actual size (1)">1:1</button>' +
          '<button type="button" class="ui-zoom__btn ui-zoom__close" data-zoom="close" aria-label="Close" title="Close (Esc)">' + icon('<path d="M4 4l8 8M12 4l-8 8"/>') + "</button>" +
        "</div>" +
      "</div>" +
      '<div class="ui-zoom__stage" tabindex="-1"><div class="ui-zoom__content"></div></div>' +
      '<p class="ui-zoom__hint">Scroll or pinch to zoom · drag to pan · double-click to zoom in</p>';
    document.body.appendChild(dialog);
    stage = dialog.querySelector(".ui-zoom__stage");
    content = dialog.querySelector(".ui-zoom__content");
    titleEl = dialog.querySelector(".ui-zoom__title");
    levelEl = dialog.querySelector(".ui-zoom__level");

    dialog.querySelector(".ui-zoom__tools").addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      var what = b.getAttribute("data-zoom");
      if (what === "close") dialog.close();
      else if (what === "fit") fit();
      else if (what === "actual") zoomTo(1);
      else zoomBy(what === "in" ? STEP : 1 / STEP);
    });
    dialog.addEventListener("close", function () {
      document.documentElement.classList.remove("ui-zoom-open");
      content.textContent = "";
      if (opener) opener.focus();
    });
    // a click on the backdrop (outside the dialog's box) closes it
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
    dialog.addEventListener("keydown", keys);
    stage.addEventListener("wheel", wheel, { passive: false });
    stage.addEventListener("dblclick", function (e) {
      zoomBy(e.shiftKey ? 1 / 2 : 2, point(e));
    });
    pointers();
    window.addEventListener("resize", function () { if (dialog.open) fit(); });
  }

  // -------------------------------------------------------------------- opening

  function captionOf(el) {
    var fig = el.closest("figure");
    var cap = fig && fig.querySelector("figcaption");
    if (cap) {
      var num = cap.querySelector(".caption-number");
      var text = cap.querySelector(".caption-text");
      if (text) return ((num ? num.textContent : "") + text.textContent).trim();
      return cap.textContent.trim();
    }
    return el.getAttribute("alt") || el.getAttribute("aria-label") || "";
  }

  function sizeOf(svg) {
    var vb = svg.viewBox && svg.viewBox.baseVal;
    if (vb && vb.width) return { w: vb.width, h: vb.height };
    var r = svg.getBoundingClientRect();
    return { w: r.width, h: r.height };
  }

  function open(target) {
    if (!dialog) build();
    opener = target;
    content.textContent = "";
    var title = captionOf(target.tagName === "IMG" ? target : target.querySelector("svg") || target);
    titleEl.textContent = title;
    titleEl.hidden = !title;

    if (target.tagName === "IMG") {
      var img = new Image();
      img.src = target.currentSrc || target.src;
      img.alt = target.alt || "";
      img.draggable = false;
      content.className = "ui-zoom__content";
      content.appendChild(img);
      var natural = function () {
        // an SVG image without intrinsic size: use the size it is shown at
        var w = img.naturalWidth || target.clientWidth, h = img.naturalHeight || target.clientHeight;
        show(w, h);
      };
      if (img.complete && img.naturalWidth) natural(); else { img.onload = natural; img.onerror = natural; }
    } else {
      var svg = target.tagName === "svg" ? target : target.querySelector("svg");
      if (!svg) return;
      var copy = svg.cloneNode(true);
      var size = sizeOf(svg);
      copy.removeAttribute("style");
      copy.setAttribute("width", size.w);
      copy.setAttribute("height", size.h);
      // keep the diagram's site styling (mermaid-diag palette overrides are set on .mermaid-diag svg)
      content.className = "ui-zoom__content" + (target.closest(".mermaid-diag") ? " mermaid-diag" : "");
      content.appendChild(copy);
      show(size.w, size.h);
    }
    document.documentElement.classList.add("ui-zoom-open");
    dialog.showModal();
    stage.focus();
  }

  function show(w, h) {
    view.w = w; view.h = h;
    content.style.width = w + "px";
    content.style.height = h + "px";
    // the dialog has to be laid out before it can be fitted
    requestAnimationFrame(fit);
  }

  // -------------------------------------------------------------------- the view

  function apply() {
    content.style.transform = "translate(" + view.x + "px," + view.y + "px) scale(" + view.scale + ")";
    levelEl.textContent = Math.round(view.scale * 100) + "%";
  }

  function fit() {
    var r = stage.getBoundingClientRect();
    var pad = 24;
    var s = Math.min((r.width - pad * 2) / view.w, (r.height - pad * 2) / view.h);
    view.scale = clamp(Math.min(s, 3));
    view.x = (r.width - view.w * view.scale) / 2;
    view.y = (r.height - view.h * view.scale) / 2;
    apply();
  }

  function clamp(s) { return Math.max(MIN, Math.min(MAX, s)); }

  function centre() {
    var r = stage.getBoundingClientRect();
    return { x: r.width / 2, y: r.height / 2 };
  }

  function point(e) {
    var r = stage.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  // zoom so the content under `at` (stage coordinates) stays put
  function zoomTo(scale, at) {
    at = at || centre();
    var s = clamp(scale), k = s / view.scale;
    view.x = at.x - (at.x - view.x) * k;
    view.y = at.y - (at.y - view.y) * k;
    view.scale = s;
    apply();
  }

  function zoomBy(factor, at) { zoomTo(view.scale * factor, at); }

  function pan(dx, dy) { view.x += dx; view.y += dy; apply(); }

  function wheel(e) {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey || !e.shiftKey) {
      // trackpad pinches arrive as ctrl+wheel with small deltas; mouse wheels as larger steps
      var delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomBy(Math.exp(-delta * (e.ctrlKey ? 0.01 : 0.0015)), point(e));
    } else {
      pan(-e.deltaX - e.deltaY, 0);
    }
  }

  function keys(e) {
    var k = e.key, step = e.shiftKey ? 120 : 40;
    if (k === "Escape") dialog.close();   // also the dialog's own cancel, which a browser may skip
    else if (k === "+" || k === "=") zoomBy(STEP);
    else if (k === "-" || k === "_") zoomBy(1 / STEP);
    else if (k === "0") fit();
    else if (k === "1") zoomTo(1);
    else if (k === "ArrowLeft") pan(step, 0);
    else if (k === "ArrowRight") pan(-step, 0);
    else if (k === "ArrowUp") pan(0, step);
    else if (k === "ArrowDown") pan(0, -step);
    else return;
    e.preventDefault();
  }

  // drag to pan with one pointer, pinch to zoom with two
  function pointers() {
    var down = new Map(), last = null, pinch = null;
    stage.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      stage.setPointerCapture(e.pointerId);
      down.set(e.pointerId, point(e));
      stage.classList.add("ui-zoom__stage--dragging");
      if (down.size === 1) last = point(e);
      if (down.size === 2) {
        var p = Array.from(down.values());
        pinch = { d: dist(p[0], p[1]), scale: view.scale };
      }
    });
    stage.addEventListener("pointermove", function (e) {
      if (!down.has(e.pointerId)) return;
      down.set(e.pointerId, point(e));
      if (down.size === 2 && pinch) {
        var p = Array.from(down.values());
        zoomTo(pinch.scale * dist(p[0], p[1]) / pinch.d, mid(p[0], p[1]));
      } else if (down.size === 1 && last) {
        var q = point(e);
        pan(q.x - last.x, q.y - last.y);
        last = q;
      }
    });
    function up(e) {
      down.delete(e.pointerId);
      if (down.size < 2) pinch = null;
      last = down.size === 1 ? Array.from(down.values())[0] : null;
      if (!down.size) stage.classList.remove("ui-zoom__stage--dragging");
    }
    stage.addEventListener("pointerup", up);
    stage.addEventListener("pointercancel", up);
  }

  function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) || 1; }
  function mid(a, b) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }

  // -------------------------------------------------------------------- the page

  function zoomable(el) {
    // a link wins, except Sphinx's own link from a scaled image to its file: the viewer does that better
    var link = el.tagName === "IMG" && el.closest("a");
    if (link && !link.classList.contains("image-reference")) return false;
    if (el.closest(".ui-zoom")) return false;
    if (el.tagName === "svg" && el.closest(".mermaid-diag__canvas")) return false;  // its canvas is the target
    return true;
  }

  function label(el) {
    var what = el.tagName === "IMG" ? "image" : "diagram";
    var name = captionOf(el.tagName === "IMG" ? el : el.querySelector("svg") || el);
    return "Enlarge " + what + (name ? ": " + name : "");
  }

  function init() {
    if (typeof HTMLDialogElement === "undefined") return;   // very old browsers: the page as it is
    document.querySelectorAll(TARGETS).forEach(function (el) {
      if (!zoomable(el)) return;
      el.classList.add("ui-zoomable");
      el.setAttribute("tabindex", "0");
      el.setAttribute("role", "button");
      el.setAttribute("aria-label", label(el));
      el.addEventListener("click", function (e) {
        var a = e.target.closest("a");
        if (a && !a.classList.contains("image-reference")) return;   // links inside a diagram still work
        if (e.ctrlKey || e.metaKey || e.shiftKey) return;              // open the file in a new tab, as asked
        e.preventDefault();
        open(el);
      });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(el); }
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
