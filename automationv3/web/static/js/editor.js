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

  var root, ws, base, editable;
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
    st.problems = st.problems || [];
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

  function adder() {
    var bar = el("div", "ed-add");
    bar.appendChild(button("+ Text", "add-prose", "ui-btn--ghost", "Add a section of text here"));
    bar.appendChild(button("+ Block", "add-rvt", "ui-btn--ghost", "Add a block of steps here"));
    return bar;
  }

  // Every card's tools, and a way to add cards at the top of the document
  // and of each variant
  function decorateAll(doc) {
    all(".ed-card", doc).forEach(decorate);
    if (doc.dataset.plain !== "true" && !$(":scope > .ed-add", doc)) doc.insertBefore(adder(), doc.firstChild);
  }

  function decorate(card) {
    if ($(":scope > .ed-card__tools", card)) return card;
    var doc = card.closest("[data-ed-doc]");
    var plain = doc && doc.dataset.plain === "true";
    var tools = el("div", "ed-card__tools");
    if (!plain) {
      var grip = el("button", "ui-btn ui-btn--sm ui-btn--ghost ed-grip", "⠿");
      grip.type = "button";
      grip.title = "Drag to move";
      grip.setAttribute("aria-label", "Drag to move");
      grip.dataset.edGrip = "";
      tools.appendChild(grip);
    }
    tools.appendChild(button("Edit", "edit", "ui-btn--ghost", isVariant(card) ? "Change which variations it is for" : "Edit this part"));
    if (!plain) {
      tools.appendChild(button("↑", "up", "ui-btn--ghost", "Move up"));
      tools.appendChild(button("↓", "down", "ui-btn--ghost", "Move down"));
      if (!isVariant(card)) tools.appendChild(button("Variant", "wrap", "ui-btn--ghost", "Only for some variations: put it in a variant"));
      else tools.appendChild(button("Unwrap", "unwrap", "ui-btn--ghost", "For every variation again: take out what it holds"));
      tools.appendChild(button("Delete", "delete", "ui-btn--ghost", isVariant(card) ? "Delete it and what it holds" : "Delete this part"));
      card.appendChild(adder());
      if (isVariant(card) && !$(":scope > .ed-add", bodyOf(card))) bodyOf(card).insertBefore(adder(), bodyOf(card).firstChild);
    }
    card.insertBefore(tools, card.firstChild);
    return card;
  }

  function dirty(path) {
    var st = states[path];
    st.dirty = true;
    keepDraft(path);
    say("Unsaved edits");
    drawTabs();
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
    all(":scope > .ed-card, :scope > .ed-add", doc).forEach(function (node) { node.remove(); });
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

  // The language server (lsp/server.py, behind /lsp): it is sent each
  // tab's file as the cards make it, edits in progress included, and its
  // diagnostics are drawn on the cards they fall in

  var lsp = { session: Math.random().toString(36).slice(2) + Date.now().toString(36), next: 1, started: false, sent: {}, queue: Promise.resolve(), problems: {} };
  var TYPES = { 3: "function", 6: "variable", 7: "class", 10: "property", 14: "keyword", 18: "text" };
  var REQ_OPEN = /:req:`[^`]*$/i;
  var NAME = /[^\s()\[\]{}"';,]*/;

  function lspUri(path) { return "rvt:///" + path.split("/").map(encodeURIComponent).join("/"); }
  function uriPath(uri) { return decodeURIComponent(uri.replace(/^rvt:\/\/\//, "")); }

  // Send messages, in order with every other send; gives the answers
  function lspPost(messages) {
    lsp.queue = lsp.queue.then(function () {
      return post(base + "/lsp", { session: lsp.session, messages: messages })
        .then(function (response) { return response.ok ? response.json() : { messages: [] }; })
        .then(function (found) {
          if (found.reset) { lspReset(); return []; }
          var published = false;
          found.messages.forEach(function (message) {
            if (message.method !== "textDocument/publishDiagnostics") return;
            var path = uriPath(message.params.uri);
            published = true;
            if (message.params.diagnostics.length) lsp.problems[path] = message.params.diagnostics;
            else delete lsp.problems[path];
            if (!states[path]) return;
            states[path].problems = message.params.diagnostics;
            showProblems(path);
          });
          if (published) { drawProblems(); drawTreeCounts(); }
          return found.messages;
        });
    }).catch(function () { return []; });
    return lsp.queue;
  }

  // The server forgot this page: start over, opening every document again
  function lspReset() {
    lsp.started = false;
    lsp.sent = {};
    setTimeout(function () { tabs.forEach(function (path) { lspSync(path); }); }, 0);
  }

  function withoutTail(text) { return text.replace(/(?:[ \t]*\r?\n)*$/, ""); }
  function count(text, what) { return text.split(what).length - 1; }
  function lineCount(text) { return count(text, "\n") + (/\n$/.test(text) || !text ? 0 : 1); }

  // An edited card as it is written in the file (framework/cards.py: written)
  function written(data) {
    if (data.kind !== "rvt") return (data.text || "").replace(/^\n+|\n+$/g, "") + "\n";
    var title = (data.title || "").split(/\s+/).filter(Boolean).join(" ");
    var lines = [title ? ".. rvt:: " + title : ".. rvt::"];
    if (data.definitions) lines.push("   :definitions:");
    if (data.table) lines.push("   :table:");
    if ((data.variations || []).length) lines.push("   :variations: " + data.variations.join(", "));
    var code = (data.code || "").replace(/^\n+|\n+$/g, "");
    if (code) lines = lines.concat([""], code.split("\n").map(function (line) { return line.trim() ? "   " + line : ""; }));
    return lines.join("\n") + "\n";
  }

  // A variant written again, around its children's text (cards.py: variant_source)
  function variantWritten(data, body) {
    var lines = [".. rvt-variant::", ("   :variations: " + (data.variations || []).join(", ")).replace(/\s+$/, "")];
    body = body.replace(/\n+$/, "");
    if (body) lines = lines.concat([""], body.split("\n").map(function (line) { return line.trim() ? "   " + line : ""; }));
    return lines.join("\n") + "\n";
  }
  var VARIANT_HEAD = 3;  // lines before a variant written again starts its children

  // The text cards make (framework/cards.py: build), and where each card
  // is in it: {text, places: [{card, start, end, codeStart, codeIndent}]},
  // lines counted from 0, a variant before what it holds. A card's code
  // (what its editor holds) starts at codeStart, indented by codeIndent.
  function assemble(els, original, typed) {
    var parts = els.map(function (card) {
      return { card: card, data: dataOf(card, typed) };
    }).filter(function (p) {
      return p.data.source != null || p.data.kind === "rvt" || p.data.kind === "variant" || (p.data.text || "").trim();
    });
    var text = "", places = [];
    parts.forEach(function (part, n) {
      var data = part.data, fresh = data.source == null, inner = null, piece;
      if (data.kind === "variant" && fresh) {
        inner = assemble(cardsOf(bodyOf(part.card)), data.count || 0, typed);
        piece = variantWritten(data, inner.text);
      } else {
        piece = fresh ? written(data) : data.source;
      }
      if (fresh) {
        // as written, which ends with one line end; spaces being typed at its end stay
        if (n < parts.length - 1) piece += "\n";
      } else if (n === parts.length - 1) {
        if (data.index !== original - 1) piece = withoutTail(piece) + "\n";
      } else {
        var after = parts[n + 1].data;
        var follows = after.source != null && data.index != null && after.index === data.index + 1;
        if (!follows) piece = withoutTail(piece) + "\n\n";
      }
      var start = count(text, "\n"), place = { card: part.card, start: start, codeStart: start, codeIndent: 0 };
      if (data.kind === "rvt" && fresh) {
        var options = (data.definitions ? 1 : 0) + (data.table ? 1 : 0) + ((data.variations || []).length ? 1 : 0);
        place.codeStart = start + 2 + options - (/^\n*/.exec(data.code || "")[0].length);
        place.codeIndent = 3;
      } else if (data.kind === "rvt") {
        place.codeStart = start + (data.code_offset || 0);
        place.codeIndent = (data.code_indent || 0) - (data.indent || 0);
      } else if (fresh && data.kind !== "variant") {
        place.codeStart = start - (/^\n*/.exec(data.text || "")[0].length);
      }
      text += piece;
      place.end = count(text, "\n") + (/\n$/.test(text) ? 0 : 1);
      places.push(place);
      if (data.kind === "variant" && fresh) {
        inner.places.forEach(function (p) {
          places.push({ card: p.card, start: p.start + start + VARIANT_HEAD, end: p.end + start + VARIANT_HEAD,
                        codeStart: p.codeStart + start + VARIANT_HEAD, codeIndent: p.codeIndent + 3 });
        });
      } else if (data.kind === "variant") {
        unchangedPlaces(part.card, start, -(data.indent || 0), places);
      }
    });
    return { text: text, places: places };
  }

  // Where the cards of a variant that is as it was cut are: their lines
  // from the server, their columns moved by `cols`
  function unchangedPlaces(variant, at, cols, places) {
    cardsOf(bodyOf(variant)).forEach(function (child) {
      var d = child._card, start = at + (d.line_in || 0);
      var place = { card: child, start: start, end: start + lineCount(d.source || ""), codeStart: start, codeIndent: 0 };
      if (d.kind === "rvt") {
        place.codeStart = start + (d.code_offset || 0);
        place.codeIndent = (d.code_indent || 0) + cols;
      }
      places.push(place);
      if (d.kind === "variant") unchangedPlaces(child, start, cols, places);
    });
  }

  function derive(doc, original) { return assemble(cardsOf(doc), original, true); }

  // Tell the server what a tab's file is now, if that changed
  function lspSync(path) {
    var st = states[path], doc = docOf(path);
    if (!editable || !st || !doc || doc.dataset.plain === "true" || doc.dataset.editable !== "true") return Promise.resolve();
    var found = derive(doc, st.count), messages = [];
    st.places = found.places;
    var named = { uri: lspUri(path) };
    if (!lsp.started) {
      lsp.started = true;
      messages.push({ jsonrpc: "2.0", id: lsp.next++, method: "initialize", params: {} },
                    { jsonrpc: "2.0", method: "initialized", params: {} });
    }
    if (!(path in lsp.sent)) {
      messages.push({ jsonrpc: "2.0", method: "textDocument/didOpen", params: { textDocument: { uri: named.uri, languageId: "rst", version: 1, text: found.text } } });
    } else if (lsp.sent[path] !== found.text) {
      messages.push({ jsonrpc: "2.0", method: "textDocument/didChange", params: { textDocument: named, contentChanges: [{ text: found.text }] } });
    }
    lsp.sent[path] = found.text;
    if (!messages.length) { showProblems(path); return lsp.queue; }
    return lspPost(messages).then(function () { showProblems(path); });
  }

  function lspClose(path) {
    if (!(path in lsp.sent)) return;
    delete lsp.sent[path];
    lspPost([{ jsonrpc: "2.0", method: "textDocument/didClose", params: { textDocument: { uri: lspUri(path) } } }]);
  }

  function lspRequest(method, params) {
    var id = lsp.next++;
    return lspPost([{ jsonrpc: "2.0", id: id, method: method, params: params }]).then(function (answers) {
      var answer = answers.filter(function (a) { return a.id === id; })[0];
      return answer ? answer.result : null;
    });
  }

  // The innermost card a line of the tab's file is in
  function placeOf(st, line) {
    var found = null;
    (st.places || []).forEach(function (p) { if (p.start <= line && line < p.end) found = p; });
    if (!found && st.places && st.places.length) {  // past the end: the last top-level card
      var last = st.places.filter(function (p) { return p.card.parentNode && p.card.parentNode.hasAttribute("data-ed-doc"); }).pop();
      found = last || st.places[st.places.length - 1];
    }
    return found;
  }

  // Draw a tab's diagnostics: squiggles in the card being edited, a list
  // under any other card, and a count on the tab
  function showProblems(path) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc || !st.places) return;
    var problems = st.problems || [];
    doc.classList.add("is-live");  // the diagnostics drawn when the page was made are out of date now
    var by = new Map();
    problems.forEach(function (p) {
      var place = placeOf(st, p.range.start.line);
      if (!place) return;
      if (!by.has(place)) by.set(place, []);
      by.get(place).push(p);
    });
    st.places.forEach(function (place) {
      var own = by.get(place) || [];
      var card = place.card, list = $(":scope > .ed-card__problems", card);
      if (list) list.remove();
      if (card._edit && card._edit.view) {
        var view = card._edit.view, text = view.state.doc;
        var at = function (position) {
          var line = position.line - place.codeStart;
          if (line < 0) return 0;
          if (line >= text.lines) return text.length;
          var found = text.line(line + 1);
          return Math.min(found.from + Math.max(position.character - place.codeIndent, 0), found.to);
        };
        view.dispatch(window.CM.setDiagnostics(view.state, own.map(function (p) {
          var from = at(p.range.start), to = Math.max(at(p.range.end), from);
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
      var after = $(":scope > .ed-add", card);
      card.insertBefore(list, after);
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
      lsp.problems[path].slice().sort(function (a, b) { return a.severity - b.severity || a.range.start.line - b.range.start.line; }).forEach(function (p) {
        var item = el("li");
        var go = el("button", "ed-problems__item " + (p.severity === 1 ? "is-error" : "is-warning"));
        go.type = "button";
        go.dataset.edReveal = path;
        go.dataset.line = p.range.start.line;
        go.appendChild(el("strong", null, p.severity === 1 ? "Error" : "Warning"));
        go.appendChild(document.createTextNode(" " + p.message + " "));
        go.appendChild(el("span", "ui-muted", "line " + (p.range.start.line + 1)));
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
    var st = states[path], place = placeOf(st, line);
    if (!place) { st.reveal = line; return; }
    var card = place.card;
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

  // Where an offset of a card's editor is in the tab's file
  function positionOf(card, view, offset) {
    var place = (states[pathOf(card)].places || []).filter(function (p) { return p.card === card; })[0];
    if (!place) return null;
    var line = view.state.doc.lineAt(offset);
    return { line: place.codeStart + line.number - 1, character: place.codeIndent + offset - line.from };
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
      var path = pathOf(card);
      return lspSync(path).then(function () {
        var position = positionOf(card, view, offset);
        if (!position) return null;
        return lspRequest("textDocument/hover", { textDocument: { uri: lspUri(path) }, position: position });
      }).then(function (found) {
        if (!found || !found.contents || !found.contents.value) return null;
        var line = view.state.doc.lineAt(offset), place = positionOf(card, view, line.from);
        var from = line.from + found.range.start.character - place.character;
        var to = line.from + found.range.end.character - place.character;
        return {
          pos: Math.max(from, line.from), end: Math.min(to, line.to), above: true,
          create: function () { return { dom: prose(found.contents.value) }; },
        };
      });
    };
  }

  // How the call the cursor is in is called, under a block's editor,
  // with the argument being typed marked
  function sign(card, view, bar) {
    if (!card._edit) return;
    var path = pathOf(card);
    lspSync(path).then(function () {
      var position = positionOf(card, view, view.state.selection.main.head);
      if (!position) return null;
      return lspRequest("textDocument/signatureHelp", { textDocument: { uri: lspUri(path) }, position: position });
    }).then(function (found) {
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
      var path = pathOf(card);
      return lspSync(path).then(function () {
        var place = (states[path].places || []).filter(function (p) { return p.card === card; })[0];
        if (!place) return null;
        var line = context.state.doc.lineAt(context.pos);
        return lspRequest("textDocument/completion", {
          textDocument: { uri: lspUri(path) },
          position: { line: place.codeStart + line.number - 1, character: place.codeIndent + context.pos - line.from },
        });
      }).then(function (found) {
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

  function field(card, name) { return $(':scope > .ed-card__edit [data-f="' + name + '"]', card); }

  // The variations a script declares, as buttons that add or take one
  // out of a variations field
  function chips(card, input) {
    var doc = card.closest("[data-ed-doc]"), names = [];
    try { names = JSON.parse(doc.dataset.variations || "[]"); } catch (e) { names = []; }
    var box = el("span", "ed-chips");
    if (!names.length) return box;
    function chosen() { return input.value.split(",").map(function (v) { return v.trim(); }).filter(Boolean); }
    function draw() {
      all(".ed-chip", box).forEach(function (chip) {
        chip.classList.toggle("is-on", chosen().indexOf(chip.dataset.name) >= 0);
        chip.setAttribute("aria-pressed", chip.classList.contains("is-on") ? "true" : "false");
      });
    }
    names.forEach(function (name) {
      var chip = el("button", "ed-chip", name);
      chip.type = "button";
      chip.dataset.name = name;
      chip.addEventListener("click", function () {
        var now = chosen(), at = now.indexOf(name);
        if (at >= 0) now.splice(at, 1); else now.push(name);
        input.value = now.join(", ");
        input.dispatchEvent(new Event("change"));
        draw();
      });
      box.appendChild(chip);
    });
    input.addEventListener("input", draw);
    draw();
    return box;
  }

  function variationsInput(card, value, placeholder) {
    var variations = el("input", "ui-input ui-input--mono ed-fields__variations");
    variations.dataset.f = "variations";
    variations.placeholder = placeholder;
    variations.value = (value || []).join(", ");
    variations.setAttribute("aria-label", "Only for these variations, separated by commas");
    variations.title = "Only for these variations, separated by commas";
    var only = el("label", "ed-fields__only");
    only.appendChild(el("span", "ui-muted", "Only for"));
    only.appendChild(variations);
    var wrap = el("span", "ed-fields__variation-field");
    wrap.appendChild(only);
    wrap.appendChild(chips(card, variations));
    return wrap;
  }

  function foot(edit) {
    var row = el("div", "ed-card__foot");
    row.appendChild(button("Done", "done", "ui-btn--primary"));
    row.appendChild(button("Cancel", "cancel"));
    row.appendChild(el("span", "ui-muted", "Esc or Ctrl+Enter when done"));
    edit.appendChild(row);
    return row;
  }

  function openCard(card, isNew, wrapping) {
    if (card._edit) return;
    editing(card.closest("[data-ed-doc]")).forEach(function (other) { if (other !== card && !other.contains(card)) closeCard(other, true); });
    var data = card._card, rvt = data.kind === "rvt", path = pathOf(card);
    var edit = el("div", "ed-card__edit");
    if (data.kind === "variant") {  // only which variations it is for
      var row = el("div", "ed-fields");
      row.appendChild(variationsInput(card, data.variations, "name the variations"));
      edit.appendChild(row);
      foot(edit);
      card.insertBefore(edit, bodyOf(card));
      card.classList.add("is-editing");
      card._edit = { view: null, element: edit, isNew: !!isNew, wrapping: !!wrapping };
      var input = field(card, "variations");
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === "Escape") { event.preventDefault(); closeCard(card, event.key === "Enter" || !wrapping); }
      });
      input.focus();
      return;
    }
    if (rvt) {
      var fields = el("div", "ed-fields");
      var title = el("input", "ui-input ed-fields__title");
      title.dataset.f = "title";
      title.placeholder = "Title (optional): what these steps do";
      title.value = data.title || "";
      title.setAttribute("aria-label", "Block title");
      fields.appendChild(title);
      [["definitions", "Definitions", "Only defines things: shown collapsed, before the first step"],
       ["table", "Table", "A table of rows, then the steps run for each row"]].forEach(function (f) {
        var box = el("label", "ed-fields__flag");
        var input = el("input");
        input.type = "checkbox";
        input.dataset.f = f[0];
        input.checked = !!data[f[0]];
        box.title = f[2];
        box.appendChild(input);
        box.appendChild(document.createTextNode(" " + f[1]));
        fields.appendChild(box);
      });
      fields.appendChild(variationsInput(card, data.variations, "every variation"));
      edit.appendChild(fields);
    }
    var holder = el("div", "ed-cm");
    edit.appendChild(holder);
    var bottom = foot(edit);
    card.insertBefore(edit, $(":scope > .ed-add", card));
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
      keys: [{ key: "Mod-Enter", run: done }, { key: "Escape", run: done }],
      extensions: [window.CM.autocompletion({ override: [completions(card)] }), window.CM.hoverTooltip(hovers(card))],
      onMove: rvt ? function (moved) { clearTimeout(signing); signing = setTimeout(function () { sign(card, moved, signature); }, 150); } : null,
      onChange: function () {  // the language server checks what is typed, once typing pauses
        clearTimeout(typing);
        typing = setTimeout(function () { if (card._edit && states[path]) lspSync(path); }, 300);
      },
    });
    card._edit = { view: view, element: edit, isNew: !!isNew };
    all("input", edit).forEach(function (input) {
      input.addEventListener("change", function () { if (card._edit) lspSync(path); });
    });
    view.focus();
    lspSync(path);
  }

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function names(input) { return input.value.split(",").map(function (v) { return v.trim(); }).filter(Boolean); }

  // What a card being edited holds right now, as an edited card. `typed`
  // keeps the spaces at the end, so a place in the editor is the same
  // place in the file the language server is sent.
  function current(card, typed) {
    var data = card._card;
    if (data.kind === "variant") {
      return Object.assign({}, data, { source: null, variations: names(field(card, "variations")) });
    }
    var text = card._edit.view.state.doc.toString();
    if (typed) text = text.replace(/\n+$/, "") + " ";
    var next = { kind: data.kind, source: null, index: null, level: data.level || 0 };
    if (data.kind === "rvt") {
      next.code = typed ? text : text.replace(/\s+$/, "");
      next.title = field(card, "title").value.trim() || null;
      next.definitions = field(card, "definitions").checked;
      next.table = field(card, "table").checked;
      next.variations = names(field(card, "variations"));
    } else {
      next.text = typed ? text : text.replace(/\s+$/, "");
    }
    return next;
  }

  function shownOf(data) {
    return data.kind === "rvt" ? [data.code || "", data.title || null, !!data.definitions, !!data.table, data.variations || []]
      : data.kind === "variant" ? [data.variations || []] : [data.text || ""];
  }

  // Close a card's editor; with `commit`, keep what it holds
  function closeCard(card, commit) {
    var edit = card._edit, path = pathOf(card);
    if (!edit) return Promise.resolve();
    var data = card._card, next = current(card);
    var changed = !same(shownOf(data), shownOf(next));
    var empty = data.kind === "prose" || data.kind === "source" ? !next.text.trim()
      : data.kind === "variant" ? !next.variations.length : false;
    setTimeout(function () { if (states[path]) lspSync(path); }, 0);
    if (edit.wrapping && (!commit || empty)) {  // a new variant called off: as it was before
      finish(card);
      var st = states[path];
      if (st.undo.length) rebuild(path, st.undo.pop());
      return Promise.resolve();
    }
    if ((!commit || empty) && edit.isNew) { finish(card); card.remove(); return Promise.resolve(); }
    if (!commit || (!changed && !edit.wrapping)) { finish(card); return Promise.resolve(); }
    if (!edit.wrapping) remember(path);  // a wrap remembered before it began
    finish(card);
    if (empty && data.kind === "variant") { unwrap(card); dirty(path); return Promise.resolve(); }
    if (empty) { touch(card); card.remove(); dirty(path); return Promise.resolve(); }
    card._card = next;
    touch(card);
    var view = viewOf(card);
    if (data.kind === "variant") {
      view.innerHTML = variantHead(next.variations);
      dirty(path);
      return Promise.resolve();
    }
    var doc = docOf(path);
    dirty(path);
    return post(base + "/editor/render", { card: next, plain: doc.dataset.plain === "true" })
      .then(function (response) { return response.ok ? response.json() : Promise.reject(); })
      .then(function (found) { view.innerHTML = found.html; })
      .catch(function () {
        view.textContent = "";
        view.appendChild(el("pre", "ui-pre", data.kind === "rvt" ? next.code : next.text));
      })
      .then(function () { if (states[path]) keepDraft(path); });
  }

  // Take a card's editor away
  function finish(card) {
    var edit = card._edit;
    if (edit.view) edit.view.destroy();
    edit.element.remove();
    card._edit = null;
    card.classList.remove("is-editing");
  }

  function addCard(after, kind) {
    var data = kind === "rvt"
      ? { kind: "rvt", source: null, index: null, code: "", title: null, definitions: false, table: false, variations: [] }
      : { kind: "prose", source: null, index: null, text: "", level: 0 };
    var card = section(data, "");
    after.parentNode.insertBefore(card, after.nextSibling);
    decorate(card);
    touch(card);
    openCard(card, true);
  }

  // Variants, cards moved

  // Put a card in a new variant, which asks which variations it is for
  function wrap(card) {
    var path = pathOf(card);
    remember(path);
    var variant = section({ kind: "variant", source: null, index: null, variations: [], count: 0, indent: 0 }, variantHead([]));
    card.parentNode.insertBefore(variant, card);
    touch(variant);
    bodyOf(variant).appendChild(card);
    card._card = Object.assign({}, card._card, { index: null });
    decorate(variant);
    dirty(path);
    openCard(variant, false, true);
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
      lspPost([{ jsonrpc: "2.0", method: "textDocument/didSave", params: { textDocument: { uri: lspUri(path) } } }]);
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
    var card = target.closest(".ed-card"), path = pathOf(target);
    if (name === "edit") openCard(card);
    else if (name === "done") closeCard(card, true);
    else if (name === "cancel") closeCard(card, false);
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
    else if (name === "add-prose" || name === "add-rvt") {
      var bar = target.closest(".ed-add");
      addCard(bar.parentNode.classList.contains("ed-card") ? card : bar, name === "add-rvt" ? "rvt" : "prose");
    }
    else if (name === "conflict-diff") showDifference(path);
    else if (name === "conflict-theirs") discard(path);
    else if (name === "conflict-mine") save(path, true);
  }

  function onClick(event) {
    var target = event.target;
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
    openCard(view.parentNode);
  }

  function typingIn(target) {
    return target.closest && target.closest("input, textarea, select, .cm-editor, dialog, [contenteditable]");
  }

  function onKey(event) {
    if (!active || !editable) return;
    var key = event.key.toLowerCase(), mod = event.ctrlKey || event.metaKey;
    if (mod && key === "s") { event.preventDefault(); save(active); return; }
    if (!mod || typingIn(event.target)) return;
    if (key === "z" && !event.shiftKey) { event.preventDefault(); undo(active); }
    else if ((key === "z" && event.shiftKey) || key === "y") { event.preventDefault(); undo(active, true); }
  }

  function start() {
    root = document.getElementById("ed");
    if (!root) return;
    ws = root.dataset.workspace;
    base = root.dataset.base.replace(/\/$/, "");
    editable = root.dataset.editable === "true";
    var asked = new URLSearchParams(location.search);  // read before a tab rewrites the address
    var given = JSON.parse(root.dataset.tabs || "[]");
    var first = root.dataset.active || null;
    if (first) firstLoad[first] = { variation: root.dataset.variation, files: root.dataset.files };
    given.forEach(addTab);
    if (editable) unsavedFiles().forEach(addTab);
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
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
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
