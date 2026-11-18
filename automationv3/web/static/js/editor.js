// The workspace editor: files open in tabs, each shown as its cards
// (web/editor.py), which open into editors in a worktree.
//
// A tab's pane holds what /view returns for its file. The cards on the
// page are the tab's state: each card element keeps what the server cut
// it from (el._card), and an edited one is that with no `source`. A
// variant card holds cards of its own in its body; when anything inside
// it changes, it loses its `source` too, and is written again on save.
// A tab with unsaved edits also keeps its cards in localStorage (a
// draft), so a reload, or anything that redraws the pane, brings them
// back. Each tab has one undo history: snapshots of its cards, taken
// before each change (typing inside an open card is CodeMirror's own).
(function () {
  "use strict";

  var root, ws, base, editable, consoleOn;
  var tabs = [];      // paths, in tab order
  var active = null;  // the active tab's path
  var states = {};    // path -> {pane, loaded, dirty, conflict, baseHash, count, undo, redo, saved}
  var firstLoad = {}; // the view options the page was opened with, for its file
  var HISTORY = 100;  // undo steps kept per tab

  function $(selector, within) { return (within || document).querySelector(selector); }
  function all(selector, within) { return Array.prototype.slice.call((within || document).querySelectorAll(selector)); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function button(label, act, cls, title) {
    var b = el("button", "ui-btn ui-btn--sm " + (cls || "ui-btn--secondary"), label);
    b.type = "button";
    b.dataset.edAct = act;
    if (title) { b.title = title; b.setAttribute("aria-label", title); }
    return b;
  }

  function url(path, what, params) {
    var query = "path=" + encodeURIComponent(path);
    Object.keys(params || {}).forEach(function (k) {
      if (params[k]) query += "&" + k + "=" + encodeURIComponent(params[k]);
    });
    return base + "/" + what + "?" + query;
  }
  function post(address, body) {
    return fetch(address, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  }

  // Cards: a document's, and a variant's own

  function docOf(path) { return states[path] ? $("[data-ed-doc]", states[path].pane) : null; }
  function pathOf(node) { var pane = node.closest(".ed-pane"); return pane ? pane.dataset.path : null; }
  function cardsOf(container) { return container ? all(":scope > .ed-card", container) : []; }
  function bodyOf(card) { return $(":scope > .ed-variant__body", card); }
  function viewOf(card) { return $(":scope > .ed-card__view", card); }
  function isVariant(card) { return card._card.kind === "variant"; }
  function isCard(node) { return !!node && node.nodeType === 1 && node.classList.contains("ed-card"); }
  // The card at or after `node` among its siblings, or null
  function cardFrom(node) { while (node && !isCard(node)) node = node.nextSibling; return node; }
  function editing(within) { return all(".ed-card.is-editing", within); }

  // A variant's own view: which variations it is for (web/editor.py: variant_head)
  function variantHead(variations) {
    var head = el("p", "ed-variant__head");
    head.appendChild(el("span", "ed-variant__label", "Only for"));
    if (!variations.length) head.appendChild(el("span", "ed-unreadable", "no variations: say which"));
    variations.forEach(function (name) { head.appendChild(document.createTextNode(" ")); head.appendChild(el("code", null, name)); });
    return head.outerHTML;
  }

  // Anything inside these variants changed: each is written again
  function touch(card) {
    for (var v = card.parentNode && card.parentNode.closest(".ed-card--variant"); v; v = v.parentNode.closest(".ed-card--variant")) {
      v._card = Object.assign({}, v._card, { source: null });
    }
  }

  // Put a card in `container`, before `before` (null: at its end). A card
  // that changes container forgets its place in its old one.
  function moveCard(card, container, before) {
    touch(card);
    if (card.parentNode !== container) card._card = Object.assign({}, card._card, { index: null });
    container.insertBefore(card, before || null);
    touch(card);
  }

  // What a card is now, as the server takes it: a variant with its
  // children. With `typed`, a card being edited is what its editor holds,
  // and a variant with one open inside it is written again.
  function dataOf(card, typed) {
    var data = card._edit ? current(card, typed) : card._card;
    if (!isVariant(card)) return data;
    if (typed && editing(bodyOf(card)).length) data = Object.assign({}, data, { source: null });
    return Object.assign({}, data, { children: cardsOf(bodyOf(card)).map(function (c) { return dataOf(c, typed); }) });
  }

  // A container's cards as a draft or an undo step keeps them: their
  // data and HTML. A new card still being written isn't one yet.
  function serialize(container) {
    return cardsOf(container).filter(function (c) { return !(c._edit && c._edit.isNew); }).map(function (c) {
      var entry = { data: c._card, html: viewOf(c).innerHTML };
      if (isVariant(c)) entry.children = serialize(bodyOf(c));
      return entry;
    });
  }
  function restore(entries, container) {
    entries.forEach(function (entry) {
      var card = section(entry.data, entry.html);
      container.appendChild(card);
      if (entry.data.kind === "variant") restore(entry.children || [], bodyOf(card));
    });
  }

  // Drafts

  var held = {};  // path -> draft, for when the browser's storage is off or full
  function draftKey(path) { return "ed:" + ws + ":" + path; }
  function draft(path) {
    try { return JSON.parse(localStorage.getItem(draftKey(path))) || held[path] || null; } catch (e) { return held[path] || null; }
  }
  function dropDraft(path) {
    delete held[path];
    try { localStorage.removeItem(draftKey(path)); } catch (e) { /* nothing kept */ }
  }
  function putDraft(path, kept) {
    held[path] = kept;
    try { localStorage.setItem(draftKey(path), JSON.stringify(kept)); delete held[path]; } catch (e) { /* held on the page only */ }
  }
  // The files made here that were never saved: they only exist as drafts
  function unsavedFiles() {
    var found = [], prefix = "ed:" + ws + ":";
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i);
        if (key.indexOf(prefix) === 0 && (draft(key.slice(prefix.length)) || {}).hash === "") found.push(key.slice(prefix.length));
      }
    } catch (e) { /* none to bring back */ }
    return found;
  }
  function keepDraft(path) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc) return;
    putDraft(path, { hash: st.baseHash, count: st.count, cards: serialize(doc) });
  }

  // Tabs

  function label(path) {
    var name = path.split("/").pop();
    var twins = tabs.filter(function (p) { return p.split("/").pop() === name; });
    return twins.length > 1 ? path.split("/").slice(-2).join("/") : name;
  }

  function drawTabs() {
    var bar = $(".ed-bar", root), strip = $(".ed-tabs", root);
    bar.hidden = !tabs.length;
    $(".ed-pane--home", root).hidden = !!tabs.length;
    strip.textContent = "";
    tabs.forEach(function (path) {
      var st = states[path];
      var tab = el("div", "ed-tab" + (path === active ? " is-active" : "") + (st.dirty ? " is-dirty" : ""));
      var open = el("button", "ed-tab__name", label(path));
      open.type = "button";
      open.title = path + (st.dirty ? " (unsaved edits)" : "");
      open.setAttribute("role", "tab");
      open.setAttribute("aria-selected", path === active ? "true" : "false");
      open.dataset.edTab = path;
      var close = el("button", "ed-tab__close", "×");
      close.type = "button";
      close.title = "Close " + path + (st.dirty ? ": its unsaved edits are kept for when you open it again" : "");
      close.setAttribute("aria-label", close.title);
      close.dataset.edClose = path;
      tab.appendChild(open);
      if (st.errors) {
        var errors = el("span", "ed-tab__errors", String(st.errors));
        errors.title = st.errors + (st.errors === 1 ? " error" : " errors");
        tab.appendChild(errors);
      }
      if (st.dirty) tab.appendChild(el("span", "ed-tab__dot"));
      tab.appendChild(close);
      strip.appendChild(tab);
    });
    drawActions();
  }

  function drawActions() {
    var st = states[active];
    var save = $("[data-ed-save]", root), discard = $("[data-ed-discard]", root);
    if (save) save.disabled = !(st && st.dirty);
    if (discard) { discard.hidden = !(st && st.dirty); discard.textContent = "Discard edits"; delete discard.dataset.sure; }
    var menu = $(".ed-menu", root);
    if (menu) { menu.hidden = !st || !!st.isNew || !st.loaded; menu.open = false; }
    var undo = $("[data-ed-undo]", root), redo = $("[data-ed-redo]", root);
    if (undo) undo.disabled = !(st && st.undo && st.undo.length);
    if (redo) redo.disabled = !(st && st.redo && st.redo.length);
  }

  function say(text) {
    var status = $(".ed-status", root);
    if (status) status.textContent = text || "";
  }

  var remembering;
  function rememberTabs() {
    clearTimeout(remembering);
    remembering = setTimeout(function () {
      fetch(base + "/tabs", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: tabs, active: active }),
      }).catch(function () { /* remembered next time */ });
    }, 200);
  }

  function addTab(path) {
    if (states[path]) return;
    var pane = el("div", "ed-pane");
    pane.hidden = true;
    pane.dataset.path = path;
    $(".ed-panes", root).appendChild(pane);
    states[path] = { pane: pane, loaded: false, dirty: !!draft(path), conflict: false, undo: [], redo: [] };
    tabs.push(path);
  }

  function open(path) {
    addTab(path);
    activate(path);
  }

  function activate(path) {
    active = path;
    tabs.forEach(function (p) {
      var pane = states[p].pane;
      pane.hidden = p !== path;
      // htmx controls in a pane aim at #content: only the active pane has it
      var content = $(":scope > div:not(.ed-conflict)", pane);
      if (content) content.id = p === path ? "content" : "";
    });
    var home = $(".ed-pane--home > div", root);
    if (home) home.id = path ? "" : "content";
    if (path && !states[path].loaded) load(path, firstLoad[path]);
    else if (path) checkDisk(path);
    all(".ui-tree__row[aria-current]").forEach(function (r) { r.removeAttribute("aria-current"); });
    all(".ui-tree__row--file[data-open]").forEach(function (r) {
      if (r.dataset.open === path) r.setAttribute("aria-current", "true");
    });
    if (path) {
      var report = $("#target-report");
      history.replaceState(null, "", base + "?path=" + encodeURIComponent(path) +
        (report ? "&report=" + encodeURIComponent(report.value) : ""));
    } else {
      history.replaceState(null, "", base);
    }
    say("");
    drawTabs();
    rememberTabs();
  }

  function closeTab(path) {
    var st = states[path];
    if (!st) return;
    st.pane.remove();
    lspClose(path);
    delete states[path];
    var at = tabs.indexOf(path);
    tabs.splice(at, 1);
    if (active === path) activate(tabs[Math.min(at, tabs.length - 1)] || null);
    else { drawTabs(); rememberTabs(); }
  }

  // A tab's pane

  function load(path, options) {
    var st = states[path];
    st.loaded = true;
    if (!st.pane.firstElementChild) st.pane.appendChild(el("div", "ui-row ui-muted", "Loading " + path));
    var report = $("#target-report");
    var params = Object.assign({ report: report && report.value }, options || {});
    return fetch(url(path, "view", params)).then(function (response) {
      if (response.status === 404) throw new Error(path + " isn't in this workspace any more.");
      if (!response.ok) throw new Error("Couldn't open " + path + " (" + response.status + ").");
      return response.text();
    }).then(function (html) {
      st.pane.innerHTML = html;
      st.conflict = false;
      if (st.pane.firstElementChild) st.pane.firstElementChild.id = path === active ? "content" : "";
      if (window.htmx) window.htmx.process(st.pane);
      scan(st.pane);
    }).catch(function (error) {
      st.pane.textContent = "";
      st.pane.appendChild(el("div", "ed-unreadable", error.message));
    });
  }

  // Make a pane's document editable, and bring back its draft
  function scan(pane) {
    var path = pane.dataset.path, st = states[path];
    var doc = $("[data-ed-doc]", pane);
    if (!st) return;
    if (!doc) { st.dirty = !!draft(path); drawTabs(); return; }
    if (doc._ready) return;
    doc._ready = true;
    st.baseHash = doc.dataset.hash;
    st.isNew = doc.dataset.hash === "";  // not on disk yet
    st.count = Number(doc.dataset.count);
    st.undo = [];
    st.redo = [];
    all(".ed-card", doc).forEach(function (card) { card._card = JSON.parse(card.dataset.card); card.removeAttribute("data-card"); });
    st.saved = snapshot(doc);
    var kept = editable && draft(path);
    if (kept) {
      doc.textContent = "";
      restore(kept.cards, doc);
      st.baseHash = kept.hash;
      st.count = kept.count;
      st.dirty = true;
      if (st.isNew) st.saved = null;  // nothing on disk to come back to
      if ((kept.hash || "") !== doc.dataset.hash) { st.conflict = true; showConflict(path); }
    } else {
      st.dirty = false;
    }
    if (editable && doc.dataset.editable === "true") {
      decorateAll(doc);
      if (doc.dataset.plain === "true" && !cardsOf(doc).length) doc.appendChild(decorate(section({ kind: "source", source: null, index: null, text: "" }, "")));
    }
    lspSync(path);
    drawTabs();
  }

  function section(data, html) {
    var card = el("section", "ed-card ed-card--" + data.kind);
    var view = el("div", "ed-card__view");
    view.innerHTML = html;
    card.appendChild(view);
    if (data.kind === "variant") card.appendChild(el("div", "ed-variant__body"));
    card._card = data;
    return card;
  }

  // The variations a script declares
  function declared(doc) {
    try { return JSON.parse(doc.dataset.variations || "[]"); } catch (e) { return []; }
  }

  // Every card's gutter, and a way to start in whatever holds no card
  function decorateAll(doc) {
    all(".ed-card", doc).forEach(decorate);
    empties(doc);
  }

  // A card's gutter, left of it and hidden until the card is pointed at:
  // ".." opens its menu, "::" drags it
  function decorate(card) {
    if ($(":scope > .ed-gutter", card)) return card;
    var doc = card.closest("[data-ed-doc]");
    if (doc && doc.dataset.plain === "true") return card;
    var gutter = el("div", "ed-gutter");
    var menu = el("button", "ed-gutter__btn", "..");
    menu.type = "button";
    menu.dataset.edMenu = "";
    menu.title = "Add, change or delete";
    menu.setAttribute("aria-label", "Add, change or delete");
    menu.setAttribute("aria-haspopup", "menu");
    var grip = el("button", "ed-gutter__btn ed-grip", "::");
    grip.type = "button";
    grip.dataset.edGrip = "";
    grip.title = "Drag to move";
    grip.setAttribute("aria-label", "Drag to move");
    if (consoleOn && card._card && card._card.kind === "rvt") {
      var play = el("button", "ed-gutter__btn ed-play", "▶");
      play.type = "button";
      play.dataset.edPlay = "";
      play.title = "Run this block in the console";
      play.setAttribute("aria-label", "Run this block in the console");
      gutter.appendChild(play);
      gutter.classList.add("has-play");
    }
    gutter.appendChild(menu);
    gutter.appendChild(grip);
    card.insertBefore(gutter, card.firstChild);
    return card;
  }

  // A document or a variant that holds no card offers to start one
  function empties(doc) {
    if (!doc || doc.dataset.plain === "true" || doc.dataset.editable !== "true") return;
    [doc].concat(all(".ed-variant__body", doc)).forEach(function (container) {
      var holds = cardsOf(container).length, offer = $(":scope > .ed-empty", container);
      if (holds && offer) offer.remove();
      if (!holds && !offer) {
        offer = el("div", "ed-empty");
        offer.appendChild(button("Add text", "add-prose", "ui-btn--ghost"));
        offer.appendChild(button("Add steps", "add-rvt", "ui-btn--ghost"));
        container.appendChild(offer);
      }
    });
  }

  function dirty(path) {
    var st = states[path];
    st.dirty = true;
    keepDraft(path);
    say("Unsaved edits");
    drawTabs();
    empties(docOf(path));
    lspSync(path);
  }

  // Undo: one history per tab

  function snapshot(doc) { return JSON.stringify(serialize(doc)); }

  // Keep how the tab is now, before a change
  function remember(path) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc) return;
    st.undo.push(snapshot(doc));
    if (st.undo.length > HISTORY) st.undo.shift();
    st.redo = [];
  }

  function rebuild(path, kept) {
    var st = states[path], doc = docOf(path);
    all(".ed-card", doc).forEach(function (card) { if (card._edit) card._edit.view.destroy(); });
    closeMenu();
    all(":scope > .ed-card, :scope > .ed-empty", doc).forEach(function (node) { node.remove(); });
    restore(JSON.parse(kept), doc);
    decorateAll(doc);
    st.dirty = st.isNew || kept !== st.saved;
    if (st.dirty) keepDraft(path); else dropDraft(path);
    say(st.dirty ? "Unsaved edits" : "");
    drawTabs();
    lspSync(path);
  }

  function undo(path, again) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc || editing(doc).length) return;
    var from = again ? st.redo : st.undo, to = again ? st.undo : st.redo;
    if (!from.length) return;
    to.push(snapshot(doc));
    rebuild(path, from.pop());
  }

  // The language server (lsp/server.py), behind /lsp (web/editor.py:
  // PageSession), spoken to in cards: it is sent each tab's cards, edits
  // in progress included, builds the file from them as a save would, and
  // answers with each problem's card (its place in walk order: a variant
  // before what it holds) and where it is in that card's editor. A tab
  // keeps, in `order`, the card elements of the cards the server has.

  var lsp = { session: Math.random().toString(36).slice(2) + Date.now().toString(36), started: false, sent: {}, queue: Promise.resolve(), problems: {} };
  var TYPES = { 3: "function", 6: "variable", 7: "class", 10: "property", 14: "keyword", 18: "text" };
  var REQ_OPEN = /:req:`[^`]*$/i;
  var NAME = /[^\s()\[\]{}"';,]*/;

  // A container's card elements in walk order: each variant before its own
  function walkCards(container) {
    var found = [];
    cardsOf(container).forEach(function (card) {
      found.push(card);
      if (isVariant(card)) found = found.concat(walkCards(bodyOf(card)));
    });
    return found;
  }

  // Send `body`, in order with every other send; gives the answer.
  // `orders`: {path: card elements} for the cards it syncs.
  function lspPost(body, orders) {
    lsp.queue = lsp.queue.then(function () {
      if (!lsp.started) { lsp.started = true; body.start = true; }
      return post(base + "/lsp", Object.assign({ session: lsp.session }, body))
        .then(function (response) { return response.ok ? response.json() : { problems: {} }; })
        .then(function (found) {
          if (found.reset) { lspReset(); return found; }
          Object.keys(orders || {}).forEach(function (path) { if (states[path]) states[path].order = orders[path]; });
          var paths = Object.keys(found.problems || {});
          paths.forEach(function (path) {
            if (found.problems[path].length) lsp.problems[path] = found.problems[path];
            else delete lsp.problems[path];
            showProblems(path);
          });
          if (paths.length) { drawProblems(); drawTreeCounts(); }
          return found;
        });
    }).catch(function () { return {}; });
    return lsp.queue;
  }

  // The server forgot this page: start over, sending every tab again
  function lspReset() {
    lsp.started = false;
    lsp.sent = {};
    setTimeout(function () { tabs.forEach(function (path) { lspSync(path); }); }, 0);
  }

  // Tell the server what a tab's cards are now, if that changed
  function lspSync(path) {
    var st = states[path], doc = docOf(path);
    if (!editable || !st || !doc || doc.dataset.plain === "true" || doc.dataset.editable !== "true") return Promise.resolve();
    var cards = cardsOf(doc).map(function (c) { return dataOf(c, true); });
    var sent = JSON.stringify([cards, st.count]), order = walkCards(doc);
    if (lsp.sent[path] === sent) {
      // the same cards, perhaps drawn again (undo): after what is on its way
      lsp.queue = lsp.queue.then(function () { st.order = order; showProblems(path); });
      return lsp.queue;
    }
    lsp.sent[path] = sent;
    var orders = {};
    orders[path] = order;
    return lspPost({ sync: [{ path: path, cards: cards, count: st.count }] }, orders);
  }

  function lspClose(path) {
    if (!(path in lsp.sent)) return;
    delete lsp.sent[path];
    lspPost({ close: [path] });
  }

  // Where an offset of a card's editor (a CodeMirror doc) is, as the
  // server is asked: {card, line, character}; null for a card it hasn't
  function positionOf(card, text, offset) {
    var st = states[pathOf(card)], index = st && st.order ? st.order.indexOf(card) : -1;
    if (index < 0) return null;
    var line = text.lineAt(offset);
    return { card: index, line: line.number - 1, character: offset - line.from };
  }

  // Ask about a place in a card: hover, completion or signature
  function lspRequest(method, card, text, offset) {
    var path = pathOf(card);
    return lspSync(path).then(function () {
      var position = positionOf(card, text, offset);
      if (!position) return null;
      return lspPost({ request: Object.assign({ method: method, path: path }, position) })
        .then(function (found) { return found && !found.reset ? found.result : null; });
    });
  }

  // Draw a tab's diagnostics: squiggles in the card being edited, a list
  // under any other card, and a count on the tab
  function showProblems(path) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc || !st.order) return;
    var problems = lsp.problems[path] || [];
    doc.classList.add("is-live");  // the diagnostics drawn when the page was made are out of date now
    var by = new Map();
    problems.forEach(function (p) {
      var card = p.card == null ? null : st.order[p.card];
      if (!card) return;
      if (!by.has(card)) by.set(card, []);
      by.get(card).push(p);
    });
    st.order.forEach(function (card) {
      var own = by.get(card) || [];
      var list = $(":scope > .ed-card__problems", card);
      if (list) list.remove();
      if (card._edit && card._edit.view) {
        var view = card._edit.view, text = view.state.doc;
        var at = function (position) {
          if (position.line < 0) return 0;
          if (position.line >= text.lines) return text.length;
          var found = text.line(position.line + 1);
          return Math.min(found.from + Math.max(position.character, 0), found.to);
        };
        view.dispatch(window.CM.setDiagnostics(view.state, own.map(function (p) {
          var from = at(p.from), to = Math.max(at(p.to), from);
          if (to === from && to < text.length) to += 1;
          else if (to === from && from > 0) from -= 1;  // at the very end: mark what comes before
          return { from: from, to: to, severity: p.severity === 1 ? "error" : "warning", message: p.message };
        })));
      }
      if (!own.length) return;
      list = el("ul", "ed-card__problems");
      own.forEach(function (p) {
        var item = el("li", p.severity === 1 ? "is-error" : "is-warning");
        item.appendChild(el("strong", null, p.severity === 1 ? "Error" : "Warning"));
        item.appendChild(document.createTextNode(" " + p.message));
        list.appendChild(item);
      });
      viewOf(card).after(list);
    });
    var errors = problems.filter(function (p) { return p.severity === 1; }).length;
    if (errors !== st.errors) { st.errors = errors; drawTabs(); }
    if (st.reveal != null) { var line = st.reveal; st.reveal = null; reveal(path, line); }
  }

  // The Problems panel: every problem the server knows of, by file

  function drawProblems() {
    var panel = $(".ed-problems", root), toggle = $("[data-ed-problems]", root);
    if (!panel || !toggle) return;
    var paths = Object.keys(lsp.problems).sort(), total = 0, errors = 0;
    paths.forEach(function (path) {
      total += lsp.problems[path].length;
      errors += lsp.problems[path].filter(function (p) { return p.severity === 1; }).length;
    });
    toggle.textContent = "Problems" + (total ? " " + total : "");
    toggle.classList.toggle("has-errors", errors > 0);
    toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
    if (panel.hidden) return;
    panel.textContent = "";
    if (!total) { panel.appendChild(el("p", "ui-muted", "No problems in the open files.")); return; }
    paths.forEach(function (path) {
      var group = el("div", "ed-problems__file");
      group.appendChild(el("div", "ed-problems__path", path));
      var list = el("ul", "ed-problems__list");
      lsp.problems[path].slice().sort(function (a, b) { return a.severity - b.severity || a.line - b.line; }).forEach(function (p) {
        var item = el("li");
        var go = el("button", "ed-problems__item " + (p.severity === 1 ? "is-error" : "is-warning"));
        go.type = "button";
        go.dataset.edReveal = path;
        go.dataset.line = p.line;
        go.appendChild(el("strong", null, p.severity === 1 ? "Error" : "Warning"));
        go.appendChild(document.createTextNode(" " + p.message + " "));
        go.appendChild(el("span", "ui-muted", "line " + (p.line + 1)));
        item.appendChild(go);
        list.appendChild(item);
      });
      group.appendChild(list);
      panel.appendChild(group);
    });
  }

  // Show the card a line is in, opening its file if it isn't open
  function reveal(path, line) {
    if (!states[path] || !states[path].loaded) { open(path); states[path].reveal = line; return; }
    if (active !== path) activate(path);
    var st = states[path];
    var problem = (lsp.problems[path] || []).filter(function (p) { return p.line === line && p.card != null; })[0];
    var card = problem && st.order ? st.order[problem.card] : null;
    if (!card) { st.reveal = line; return; }
    for (var d = card.closest("details"); d; d = d.parentNode.closest("details")) d.open = true;
    card.scrollIntoView({ block: "center", behavior: "smooth" });
    card.classList.remove("is-flashing");
    void card.offsetWidth;
    card.classList.add("is-flashing");
  }

  // How many problems each file in the tree has
  function drawTreeCounts() {
    all(".ed-tree-count").forEach(function (badge) { badge.remove(); });
    Object.keys(lsp.problems).forEach(function (path) {
      var row = $('.ui-tree__row--file[data-open="' + window.CSS.escape(path) + '"]');
      if (!row) return;
      var errors = lsp.problems[path].filter(function (p) { return p.severity === 1; }).length;
      var number = errors || lsp.problems[path].length;
      var badge = el("span", "ed-tree-count " + (errors ? "is-error" : "is-warning"), String(number));
      badge.title = errors ? errors + (errors === 1 ? " error" : " errors") : number + (number === 1 ? " warning" : " warnings");
      row.appendChild(badge);
    });
  }

  // The little markdown the server writes, as elements: code fences,
  // `code`, **bold**, lists and paragraphs
  function prose(markdown) {
    var box = el("div", "ed-hover");
    function inline(parent, text) {
      text.split(/(`[^`]+`|\*\*[^*]+\*\*)/).forEach(function (piece) {
        if (/^`[^`]+`$/.test(piece)) parent.appendChild(el("code", null, piece.slice(1, -1)));
        else if (/^\*\*[^*]+\*\*$/.test(piece)) parent.appendChild(el("strong", null, piece.slice(2, -2)));
        else if (piece) parent.appendChild(document.createTextNode(piece));
      });
    }
    markdown.split(/```[a-z]*\n([\s\S]*?)\n```/).forEach(function (part, n) {
      if (n % 2) { box.appendChild(el("pre", "ui-pre", part)); return; }
      part.split(/\n\n+/).forEach(function (block) {
        if (!block.trim()) return;
        if (/^- /.test(block)) {
          var list = el("ul");
          block.split("\n").forEach(function (row) { inline(list.appendChild(el("li")), row.replace(/^- /, "")); });
          box.appendChild(list);
        } else if (/^ {4}/.test(block) || /::$/.test(block)) {
          box.appendChild(el("pre", "ui-pre", block.replace(/^ {4}/gm, "")));
        } else {
          inline(box.appendChild(el("p")), block.replace(/``/g, "`"));
        }
      });
    });
    return box;
  }

  // What the name under the pointer is
  function hovers(card) {
    return function (view, offset) {
      return lspRequest("hover", card, view.state.doc, offset).then(function (found) {
        if (!found || !found.contents || !found.contents.value) return null;
        var line = view.state.doc.lineAt(offset);
        return {
          pos: Math.max(line.from + found.range.start.character, line.from),
          end: Math.min(line.from + found.range.end.character, line.to), above: true,
          create: function () { return { dom: prose(found.contents.value) }; },
        };
      });
    };
  }

  // How the call the cursor is in is called, under a block's editor,
  // with the argument being typed marked
  function sign(card, view, bar) {
    if (!card._edit) return;
    lspRequest("signature", card, view.state.doc, view.state.selection.main.head).then(function (found) {
      bar.textContent = "";
      bar.hidden = !found || !found.signatures.length;
      if (bar.hidden) return;
      found.signatures.forEach(function (signature, n) {
        var row = el("div", "ed-signature__row" + (n === found.activeSignature ? " is-active" : ""));
        var rest = signature.label, at = 0;
        signature.parameters.forEach(function (parameter, index) {
          var start = rest.indexOf(parameter.label, at);
          if (start < 0) return;
          row.appendChild(document.createTextNode(rest.slice(at, start)));
          row.appendChild(el(n === found.activeSignature && index === found.activeParameter ? "strong" : "span", null, parameter.label));
          at = start + parameter.label.length;
        });
        row.appendChild(document.createTextNode(rest.slice(at)));
        bar.appendChild(row);
      });
    });
  }

  // The names that complete where the cursor is in a block's editor
  function completions(card) {
    return function (context) {
      var req = context.matchBefore(REQ_OPEN), valid = /^[^\s()\[\]{}"';,]*$/;
      var word = context.matchBefore(NAME) || { from: context.pos, to: context.pos };
      if (req) {  // a requirement id, in prose
        word = { from: req.from + 6, to: context.pos };
        valid = /^[^`]*$/;
      } else {
        if (card._card.kind === "prose") return null;
        var before = context.state.sliceDoc(Math.max(0, word.from - 1), word.from);
        if (!context.explicit && word.from === word.to && before !== "(" && before !== '"') return null;
      }
      return lspRequest("completion", card, context.state.doc, context.pos).then(function (found) {
        if (!found || !found.items.length) return null;
        return {
          from: word.from, validFor: valid,
          options: found.items.map(function (item) {
            return { label: item.label, type: TYPES[item.kind], detail: item.detail, info: item.documentation ? function () { return prose(item.documentation); } : null,
                     boost: 5 - Number((item.sortText || "5")[0]) };
          }),
        };
      });
    };
  }

  // Editing a card

  function foot(edit, rvt) {
    var row = el("div", "ed-card__foot");
    row.appendChild(button("Done", "done", "ui-btn--primary"));
    row.appendChild(button("Cancel", "cancel"));
    row.appendChild(el("span", "ui-muted", "Esc or Ctrl+Enter when done" + (consoleOn && rvt ? "; Shift+Enter runs the form at the cursor" : "")));
    edit.appendChild(row);
    return row;
  }

  // Open a card's text for editing: a block's code, a section's rst. What
  // else a card has (a title, its variations) is changed where it shows,
  // or from the card's menu.
  function openCard(card, isNew) {
    if (card._edit) return;
    if (isVariant(card)) { openMenu(card); return; }
    closeMenu();
    editing(card.closest("[data-ed-doc]")).forEach(function (other) { if (other !== card) closeCard(other, true); });
    var data = card._card, rvt = data.kind === "rvt", path = pathOf(card);
    var edit = el("div", "ed-card__edit");
    if (rvt && data.title) edit.appendChild(el("div", "ed-card__title", data.title));
    var holder = el("div", "ed-cm");
    edit.appendChild(holder);
    var bottom = foot(edit, rvt);
    card.appendChild(edit);
    card.classList.add("is-editing");
    function done() { closeCard(card, true); return true; }
    var typing, signing;
    var signature = el("div", "ed-signature");
    signature.hidden = true;
    edit.insertBefore(signature, bottom);
    var view = window.CM.editor(holder, {
      text: rvt ? data.code || "" : data.text || "",
      language: rvt ? "rvt" : null,
      placeholder: rvt ? "(Verify ...)" : "Text, as reStructuredText",
      keys: [{ key: "Mod-Enter", run: done }, { key: "Escape", run: done }]
        .concat(rvt && consoleOn ? [{ key: "Shift-Enter", run: function (v) { return runAtCursor(card, v); } }] : []),
      extensions: [window.CM.autocompletion({ override: [completions(card)] }), window.CM.hoverTooltip(hovers(card))],
      onMove: rvt ? function (moved) { clearTimeout(signing); signing = setTimeout(function () { sign(card, moved, signature); }, 150); } : null,
      onChange: function () {  // the language server checks what is typed, once typing pauses
        clearTimeout(typing);
        typing = setTimeout(function () { if (card._edit && states[path]) lspSync(path); }, 300);
      },
    });
    card._edit = { view: view, element: edit, isNew: !!isNew };
    view.focus();
    lspSync(path);
  }

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  // What a card being edited holds right now, as an edited card. `typed`
  // keeps the spaces at the end, so a place in the editor is the same
  // place in the file the language server is sent.
  function current(card, typed) {
    var data = card._card;
    var text = card._edit.view.state.doc.toString();
    if (typed) text = text.replace(/\n+$/, "") + " ";
    var next = { kind: data.kind, source: null, index: null, level: data.level || 0 };
    if (data.kind === "rvt") {
      next.code = typed ? text : text.replace(/\s+$/, "");
      next.title = data.title || null;
      next.definitions = !!data.definitions;
      next.table = !!data.table;
      next.variations = data.variations || [];
    } else {
      next.text = typed ? text : text.replace(/\s+$/, "");
    }
    return next;
  }

  function shownOf(data) {
    return data.kind === "rvt" ? [data.code || "", data.title || null, !!data.definitions, !!data.table, data.variations || []]
      : data.kind === "variant" ? [data.variations || []] : [data.text || ""];
  }

  // Draw a card again from what it is now
  function redraw(card) {
    var path = pathOf(card), doc = docOf(path), view = viewOf(card), data = card._card;
    if (data.kind === "variant") { view.innerHTML = variantHead(data.variations || []); return Promise.resolve(); }
    return post(base + "/editor/render", { card: data, plain: doc.dataset.plain === "true" })
      .then(function (response) { return response.ok ? response.json() : Promise.reject(); })
      .then(function (found) { view.innerHTML = found.html; })
      .catch(function () {
        view.textContent = "";
        view.appendChild(el("pre", "ui-pre", data.kind === "rvt" ? data.code : data.text));
      })
      .then(function () { if (states[path]) keepDraft(path); });
  }

  // Change something of a card that isn't its text: a block's title, its
  // variations, what kind of block it is
  function change(card, patch) {
    var path = pathOf(card);
    remember(path);
    card._card = Object.assign({}, card._card, patch, { source: null });
    if (!isVariant(card)) card._card.index = null;
    touch(card);
    dirty(path);
    return redraw(card);
  }

  // Close a card's editor; with `commit`, keep what it holds
  function closeCard(card, commit) {
    var edit = card._edit, path = pathOf(card);
    if (!edit) return Promise.resolve();
    var data = card._card, next = current(card);
    var changed = !same(shownOf(data), shownOf(next));
    var empty = data.kind !== "rvt" && !next.text.trim();
    setTimeout(function () { if (states[path]) { lspSync(path); empties(docOf(path)); } }, 0);
    if ((!commit || empty) && edit.isNew) { finish(card); card.remove(); return Promise.resolve(); }
    if (!commit || !changed) { finish(card); return Promise.resolve(); }
    remember(path);
    finish(card);
    if (empty) { touch(card); card.remove(); dirty(path); return Promise.resolve(); }
    card._card = next;
    delete card.dataset.edRan;
    touch(card);
    dirty(path);
    return redraw(card);
  }

  // Take a card's editor away
  function finish(card) {
    var edit = card._edit;
    if (edit.view) edit.view.destroy();
    edit.element.remove();
    card._edit = null;
    card.classList.remove("is-editing");
  }

  // A new card in `container`, before `before` (null: at its end), open
  function addCard(container, before, kind) {
    var data = kind === "rvt"
      ? { kind: "rvt", source: null, index: null, code: "", title: null, definitions: false, table: false, variations: [] }
      : { kind: "prose", source: null, index: null, text: "", level: 0 };
    var card = section(data, "");
    container.insertBefore(card, before || $(":scope > .ed-empty", container));
    decorate(card);
    touch(card);
    empties(card.closest("[data-ed-doc]"));
    openCard(card, true);
  }

  // A title changed where it shows: a block's, or a section's heading

  var ADORNMENT = /^([=\-~`#"^+*:.'_])\1+\s*$/;

  // A section's text under another heading
  function retitle(text, title) {
    var lines = text.replace(/^\n+/, "").split("\n");
    var size = ADORNMENT.test(lines[0]) ? 3 : 2;
    var bar = lines[size - 1][0].repeat(Math.max(title.length, 3));
    return (size === 3 ? [bar, title, bar] : [title, bar]).concat(lines.slice(size)).join("\n");
  }

  function editTitle(card) {
    var data = card._card, view = viewOf(card), rvt = data.kind === "rvt";
    if (card._edit || $(".ed-inline", card)) return;
    var shown = rvt ? $("details.titled > summary strong", view) : $(".ed-heading", view);
    if (!rvt && !shown) return;
    closeMenu();
    var input = el("input", "ed-inline" + (rvt ? " ed-inline--block" : " ed-inline--h" + (data.level || 2)));
    input.value = rvt ? data.title || "" : shown.textContent;
    input.placeholder = rvt ? "What these steps do" : "Heading";
    input.setAttribute("aria-label", rvt ? "Block title" : "Heading");
    if (rvt) {
      view.insertBefore(input, view.firstChild);
      view.classList.add("is-titling");
    } else {
      shown.hidden = true;
      shown.parentNode.insertBefore(input, shown);
    }
    var over = false;
    function end(commit) {
      if (over) return;
      over = true;
      var value = input.value.trim().split(/\s+/).filter(Boolean).join(" ");
      input.remove();
      view.classList.remove("is-titling");
      if (shown) shown.hidden = false;
      if (!commit) return;
      if (rvt && value !== (data.title || "")) change(card, { title: value || null });
      else if (!rvt && value && value !== shown.textContent) change(card, { text: retitle(data.text, value) });
    }
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); end(true); }
      else if (event.key === "Escape") { event.preventDefault(); end(false); }
    });
    input.addEventListener("blur", function () { end(true); });
    input.focus();
    input.select();
  }

  // A card's menu, from ".." in its gutter

  var pop = null;

  function closeMenu() {
    if (!pop) return;
    if (pop._card) pop._card.classList.remove("has-menu");
    pop.remove();
    pop = null;
  }

  // Which variations a card is only for: every one unless some are picked
  function onlyFor(card, names) {
    var box = el("div", "ed-only");
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Only for these variations");
    var variant = isVariant(card);
    function chosen() { return (card._card.variations || []).filter(function (n) { return names.indexOf(n) >= 0; }); }
    function draw() {
      var now = chosen();
      all("button", box).forEach(function (b) {
        var on = b.dataset.name ? now.indexOf(b.dataset.name) >= 0 : !now.length;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }
    function chip(label, name) {
      var b = el("button", "ed-only__chip", label);
      b.type = "button";
      b.dataset.name = name;
      b.addEventListener("click", function () {
        var now = chosen(), at = now.indexOf(name);
        if (!name) now = [];
        else if (at >= 0) now.splice(at, 1);
        else now.push(name);
        if (variant && !now.length) return;  // a variant is for some
        now = names.filter(function (n) { return now.indexOf(n) >= 0; });  // as the script declares them
        change(card, { variations: now }).then(draw);
        draw();
      });
      box.appendChild(b);
    }
    if (!variant) chip("All", "");
    names.forEach(function (name) { chip(name, name); });
    draw();
    return box;
  }

  function openMenu(card) {
    var again = pop && pop._card === card;
    closeMenu();
    if (again) return;
    (card._edit ? closeCard(card, true) : Promise.resolve()).then(function () {
      if (!card.isConnected) return;
      var doc = card.closest("[data-ed-doc]"), data = card._card, names = declared(doc);
      var rvt = data.kind === "rvt", variant = isVariant(card);
      pop = el("div", "ed-pop");
      pop._card = card;
      pop.setAttribute("role", "menu");
      function item(text, act, checked) {
        var b = el("button", "ed-pop__item" + (act === "delete" ? " is-danger" : ""), text);
        b.type = "button";
        b.dataset.edAct = act;
        b.setAttribute("role", checked == null ? "menuitem" : "menuitemcheckbox");
        if (checked != null) b.setAttribute("aria-checked", checked ? "true" : "false");
        pop.appendChild(b);
      }
      function rule() { pop.appendChild(el("div", "ed-pop__rule")); }
      function heading(text) { pop.appendChild(el("div", "ed-pop__label", text)); }
      heading("Add below");
      var add = el("div", "ed-pop__row");
      add.appendChild(button("Text", "add-prose", "ui-btn--secondary"));
      add.appendChild(button("Steps", "add-rvt", "ui-btn--secondary"));
      add.appendChild(el("span", "ui-spacer"));
      add.appendChild(button("Text above", "add-prose-above", "ui-btn--ghost"));
      add.appendChild(button("Steps above", "add-rvt-above", "ui-btn--ghost"));
      pop.appendChild(add);
      rule();
      if (!variant) item(rvt ? "Edit the steps" : "Edit the text", "edit");
      if (rvt) {
        item(data.title ? "Rename" : "Give it a title", "title");
        item("Only definitions", "toggle-definitions", !!data.definitions);
        item("A table of rows", "toggle-table", !!data.table);
      } else if (data.kind === "prose" && $(".ed-heading", viewOf(card))) {
        item("Rename the heading", "title");
      }
      if (names.length && (rvt || variant)) {
        heading("Only for");
        pop.appendChild(onlyFor(card, names));
      }
      rule();
      if (variant) item("Take out of the variant", "unwrap");
      else if (names.length) item("Put in a variant", "wrap");
      item("Move up", "up");
      item("Move down", "down");
      rule();
      item(variant ? "Delete, with what it holds" : "Delete", "delete");
      document.body.appendChild(pop);
      card.classList.add("has-menu");
      var anchor = $(":scope > .ed-gutter [data-ed-menu]", card) || viewOf(card);
      var at = anchor.getBoundingClientRect();
      var left = Math.min(at.left, window.innerWidth - pop.offsetWidth - 12);
      var top = at.bottom + 4;
      if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, at.top - pop.offsetHeight - 4);
      pop.style.left = (window.scrollX + Math.max(left, 8)) + "px";
      pop.style.top = (window.scrollY + top) + "px";
      var first = $("button", pop);
      if (first) first.focus({ preventScroll: true });
    });
  }

  // Variants, cards moved

  // Put a card in a new variant, then ask which variations it is for
  function wrap(card) {
    var path = pathOf(card), names = declared(card.closest("[data-ed-doc]"));
    remember(path);
    var chosen = names.slice(0, 1);
    var variant = section({ kind: "variant", source: null, index: null, variations: chosen, count: 0, indent: 0 }, variantHead(chosen));
    card.parentNode.insertBefore(variant, card);
    touch(variant);
    bodyOf(variant).appendChild(card);
    card._card = Object.assign({}, card._card, { index: null });
    decorate(variant);
    dirty(path);
    openMenu(variant);
  }

  // Take what a variant holds out of it, where it was
  function unwrap(variant) {
    cardsOf(bodyOf(variant)).forEach(function (card) { moveCard(card, variant.parentNode, variant); });
    touch(variant);
    variant.remove();
  }

  // A card one step up or down: past its neighbour, into a variant next
  // to it, or out of the variant it is in at either end
  function step(card, up) {
    var container = card.parentNode, siblings = cardsOf(container), at = siblings.indexOf(card);
    var next = siblings[at + (up ? -1 : 1)];
    if (next && isVariant(next)) {
      var kids = cardsOf(bodyOf(next));
      moveCard(card, bodyOf(next), up ? null : kids[0] || null);
    } else if (next) {
      container.insertBefore(card, up ? next : next.nextSibling);
      touch(card);
    } else if (container.classList.contains("ed-variant__body")) {
      var variant = container.parentNode;
      moveCard(card, variant.parentNode, up ? variant : variant.nextSibling);
    } else {
      return false;
    }
    return true;
  }

  // Dragging a card by its grip, with the pointer

  var drag = null;

  function dropTarget(x, y) {
    var under = document.elementFromPoint(x, y);
    var doc = drag.card.closest("[data-ed-doc]");
    if (!under || !doc.contains(under) || drag.card.contains(under)) return null;
    var card = under.closest(".ed-card");
    if (card && drag.card.contains(card)) return null;
    var body = under.closest(".ed-variant__body");
    if (card && body && !body.contains(card)) card = null;
    if (!card) {  // empty space: the end of the variant or the document under it
      var container = body || doc;
      if (drag.card.contains(container)) return null;
      return { container: container, before: null };
    }
    var box = viewOf(card).getBoundingClientRect(), upper = y < box.top + box.height / 2;
    if (isVariant(card) && !upper && y < box.bottom) {
      return { container: bodyOf(card), before: cardsOf(bodyOf(card))[0] || null };  // into it, at its top
    }
    if (!upper) {
      var whole = card.getBoundingClientRect();
      if (isVariant(card) && y < whole.bottom - 8) return { container: bodyOf(card), before: null };
    }
    return { container: card.parentNode, before: upper ? card : card.nextSibling };
  }

  function dragMove(event) {
    if (!drag) return;
    if (!drag.moved && Math.abs(event.clientY - drag.y) + Math.abs(event.clientX - drag.x) < 4) return;
    drag.moved = true;
    drag.card.classList.add("is-dragging");
    var target = dropTarget(event.clientX, event.clientY);
    if (!target) { drag.line.remove(); drag.target = null; return; }
    var before = target.before;
    while (before && before !== drag.line && !isCard(before)) before = before.nextSibling;
    if (drag.line.parentNode !== target.container || drag.line.nextSibling !== before) target.container.insertBefore(drag.line, before);
    drag.target = target;
  }

  function dragEnd(event) {
    if (!drag) return;
    var current = drag;
    drag = null;
    document.removeEventListener("pointermove", dragMove);
    document.removeEventListener("pointerup", dragEnd);
    document.removeEventListener("keydown", dragCancel, true);
    current.card.classList.remove("is-dragging");
    var line = current.line, container = line.parentNode;
    if (event && current.moved && container) {
      var before = cardFrom(line.nextSibling), path = pathOf(current.card);
      line.remove();
      var siblings = cardsOf(container), now = siblings.indexOf(current.card);
      var where = before === null ? siblings.length : siblings.indexOf(before);
      var stays = now >= 0 && (where === now || where === now + 1);  // dropped where it is
      if (!stays) {
        remember(path);
        moveCard(current.card, container, before);
        dirty(path);
      }
    }
    line.remove();
  }

  function dragCancel(event) {
    if (event.key === "Escape" && drag) { event.preventDefault(); drag.moved = false; dragEnd(null); }
  }

  function dragStart(event, grip) {
    var card = grip.closest(".ed-card");
    if (!card || card._edit || event.button !== 0) return;
    event.preventDefault();
    drag = { card: card, x: event.clientX, y: event.clientY, moved: false, line: el("div", "ed-drop"), target: null };
    document.addEventListener("pointermove", dragMove);
    document.addEventListener("pointerup", dragEnd);
    document.addEventListener("keydown", dragCancel, true);
  }

  // Saving: resolves true when the file on disk is the tab's

  function save(path, force) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc) return Promise.resolve(false);
    if (!st.dirty) return Promise.resolve(true);
    var closing = editing(doc).map(function (card) { return closeCard(card, true); });
    return Promise.all(closing).then(function () {
      say("Saving");
      return post(url(path, "editor/save"), {
        hash: st.baseHash, count: st.count, force: !!force,
        cards: cardsOf(doc).map(function (c) { return dataOf(c); }),
      });
    }).then(function (response) {
      if (response.status === 409) {
        st.conflict = true;
        showConflict(path);
        say("Not saved: the file changed on disk");
        return false;
      }
      if (!response.ok) { say("Couldn't save (" + response.status + ")"); return false; }
      dropDraft(path);
      st.dirty = false;
      if (st.isNew) refreshTree();
      return load(path).then(function () { if (active === path) say("Saved"); return true; });
    }).catch(function () { say("Couldn't save: the server didn't answer"); return false; });
  }

  function discard(path) {
    dropDraft(path);
    if (states[path].isNew) { closeTab(path); return Promise.resolve(); }  // it was never a file
    states[path].dirty = false;
    return load(path).then(function () { say("Edits discarded"); });
  }

  // Run in scratch runs what is on disk: save first, and offer to save the
  // other unsaved files the script loads

  function runSaved(form) {
    var path = pathOf(form);
    var closure = [];
    try { closure = JSON.parse(form.dataset.closure || "[]"); } catch (e) { closure = []; }
    var unsaved = closure.filter(function (p) { return states[p] && states[p].dirty; });
    if (path && states[path] && states[path].dirty && unsaved.indexOf(path) < 0) unsaved.push(path);
    if (!unsaved.length) return false;
    var copy = form.cloneNode(true);  // the pane is redrawn by a save; this one stays
    copy.hidden = true;
    copy.removeAttribute("data-ed-run");
    all("select", form).forEach(function (select) { var twin = $('[name="' + select.name + '"]', copy); if (twin) twin.value = select.value; });
    function run(paths) {
      return paths.reduce(function (done, p) {
        return done.then(function (ok) { return ok && save(p); });
      }, Promise.resolve(true)).then(function (ok) {
        if (!ok) { say("Not run: a file couldn't be saved"); return; }
        document.body.appendChild(copy);
        copy.submit();
      });
    }
    var others = unsaved.filter(function (p) { return p !== path; });
    if (!others.length) { run([path]); return true; }
    var dialog = $("#ed-dialog");
    dialog.textContent = "";
    var box = el("form", "ui-form ed-dialog__form");
    box.appendChild(el("h2", "ed-dialog__title", "Save before running?"));
    box.appendChild(el("p", null, "A run uses the files on disk. These files it loads have unsaved edits:"));
    var list = el("ul", "ed-dialog__list");
    others.forEach(function (p) { list.appendChild(el("li", "ui-mono", p)); });
    box.appendChild(list);
    var row = el("div", "ui-row ed-dialog__foot");
    var both = el("button", "ui-btn ui-btn--primary", "Save them all and run");
    both.type = "submit";
    var only = el("button", "ui-btn ui-btn--secondary", path && states[path].dirty ? "Save only this script" : "Run without them");
    only.type = "button";
    var cancel = el("button", "ui-btn ui-btn--secondary", "Cancel");
    cancel.type = "button";
    row.appendChild(both);
    row.appendChild(only);
    row.appendChild(cancel);
    box.appendChild(row);
    box.addEventListener("submit", function (event) { event.preventDefault(); dialog.close(); run(unsaved); });
    only.addEventListener("click", function () { dialog.close(); run(states[path] && states[path].dirty ? [path] : []); });
    cancel.addEventListener("click", function () { dialog.close(); });
    dialog.appendChild(box);
    dialog.showModal();
    return true;
  }

  // The file changed on disk under a tab

  function checkDisk(path) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc || !editable || st.checking) return;
    st.checking = true;
    fetch(url(path, "editor/state")).then(function (r) { return r.ok ? r.json() : null; }).then(function (found) {
      st.checking = false;
      doc = docOf(path);
      if (!found || !doc || (found.hash || "") === doc.dataset.hash) return;
      if (!st.dirty && !editing(doc).length) { load(path); return; }
      doc.dataset.hash = found.hash || "";
      st.conflict = true;
      showConflict(path);
    }).catch(function () { st.checking = false; });
  }

  function showConflict(path) {
    var st = states[path];
    var bar = $(":scope > .ed-conflict", st.pane);
    if (bar) bar.remove();
    bar = el("div", "ed-conflict");
    var row = el("div", "ed-conflict__row");
    row.appendChild(el("strong", null, "This file changed on disk"));
    row.appendChild(el("span", null, "since you started editing it. Your edits aren't saved."));
    row.appendChild(el("span", "ui-spacer"));
    row.appendChild(button("See the difference", "conflict-diff"));
    row.appendChild(button("Take the file's", "conflict-theirs", null, "Drop your edits and show the file as it is on disk"));
    row.appendChild(button("Keep mine", "conflict-mine", "ui-btn--primary", "Save your version over the file on disk"));
    bar.appendChild(row);
    st.pane.insertBefore(bar, st.pane.firstChild);
  }

  function showDifference(path) {
    var st = states[path], doc = docOf(path), bar = $(":scope > .ed-conflict", st.pane);
    post(url(path, "editor/diff"), { count: st.count, cards: cardsOf(doc).map(function (c) { return dataOf(c); }) })
      .then(function (r) { return r.json(); }).then(function (found) {
        var old = $("pre", bar);
        if (old) old.remove();
        var pre = el("pre", "ui-pre ui-diff-lines");
        if (!found.lines.length) pre.textContent = "Your version and the file on disk are the same.";
        found.lines.forEach(function (line) {
          var kind = line[0] === "+" ? "is-added" : line[0] === "-" ? "is-removed" : line.slice(0, 2) === "@@" ? "is-hunk" : "";
          pre.appendChild(el("span", kind, line || " "));
        });
        bar.appendChild(pre);
      });
  }

  // Files: new, clone, rename or move, delete, new folder

  function refreshTree() {
    if (window.htmx) window.htmx.ajax("GET", base + "/tree", { target: "#treeview", swap: "innerHTML" });
  }
  function folderOf(path) { return path ? path.split("/").slice(0, -1).join("/") : ""; }
  function fileName(title) {
    var name = title.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    return (name || "script") + ".rst";
  }

  function labelled(text, input, hint) {
    var wrap = el("label", "ui-field");
    wrap.appendChild(el("span", "ui-field__label", text));
    wrap.appendChild(input);
    if (hint) wrap.appendChild(el("span", "ui-field__hint ui-muted", hint));
    return wrap;
  }
  function textInput(name, value, mono) {
    var input = el("input", "ui-input" + (mono ? " ui-input--mono" : ""));
    input.name = name;
    input.value = value || "";
    input.autocomplete = "off";
    return input;
  }
  function folderSelect(folders, chosen) {
    var select = el("select", "ui-select ui-select--mono");
    select.name = "folder";
    folders.forEach(function (folder) {
      var option = el("option", null, folder || "(the workspace's top folder)");
      option.value = folder;
      option.selected = folder === chosen;
      select.appendChild(option);
    });
    return select;
  }

  // What each dialog asks, and what happens with the server's answer
  var DIALOGS = {
    "new": {
      title: "New script", go: "Create", to: "new",
      note: "It opens as a tab with unsaved edits: nothing is written until you save.",
      fields: function (form, o) {
        var title = textInput("title", ""), name = textInput("name", "", true);
        title.required = true;
        name.placeholder = "from the title";
        title.addEventListener("input", function () { if (!name._typed) name.value = title.value.trim() ? fileName(title.value) : ""; });
        name.addEventListener("input", function () { name._typed = !!name.value; });
        form.appendChild(labelled("Title", title));
        form.appendChild(labelled("File name", name));
        form.appendChild(labelled("Folder", folderSelect(o.folders, o.folder)));
        if (o.requirement) {
          var req = textInput("requirement", o.requirement, true);
          form.appendChild(labelled("Verifies", req, "Its text starts the script, and it goes in the Requirements section."));
        }
      },
      done: function (found) { putDraft(found.path, { hash: "", count: found.count, cards: found.cards }); open(found.path); },
    },
    "clone": {
      title: "Clone", go: "Clone", to: "clone",
      note: "The copy opens as a tab with unsaved edits, requirements and all: nothing is written until you save.",
      fields: function (form, o) {
        var title = textInput("title", o.title ? o.title + " (copy)" : ""), name = textInput("name", fileName(o.title ? o.title + " copy" : ""), true);
        title.required = true;
        title.addEventListener("input", function () { if (!name._typed) name.value = fileName(title.value); });
        name.addEventListener("input", function () { name._typed = !!name.value; });
        form.appendChild(labelled("Title of the copy", title));
        form.appendChild(labelled("File name", name));
        form.appendChild(labelled("Folder", folderSelect(o.folders, o.folder)));
      },
      body: function (o) { return { from: o.path }; },
      done: function (found) { putDraft(found.path, { hash: "", count: found.count, cards: found.cards }); open(found.path); },
    },
    "move": {
      title: "Rename or move", go: "Rename", to: "move",
      note: "Reports that already ran it keep the name it had then.",
      fields: function (form, o) {
        var name = textInput("name", o.path.split("/").pop(), true);
        name.required = true;
        form.appendChild(labelled("File name", name));
        form.appendChild(labelled("Folder", folderSelect(o.folders, o.folder)));
      },
      body: function (o) { return { from: o.path }; },
      done: function (found, o) {
        var kept = draft(o.path);
        if (kept) { dropDraft(o.path); putDraft(found.path, kept); }
        closeTab(o.path);
        open(found.path);
        refreshTree();
      },
    },
    "delete": {
      title: "Delete", go: "Delete", to: "delete", danger: true, folders: false,
      fields: function (form, o) {
        form.appendChild(el("p", null, "Delete " + o.path + " from the worktree? If it was committed, git can bring it back."));
      },
      body: function (o) { return { path: o.path }; },
      done: function (found, o) { dropDraft(o.path); closeTab(o.path); refreshTree(); },
    },
    "folder": {
      title: "New folder", go: "Create", to: "folder",
      fields: function (form, o) {
        var name = textInput("name", "", true);
        name.required = true;
        form.appendChild(labelled("Name", name));
        form.appendChild(labelled("In", folderSelect(o.folders, o.folder)));
        var box = el("label", "ed-fields__flag"), core = el("input");
        core.type = "checkbox";
        core.name = "core";
        box.appendChild(core);
        box.appendChild(document.createTextNode(" With a core.rst, for definitions its scripts share"));
        form.appendChild(box);
      },
      done: function () { refreshTree(); },
    },
  };

  function fileDialog(kind, options) {
    var spec = DIALOGS[kind], dialog = $("#ed-dialog");
    if (!spec || !dialog) return;
    var o = Object.assign({ path: active, folder: folderOf(active) }, options || {});
    var heading = o.path && states[o.path] ? $(".ed-heading", states[o.path].pane) : null;
    o.title = heading ? heading.textContent.trim() : "";
    var ready = spec.folders === false ? Promise.resolve({ folders: [] })
      : fetch(base + "/editor/folders").then(function (r) { return r.json(); });
    ready.then(function (found) {
      o.folders = found.folders;
      dialog.textContent = "";
      var form = el("form", "ui-form ed-dialog__form");
      form.appendChild(el("h2", "ed-dialog__title", spec.title + (kind === "new" || kind === "folder" ? "" : " " + o.path)));
      spec.fields(form, o);
      if (spec.note) form.appendChild(el("p", "ui-muted ed-dialog__note", spec.note));
      var error = el("div", "ed-unreadable");
      error.hidden = true;
      form.appendChild(error);
      var row = el("div", "ui-row ed-dialog__foot");
      var go = el("button", "ui-btn " + (spec.danger ? "ui-btn--danger" : "ui-btn--primary"), spec.go);
      go.type = "submit";
      var cancel = el("button", "ui-btn ui-btn--secondary", "Cancel");
      cancel.type = "button";
      cancel.addEventListener("click", function () { dialog.close(); });
      row.appendChild(go);
      row.appendChild(cancel);
      form.appendChild(row);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var body = spec.body ? spec.body(o) : {};
        all("input, select", form).forEach(function (input) {
          if (input.name) body[input.name] = input.type === "checkbox" ? input.checked : input.value;
        });
        go.disabled = true;
        post(base + "/editor/" + spec.to, body).then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (found) {
            go.disabled = false;
            if (!response.ok) {
              error.textContent = found.error || "That didn't work (" + response.status + ").";
              error.hidden = false;
              return;
            }
            dialog.close();
            spec.done(found, o);
          });
        }).catch(function () { go.disabled = false; error.textContent = "The server didn't answer."; error.hidden = false; });
      });
      dialog.appendChild(form);
      dialog.showModal();
      var first = $("input:not([type=checkbox]), select", form);
      if (first) first.focus();
    });
  }

  // Events

  function act(name, target) {
    var inMenu = pop && pop.contains(target);
    var card = inMenu ? pop._card : target.closest(".ed-card"), path = pathOf(card || target);
    var stays = name === "toggle-definitions" || name === "toggle-table";
    if (inMenu && !stays) closeMenu();
    if (name === "edit") openCard(card);
    else if (name === "done") closeCard(card, true);
    else if (name === "cancel") closeCard(card, false);
    else if (name === "title") editTitle(card);
    else if (stays) {
      var key = name.slice(7), on = !card._card[key], patch = {};
      patch[key] = on;
      target.setAttribute("aria-checked", on ? "true" : "false");
      change(card, patch);
    }
    else if (name === "delete") {
      if (card._edit) closeCard(card, false);
      remember(path);
      touch(card);
      card.remove();
      dirty(path);
    }
    else if (name === "up" || name === "down") {
      remember(path);
      if (step(card, name === "up")) dirty(path); else states[path].undo.pop();
    }
    else if (name === "wrap") wrap(card);
    else if (name === "unwrap") { remember(path); unwrap(card); dirty(path); }
    else if (name.indexOf("add-") === 0) {
      var kind = name.indexOf("rvt") >= 0 ? "rvt" : "prose";
      var offer = target.closest(".ed-empty");
      if (offer) addCard(offer.parentNode, null, kind);
      else addCard(card.parentNode, /-above$/.test(name) ? card : cardFrom(card.nextSibling), kind);
    }
    else if (name === "conflict-diff") showDifference(path);
    else if (name === "conflict-theirs") discard(path);
    else if (name === "conflict-mine") save(path, true);
  }

  function onClick(event) {
    var target = event.target;
    if (pop && pop.contains(target)) {  // the card menu, which isn't in the editor's element
      var chosen = target.closest("[data-ed-act]");
      if (chosen) act(chosen.dataset.edAct, chosen);
      return;
    }
    var opener = target.closest("[data-ed-menu]");
    if (opener) { openMenu(opener.closest(".ed-card")); return; }
    var play = target.closest("[data-ed-play]");
    if (play) { closeMenu(); runCard(play.closest(".ed-card")); return; }
    if (target.closest("[data-ed-console]")) { consoleOpenPanel(); return; }
    closeMenu();
    var row = target.closest(".ui-tree__row--file[data-open]");
    if (row) { open(row.dataset.open); return; }
    var menu = $(".ed-menu[open]");
    if (menu && !target.closest(".ed-menu > summary")) menu.open = false;
    var file = target.closest("[data-ed-file]");
    if (file) { fileDialog(file.dataset.edFile); return; }
    if (!root.contains(target)) return;
    var tab = target.closest("[data-ed-tab]"), close = target.closest("[data-ed-close]");
    if (close) { closeTab(close.dataset.edClose); return; }
    if (tab) { activate(tab.dataset.edTab); return; }
    if (target.closest("[data-ed-save]")) { save(active); return; }
    if (target.closest("[data-ed-undo]")) { undo(active); return; }
    if (target.closest("[data-ed-redo]")) { undo(active, true); return; }
    if (target.closest("[data-ed-problems]")) {
      var panel = $(".ed-problems", root);
      panel.hidden = !panel.hidden;
      drawProblems();
      return;
    }
    var shown = target.closest("[data-ed-reveal]");
    if (shown) { reveal(shown.dataset.edReveal, Number(shown.dataset.line)); return; }
    var drop = target.closest("[data-ed-discard]");
    if (drop) {
      if (drop.dataset.sure) discard(active);
      else { drop.dataset.sure = "1"; drop.textContent = "Discard them?"; setTimeout(drawActions, 4000); }
      return;
    }
    var button = target.closest("[data-ed-act]");
    if (button) { act(button.dataset.edAct, button); return; }
    // A click on a card opens it, unless it is on something of its own or selects text
    var view = target.closest(".ed-card__view");
    if (!view || !editable) return;
    var doc = view.closest("[data-ed-doc]");
    if (!doc || doc.dataset.editable !== "true") return;
    if (target.closest("a, button, summary, input, select, textarea, label")) return;
    if (String(window.getSelection())) return;
    var card = view.parentNode;
    if ($(".ed-inline", card)) return;
    if (target.closest(".ed-heading")) {  // it may be the first click of two, to rename it
      clearTimeout(opening);
      opening = setTimeout(function () { if (card.isConnected && !$(".ed-inline", card)) openCard(card); }, 280);
      return;
    }
    openCard(card);
  }

  var opening;  // a click on a heading, waiting to see if it is a double click

  // Double click a title to change it in place
  function onDoubleClick(event) {
    var target = event.target;
    if (!editable || !target.closest) return;
    var title = target.closest(".ed-heading, details.titled > summary strong");
    var view = title && title.closest(".ed-card__view");
    var doc = view && view.closest("[data-ed-doc]");
    if (!doc || doc.dataset.editable !== "true" || doc.dataset.plain === "true") return;
    var card = view.parentNode;
    if (title.closest(".ed-card") !== card) return;
    event.preventDefault();
    clearTimeout(opening);
    editTitle(card);
  }

  function typingIn(target) {
    return target.closest && target.closest("input, textarea, select, .cm-editor, dialog, [contenteditable]");
  }

  function onKey(event) {
    if (!active || !editable) return;
    var key = event.key.toLowerCase(), mod = event.ctrlKey || event.metaKey;
    if (key === "escape" && pop) { closeMenu(); return; }
    if (mod && key === "s") { event.preventDefault(); save(active); return; }
    if (!mod || typingIn(event.target)) return;
    if (key === "z" && !event.shiftKey) { event.preventDefault(); undo(active); }
    else if ((key === "z" && event.shiftKey) || key === "y") { event.preventDefault(); undo(active, true); }
  }


  // The console (web/console.py): a kernel on this machine, kept between
  // commands. A card's ▶ runs the card; Shift+Enter in a card's editor runs
  // the form at the cursor, or the selection; the prompt runs what is typed.
  //
  // While it is open the page is a workbench: full width and window high,
  // the cards above and the console below, split by a handle. The console
  // has the transcript and the prompt, and a side pane with the history of
  // what was run (kept in this browser, per workspace) and the names in the
  // console's scope. The transcript is the kernel's: the page asks for the
  // lines after the last it has while the kernel is busy.

  var con = null;  // the panel's parts and state, once it is made
  var HISTORY_KEPT = 200;

  function consoleBase() { return base + "/console"; }
  function stored(key, fallback) {
    try { var v = localStorage.getItem("ed-console:" + key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  }
  function store(key, value) {
    try { localStorage.setItem("ed-console:" + key, JSON.stringify(value)); } catch (e) { /* this page only */ }
  }

  function consoleStart() {
    fetch(consoleBase()).then(function (r) { return r.ok ? r.json() : null; }).then(function (found) {
      if (found && found.state && found.state.workspace === ws) {
        consolePanel();
        consoleState(found.state);
        consoleShow(stored("open", true));
        consolePoll(true);
      }
    }).catch(function () { /* no console now */ });
    window.addEventListener("focus", function () { if (con && con.state) consolePoll(true); });
  }

  function conButton(label, name, title, cls) {
    var b = el("button", "ui-btn ui-btn--sm " + (cls || "ui-btn--ghost"), label);
    b.type = "button";
    b.dataset.con = name;
    if (title) b.title = title;
    return b;
  }

  function consolePanel() {
    if (con) return con;
    var panel = el("section", "ed-console");
    panel.setAttribute("aria-label", "Console");
    var grip = el("div", "ed-console__grip");
    grip.setAttribute("role", "separator");
    grip.setAttribute("aria-orientation", "horizontal");
    grip.title = "Drag to give the console more or less of the window";
    var head = el("header", "ed-console__head");
    var toggle = el("button", "ed-console__toggle", "Console");
    toggle.type = "button";
    toggle.dataset.con = "toggle";
    toggle.setAttribute("aria-expanded", "true");
    var what = el("span", "ed-console__what ui-mono");
    var status = el("span", "ed-console__status");
    status.setAttribute("aria-live", "polite");
    var held = el("span", "ed-console__held");
    var tools = el("span", "ed-console__tools");
    tools.appendChild(conButton("Stop", "stop", "Stop the command running, and drop the ones waiting"));
    tools.appendChild(conButton("Reset", "reset", "Release what is held and load the definitions again; the UUT is left as it is"));
    tools.appendChild(conButton("Restart", "restart", "Reset, and start the UUT fresh"));
    tools.appendChild(conButton("Clear", "clear", "Empty the transcript"));
    tools.appendChild(conButton("Close", "close", "Close the console: what is held is released, and the local worker takes jobs again"));
    [toggle, what, status, held, tools].forEach(function (x) { head.appendChild(x); });

    var main = el("div", "ed-console__main");
    var body = el("div", "ed-console__body");
    var opening = el("div", "ed-console__opening");
    opening.hidden = true;
    var scroll = el("div", "ed-console__scroll");
    var list = el("ol", "ed-console__lines");
    scroll.appendChild(list);
    var prompt = el("div", "ed-console__prompt");
    prompt.appendChild(el("span", "ed-console__mark", "»"));
    var holder = el("div", "ed-console__input");
    prompt.appendChild(holder);
    body.appendChild(opening);
    body.appendChild(scroll);
    body.appendChild(prompt);

    var vgrip = el("div", "ed-console__vgrip");
    vgrip.setAttribute("role", "separator");
    vgrip.setAttribute("aria-orientation", "vertical");
    vgrip.title = "Drag to resize the side pane";
    var side = el("aside", "ed-console__side");
    var tabs = el("div", "ed-console__tabs");
    tabs.setAttribute("role", "tablist");
    [["History", "history"], ["Names", "names"]].forEach(function (t) {
      var b = el("button", "ed-console__tab", t[0]);
      b.type = "button";
      b.dataset.conTab = t[1];
      b.setAttribute("role", "tab");
      tabs.appendChild(b);
    });
    var history = el("div", "ed-console__pane ed-history");
    var historyHead = el("div", "ed-console__pane-head");
    historyHead.appendChild(el("span", "ui-muted", "Kept in this browser"));
    historyHead.appendChild(conButton("Clear history", "clear-history", "Forget what was run here"));
    var historyList = el("ol", "ed-history__list");
    history.appendChild(historyHead);
    history.appendChild(historyList);
    var names = el("div", "ed-console__pane ed-names");
    var namesHead = el("div", "ed-console__pane-head");
    var filter = el("input", "ui-input ui-input--sm ed-names__filter");
    filter.type = "search";
    filter.placeholder = "Filter names";
    filter.setAttribute("aria-label", "Filter names");
    namesHead.appendChild(filter);
    var namesList = el("div", "ed-names__list");
    names.appendChild(namesHead);
    names.appendChild(namesList);
    side.appendChild(tabs);
    side.appendChild(history);
    side.appendChild(names);
    main.appendChild(body);
    main.appendChild(vgrip);
    main.appendChild(side);

    panel.appendChild(grip);
    panel.appendChild(head);
    panel.appendChild(main);
    root.appendChild(panel);
    main.style.height = stored("height", 300) + "px";
    side.style.width = stored("side", 340) + "px";
    con = { panel: panel, head: head, main: main, body: body, scroll: scroll, list: list, what: what,
            status: status, held: held, tools: tools, opening: opening, toggle: toggle,
            side: side, historyList: historyList, namesList: namesList, filter: filter,
            state: null, last: 0, cards: {}, entries: {}, polling: null, at: -1, names: [],
            history: stored("history:" + ws, []).filter(function (h) { return h && h.payload; }) };
    con.input = window.CM.editor(holder, {
      language: "rvt", placeholder: "A form to run: Enter runs it, Shift+Enter starts a new line, Up goes back",
      keys: [
        { key: "Enter", run: function (view) { promptRun(view); return true; } },
        { key: "Shift-Enter", run: function (view) { view.dispatch(view.state.replaceSelection("\n")); return true; } },
        { key: "ArrowUp", run: function (view) { return promptHistory(view, -1); } },
        { key: "ArrowDown", run: function (view) { return promptHistory(view, 1); } },
      ],
    });
    panel.addEventListener("click", consoleClick);
    grip.addEventListener("pointerdown", function (event) { dragSize(event, "height"); });
    vgrip.addEventListener("pointerdown", function (event) { dragSize(event, "side"); });
    filter.addEventListener("input", drawNames);
    sideTab(stored("tab", "history"));
    drawHistory();
    return con;
  }

  function consoleShow(open) {
    con.panel.hidden = false;
    con.main.hidden = !open;
    con.toggle.setAttribute("aria-expanded", String(open));
    document.documentElement.classList.add("ed-workbench");
    store("open", open);
    if (open) con.scroll.scrollTop = con.scroll.scrollHeight;
  }

  // Drag the split between the cards and the console, or between the
  // transcript and the side pane
  function dragSize(event, which) {
    event.preventDefault();
    var startX = event.clientX, startY = event.clientY;
    var startH = con.main.offsetHeight, startW = con.side.offsetWidth;
    document.documentElement.classList.add("ed-resizing");
    function move(e) {
      if (which === "height") {
        if (con.main.hidden) consoleShow(true);
        var h = Math.max(80, Math.min(window.innerHeight * 0.8, startH + startY - e.clientY));
        con.main.style.height = h + "px";
      } else {
        var w = Math.max(200, Math.min(con.main.offsetWidth * 0.6, startW + startX - e.clientX));
        con.side.style.width = w + "px";
      }
    }
    function up() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      document.documentElement.classList.remove("ed-resizing");
      if (which === "height") store("height", con.main.offsetHeight);
      else store("side", con.side.offsetWidth);
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
  }

  function sideTab(name) {
    all("[data-con-tab]", con.side).forEach(function (b) {
      var on = b.dataset.conTab === name;
      b.setAttribute("aria-selected", String(on));
    });
    $(".ed-history", con.side).hidden = name !== "history";
    $(".ed-names", con.side).hidden = name !== "names";
    store("tab", name);
    if (name === "names") fetchNames();
  }

  function consoleClick(event) {
    var target = event.target;
    var tab = target.closest("[data-con-tab]");
    if (tab) { sideTab(tab.dataset.conTab); return; }
    var hist = target.closest("[data-hist]");
    if (hist) { historyAct(hist.dataset.hist, hist.closest(".ed-hist")._entry); return; }
    var name = target.closest(".ed-name");
    if (name) { insertInPrompt(name.dataset.name); return; }
    var which = target.closest("[data-con]");
    if (which) {
      var act = which.dataset.con;
      if (act === "toggle") { consoleShow(con.main.hidden); return; }
      if (act === "clear-history") { con.history = []; store("history:" + ws, []); drawHistory(); return; }
      if (act === "clear") con.list.textContent = "";
      consoleControl(act);
      return;
    }
    var line = target.closest(".ed-cl");
    if (!line) return;
    if (line._more) { line.textContent = ""; line.appendChild(document.createTextNode(line._more)); line._more = null; return; }
    var card = line._card;
    if (card && card.isConnected) jumpTo(card, line._at || null);
  }

  function consoleControl(name) {
    return post(consoleBase() + "/" + name, {}).then(function (r) {
      return r.json().then(function (found) {
        if (!r.ok) { consoleSay(found.error || "The console couldn't " + name); return; }
        if (name === "close") { consoleClosed(); return; }
        consoleState(found.state);
        consolePoll(true);
      });
    });
  }

  function consoleClosed() {
    con.state = null;
    con.list.textContent = "";
    con.last = 0;
    con.names = [];
    drawNames();
    con.panel.hidden = true;
    document.documentElement.classList.remove("ed-workbench");
    all("[data-ed-ran]").forEach(function (card) { delete card.dataset.edRan; });
    all("[data-ed-running]").forEach(function (card) { delete card.dataset.edRunning; });
  }

  function consoleSay(text) {
    var line = el("li", "ed-cl ed-cl--fail", text);
    con.list.appendChild(line);
    con.scroll.scrollTop = con.scroll.scrollHeight;
  }

  // The header, from the kernel's state
  function consoleState(state) {
    var was = con.state;
    con.state = state;
    if (!state) { con.what.textContent = ""; con.status.textContent = "closed"; return; }
    var versions = Object.keys(state.versions || {}).map(function (k) { return k + " " + state.versions[k]; });
    con.what.textContent = [state.script, state.environment].concat(versions)
      .concat(state.variation ? [state.variation] : []).concat(state.start ? [state.start] : []).join(" · ");
    var status = state.problem ? "can't load: " + state.problem
      : state.busy ? "running" + (state.running ? " " + state.running : "") + (state.queued ? " (+" + state.queued + " waiting)" : "")
      : "idle";
    if (state.abandoned) status += " · " + state.abandoned + " left running in the background";
    con.status.textContent = status;
    con.status.classList.toggle("is-busy", !!state.busy);
    con.held.textContent = "";
    if (state.held && state.held.length) {
      var held = conButton(state.held.length + " held · Release all", "release", state.held.join("\n"));
      held.classList.add("ed-console__held-btn");
      con.held.appendChild(held);
    }
    $("[data-con=stop]", con.tools).disabled = !state.busy;
    var changed = false;
    Object.keys(state.outcomes || {}).forEach(function (id) {
      var outcome = state.outcomes[id], card = con.cards[id], entry = con.entries[id];
      if (card && card.isConnected) { card.dataset.edRan = outcome; delete card.dataset.edRunning; }
      if (entry && entry.outcome !== outcome) { entry.outcome = outcome; changed = true; }
    });
    if (changed) { saveHistory(); drawHistory(); }
    if (was && was.busy && !state.busy) fetchNames();  // a command ended: names may have changed
  }

  // Ask for new lines; keep asking while the kernel is busy
  function consolePoll(now) {
    if (!con || con.polling) return;
    con.polling = setTimeout(function () {
      fetch(consoleBase() + "/lines?since=" + con.last).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (found) {
          con.polling = null;
          if (!found || !found.state || found.state.workspace !== ws) {
            if (found && !found.state && con.state) consoleClosed();
            return;
          }
          found.lines.forEach(drawLine);
          consoleState(found.state);
          if (found.state.busy) consolePoll();
          else if (!con.names.length) fetchNames();
        })
        .catch(function () { con.polling = null; });
    }, now ? 0 : 300);
  }

  function drawLine(line) {
    con.last = Math.max(con.last, line.n);
    var item = el("li", "ed-cl ed-cl--" + line.kind);
    if (line.depth) item.style.paddingLeft = (26 + 14 * line.depth) + "px";
    var card = con.cards[line.command];
    if (line.kind === "error") {
      var details = el("details");
      details.appendChild(el("summary", null, "Traceback"));
      details.appendChild(el("pre", "ed-cl__pre", line.text));
      item.appendChild(details);
    } else if (line.kind === "file" && line.file) {
      var link = el("a", null, "📎 " + line.text);
      link.href = consoleBase() + "/files/" + encodeURIComponent(line.file);
      link.target = "_blank";
      link.rel = "noopener";
      item.appendChild(link);
    } else {
      item.textContent = line.text;
      if (line.duration && line.kind === "step") item.appendChild(el("span", "ed-cl__time", " " + line.duration + "s"));
      if (line.at_text) item.appendChild(el("span", "ed-cl__time", " " + line.at_text));
    }
    if (line.more) { item._more = line.text + "\n" + line.more; item.classList.add("is-more"); item.title = "Show the rest"; }
    if (card && (line.kind === "command" || line.at)) {
      item._card = card;
      item._at = line.at || null;
      item.classList.add("is-link");
      item.title = line.at ? "Go to line " + (line.at.line + 1) + " of the block" : "Go to the block";
    }
    var follow = con.scroll.scrollTop + con.scroll.clientHeight >= con.scroll.scrollHeight - 8;
    con.list.appendChild(item);
    while (con.list.children.length > 2000) con.list.removeChild(con.list.firstChild);
    if (follow) con.scroll.scrollTop = con.scroll.scrollHeight;
  }

  // Put the cursor on a line of a card
  function jumpTo(card, at) {
    if (card._card.kind !== "rvt") return;
    if (!card._edit) openCard(card);
    card.scrollIntoView({ block: "center" });
    if (!at || !card._edit) return;
    var view = card._edit.view, doc = view.state.doc;
    var line = doc.line(Math.min(Math.max(at.line + 1, 1), doc.lines));
    view.dispatch({ selection: { anchor: Math.min(line.from + (at.character || 0), line.to) }, scrollIntoView: true });
    view.focus();
  }

  // The variations a card is for: its own, and each variant's it is in
  function scopesOf(card) {
    var scopes = [];
    for (var at = card; at; at = at.parentNode && at.parentNode.closest(".ed-card--variant")) {
      if (at._card && (at._card.variations || []).length) scopes.push(at._card.variations);
    }
    return scopes;
  }

  function runCard(card) {
    var data = dataOf(card, false);
    consoleRun({ kind: "card", code: data.code || "", title: data.title || null,
                 definitions: !!data.definitions, table: !!data.table, variations: scopesOf(card) }, card);
  }

  // Shift+Enter in a card's editor: the selection, or the form at the cursor
  // (in a table card, with its first row's symbols bound)
  function runAtCursor(card, view) {
    var sel = view.state.selection.main, doc = view.state.doc;
    var table = card._card.table ? doc.toString() : null;
    if (!sel.empty) {
      var line = doc.lineAt(sel.from);
      consoleRun({ kind: "forms", text: doc.sliceString(sel.from, sel.to), line: line.number - 1,
                   character: sel.from - line.from, variations: scopesOf(card), table: table }, card);
    } else {
      var here = doc.lineAt(sel.head);
      consoleRun({ kind: "form", code: doc.toString(), line: here.number - 1, character: sel.head - here.from,
                   variations: scopesOf(card), table: table }, card);
    }
    return true;
  }

  function promptRun(view) {
    var text = view.state.doc.toString();
    if (!text.trim()) return;
    con.at = -1;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: "" } });
    consoleRun({ kind: "forms", text: text }, null);
  }

  function setPrompt(text) {
    var view = con.input;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, selection: { anchor: text.length } });
    view.focus();
  }

  function insertInPrompt(text) {
    var view = con.input;
    view.dispatch(view.state.replaceSelection(text));
    view.focus();
  }

  // Up and Down in the prompt: back through the forms run, newest first
  function promptHistory(view, step) {
    var doc = view.state.doc, head = view.state.selection.main.head;
    if (step < 0 && doc.lineAt(head).number !== 1) return false;
    if (step > 0 && doc.lineAt(head).number !== doc.lines) return false;
    var texts = con.history.filter(function (h) { return h.payload.kind === "forms"; })
      .map(function (h) { return h.payload.text; });
    if (!texts.length) return false;
    var at = con.at < 0 ? texts.length : con.at;
    at = Math.max(0, Math.min(texts.length, at + step));
    con.at = at === texts.length ? -1 : at;
    var text = con.at < 0 ? "" : texts[at];
    view.dispatch({ changes: { from: 0, to: doc.length, insert: text }, selection: { anchor: text.length } });
    return true;
  }

  // History: what was run, as it was run, to run again

  function saveHistory() { store("history:" + ws, con.history.slice(-HISTORY_KEPT)); }

  function firstLine(text) {
    var line = String(text || "").trim().split("\n")[0];
    return line.length > 90 ? line.slice(0, 89) + "…" : line;
  }

  function rememberRun(payload, card, label) {
    var entry = { at: Date.now(), payload: payload, path: active, label: label, outcome: null };
    con.history.push(entry);
    if (con.history.length > HISTORY_KEPT) con.history.splice(0, con.history.length - HISTORY_KEPT);
    saveHistory();
    drawHistory();
    return entry;
  }

  function labelOf(payload) {
    var pre = payload.kind === "card" && /^\s*\(Precondition\s+"((?:[^"\\]|\\.)*)"/.exec(payload.code || "");
    if (payload.kind === "card") return "▶ " + (payload.title || (pre ? "Precondition: " + pre[1] : firstLine(payload.code)) || "(empty)");
    if (payload.kind === "form") return firstLine(payload.code.split("\n")[payload.line] || "");
    return firstLine(payload.text);
  }

  function drawHistory() {
    if (!con) return;
    var list = con.historyList;
    list.textContent = "";
    if (!con.history.length) {
      list.appendChild(el("li", "ed-history__empty ui-muted", "What you run in the console shows here, to run again."));
      return;
    }
    con.history.slice().reverse().forEach(function (entry) {
      var item = el("li", "ed-hist");
      item._entry = entry;
      var dot = el("span", "ed-hist__dot");
      dot.dataset.outcome = entry.outcome || "";
      dot.title = entry.outcome || "not finished";
      item.appendChild(dot);
      var label = el("span", "ed-hist__label", entry.label);
      label.title = (entry.payload.kind === "card" ? entry.payload.code : entry.payload.text || entry.label) +
        (entry.path ? "\n\nfrom " + entry.path : "");
      item.appendChild(label);
      var when = new Date(entry.at);
      item.appendChild(el("span", "ed-hist__time", String(when.getHours()).padStart(2, "0") + ":" + String(when.getMinutes()).padStart(2, "0")));
      var again = el("button", "ed-hist__btn", "▶");
      again.type = "button";
      again.dataset.hist = "run";
      again.title = "Run it again, as it was";
      var edit = el("button", "ed-hist__btn", "✎");
      edit.type = "button";
      edit.dataset.hist = "edit";
      edit.title = "Put it in the prompt, to change it first";
      item.appendChild(again);
      item.appendChild(edit);
      list.appendChild(item);
    });
  }

  function historyAct(action, entry) {
    if (!entry) return;
    if (action === "edit") { setPrompt(entry.payload.kind === "card" ? entry.payload.code : entry.payload.text); return; }
    consoleRun(entry.payload, null, entry.label);
  }

  // Names: what the console's scope holds

  function fetchNames() {
    if (!con || !con.state || $(".ed-names", con.side).hidden) return;
    fetch(consoleBase() + "/names").then(function (r) { return r.ok ? r.json() : { names: [] }; })
      .then(function (found) { con.names = found.names || []; drawNames(); })
      .catch(function () { /* next time */ });
  }

  var SOURCES = { uut: "UUTs", variation: "Variation", console: "Defined in the console" };

  function drawNames() {
    if (!con) return;
    var list = con.namesList, filter = con.filter.value.trim().toLowerCase();
    list.textContent = "";
    var shown = con.names.filter(function (n) { return !filter || n.name.toLowerCase().indexOf(filter) >= 0; });
    if (!shown.length) {
      list.appendChild(el("p", "ed-history__empty ui-muted", con.state ? (filter ? "No name matches." : "Nothing yet.") : "Start the console to see its names."));
      return;
    }
    var group = null;
    shown.forEach(function (n) {
      if (n.source !== group) {
        group = n.source;
        list.appendChild(el("div", "ed-names__group", SOURCES[group] || group));
      }
      var row = el("div", "ed-name");
      row.dataset.name = n.name;
      row.title = "Put " + n.name + " in the prompt\n" + n.value;
      row.appendChild(el("span", "ed-name__name", n.name));
      row.appendChild(el("span", "ed-name__kind", n.kind));
      row.appendChild(el("span", "ed-name__value", n.value));
      list.appendChild(row);
    });
  }

  // Run something: open the console first if it isn't
  function consoleRun(payload, card, label) {
    consolePanel();
    consoleShow(true);
    if (!con.state || con.state.workspace !== ws) { con.waiting = { payload: payload, card: card, label: label }; consoleChoose(); return; }
    post(consoleBase() + "/run", payload).then(function (r) {
      return r.json().then(function (found) {
        if (!r.ok) { consoleSay(found.error || "Couldn't run it"); return; }
        var kept = payload;
        if (found.ran) {  // the form the server found at the cursor: kept as text, to run again
          kept = { kind: "forms", text: found.ran.text, line: found.ran.line, character: found.ran.character,
                   variations: payload.variations, table: payload.table };
        }
        con.entries[found.command] = rememberRun(kept, card, label || labelOf(kept));
        if (card) { con.cards[found.command] = card; delete card.dataset.edRan; card.dataset.edRunning = ""; }
        consoleState(found.state);
        consolePoll(true);
      });
    }).catch(function () { consoleSay("The server can't be reached"); });
  }

  // The choices to open the console with, for the active tab's script
  function consoleChoose() {
    var box = con.opening;
    box.hidden = false;
    box.textContent = "";
    if (!active) { box.appendChild(el("p", "ui-muted", "Open a script to start the console on it.")); return; }
    box.appendChild(el("p", "ui-muted", "Loading the choices for " + active + "…"));
    fetch(consoleBase() + "?path=" + encodeURIComponent(active)).then(function (r) { return r.json(); }).then(function (found) {
      box.textContent = "";
      var state = found.state;
      if (state && state.workspace !== ws) {
        box.appendChild(el("p", null, "The console is open on " + state.workspace + ". Close it there to open it here."));
        return;
      }
      var choices = found.choices || {};
      if (choices.error) { box.appendChild(el("p", "ed-cl--fail", choices.error)); return; }
      var form = el("form", "ed-console__form");
      form.appendChild(el("strong", null, "Start the console on " + active));
      function pick(label, name, options, selected) {
        if (!options.length) return;
        var field = el("label", "ed-console__field");
        field.appendChild(el("span", "ui-muted", label));
        var select = el("select", "ui-select ui-select--sm");
        select.name = name;
        options.forEach(function (o) { var opt = el("option", null, o); opt.value = o; if (o === selected) opt.selected = true; select.appendChild(opt); });
        field.appendChild(select);
        form.appendChild(field);
      }
      var d = choices.defaults || {};
      pick("Environment", "environment", choices.environments || [], d.environment);
      Object.keys(choices.versions || {}).forEach(function (uut) {
        pick(uut, "version-" + uut, choices.versions[uut].slice().reverse(), (d.versions || {})[uut]);
      });
      pick("Variation", "variation", choices.variations || [], d.variation);
      var go = el("button", "ui-btn ui-btn--sm ui-btn--primary", "Start");
      go.type = "submit";
      var cancel = el("button", "ui-btn ui-btn--sm ui-btn--ghost", "Cancel");
      cancel.type = "button";
      cancel.addEventListener("click", function () { box.hidden = true; con.waiting = null; if (!con.state) consoleClosed(); });
      form.appendChild(go);
      form.appendChild(cancel);
      form.addEventListener("submit", function (event) { event.preventDefault(); consoleOpen(form); });
      box.appendChild(form);
      go.focus();
    }).catch(function () { box.textContent = "The server can't be reached"; });
  }

  function consoleOpen(form) {
    var body = { path: active, versions: {} };
    if (form) {
      all("select", form).forEach(function (select) {
        if (select.name.indexOf("version-") === 0) body.versions[select.name.slice(8)] = select.value;
        else body[select.name] = select.value;
      });
    }
    con.opening.textContent = "";
    con.opening.appendChild(el("p", "ui-muted", "Starting… (waiting for the local worker if it is running a job)"));
    post(consoleBase() + "/open", body).then(function (r) {
      return r.json().then(function (found) {
        if (!r.ok) { con.opening.textContent = ""; con.opening.appendChild(el("p", "ed-cl--fail", found.error || "The console couldn't start")); return; }
        con.opening.hidden = true;
        con.list.textContent = "";
        con.last = 0;
        consoleState(found.state);
        consolePoll(true);
        var waiting = con.waiting;
        con.waiting = null;
        if (waiting) consoleRun(waiting.payload, waiting.card, waiting.label);
      });
    }).catch(function () { con.opening.textContent = "The server can't be reached"; });
  }

  // Open the console's choices without running anything
  function consoleOpenPanel() {
    consolePanel();
    consoleShow(true);
    if (!con.state) consoleChoose();
  }

  function start() {
    root = document.getElementById("ed");
    if (!root) return;
    ws = root.dataset.workspace;
    base = root.dataset.base.replace(/\/$/, "");
    editable = root.dataset.editable === "true";
    consoleOn = editable && root.dataset.console === "true";
    var asked = new URLSearchParams(location.search);  // read before a tab rewrites the address
    var given = JSON.parse(root.dataset.tabs || "[]");
    var first = root.dataset.active || null;
    if (first) firstLoad[first] = { variation: root.dataset.variation, files: root.dataset.files };
    given.forEach(addTab);
    if (editable) unsavedFiles().forEach(addTab);
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    document.addEventListener("dblclick", onDoubleClick);
    document.addEventListener("pointerdown", function (event) {
      var grip = event.target.closest && event.target.closest("[data-ed-grip]");
      if (grip && editable) dragStart(event, grip);
    });
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (editable && form.matches && form.matches("[data-ed-run]") && runSaved(form)) event.preventDefault();
    }, true);
    // Anything htmx redraws in a pane (another variation, the checked-in view) is scanned again
    document.body.addEventListener("htmx:afterSettle", function () {
      if (active && states[active]) scan(states[active].pane);
      var current = active && $('.ui-tree__row--file[data-open="' + window.CSS.escape(active) + '"]');
      if (current) current.setAttribute("aria-current", "true");
      drawTreeCounts();
    });
    window.addEventListener("focus", function () { if (active) checkDisk(active); });
    window.addEventListener("beforeunload", function () { if (active && states[active] && states[active].dirty) keepDraft(active); });
    if (first || tabs.length) activate(first || tabs[0]);
    else drawTabs();
    drawProblems();
    // A link from a requirement's page: write a script for it
    if (editable && asked.get("new")) fileDialog("new", { requirement: asked.get("requirement") || "" });
    if (consoleOn) consoleStart();
    var panes = $(".ed-panes", root);
    if (panes) panes.addEventListener("scroll", function () { if (pop) closeMenu(); }, { passive: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
