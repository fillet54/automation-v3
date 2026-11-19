/* paper-ui's TeX line breaks, worked out in the reader's browser (html_theme_options line_breaks = "live").
 *
 * One plain script: no build step, no dependencies (hyph-en-us.js, loaded before it, has the hyphenation
 * patterns). Once the fonts have loaded, it measures each paragraph's words with canvas (no DOM reads per
 * word, so no reflow), finds where they hyphenate (Liang's algorithm with TeX's patterns), breaks the lines
 * with the Knuth-Plass rules at the paragraph's width now, and splits it into justified .ui-line spans
 * (docs.css). A resize, or a change of layout, breaks the lines again from the same measurements. A paragraph
 * whose lines come out too long for it is left to the browser.
 *
 * The parts, in order: Knuth-Plass (layout), hyphenation (hyphens), the page. In Node (the tests), require()
 * gives { layout, hyphens } and nothing touches a page.
 *
 * window.__uiLiveLines: what it did and how long it took; __uiLiveLines.why() counts why paragraphs were left
 * to the browser.
 */
(function (global) {
  "use strict";

  // ---------------------------------------------------------------------------------------------- Knuth-Plass
  //
  // TeX's line breaks (Knuth and Plass, "Breaking paragraphs into lines", 1981): breaks, layout, spacing.
  // layout({width, widths, items}) takes a paragraph measured as items ["b", width] (a box), ["g", width, offset]
  // (a space), ["h", width, offset] (a place to hyphenate, with the hyphen's width) and ["x", 0, offset] (after a
  // hyphen in the text); widths: the first lines' own lengths (beside a float). It returns {breaks: [[offset, kind]...], spacing: [per line]}, or null.

  const SLACK = 0.5;
  const STRETCH = 1 / 2, SHRINK = 1 / 3;
  const HYPHEN_PENALTY = 50;
  const LINE_PENALTY = 10;
  const FLAGGED_DEMERITS = 3000;
  const FITNESS_DEMERITS = 100;
  const RATIOS = [1, 2, 4];
  const INF = Infinity;

  const BOX = 0, GLUE = 1, PENALTY = 2;

  // `width(line)`: how long line `line` (from 0) may be; the lines from `irregular` on are all as long
  function breaks(items, width, maxRatio, irregular = 0) {
    const n = items.length;
    const W = new Float64Array(n + 1), Y = new Float64Array(n + 1), Z = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) {
      const it = items[i];
      W[i + 1] = W[i] + (it.type !== PENALTY ? it.width : 0);
      Y[i + 1] = Y[i] + (it.type === GLUE ? it.stretch : 0);
      Z[i + 1] = Z[i] + (it.type === GLUE ? it.shrink : 0);
    }
    const lineStart = (b) => {
      let s = b + 1;
      while (s < n && items[s].type !== BOX && !(items[s].type === PENALTY && items[s].penalty === -INF)) s++;
      return s;
    };
    // an active node: {at, start, line (the lines before it), fitness, demerits, prev, ratio}
    let active = [{ at: -1, start: 0, line: 0, fitness: 1, demerits: 0, prev: null, ratio: 0 }];
    for (let b = 0; b < n; b++) {
      const it = items[b];
      if (it.type === BOX) continue;
      let penalty, flagged, extra;
      if (it.type === GLUE) {
        if (b === 0 || items[b - 1].type !== BOX) continue;
        penalty = 0; flagged = false; extra = 0;
      } else {
        if (it.penalty === INF) continue;
        penalty = it.penalty; flagged = it.flagged; extra = it.width;
      }
      const best = new Map();
      const still = [];
      for (const node of active) {
        const length = width(node.line);
        const natural = W[b] - W[node.start] + extra;
        let ratio;
        if (natural < length) {
          const stretch = Y[b] - Y[node.start];
          ratio = stretch > 0 ? (length - natural) / stretch : INF;
        } else if (natural > length) {
          const shrink = Z[b] - Z[node.start];
          ratio = shrink > 0 ? (length - natural) / shrink : -INF;
        } else ratio = 0;
        if (ratio >= -1 && penalty !== -INF) still.push(node);
        if (ratio < -1 || ratio > maxRatio) continue;
        const badness = 100 * Math.abs(ratio) ** 3;
        let d = (LINE_PENALTY + badness) ** 2;
        if (penalty >= 0) d += penalty ** 2;
        else if (penalty > -INF) d -= penalty ** 2;
        const prevFlagged = node.at >= 0 && items[node.at].type === PENALTY && items[node.at].flagged;
        if (flagged && prevFlagged) d += FLAGGED_DEMERITS;
        const klass = ratio < -0.5 ? 0 : ratio <= 0.5 ? 1 : ratio <= 1 ? 2 : 3;
        if (Math.abs(klass - node.fitness) > 1) d += FITNESS_DEMERITS;
        const total = node.demerits + d;
        // while lines differ in length, breaks after different numbers of lines are different ways on
        const key = node.line + 1 < irregular ? `${klass} ${node.line + 1}` : klass;
        if (!best.has(key) || total < best.get(key).demerits) {
          best.set(key, { at: b, start: lineStart(b), line: node.line + 1, fitness: klass, demerits: total, prev: node, ratio });
        }
      }
      active = still.concat([...best.values()]);
      if (!active.length) return null;
    }
    const end = active.filter((node) => node.at === n - 1);
    if (!end.length) return null;
    let node = end.reduce((a, c) => (c.demerits < a.demerits ? c : a));
    const lines = [];
    while (node.prev) {
      lines.push([node.at, node.ratio]);
      node = node.prev;
    }
    return lines.reverse();
  }

  function spacing(items, lines) {
    const out = [];
    let start = 0;
    for (const [b, ratio] of lines) {
      const spaces = items.slice(start, b).filter((it) => it.type === GLUE && it.stretch !== INF);
      out.push(ratio < 0 && spaces.length
        ? Math.round(ratio * spaces.reduce((s, g) => s + g.shrink, 0) / spaces.length * 1000) / 1000 : 0);
      start = b + 1;
    }
    return out;
  }

  // measured.widths: the first lines' lengths where they differ (beside a float); then measured.width
  // ratios: how far a space may stretch, tried in turn (TeX's first pass, without hyphens: [1])
  function layout(measured, ratios = RATIOS) {
    const items = [], offsets = [];
    for (const [kind, width, at] of measured.items) {
      if (kind === "b") items.push({ type: BOX, width });
      else if (kind === "g") items.push({ type: GLUE, width, stretch: width * STRETCH, shrink: width * SHRINK });
      else items.push({ type: PENALTY, width, penalty: HYPHEN_PENALTY, flagged: true });
      offsets.push(at === undefined ? null : [at, kind]);
    }
    while (items.length && items[items.length - 1].type !== BOX) {   // a space before </p> is no break
      items.pop();
      offsets.pop();
    }
    items.push({ type: GLUE, width: 0, stretch: INF, shrink: 0 }, { type: PENALTY, width: 0, penalty: -INF, flagged: false });
    const first = measured.widths || [];
    const width = (line) => (line < first.length ? first[line] : measured.width) - SLACK;
    let lines = null;
    for (const ratio of ratios) {
      lines = breaks(items, width, ratio, first.length);
      if (lines) break;
    }
    // one line as it is: the browser sets it the same (one that had to shrink to be one line, it wouldn't)
    if (!lines || (lines.length < 2 && lines[0][1] >= 0)) return null;
    return { breaks: lines.slice(0, -1).map(([b]) => offsets[b]), spacing: spacing(items, lines) };
  }

  // ---------------------------------------------------------------------------------------------- hyphenation
  //
  // Where an English word hyphenates: Liang's algorithm, as TeX does it, with TeX's American English patterns
  // and exceptions (hyph-en-us.js: global.paperUiHyphenation). hyphens("computer") -> [3, 5]: the hyphens go
  // before those letters. The patterns are read the first time a word is asked about, so a page that needs no
  // hyphens pays nothing for them.

  const HYPHENATION = () => {
    const data = global.paperUiHyphenation || (typeof require === "function" ? require("./hyph-en-us.js") : null);
    return data ? { PATTERNS: data.patterns, EXCEPTIONS: data.exceptions } : { PATTERNS: "", EXCEPTIONS: "" };
  };

  const LEFT = 2, RIGHT = 3;
  const DIGITS = /\d/g;
  let patterns = null;    // a pattern's letters -> the pattern: ".ach" -> ".ach4"
  let exceptions = null;  // word -> its hyphens
  let longest = 0;

  function load() {
    const { PATTERNS, EXCEPTIONS } = HYPHENATION();
    // a pattern's letters -> the pattern; its digits are read only when it matches (most never do on a page)
    patterns = new Map();
    for (const pattern of PATTERNS.split("\n")) {
      if (!pattern) continue;
      const letters = pattern.replace(DIGITS, "");
      patterns.set(letters, pattern);
      if (letters.length > longest) longest = letters.length;
    }
    exceptions = new Map();
    const lines = EXCEPTIONS.split("\n").filter((line) => !line.startsWith("%"));
    for (const word of lines.join(" ").split(/\s+/)) {
      if (!word) continue;
      const at = [];
      let n = 0;
      for (const ch of word) {
        if (ch === "-") at.push(n);
        else n++;
      }
      exceptions.set(word.replace(/-/g, ""), at);
    }
  }

  function hyphens(word) {
    if (word.length < LEFT + RIGHT) return [];
    if (!patterns) load();
    const lower = word.toLowerCase();
    if (exceptions.has(lower)) return exceptions.get(lower);
    const text = `.${lower}.`;
    const levels = new Uint8Array(text.length + 1);
    for (let i = 0; i < text.length; i++) {
      for (let j = i + 1; j <= Math.min(text.length, i + longest); j++) {
        const found = patterns.get(text.slice(i, j));
        if (!found) continue;
        // each digit is the level before the letter at k (counting the pattern's letters from i)
        for (let c = 0, k = i; c < found.length; c++) {
          const d = found.charCodeAt(c) - 48;
          if (d >= 0 && d <= 9) { if (d > levels[k]) levels[k] = d; }
          else k++;
        }
      }
    }
    // levels[i + 1] is the level before the word's letter i (the text starts with ".")
    const out = [];
    for (let at = LEFT; at <= word.length - RIGHT; at++) if (levels[at + 1] % 2) out.push(at);
    return out;
  }

  // ---------------------------------------------------------------------------------------------- the page

  if (typeof module === "object" && module.exports) {
    module.exports = { layout, hyphens };
    return;
  }
  const solve = layout;

  if (!("ResizeObserver" in window) || !document.fonts) return;
  const root = document.documentElement;
  const stats = (window.__uiLiveLines = { passes: [], misfits: 0, set: 0, skipped: 0 });
  const NOT_IN = "table, figcaption, svg, nav, header, footer, pre, button, label, .ui-sidenote";
  const paragraphs = [...document.querySelectorAll(".ui-doc p")].filter((p) => !p.parentElement.closest(NOT_IN));
  if (!paragraphs.length) return;
  const english = /^en\b/i.test(root.lang || "en");

  const REPLACED = new Set(["IMG", "SVG", "VIDEO", "CANVAS", "IFRAME", "OBJECT", "EMBED", "INPUT", "MATH", "SELECT", "TEXTAREA", "BUTTON"]);
  const BLOCKS = new Set(["block", "flex", "grid", "table", "list-item", "flow-root"]);
  const px = (v) => parseFloat(v) || 0;

  // ------------------------------------------------------------------------------------------ measuring (canvas)
  //
  // A word's width comes from canvas measureText, in the font its element has. Widths and hyphens are kept in the browser between
  // pages (localStorage, STORE): the next page measures only the words it hasn't seen. The store is the
  // browser's own, so its widths are that browser's; it is dropped when the browser changes, when a line
  // measured from it doesn't fit, and when it grows past MAX_STORED.

  const STORE = "paper-ui-lines", VERSION = 1, MAX_STORED = 40000;
  let store = null;
  try {
    const kept = JSON.parse(localStorage.getItem(STORE));
    if (kept && kept.v === VERSION && kept.ua === navigator.userAgent && kept.n < MAX_STORED) store = kept;
  } catch (e) { /* none kept, or no storage: measure everything */ }
  store ||= { v: VERSION, ua: navigator.userAgent, n: 0, fonts: [], widths: {}, hyphens: {} };
  let dirty = false;
  stats.stored = store.n;
  stats.measuredWords = 0;
  function save() {
    if (!dirty) return;
    dirty = false;
    try { localStorage.setItem(STORE, JSON.stringify(store)); } catch (e) { /* full, or private: next time */ }
  }
  function forget() {
    store = { v: VERSION, ua: navigator.userAgent, n: 0, fonts: [], widths: {}, hyphens: {} };
    try { localStorage.removeItem(STORE); } catch (e) {}
  }

  const context = new OffscreenCanvas(1, 1).getContext("2d");
  let contextFont = "";
  function freshWidth(text, font, letterSpacing) {
    stats.measuredWords++;
    const key = `${font}|${letterSpacing}`;
    if (contextFont !== key) {
      context.font = font;
      context.letterSpacing = `${letterSpacing}px`;
      contextFont = key;
    }
    return context.measureText(text).width;
  }
  // what a width is kept under: the font (a number, its place in store.fonts), letter spacing and text
  const fontKeys = new Map();
  function keyOf(font, letterSpacing) {
    const k = `${font}|${letterSpacing}`;
    let n = fontKeys.get(k);
    if (n === undefined) {
      n = store.fonts.indexOf(k);
      if (n < 0) n = store.fonts.push(k) - 1;
      fontKeys.set(k, n);
    }
    return n + "|";
  }
  const fontOf = (style) => [style.fontStyle, style.fontVariantCaps === "small-caps" ? "small-caps" : "",
    style.fontWeight, style.fontSize, style.fontFamily].filter(Boolean).join(" ");
  function textWidth(text, font, letterSpacing) {
    const k = keyOf(font, letterSpacing) + text;
    let w = store.widths[k];
    if (w === undefined) {
      w = store.widths[k] = Math.round(freshWidth(text, font, letterSpacing) * 1000) / 1000;
      store.n++;
      dirty = true;
    }
    return w;
  }
  const spaceWidth = (font, letterSpacing) => textWidth(" ", font, letterSpacing);
  function hyphensOf(word) {
    if (!english || word.length < 5) return [];
    let found = store.hyphens[word];
    if (!found) {
      found = store.hyphens[word] = hyphens(word);
      store.n++;
      dirty = true;
    }
    return found;
  }
  // a word's items: its pieces, between the places it may break (after a hyphen in it, and where it hyphenates)
  function wordItems(out, piece, whole, font, ls, at, breakable, hyphenate) {
    const points = [];
    if (breakable) {
      for (const m of piece.matchAll(/(?<=[\p{L}\p{N}]-)(?=\p{L})/gu)) points.push([m.index, "x"]);
      if (hyphenate) for (const m of piece.matchAll(/\p{L}+/gu)) for (const h of hyphensOf(m[0])) points.push([m.index + h, "h"]);
      points.sort((a, b) => a[0] - b[0]);
    }
    let lastWidth = 0;
    for (const [i, kind] of points) {
      const w = textWidth(piece.slice(0, i), font, ls);    // from the word's start: kerning stays in
      out.push(["b", w - lastWidth]);
      out.push([kind, kind === "h" ? textWidth("-", font, ls) : 0, at + i]);
      lastWidth = w;
    }
    out.push(["b", whole - lastWidth]);
  }
  // a measured paragraph's items with the places its words hyphenate: made from what was measured, without
  // the page, the first time TeX's first pass (no hyphens) can't set it
  function hyphenated(m) {
    if (m.hyphenated) return m.hyphenated;
    const out = [];
    let i = 0;
    for (const w of m.words) {
      while (i < w.index) out.push(m.items[i++]);
      wordItems(out, w.piece, w.whole, w.font, w.ls, w.at, true, true);
      i += w.count;
    }
    while (i < m.items.length) out.push(m.items[i++]);
    return (m.hyphenated = out);
  }
  function pseudo(el, which, font, ls) {
    const content = getComputedStyle(el, which).content;
    if (!content || content === "none" || content === "normal") return 0;
    const m = content.match(/^"(.*)"$/);
    return m ? textWidth(m[1], font, ls) : 0;
  }

  class Skip extends Error {}

  // the paragraph's items, measured in the page
  function measure(p) {
    const style = getComputedStyle(p);
    if (!["start", "left", "justify"].includes(style.textAlign) || style.whiteSpace !== "normal"
        || px(style.textIndent) !== 0) return { skip: "centred, pre-formatted or indented" };
    const items = [], words = [];         // words: those that may hyphenate, and where their items are
    let offset = 0, collapse = true;    // spaces collapse at the start and after a space

    function text(node, font, ls, upper, breakable) {
      const data = node.data;
      const tokens = [...data.matchAll(/[ \t\n\r\f]+|[^ \t\n\r\f]+/g)];
      for (const match of tokens) {
        const start = match.index;
        let piece = match[0];
        if (/^[ \t\n\r\f]/.test(piece)) {
          if (!collapse) items.push(breakable ? ["g", spaceWidth(font, ls), offset + start] : ["b", spaceWidth(font, ls)]);
          collapse = true;
          continue;
        }
        collapse = false;
        if (upper) piece = piece.toUpperCase();
        const whole = textWidth(piece, font, ls);
        const index = items.length;
        wordItems(items, piece, whole, font, ls, offset + start, breakable, false);
        if (breakable && english && /\p{L}{5}/u.test(piece)) {
          words.push({ index, count: items.length - index, piece, whole, font, ls, at: offset + start });
        }
      }
      offset += data.length;
    }

    function walk(parent, pstyle, breakable) {
      const font = fontOf(pstyle), ls = px(pstyle.letterSpacing), upper = pstyle.textTransform === "uppercase";
      for (const node of parent.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) { text(node, font, ls, upper, breakable); continue; }
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        const s = getComputedStyle(node);
        if (s.display === "none" || s.float !== "none") { offset += node.textContent.length; continue; }
        if (node.tagName === "BR" || BLOCKS.has(s.display) || s.position === "absolute" || s.position === "fixed") {
          throw new Skip(node.tagName === "BR" ? "a line break in it" : `a block in it (${node.tagName.toLowerCase()})`);
        }
        const margins = px(s.marginLeft) + px(s.marginRight);
        // one box: an image, a key, an inline block, a formula (MathJax's mjx-container: a custom element)
        if (s.display !== "inline" || REPLACED.has(node.tagName.toUpperCase()) || node.tagName.includes("-")) {
          items.push(["b", node.getBoundingClientRect().width + margins]);   // one box: its size is the page's
          offset += node.textContent.length;
          collapse = false;
          continue;
        }
        const f = fontOf(s), l = px(s.letterSpacing);
        const left = px(s.marginLeft) + px(s.paddingLeft) + px(s.borderLeftWidth) + pseudo(node, "::before", f, l);
        const right = px(s.marginRight) + px(s.paddingRight) + px(s.borderRightWidth) + pseudo(node, "::after", f, l);
        const whole = left > 0.01 || right > 0.01 || s.whiteSpace !== "normal";
        if (left > 0.01) { items.push(["b", left]); collapse = false; }
        walk(node, s, breakable && !whole);
        if (right > 0.01) { items.push(["b", right]); collapse = false; }
      }
    }

    try {
      walk(p, style, true);
    } catch (e) {
      if (e instanceof Skip) return { skip: e.message };
      throw e;
    }
    return { items, words, length: offset };
  }

  // ------------------------------------------------------------------------------------------------------ lines

  const original = new Map();   // p -> its child nodes as the page had them
  const shown = new Map();      // p -> the breaks its spans are for (JSON)
  const measured = new Map();   // p -> Map(font size -> its items, or null)
  const misfits = new Map();    // p -> the width its lines didn't fit at
  const reasons = new Map();    // p -> why it is left to the browser now
  function skip(p, why) {
    restore(p);
    reasons.set(p, why);
  }
  // why paragraphs are left to the browser: {reason: count}, for the console
  stats.why = () => [...reasons.values()].reduce((o, r) => ({ ...o, [r]: (o[r] || 0) + 1 }), {});

  function position(p, at) {
    const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    let seen = 0, node;
    while ((node = walker.nextNode())) {
      if (at < seen + node.data.length) {
        if (at > seen) return [node, at - seen];
        // at the start of an element's text: before the element, so the line before keeps no empty copy of it
        let n = node;
        while (n.parentNode !== p && n.parentNode.firstChild === n) n = n.parentNode;
        return [n.parentNode, [...n.parentNode.childNodes].indexOf(n)];
      }
      seen += node.data.length;
    }
    return [p, p.childNodes.length];
  }

  function restore(p) {
    if (!shown.has(p)) return;
    p.replaceChildren(...original.get(p).map((n) => n.cloneNode(true)));
    p.classList.remove("ui-lines");
    shown.delete(p);
  }

  function divide(p, { breaks, spacing }) {
    if (!original.has(p)) original.set(p, [...p.childNodes].map((n) => n.cloneNode(true)));
    const text = p.textContent;
    const starts = [0, ...breaks.map(([at, kind]) => {
      if (kind === "g") while (at < text.length && /\s/.test(text[at])) at++;
      return at;
    })];
    const range = document.createRange();
    const pieces = [];
    for (let i = starts.length - 1; i >= 0; i--) {
      range.setStart(...position(p, starts[i]));
      range.setEnd(p, p.childNodes.length);
      pieces.unshift(range.extractContents());
    }
    p.replaceChildren();
    pieces.forEach((piece, i) => {
      const line = document.createElement("span");
      line.className = "ui-line";
      if (spacing[i]) line.style.setProperty("--ui-line-ws", `${spacing[i]}px`);
      line.append(piece);
      if (i < breaks.length && breaks[i][1] === "h") {
        const hyphen = document.createElement("span");
        hyphen.className = "ui-line__hy";
        line.append(hyphen);
      }
      p.append(line);
    });
    const ids = new Set();
    for (const el of p.querySelectorAll("[id]")) {
      if (ids.has(el.id)) el.removeAttribute("id");
      else ids.add(el.id);
    }
    p.classList.add("ui-lines");
  }

  // ------------------------------------------------------------------------------------------ floats
  //
  // Text beside a float (a sidebar, a citation's label, a figure set to one side) runs in shorter lines, as far
  // down as the float reaches: those lines get their own lengths. Their places come from the line height, so
  // a line made taller (a key, a formula) can throw them out; the check after setting the lines catches that.

  // whatever floats in the document, with its margins (they keep text away too)
  const floating = () => [...document.querySelectorAll(".ui-doc *")].flatMap((el) => {
    const s = getComputedStyle(el);
    return s.float === "none" ? [] : [[el, [px(s.marginTop), px(s.marginRight), px(s.marginBottom), px(s.marginLeft)]]];
  });
  const places = (floats) => floats.map(([el, [mt, mr, mb, ml]]) => {
    const r = el.getBoundingClientRect();
    return [el, { top: r.top - mt, right: r.right + mr, bottom: r.bottom + mb, left: r.left - ml }];
  });
  // a paragraph in a float (a margin note) is left ragged, as margin notes are set
  const inFloat = (p, boxes) => boxes.some(([el]) => el.contains(p));
  const lineHeight = (style) => parseFloat(style.lineHeight) || 1.2 * parseFloat(style.fontSize);

  // the lengths of a paragraph's first lines beside floats: [] when none is beside it, null when one leaves
  // too little room
  function besideFloats(p, rect, style, width, boxes) {
    const near = boxes.filter(([el, b]) => !p.contains(el) && !el.contains(p)
      && b.bottom > rect.top && b.top < rect.bottom && b.right > rect.left && b.left < rect.right);
    if (!near.length) return [];
    const left = rect.left + px(style.borderLeftWidth) + px(style.paddingLeft), right = left + width;
    const lh = lineHeight(style);
    const reach = Math.max(...near.map(([, b]) => b.bottom));
    const widths = [];
    for (let y = rect.top + px(style.borderTopWidth) + px(style.paddingTop); y < reach && widths.length < 100; y += lh) {
      let from = left, to = right;
      for (const [, b] of near) {
        if (b.bottom <= y || b.top >= y + lh) continue;
        if (b.left + b.right < left + right) from = Math.max(from, b.right);     // on the left
        else to = Math.min(to, b.left);
      }
      widths.push(to - from);
    }
    return widths.some((w) => w < Math.min(width, 160)) ? null : widths;
  }

  // a line longer than its room: past its end, into a float, or pushed down below one (a taller line box)
  const range = document.createRange();
  function overflowing(p, boxes) {
    const near = boxes.filter(([el]) => !p.contains(el) && !el.contains(p)).map(([, b]) => b);
    const lh = lineHeight(getComputedStyle(p));
    return [...p.children].some((line) => {
      if (!line.classList.contains("ui-line")) return false;
      const box = line.getBoundingClientRect();
      if (near.length && box.height > lh * 1.5 && !line.querySelector("img, svg, mjx-container, kbd")) return true;
      const end = box.right + 0.5;
      const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if (node.parentElement.closest(".ui-sidenote")) continue;
        range.selectNodeContents(node);
        for (const r of range.getClientRects()) {
          if (r.right > end) return true;
          if (near.some((b) => r.right > b.left + 0.5 && r.left < b.right - 0.5 && r.bottom > b.top + 1 && r.top < b.bottom - 1)) return true;
        }
      }
      return false;
    });
  }

  // ------------------------------------------------------------------------------------------ passes
  //
  // A pass sets every paragraph's lines for the page as it is now. The paragraphs in view (and just around it)
  // go first, then the rest nearest first, in slices of BUDGET ms, one a frame, so the page never stalls; a new
  // pass (a resize, a layout change) drops what is left of the last one.

  const BUDGET = 8;           // ms a frame
  const AROUND = 160;         // px above and below the viewport that count as in view
  let generation = 0;

  function update(reason) {
    if (document.fonts.status !== "loaded") return;
    const pass = ++generation;
    const t0 = performance.now();
    const record = { reason, layout: root.getAttribute("data-ui-layout"), paragraphs: paragraphs.length,
      measured: 0, solved: 0, firstPass: 0, changed: 0, misfit: 0, frames: 0,
      ms: { measure: 0, solve: 0, dom: 0, check: 0, visible: 0, total: 0, work: 0 } };
    stats.passes.push(record);
    // what floats in the document, once a pass (their places, once a slice)
    const floats = floating();
    let besideAny = false;
    const top = -AROUND, bottom = innerHeight + AROUND;
    const distance = (r) => (r.bottom < top ? top - r.bottom : r.top > bottom ? r.top - bottom : 0);
    const queue = paragraphs.map((p) => [p, distance(p.getBoundingClientRect())]).sort((a, b) => a[1] - b[1]);
    const visible = queue.filter(([, d]) => d === 0).length;
    let processed = 0;

    function slice() {
      if (pass !== generation) return;          // a newer pass took over
      const s0 = performance.now();
      record.frames++;
      const boxes = places(floats);
      const done = [];
      // a few paragraphs at a time: read them all, then change them, so the page is laid out once a batch
      while (queue.length && performance.now() - s0 < BUDGET) {
        const batch = queue.splice(0, 8).map(([p]) => {
          const style = getComputedStyle(p);
          const width = p.clientWidth - px(style.paddingLeft) - px(style.paddingRight), rect = p.getBoundingClientRect();
          return { p, width, size: style.fontSize + style.fontFamily, rect,
                   widths: width && !inFloat(p, boxes) ? besideFloats(p, rect, style, width, boxes) : [] };
        });
        for (const { p, width, size, rect, widths } of batch) {
          processed++;
          const why = !width ? "hidden" : inFloat(p, boxes) ? "in a float (the margin)"
            : !widths ? "too little room beside a float" : misfits.get(p) === width ? "its lines didn't fit" : null;
          if (why) { skip(p, why); continue; }
          if (widths.length) besideAny = true;
          // as TeX does: first without hyphens, keeping every space within its stretch; only if that can't be
          // done, again with the places words hyphenate (worked out, and their pieces measured, only then)
          if (!measured.has(p)) measured.set(p, new Map());
          const sizes = measured.get(p);
          if (!sizes.has(size)) {
            const a = performance.now();
            restore(p);                         // measure the paragraph as written, not its spans
            sizes.set(size, measure(p));
            record.measured++;
            record.ms.measure += performance.now() - a;
          }
          const m = sizes.get(size);
          if (m.skip) { skip(p, m.skip); continue; }
          let a = performance.now();
          let lines = solve({ width, widths, items: m.items }, [1]);
          if (lines) record.firstPass++;
          else lines = solve({ width, widths, items: hyphenated(m) });
          record.ms.solve += performance.now() - a;
          record.solved++;
          if (!lines) { skip(p, "one line, or no good breaks"); continue; }
          const k = JSON.stringify(lines);                // the breaks and the lines' spacing
          reasons.delete(p);
          if (shown.get(p) === k) continue;
          const b = performance.now();
          restore(p);
          divide(p, lines);
          shown.set(p, k);
          record.changed++;
          record.ms.dom += performance.now() - b;
          done.push([p, width]);
        }
      }
      // check: a line longer than its paragraph means the canvas and the page disagree
      const c = performance.now();
      const after = done.length ? places(floats) : [];
      for (const [p, width] of done) {
        if (shown.has(p) && overflowing(p, after)) {
          misfits.set(p, width);
          skip(p, "its lines didn't fit");
          forget();                             // perhaps a width kept from before is wrong now
          record.misfit++;
          stats.misfits++;
          (stats.misfitText ||= []).push(`${record.layout} ${width}: ${p.textContent.slice(0, 50)}`);
        }
      }
      const now = performance.now();
      record.ms.check += now - c;
      record.ms.work += now - s0;
      if (!record.ms.visible && processed >= visible) record.ms.visible = now - t0;   // the ones in view are set
      if (queue.length) requestAnimationFrame(slice);
      else {
        record.ms.total = now - t0;
        for (const k in record.ms) record.ms[k] = +record.ms[k].toFixed(2);
        stats.set = shown.size;
        stats.skipped = paragraphs.length - shown.size;
        stats.done = true;
        document.dispatchEvent(new CustomEvent("ui-lines", { detail: record }));
        ("requestIdleCallback" in window ? requestIdleCallback : setTimeout)(save);
        // the lines beside floats were placed from where things were; setting the paragraphs above them may
        // have moved them, so look once more (with nothing to measure, it is quick)
        if (besideAny && reason !== "settle") later("settle")();
      }
    }
    stats.done = false;
    slice();
  }

  stats.debug = { measure, solve, divide, restore, reason: (p) => reasons.get(p) };     // for the console

  let queued = false;
  const later = (reason) => () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; update(reason); });
  };
  // MathJax rewrites the paragraphs with formulas in them: measure them once it has
  const typeset = () => window.MathJax?.startup?.promise || Promise.resolve();
  const math = document.querySelector(".ui-doc .math, .ui-doc mjx-container");
  Promise.all([document.fonts.ready, math ? new Promise((done) => (document.readyState === "complete" ? done() : addEventListener("load", done))).then(typeset) : null]).then(() => {
    update("load");
    const page = document.querySelector(".ui-doc") || document.body;
    let last = page.clientWidth;
    new ResizeObserver(() => { if (page.clientWidth !== last) { last = page.clientWidth; later("resize")(); } }).observe(page);
    document.fonts.addEventListener("loadingdone", later("fonts"));
    document.addEventListener("ui-layout", later("layout"));
  });
})(typeof window === "undefined" ? globalThis : window);
