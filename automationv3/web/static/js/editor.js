// The workspace editor: files open in tabs, each shown as its cards
// (web/editor.py), which open into editors in a worktree.
//
// A tab's pane holds what /view returns for its file. The cards on the
// page are the tab's state: each card element keeps what the server cut
// it from (el._card), and an edited one is that with no `source`. A tab
// with unsaved edits also keeps its cards in localStorage (a draft), so
// a reload, or anything that redraws the pane, brings them back.
(function () {
  "use strict";

  var root, ws, base, editable;
  var tabs = [];      // paths, in tab order
  var active = null;  // the active tab's path
  var states = {};    // path -> {pane, loaded, dirty, conflict, baseHash, count}
  var firstLoad = {}; // the view options the page was opened with, for its file

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
    var cards = cardsOf(doc).map(function (c) {
      return { data: c._card, html: $(".ed-card__view", c).innerHTML };
    });
    putDraft(path, { hash: st.baseHash, count: st.count, cards: cards });
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
  }

  function say(text) {
    var status = $(".ed-status", root);
    if (status) status.textContent = text || "";
  }

  var remember;
  function rememberTabs() {
    clearTimeout(remember);
    remember = setTimeout(function () {
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
    states[path] = { pane: pane, loaded: false, dirty: !!draft(path), conflict: false };
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

  function docOf(path) { return states[path] ? $("[data-ed-doc]", states[path].pane) : null; }
  function pathOf(node) { var pane = node.closest(".ed-pane"); return pane ? pane.dataset.path : null; }
  function cardsOf(doc) { return all(":scope > .ed-card", doc); }

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
    cardsOf(doc).forEach(function (card) { card._card = JSON.parse(card.dataset.card); card.removeAttribute("data-card"); });
    var kept = editable && draft(path);
    if (kept) {
      doc.textContent = "";
      kept.cards.forEach(function (c) { doc.appendChild(section(c.data, c.html)); });
      st.baseHash = kept.hash;
      st.count = kept.count;
      st.dirty = true;
      if ((kept.hash || "") !== doc.dataset.hash) { st.conflict = true; showConflict(path); }
    } else {
      st.dirty = false;
    }
    if (editable && doc.dataset.editable === "true") {
      cardsOf(doc).forEach(decorate);
      if (doc.dataset.plain !== "true") doc.insertBefore(adder(), doc.firstChild);
      else if (!cardsOf(doc).length) doc.appendChild(decorate(section({ kind: "source", source: null, index: null, text: "" }, "")));
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
    card._card = data;
    return card;
  }

  function adder() {
    var bar = el("div", "ed-add");
    bar.appendChild(button("+ Text", "add-prose", "ui-btn--ghost", "Add a section of text here"));
    bar.appendChild(button("+ Block", "add-rvt", "ui-btn--ghost", "Add a block of steps here"));
    return bar;
  }

  function decorate(card) {
    if ($(":scope > .ed-card__tools", card)) return card;
    var plain = card.closest("[data-ed-doc]") && card.closest("[data-ed-doc]").dataset.plain === "true";
    var tools = el("div", "ed-card__tools");
    tools.appendChild(button("Edit", "edit", "ui-btn--ghost", "Edit this part"));
    if (!plain) {
      tools.appendChild(button("↑", "up", "ui-btn--ghost", "Move up"));
      tools.appendChild(button("↓", "down", "ui-btn--ghost", "Move down"));
      tools.appendChild(button("Delete", "delete", "ui-btn--ghost", "Delete this part"));
      card.appendChild(adder());
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

  // The language server (lsp/server.py, behind /lsp): it is sent each
  // tab's file as the cards make it, edits in progress included, and its
  // diagnostics are drawn on the cards they fall in

  var lsp = { session: Math.random().toString(36).slice(2) + Date.now().toString(36), next: 1, started: false, sent: {}, queue: Promise.resolve() };
  var TYPES = { 3: "function", 6: "variable", 7: "class", 14: "keyword" };
  var NAME = /[^\s()\[\]{}"';,]*/;

  function lspUri(path) { return "rvt:///" + path.split("/").map(encodeURIComponent).join("/"); }

  // Send messages, in order with every other send; gives the answers
  function lspPost(messages) {
    lsp.queue = lsp.queue.then(function () {
      return post(base + "/lsp", { session: lsp.session, messages: messages })
        .then(function (response) { return response.ok ? response.json() : { messages: [] }; })
        .then(function (found) {
          if (found.reset) { lspReset(); return []; }
          found.messages.forEach(function (message) {
            if (message.method !== "textDocument/publishDiagnostics") return;
            var path = decodeURIComponent(message.params.uri.replace(/^rvt:\/\/\//, ""));
            if (!states[path]) return;
            states[path].problems = message.params.diagnostics;
            showProblems(path);
          });
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

  // The file a tab's cards make (framework/cards.py: build), and where
  // each card is in it: {text, places: [{card, start, end, codeStart, codeIndent}]},
  // lines counted from 0. A card's code (what its editor holds) starts at
  // codeStart, indented by codeIndent.
  function derive(doc, original) {
    var parts = cardsOf(doc).map(function (card) {
      return { card: card, data: card._edit ? current(card) : card._card };
    }).filter(function (p) { return p.data.source != null || p.data.kind === "rvt" || (p.data.text || "").trim(); });
    var text = "", places = [];
    parts.forEach(function (part, n) {
      var data = part.data, fresh = data.source == null;
      var piece = fresh ? written(data) : data.source;
      if (n === parts.length - 1) {
        if (fresh || data.index !== original - 1) piece = withoutTail(piece) + "\n";
      } else {
        var after = parts[n + 1].data;
        var follows = !fresh && after.source != null && data.index != null && after.index === data.index + 1;
        if (!follows) piece = withoutTail(piece) + "\n\n";
      }
      var start = count(text, "\n"), place = { card: part.card, start: start, codeStart: start, codeIndent: 0 };
      if (data.kind === "rvt" && fresh) {
        var options = (data.definitions ? 1 : 0) + (data.table ? 1 : 0) + ((data.variations || []).length ? 1 : 0);
        place.codeStart = start + 2 + options - (/^\n*/.exec(data.code || "")[0].length);
        place.codeIndent = 3;
      } else if (data.kind === "rvt") {
        place.codeStart = start + (data.code_offset || 0);
        place.codeIndent = data.code_indent || 0;
      } else if (fresh) {
        place.codeStart = start - (/^\n*/.exec(data.text || "")[0].length);
      }
      text += piece;
      place.end = count(text, "\n") + (/\n$/.test(text) ? 0 : 1);
      places.push(place);
    });
    return { text: text, places: places };
  }

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

  // Draw a tab's diagnostics: squiggles in the card being edited, a list
  // under any other card, and a count on the tab
  function showProblems(path) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc || !st.places) return;
    var problems = st.problems || [];
    doc.classList.add("is-live");  // the diagnostics drawn when the page was made are out of date now
    st.places.forEach(function (place, n) {
      var last = n === st.places.length - 1;
      var own = problems.filter(function (p) {
        var line = p.range.start.line;
        return line >= place.start && (line < place.end || last);
      });
      var card = place.card, list = $(":scope > .ed-card__problems", card);
      if (list) list.remove();
      if (card._edit) {
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
      card.appendChild(list);
    });
    var errors = problems.filter(function (p) { return p.severity === 1; }).length;
    if (errors !== st.errors) { st.errors = errors; drawTabs(); }
  }

  // The names that complete where the cursor is in a block's editor
  function completions(card) {
    return function (context) {
      var word = context.matchBefore(NAME) || { from: context.pos, to: context.pos };
      var before = context.state.sliceDoc(Math.max(0, word.from - 1), word.from);
      if (!context.explicit && word.from === word.to && before !== "(") return null;
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
          from: word.from, validFor: /^[^\s()\[\]{}"';,]*$/,
          options: found.items.map(function (item) {
            return { label: item.label, type: TYPES[item.kind], detail: item.detail, info: item.documentation || null,
                     boost: 5 - Number((item.sortText || "5")[0]) };
          }),
        };
      });
    };
  }

  // Editing a card

  function field(card, name) { return $('[data-f="' + name + '"]', card); }

  function openCard(card, isNew) {
    if (card._edit) return;
    all(".ed-card.is-editing", card.parentNode).forEach(function (other) { closeCard(other, true); });
    var data = card._card, rvt = data.kind === "rvt";
    var edit = el("div", "ed-card__edit");
    if (rvt) {
      var fields = el("div", "ed-fields");
      var title = el("input", "ui-input ed-fields__title");
      title.dataset.f = "title";
      title.placeholder = "Title (optional): what these steps do";
      title.value = data.title || "";
      title.setAttribute("aria-label", "Block title");
      var variations = el("input", "ui-input ui-input--mono ed-fields__variations");
      variations.dataset.f = "variations";
      variations.placeholder = "every variation";
      variations.value = (data.variations || []).join(", ");
      variations.setAttribute("aria-label", "Only for these variations, separated by commas");
      variations.title = "Only for these variations, separated by commas. Empty: every variation.";
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
      var only = el("label", "ed-fields__only");
      only.appendChild(el("span", "ui-muted", "Only for"));
      only.appendChild(variations);
      fields.appendChild(only);
      edit.appendChild(fields);
    }
    var holder = el("div", "ed-cm");
    edit.appendChild(holder);
    var foot = el("div", "ed-card__foot");
    foot.appendChild(button("Done", "done", "ui-btn--primary"));
    foot.appendChild(button("Cancel", "cancel"));
    foot.appendChild(el("span", "ui-muted", "Esc or Ctrl+Enter when done"));
    edit.appendChild(foot);
    card.appendChild(edit);
    card.classList.add("is-editing");
    function done() { closeCard(card, true); return true; }
    var path = pathOf(card), typing;
    var view = window.CM.editor(holder, {
      text: rvt ? data.code || "" : data.text || "",
      language: rvt ? "rvt" : null,
      placeholder: rvt ? "(Verify ...)" : "Text, as reStructuredText",
      keys: [{ key: "Mod-Enter", run: done }, { key: "Escape", run: done }],
      extensions: rvt ? [window.CM.autocompletion({ override: [completions(card)] })] : [],
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

  // What a card being edited holds right now, as an edited card
  function current(card) {
    var data = card._card, text = card._edit.view.state.doc.toString();
    var next = { kind: data.kind, source: null, index: null, level: data.level || 0 };
    if (data.kind === "rvt") {
      next.code = text.replace(/\s+$/, "");
      next.title = field(card, "title").value.trim() || null;
      next.definitions = field(card, "definitions").checked;
      next.table = field(card, "table").checked;
      next.variations = field(card, "variations").value.split(",").map(function (v) { return v.trim(); }).filter(Boolean);
    } else {
      next.text = text.replace(/\s+$/, "");
    }
    return next;
  }

  // Close a card's editor; with `commit`, keep what it holds
  function closeCard(card, commit) {
    var edit = card._edit, path = pathOf(card);
    if (!edit) return Promise.resolve();
    var data = card._card, next = current(card);
    setTimeout(function () { if (states[path]) lspSync(path); }, 0);
    var was = data.kind === "rvt"
      ? [data.code || "", data.title || null, !!data.definitions, !!data.table, data.variations || []]
      : [data.text || ""];
    var now = data.kind === "rvt"
      ? [next.code, next.title, next.definitions, next.table, next.variations] : [next.text];
    edit.view.destroy();
    edit.element.remove();
    card._edit = null;
    card.classList.remove("is-editing");
    var empty = data.kind !== "rvt" && !next.text.trim();
    if ((!commit || empty) && edit.isNew) { card.remove(); return Promise.resolve(); }
    if (!commit || same(was, now)) return Promise.resolve();
    if (empty) { card.remove(); dirty(path); return Promise.resolve(); }
    card._card = next;
    var doc = docOf(path), view = $(".ed-card__view", card);
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

  function addCard(after, kind) {
    var data = kind === "rvt"
      ? { kind: "rvt", source: null, index: null, code: "", title: null, definitions: false, table: false, variations: [] }
      : { kind: "prose", source: null, index: null, text: "", level: 0 };
    var card = decorate(section(data, ""));
    after.parentNode.insertBefore(card, after.nextSibling);
    decorate(card);
    openCard(card, true);
  }

  // Saving

  function save(path, force) {
    var st = states[path], doc = docOf(path);
    if (!st || !doc || !st.dirty) return Promise.resolve();
    var open = all(".ed-card.is-editing", doc).map(function (card) { return closeCard(card, true); });
    return Promise.all(open).then(function () {
      say("Saving");
      return post(url(path, "editor/save"), {
        hash: st.baseHash, count: st.count, force: !!force,
        cards: cardsOf(doc).map(function (c) { return c._card; }),
      });
    }).then(function (response) {
      if (response.status === 409) {
        st.conflict = true;
        showConflict(path);
        say("Not saved: the file changed on disk");
        return;
      }
      if (!response.ok) { say("Couldn't save (" + response.status + ")"); return; }
      dropDraft(path);
      st.dirty = false;
      if (st.isNew) refreshTree();
      lspPost([{ jsonrpc: "2.0", method: "textDocument/didSave", params: { textDocument: { uri: lspUri(path) } } }]);
      return load(path).then(function () { if (active === path) say("Saved"); });
    }).catch(function () { say("Couldn't save: the server didn't answer"); });
  }

  function discard(path) {
    dropDraft(path);
    if (states[path].isNew) { closeTab(path); return Promise.resolve(); }  // it was never a file
    states[path].dirty = false;
    return load(path).then(function () { say("Edits discarded"); });
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
      if (!st.dirty && !all(".ed-card.is-editing", doc).length) { load(path); return; }
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
    post(url(path, "editor/diff"), { count: st.count, cards: cardsOf(doc).map(function (c) { return c._card; }) })
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
    else if (name === "delete") { if (card._edit) closeCard(card, false); card.remove(); dirty(path); }
    else if (name === "up" || name === "down") {
      var others = cardsOf(card.parentNode), at = others.indexOf(card);
      var swap = others[at + (name === "up" ? -1 : 1)];
      if (!swap) return;
      card.parentNode.insertBefore(card, name === "up" ? swap : swap.nextSibling);
      dirty(path);
    }
    else if (name === "add-prose" || name === "add-rvt") addCard(target.closest(".ed-add").parentNode.classList.contains("ed-card") ? card : target.closest(".ed-add"), name === "add-rvt" ? "rvt" : "prose");
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
    document.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && active && editable) {
        event.preventDefault();
        save(active);
      }
    });
    // Anything htmx redraws in a pane (another variation, the checked-in view) is scanned again
    document.body.addEventListener("htmx:afterSettle", function () {
      if (active && states[active]) scan(states[active].pane);
      var current = active && $('.ui-tree__row--file[data-open="' + window.CSS.escape(active) + '"]');
      if (current) current.setAttribute("aria-current", "true");
    });
    window.addEventListener("focus", function () { if (active) checkDisk(active); });
    window.addEventListener("beforeunload", function () { if (active && states[active] && states[active].dirty) keepDraft(active); });
    if (first || tabs.length) activate(first || tabs[0]);
    else drawTabs();
    // A link from a requirement's page: write a script for it
    if (editable && asked.get("new")) fileDialog("new", { requirement: asked.get("requirement") || "" });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
