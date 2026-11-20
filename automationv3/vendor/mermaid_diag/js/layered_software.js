/* layered-software: a mermaid-diag diagram type for software architecture drawn as partitions (address spaces,
 * side by side), each a stack of layers of components, standing on full-width bars (framework, OS, hardware).
 *
 *   layered-software
 *     title Flight software
 *     partition NET "Network Partition"
 *       ETH UDP TCP DNS
 *     end
 *     partition CRIT "Critical Partition"
 *       layer APP "Application"
 *         FMS["Flight Mgmt"] NAV["Nav Display"]:::accent MSN
 *       end
 *       layer SYS "System" columns 8
 *         SCH TMR EVT MSG
 *       end
 *       bar RTCF "RTCF Framework"
 *     end
 *     layer KDRV "OS Drivers"
 *       ENET SER FLASH
 *     end
 *     bar OS "Green Hills INTEGRITY"
 *     bar HW "Target Hardware" :::ghost
 *
 * Statements: `title`, `accTitle:`, `accDescr:`, `partition [ID] ["Label"] [columns N] [:::tone]` ... `end`,
 * `layer [ID] ["Label"] [columns N] [:::tone]` ... `end` and `bar [ID] ["Label"] [:::tone]` (inside a partition
 * they span that partition; outside, they span them all, above the partitions if they come before the first one
 * and below otherwise), `columns N` on a line of its own, and
 * components: `ID`, `ID["Label"]`, `"Label"`, each optionally `:::tone`, several to a line. Components placed
 * straight in a partition form a layer without a label.
 *
 * Styling and links, as in flowcharts (anywhere in the diagram, for anything with an ID):
 *   classDef name fill:#fde,stroke:#a33,color:#300      `:::name` or `class A,B name` applies it; any class works
 *   class FMS,NAV name                                  (the tones are classes too)
 *   style FMS fill:#fde,stroke-dasharray:4 3            one element
 *   click FMS "https://docs/fms" "Tooltip" _blank       a link (`click FMS href "url"` also works)
 * `color`, `font-weight` and `font-style` go to the label, the rest to the box.
 *
 * Layout: a layer's components share one cell width (its widest label) and fill rows of the partition's width,
 * at most `maxColumns` (10) to a row unless the layer says `columns N`.
 * The tallest partition keeps up to `maxColumns` components a row; the others take the fewest columns that keep
 * them no taller, so a small partition becomes a narrow column. All partitions are drawn the same height,
 * with any spare height above their trailing bars so the bars line up.
 *
 * mermaid-diag registers it with Mermaid (driver.js); the definition is globalThis.__mdLayeredSoftware.
 */
(function () {
  "use strict";

  const TYPE = "layered-software";

  // ---- parser ------------------------------------------------------------------------------------------------
  class LsError extends Error {
    constructor(message, line) {
      super(line ? `Parse error on line ${line}: ${message}` : message);
      this.name = "LayeredSoftwareError";
    }
  }

  const TOKEN = /\s*(?:(:::)([\w-]+)|"([^"]*)"|([A-Za-z_][\w.-]*)(?:\["([^"]*)"\]|\[([^\]"]*)\])?|(\d+)|(\S))/y;

  function tokenize(text, line) {
    const out = [];
    TOKEN.lastIndex = 0;
    let m;
    while (TOKEN.lastIndex < text.length && (m = TOKEN.exec(text))) {
      if (m[0].trim() === "") break;
      if (m[1]) out.push({ kind: "tone", value: m[2] });
      else if (m[3] !== undefined) out.push({ kind: "string", value: m[3] });
      else if (m[4]) out.push({ kind: "id", value: m[4], label: m[5] ?? m[6] });
      else if (m[7]) out.push({ kind: "number", value: Number(m[7]) });
      else throw new LsError(`unexpected "${m[8]}"`, line);
    }
    return out;
  }

  let seq = 0;
  const autoId = (prefix) => `${prefix}${++seq}`;

  // [ID] ["Label"] [columns N] [:::class...] -> {id, label, columns, classes}
  function header(tokens, line, prefix) {
    const h = { id: null, label: null, columns: null, classes: [] };
    let i = 0;
    if (tokens[i]?.kind === "id" && tokens[i].value !== "columns") {
      h.id = tokens[i].value;
      if (tokens[i].label !== undefined) h.label = tokens[i].label;
      i++;
    }
    if (tokens[i]?.kind === "string") h.label = tokens[i++].value;
    while (i < tokens.length) {
      const t = tokens[i++];
      if (t.kind === "id" && t.value === "columns") {
        if (tokens[i]?.kind !== "number" || tokens[i].value < 1) throw new LsError("columns needs a number", line);
        h.columns = tokens[i++].value;
      } else if (t.kind === "tone") h.classes.push(t.value);
      else if (t.kind === "string" && h.label === null) h.label = t.value;
      else throw new LsError(`unexpected "${t.value}"`, line);
    }
    if (h.label === null) h.label = h.id ?? "";
    if (h.id === null) h.id = autoId(prefix);
    return h;
  }

  function components(tokens, line) {
    const out = [];
    for (const t of tokens) {
      if (t.kind === "tone") {
        if (!out.length) throw new LsError(":::class must follow a component", line);
        out[out.length - 1].classes.push(t.value);
      } else if (t.kind === "id") out.push({ id: t.value, label: t.label ?? t.value, classes: [] });
      else if (t.kind === "string") out.push({ id: autoId("c"), label: t.value, classes: [] });
      else throw new LsError(`unexpected "${t.value}"`, line);
    }
    return out;
  }

  const CLASS_NAME = /^[A-Za-z_][\w-]*$/;
  const TEXT_PROPS = new Set(["color", "font-weight", "font-style", "text-decoration"]);

  // "fill:#f9f,stroke:#333,stroke-width:2px" -> {box: [[prop, value]...], text: [...]}; commas inside (...) stay.
  function styleProps(spec, line) {
    const out = { box: [], text: [] };
    let depth = 0, cur = "";
    const parts = [];
    for (const ch of spec) {
      if (ch === "(") depth++;
      if (ch === ")") depth--;
      if (ch === "," && depth === 0) { parts.push(cur); cur = ""; } else cur += ch;
    }
    parts.push(cur);
    for (const part of parts) {
      if (!part.trim()) continue;
      const i = part.indexOf(":");
      if (i < 1) throw new LsError(`"${part.trim()}" is not property:value`, line);
      const prop = part.slice(0, i).trim().toLowerCase(), value = part.slice(i + 1).trim();
      if (!/^[a-z-]+$/.test(prop) || !value || /[;{}<>\\]/.test(value))
        throw new LsError(`bad style "${part.trim()}"`, line);
      if (TEXT_PROPS.has(prop)) out.text.push([prop === "color" ? "fill" : prop, value]);
      else out.box.push([prop, value]);
    }
    return out;
  }

  // Links to javascript:, data: and the like become harmless.
  const safeUrl = (url) => (/^\s*(?:javascript|data|vbscript|file):/i.test(url.replace(/[\u0000-\u001f\s]/g, "")) ? "about:blank" : url);

  function parse(text, db) {
    seq = 0;
    const lines = text.split(/\r?\n/);
    let started = false;
    let last = 1;             // the last line with something on it
    const stack = [];         // open partition, then open layer
    const here = () => stack[stack.length - 1];
    const ids = new Map();
    const claim = (id, line, item) => {
      if (ids.has(id)) throw new LsError(`"${id}" is already used on line ${ids.get(id).line}`, line);
      ids.set(id, { line, item });
    };
    const later = [];         // class, style and click name IDs that may come further down
    const idList = (spec, line) => spec.split(",").map((x) => x.trim()).filter((x) => {
      if (!/^[A-Za-z_][\w.-]*$/.test(x)) throw new LsError(`"${x}" is not an ID`, line);
      return true;
    });

    lines.forEach((raw, n) => {
      const line = n + 1;
      const s = raw.replace(/%%.*$/, "").trim();
      if (!s) return;
      last = line;
      if (!started) {
        if (!/^layered-software\b/.test(s)) throw new LsError("expected layered-software", line);
        started = true;
        const rest = s.slice(TYPE.length).trim();
        if (rest) throw new LsError(`unexpected "${rest}"`, line);
        return;
      }
      let m;
      if ((m = /^title(?:\s+(.*))?$/.exec(s))) { db.setDiagramTitle(m[1] ?? ""); return; }
      if ((m = /^accTitle\s*:\s*(.*)$/.exec(s))) { db.setAccTitle(m[1]); return; }
      if ((m = /^accDescr\s*:\s*(.*)$/.exec(s))) { db.setAccDescription(m[1]); return; }
      if ((m = /^classDef\s+([\w,-]+)\s+(.+)$/.exec(s))) {
        const props = styleProps(m[2], line);
        for (const name of m[1].split(",")) {
          if (!CLASS_NAME.test(name)) throw new LsError(`"${name}" is not a class name`, line);
          db.classDefs.set(name, props);
        }
        return;
      }
      if ((m = /^class\s+([\w.,\s-]+?)\s+([A-Za-z_][\w-]*)$/.exec(s))) {
        const name = m[2];
        later.push({ line, ids: idList(m[1], line), apply: (it) => it.classes.push(name) });
        return;
      }
      if ((m = /^style\s+([A-Za-z_][\w.-]*)\s+(.+)$/.exec(s))) {
        const props = styleProps(m[2], line);
        later.push({ line, ids: [m[1]], apply: (it) => { it.style = props; } });
        return;
      }
      if ((m = /^click\s+([A-Za-z_][\w.-]*)\s+(.*)$/.exec(s))) {
        let args = m[2];
        const href = /^href\s+/.exec(args);
        if (href) args = args.slice(href[0].length);
        const a = /^"([^"]*)"(?:\s+"([^"]*)")?(?:\s+(_self|_blank|_parent|_top))?$/.exec(args.trim());
        if (!a) throw new LsError('click needs a quoted URL: click ID "url" ["tooltip"] [_blank]', line);
        later.push({ line, ids: [m[1]], apply: (it) => { it.link = { url: safeUrl(a[1]), tooltip: a[2], target: a[3] }; } });
        return;
      }
      const word = /^[\w-]+/.exec(s)?.[0];
      const rest = () => tokenize(s.slice(word.length), line);
      const cur = here();

      if (word === "end") {
        if (!stack.length) throw new LsError("end without partition or layer", line);
        stack.pop();
        return;
      }
      if (word === "partition") {
        if (stack.length) throw new LsError("a partition can't be inside another partition or a layer", line);
        const h = header(rest(), line, "partition");
        const p = { ...h, kind: "partition", items: [], line };
        claim(h.id, line, p);
        db.items.push(p);
        stack.push(p);
        return;
      }
      if (word === "layer") {
        if (cur?.kind === "layer") throw new LsError("a layer can't be inside another layer", line);
        const h = header(rest(), line, "layer");
        const l = { ...h, kind: "layer", components: [], anonymous: false };
        claim(h.id, line, l);
        (cur ? cur.items : db.items).push(l);
        stack.push(l);
        return;
      }
      if (word === "bar") {
        if (cur?.kind === "layer") throw new LsError("a bar can't be inside a layer", line);
        const h = header(rest(), line, "bar");
        if (h.columns) throw new LsError("a bar has no columns", line);
        const b = { ...h, kind: "bar" };
        claim(h.id, line, b);
        (cur ? cur.items : db.items).push(b);
        return;
      }
      if (word === "columns") {
        const t = rest();
        if (!cur || t.length !== 1 || t[0].kind !== "number" || t[0].value < 1)
          throw new LsError("columns N goes inside a partition or layer", line);
        cur.columns = t[0].value;
        return;
      }
      if (!cur) throw new LsError("components must be inside a partition or layer", line);
      const comps = components(tokenize(s, line), line);
      for (const c of comps) claim(c.id, line, c);
      let layer = cur;
      if (cur.kind === "partition") {
        layer = cur.items[cur.items.length - 1];
        if (!layer || layer.kind !== "layer" || !layer.anonymous) {
          layer = { id: autoId("layer"), label: "", columns: null, classes: [], kind: "layer", components: [], anonymous: true };
          cur.items.push(layer);
        }
      }
      layer.components.push(...comps);
    });
    if (!started) throw new LsError("expected layered-software", 1);
    if (stack.length) throw new LsError(`${here().kind} "${here().label}" has no end`, last);
    if (!db.items.some((i) => i.kind === "partition")) throw new LsError("a layered-software diagram needs a partition", last);
    for (const { line, ids: list, apply } of later) {
      for (const id of list) {
        if (!ids.has(id)) throw new LsError(`no partition, layer, bar or component "${id}"`, line);
        apply(ids.get(id).item);
      }
    }
  }

  // ---- db ----------------------------------------------------------------------------------------------------
  const db = {
    items: [], classDefs: new Map(), title: "", accTitle: "", accDescription: "",
    clear() { this.items = []; this.classDefs = new Map(); this.title = ""; this.accTitle = ""; this.accDescription = ""; },
    setDiagramTitle(t) { this.title = t; },
    getDiagramTitle() { return this.title; },
    setAccTitle(t) { this.accTitle = t; },
    getAccTitle() { return this.accTitle; },
    setAccDescription(t) { this.accDescription = t; },
    getAccDescription() { return this.accDescription; },
  };

  // ---- layout ------------------------------------------------------------------------------------------------
  const DEFAULTS = {
    maxColumns: 10,       // components in a row of the tallest partition, when nothing says otherwise
    componentHeight: 32,
    componentPaddingX: 12,
    componentMinWidth: 44,
    gap: 8,               // between components, and between layers
    layerPadding: 10,
    layerLabelHeight: 20,
    partitionPadding: 12,
    partitionTitleHeight: 28,
    partitionGap: 14,
    barHeight: 34,
    titleHeight: 40,
    diagramPadding: 8,
    fontSize: 14,
    layerLabelSize: 11,
    partitionTitleSize: 13,
    titleSize: 18,
    titleFontFamily: null,
  };

  function layoutLayer(layer, inner, o) {
    // inner: the width of the partition's content box.
    const n = layer.components.length;
    const pad = layer.anonymous ? 0 : o.layerPadding;
    const avail = inner - 2 * pad;
    let cols = layer.columns ?? Math.max(1, Math.min(n, o.maxColumns, Math.floor((avail + o.gap) / (layer.cell + o.gap))));
    cols = Math.max(1, Math.min(cols, n));
    const rows = Math.max(1, Math.ceil(n / cols));
    if (!layer.columns) cols = Math.max(1, Math.ceil(n / rows));
    layer.cols = cols;
    layer.rows = n ? rows : 0;
    const top = layer.anonymous ? 0 : (layer.label ? o.layerLabelHeight : o.layerPadding);
    layer.height = top + (n ? rows * o.componentHeight + (rows - 1) * o.gap : 0) + pad;
  }

  // The width a layer needs at `cols` columns.
  function layerWidth(layer, cols, o) {
    const pad = layer.anonymous ? 0 : o.layerPadding;
    return Math.max(cols * layer.cell + (cols - 1) * o.gap + 2 * pad, layer.labelWidth + 2 * pad);
  }

  function partitionHeight(p, inner, o) {
    let h = o.partitionTitleHeight;
    p.items.forEach((it, i) => {
      if (it.kind === "layer") layoutLayer(it, inner, o);
      h += (it.kind === "layer" ? it.height : o.barHeight) + (i ? o.gap : 0);
    });
    return h + o.partitionPadding;
  }

  // The narrowest content width of each column count of p's layers, smallest first.
  function candidateWidths(p, o) {
    const ws = new Set();
    const minW = Math.max(p.titleWidth, ...p.items.map((it) => it.kind === "bar" ? it.labelWidth + 2 * o.componentPaddingX : 0));
    for (const l of p.items.filter((it) => it.kind === "layer")) {
      const n = l.columns ?? p.columns ?? null;
      if (n) { ws.add(Math.max(layerWidth(l, Math.min(n, l.components.length || 1), o), minW)); continue; }
      for (let c = 1; c <= Math.max(1, l.components.length); c++) ws.add(Math.max(layerWidth(l, c, o), minW));
    }
    if (!ws.size) ws.add(minW);
    return [...ws].sort((a, b) => a - b);
  }

  function layout(items, measure, o) {
    const parts = items.filter((i) => i.kind === "partition");
    const first = items.indexOf(parts[0]);
    // Layers and bars outside the partitions, full width: those before the first partition go above them.
    const above = items.slice(0, first).filter((i) => i.kind !== "partition");
    const below = items.slice(first).filter((i) => i.kind !== "partition");
    const measureItem = (it) => {
      if (it.kind === "bar") { it.labelWidth = measure(it.label, o.fontSize, 400); return; }
      it.labelWidth = it.label && !it.anonymous ? measure(it.label.toUpperCase(), o.layerLabelSize, 500, 0.09) : 0;
      let cell = o.componentMinWidth;
      for (const c of it.components) {
        c.textWidth = measure(c.label, o.fontSize, 400);
        cell = Math.max(cell, Math.ceil(c.textWidth + 2 * o.componentPaddingX));
      }
      it.cell = cell;
    };
    for (const p of parts) {
      p.titleWidth = measure(p.label, o.partitionTitleSize, 600) + 2 * 4;
      for (const it of p.items) {
        if (it.kind === "layer" && p.columns && !it.columns) it.columns = p.columns;
        measureItem(it);
      }
    }
    for (const it of [...above, ...below]) measureItem(it);

    // Natural width: each layer at its own columns, or maxColumns.
    for (const p of parts) {
      const ws = candidateWidths(p, o);
      let natural = ws[0];
      for (const l of p.items.filter((it) => it.kind === "layer")) {
        const cols = Math.min(l.columns ?? o.maxColumns, Math.max(1, l.components.length));
        natural = Math.max(natural, layerWidth(l, cols, o));
      }
      p.inner = natural;
      p.natural = natural;
      p.height = partitionHeight(p, natural, o);
    }
    const tallest = Math.max(...parts.map((p) => p.height));
    // Partitions other than the tallest take the narrowest width that keeps them no taller.
    for (const p of parts) {
      if (p.height === tallest) continue;
      for (const w of candidateWidths(p, o)) {
        if (w > p.natural) break;
        if (partitionHeight(p, w, o) <= tallest) { p.inner = w; break; }
      }
      p.height = partitionHeight(p, p.inner, o);
    }
    const height = Math.max(...parts.map((p) => p.height));
    let width = parts.reduce((s, p) => s + p.inner + 2 * o.partitionPadding, 0) + o.partitionGap * (parts.length - 1);
    for (const it of [...above, ...below]) {
      width = Math.max(width, it.kind === "bar" ? it.labelWidth + 2 * o.componentPaddingX
        : layerWidth(it, Math.min(it.columns ?? 1, Math.max(1, it.components.length)), o));
    }
    return { parts, above, below, height, width };
  }

  // ---- renderer ----------------------------------------------------------------------------------------------
  const SVG = "http://www.w3.org/2000/svg";

  function el(parent, tag, attrs) {
    const e = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, String(v));
    parent.appendChild(e);
    return e;
  }

  const r2 = (v) => Math.round(v * 100) / 100;

  function draw(_text, id, _version, diagram) {
    const conf = (globalThis.mermaid?.mermaidAPI?.getConfig?.() ?? {});
    const o = { ...DEFAULTS, ...(conf.layeredSoftware || {}) };
    const family = conf.themeVariables?.fontFamily || conf.fontFamily || "sans-serif";
    const titleFamily = o.titleFontFamily || family;
    const svg = document.getElementById(id);
    const dbi = diagram.db;

    const probe = el(svg, "text", { x: 0, y: 0 });
    const measure = (s, size, weight, spacing = 0, fam = family) => {
      probe.setAttribute("font-family", fam);
      probe.setAttribute("font-size", size);
      probe.setAttribute("font-weight", weight);
      probe.textContent = s;
      // Whole pixels, so engines whose text widths differ in the last digits lay out the same.
      return Math.ceil(probe.getComputedTextLength() + spacing * size * s.length - 1e-3);
    };
    const L = layout(dbi.items, measure, o);
    const titleW = dbi.title ? measure(dbi.title, o.titleSize, 600, 0, titleFamily) : 0;
    svg.removeChild(probe);

    const pad = o.diagramPadding;
    const width = Math.max(L.width, titleW);
    const partsTop = pad + (dbi.title ? o.titleHeight : 0);
    const text = (parent, s, x, y, size, weight, cls, extra = {}) => {
      const t = el(parent, "text", {
        x: r2(x), y: r2(y + size * 0.35), class: cls, "text-anchor": "middle",
        "font-family": family, "font-size": size, "font-weight": weight, ...extra,
      });
      t.textContent = s;
      return t;
    };
    const root = el(svg, "g", { class: "ls-diagram" });

    // An element's <g> (its classes and id) and what its box and label go in: the <g>, or a link inside it. The
    // link holds only the box and label, so a partition's link doesn't wrap its components' links.
    // `style ID ...` goes on the element's own box and label as inline style: no selector can reach the boxes
    // inside it, and PNG/PDF (novasvg) apply it as browsers do.
    const own = (it, rect, label) => {
      if (!it.style) return;
      const decl = (list) => list.map(([k, v]) => `${k}: ${v} !important`).join("; ");
      if (it.style.box.length) rect.setAttribute("style", decl(it.style.box));
      if (label && it.style.text.length) label.setAttribute("style", decl(it.style.text));
    };
    const group = (parent, base, it) => {
      const g = el(parent, "g", { class: [base, ...it.classes].join(" "), id: `${id}-${it.id}` });
      if (!it.link) return [g, g];
      const a = el(g, "a", { href: it.link.url, target: it.link.target, class: "ls-link" });
      if (it.link.tooltip) el(a, "title").textContent = it.link.tooltip;
      return [g, a];
    };

    if (dbi.title) text(root, dbi.title, pad + width / 2, pad + o.titleHeight / 2 - 4, o.titleSize, 600, "ls-title",
      { "font-family": titleFamily });

    const box = (g, x, y, w, h, c) => el(g, "rect", { x: r2(x), y: r2(y), width: r2(w), height: r2(h), rx: 3, ry: 3, class: c });

    const drawBar = (parent, b, x, y, w) => {
      const [, g] = group(parent, "ls-bar", b);
      own(b, box(g, x, y, w, o.barHeight, "ls-bar-box"),
        text(g, b.label, x + w / 2, y + o.barHeight / 2, o.fontSize, 400, "ls-bar-label"));
    };

    // A layer drawn at (x, y), `w` wide; layoutLayer() has set its columns and height for that width.
    const drawLayer = (parent, it, x, y, w) => {
      const [lg, body] = group(parent, it.anonymous ? "ls-layer ls-anonymous" : "ls-layer", it);
      const lp = it.anonymous ? 0 : o.layerPadding;
      if (!it.anonymous) {
        const r = box(body, x, y, w, it.height, "ls-layer-box");
        own(it, r, null);
        if (it.label) {
          const t = el(body, "text", {
            x: r2(x + lp), y: r2(y + o.layerLabelHeight / 2 + 1 + o.layerLabelSize * 0.35), class: "ls-layer-label",
            "font-family": family, "font-size": o.layerLabelSize, "font-weight": 500, "letter-spacing": `${0.09 * o.layerLabelSize}`,
          });
          t.textContent = it.label.toUpperCase();
          own(it, r, t);
        }
      }
      const cw = (w - 2 * lp - (it.cols - 1) * o.gap) / it.cols;
      const y0 = y + (it.anonymous ? 0 : (it.label ? o.layerLabelHeight : o.layerPadding));
      it.components.forEach((c, k) => {
        const col = k % it.cols, row = Math.floor(k / it.cols);
        const bx = x + lp + col * (cw + o.gap), by = y0 + row * (o.componentHeight + o.gap);
        const [, cg] = group(lg, "ls-component", c);
        own(c, box(cg, bx, by, cw, o.componentHeight, "ls-component-box"),
          text(cg, c.label, bx + cw / 2, by + o.componentHeight / 2, o.fontSize, 400, "ls-component-label"));
      });
    };

    // Full-width layers and bars outside the partitions, from y down; returns the y below them.
    const drawOuter = (list, y) => {
      for (const it of list) {
        if (it.kind === "bar") { drawBar(root, it, pad, y, width); y += o.barHeight + o.gap; continue; }
        layoutLayer(it, width, o);
        drawLayer(root, it, pad, y, width);
        y += it.height + o.gap;
      }
      return y;
    };
    const top = drawOuter(L.above, partsTop);

    // Partitions get the width left over by a wider bar or title, shared out in proportion.
    const natural = L.parts.reduce((s, p) => s + p.inner + 2 * o.partitionPadding, 0) + o.partitionGap * (L.parts.length - 1);
    const spare = width - natural;
    let x = pad;
    for (const p of L.parts) {
      const inner = p.inner + (spare > 0 ? spare * (p.inner / (natural - o.partitionGap * (L.parts.length - 1) - 2 * o.partitionPadding * L.parts.length)) : 0);
      if (inner !== p.inner) p.height = partitionHeight(p, inner, o);
      const pw = inner + 2 * o.partitionPadding;
      const [g, pbody] = group(root, "ls-partition", p);
      own(p, box(pbody, x, top, pw, L.height, "ls-partition-box"),
        text(pbody, p.label, x + pw / 2, top + o.partitionTitleHeight / 2 + 2, o.partitionTitleSize, 600, "ls-partition-label"));
      // Spare height goes above the trailing bars, so bars line up across partitions.
      let trailing = p.items.length;
      while (trailing > 0 && p.items[trailing - 1].kind === "bar") trailing--;
      let y = top + o.partitionTitleHeight;
      const cx = x + o.partitionPadding;
      p.items.forEach((it, i) => {
        if (i === trailing && trailing < p.items.length) y += L.height - p.height;
        if (i) y += o.gap;
        if (it.kind === "bar") { drawBar(g, it, cx, y, inner); y += o.barHeight; return; }
        drawLayer(g, it, cx, y, inner);
        y += it.height;
      });
      x += pw + o.partitionGap;
    }
    const y = L.below.length ? drawOuter(L.below, top + L.height + o.gap) - o.gap : top + L.height;

    // classDef rules. They beat the theme's tones (an id in the selector, and !important like them).
    const rules = [];
    const rule = (sel, props) => {
      const sels = (part) => sel.map((x) => `#${id} ${x} > ${part}, #${id} ${x} > a > ${part}`).join(", ");
      const decl = (list) => list.map(([k, v]) => `${k}: ${v} !important;`).join(" ");
      if (props.box.length) rules.push(`${sels("rect")} { ${decl(props.box)} }`);
      if (props.text.length) rules.push(`${sels("text")} { ${decl(props.text)} }`);
    };
    for (const [name, props] of dbi.classDefs) rule([`.ls-diagram .${name}`], props);
    if (rules.length) el(svg, "style", {}).textContent = rules.join("\n");

    const W = r2(width + 2 * pad), H = r2(y + pad);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("style", `max-width: ${W}px;`);
    svg.setAttribute("role", "graphics-document document");
  }

  // Default look from Mermaid's theme variables; mermaid-diag's theme adds the tones (theme.py).
  const styles = (t) => `
    .ls-partition-box { fill: ${t.clusterBkg}; stroke: ${t.clusterBorder}; stroke-width: 1px; }
    .ls-partition-label { fill: ${t.titleColor || t.textColor}; }
    .ls-layer-box { fill: ${t.tertiaryColor}; stroke: ${t.clusterBorder}; stroke-width: 1px; }
    .ls-layer-label { fill: ${t.lineColor}; }
    .ls-component-box { fill: ${t.mainBkg}; stroke: ${t.nodeBorder}; stroke-width: 1px; }
    .ls-component-label, .ls-bar-label { fill: ${t.nodeTextColor || t.textColor}; }
    .ls-bar-box { fill: ${t.secondaryColor}; stroke: ${t.nodeBorder}; stroke-width: 1px; }
    .ls-title { fill: ${t.titleColor || t.textColor}; }
    .ls-link { cursor: pointer; }
  `;

  const diagram = {
    db,
    parser: { parse: (text) => parse(text, db) },
    renderer: { draw },
    styles,
  };

  globalThis.__mdLayeredSoftware = {
    id: TYPE,
    detector: (text) => /^\s*layered-software\b/.test(text),
    loader: async () => ({ id: TYPE, diagram }),
  };
})();
