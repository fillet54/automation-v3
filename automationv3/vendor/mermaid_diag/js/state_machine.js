/* state-machine: a mermaid-diag diagram type for state machines with prioritised, guarded transitions, the kind
 * that are specified and then generated as code. It describes the machine; the diagram decides how to draw it.
 *
 *   state-machine
 *     title Arm control
 *     direction auto
 *     initial idle
 *     state idle
 *       note Stowed and safe.
 *     state arming
 *       entry arm_timer = 0
 *       during arm_timer += 1
 *     state fault :::danger
 *     idle --> arming
 *       priority 1
 *       guard arm_cmd
 *       note An arm command starts the arming delay.
 *     arming --> arming : [3] arm_cmd
 *       action arm_timer = 0
 *     any --> fault : [0] fault_detected
 *
 * Statements:
 * - `title`, `accTitle:`, `accDescr:`; `direction auto|right|down` (also LR, TB); `initial NAME` (default: the first
 *   state).
 * - `state NAME [:::tone]`, then `entry`, `during`, `exit` (code) and `note` (the tooltip; several join as lines).
 * - `SOURCE --> TARGET [: [N] guard]` (`->` and `→` work too), then `priority N`, `guard`, `action` and `note`.
 *   `any` as the source means every state except the target. A state named only in a transition is declared there.
 * - `click NAME "url" ["tooltip"] [_blank]` makes a state a link.
 * Property lines belong to the state or transition above them; indentation is for the reader.
 *
 * Before layout the machine is made readable (as Heddle did, which this came from):
 * - `any --> X` transitions become one edge from a dashed "any state" group around the states they apply to,
 *   instead of an arrow from every state;
 * - transitions between the same two states become one edge with their labels stacked, in priority order;
 * - self-transitions become lines in their state's box (`↻ [3] arm_cmd`);
 * - the order states and transitions are written in is kept, and ELK uses it to decide what reads as forward, so
 *   recovery transitions become the back edges.
 * Layout is ELK Layered (Mermaid's own copy, globalThis.__mdELK: see engines/base.py's expose_elk) with orthogonal
 * routing. An edge that crosses the group's border is split at a port on it, laid out in two halves and joined.
 * `direction auto` lays the machine out left to right and switches to top-down when wider than `maxAutoWidth`.
 *
 * Every state's <g> has data-state="NAME" and every edge's data-edge="ID", for overlays (coverage, a live state);
 * states and edges carry their notes as <title> tooltips.
 *
 * mermaid-diag registers it with Mermaid (driver.js); the definition is globalThis.__mdStateMachine.
 */
(function () {
  "use strict";

  const TYPE = "state-machine";
  const ANY = "any";

  class SmError extends Error {
    constructor(message, line) {
      super(line ? `Parse error on line ${line}: ${message}` : message);
      this.name = "StateMachineError";
    }
  }

  // ---- parser ------------------------------------------------------------------------------------------------
  const NAME = "[A-Za-z_][\\w.]*";
  const TRANSITION = new RegExp(`^(${NAME})\\s*(?:-->|->|→)\\s*(${NAME})\\s*(?::\\s*(.*))?$`);
  const STATE = new RegExp(`^state\\s+(${NAME})((?:\\s*:::[\\w-]+)*)\\s*$`);
  const TONES = /:::([\w-]+)/g;
  const safeUrl = (url) => (/^\s*(?:javascript|data|vbscript|file):/i.test(url.replace(/[\u0000-\u001f\s]/g, "")) ? "about:blank" : url);

  function parse(text, db) {
    const lines = text.split(/\r?\n/);
    let started = false;
    let last = null;          // the state or transition that property lines belong to
    const states = new Map();
    const declare = (name, line) => {
      if (name === ANY) throw new SmError(`"${ANY}" is not a state name`, line);
      if (!states.has(name)) {
        const s = { name, entry: [], during: [], exit: [], note: [], classes: [], link: null, line };
        states.set(name, s);
        db.states.push(s);
      }
      return states.get(name);
    };
    const later = [];

    lines.forEach((raw, n) => {
      const line = n + 1;
      const s = raw.replace(/%%.*$/, "").trim();
      if (!s) return;
      if (!started) {
        if (!/^state-machine\b/.test(s)) throw new SmError("expected state-machine", line);
        if (s.slice(TYPE.length).trim()) throw new SmError(`unexpected "${s.slice(TYPE.length).trim()}"`, line);
        started = true;
        return;
      }
      let m;
      if ((m = /^title(?:\s+(.*))?$/.exec(s))) { db.setDiagramTitle(m[1] ?? ""); return; }
      if ((m = /^accTitle\s*:\s*(.*)$/.exec(s))) { db.setAccTitle(m[1]); return; }
      if ((m = /^accDescr\s*:\s*(.*)$/.exec(s))) { db.setAccDescription(m[1]); return; }
      if ((m = /^direction\s+(\S+)$/.exec(s))) {
        const d = { auto: "auto", right: "right", lr: "right", down: "down", tb: "down", td: "down" }[m[1].toLowerCase()];
        if (!d) throw new SmError(`direction is auto, right or down, not "${m[1]}"`, line);
        db.direction = d;
        return;
      }
      if ((m = new RegExp(`^initial\\s+(${NAME})$`).exec(s))) { db.initial = { name: m[1], line }; return; }
      if ((m = STATE.exec(s))) {
        const st = declare(m[1], line);
        for (const t of m[2].matchAll(TONES)) st.classes.push(t[1]);
        last = st;
        return;
      }
      if ((m = new RegExp(`^click\\s+(${NAME})\\s+(.*)$`).exec(s))) {
        let args = m[2].trim().replace(/^href\s+/, "");
        const a = /^"([^"]*)"(?:\s+"([^"]*)")?(?:\s+(_self|_blank|_parent|_top))?$/.exec(args);
        if (!a) throw new SmError('click needs a quoted URL: click NAME "url" ["tooltip"] [_blank]', line);
        later.push({ line, name: m[1], link: { url: safeUrl(a[1]), tooltip: a[2], target: a[3] } });
        return;
      }
      if ((m = TRANSITION.exec(s))) {
        const t = { source: m[1], target: m[2], priority: null, guard: "", action: [], note: [], line };
        if (t.source !== ANY) declare(t.source, line);
        declare(t.target, line);
        if (m[3] !== undefined) {
          const g = /^\[\s*(-?\d+)\s*\]\s*(.*)$/.exec(m[3].trim());
          if (g) { t.priority = Number(g[1]); t.guard = g[2]; } else t.guard = m[3].trim();
        }
        db.transitions.push(t);
        last = t;
        return;
      }
      if ((m = /^(entry|during|exit|note|priority|guard|action)(?:\s+(.*))?$/.exec(s))) {
        const [, key, value = ""] = m;
        if (!last) throw new SmError(`${key} must follow a state or a transition`, line);
        const isState = "entry" in last;
        if (["entry", "during", "exit"].includes(key) && !isState) throw new SmError(`${key} belongs to a state`, line);
        if (["priority", "guard", "action"].includes(key) && isState) throw new SmError(`${key} belongs to a transition`, line);
        if (key === "priority") {
          if (!/^-?\d+$/.test(value.trim())) throw new SmError("priority needs a whole number", line);
          last.priority = Number(value);
        } else if (key === "guard") last.guard = value.trim();
        else last[key].push(value.trim());
        return;
      }
      throw new SmError(`unexpected "${s}"`, line);
    });
    if (!started) throw new SmError("expected state-machine", 1);
    if (!db.states.length) throw new SmError("a state machine needs a state", lines.length);
    if (db.initial && !states.has(db.initial.name))
      throw new SmError(`no state "${db.initial.name}" to start in`, db.initial.line);
    for (const { line, name, link } of later) {
      if (!states.has(name)) throw new SmError(`no state "${name}"`, line);
      states.get(name).link = link;
    }
  }

  // ---- db ----------------------------------------------------------------------------------------------------
  const db = {
    states: [], transitions: [], initial: null, direction: "auto", title: "", accTitle: "", accDescription: "",
    clear() {
      this.states = []; this.transitions = []; this.initial = null; this.direction = "auto";
      this.title = ""; this.accTitle = ""; this.accDescription = "";
    },
    setDiagramTitle(t) { this.title = t; },
    getDiagramTitle() { return this.title; },
    setAccTitle(t) { this.accTitle = t; },
    getAccTitle() { return this.accTitle; },
    setAccDescription(t) { this.accDescription = t; },
    getAccDescription() { return this.accDescription; },
  };

  // ---- view: the readability transforms --------------------------------------------------------------------
  const DEFAULTS = {
    maxAutoWidth: 1100,   // wider than this left to right, `direction auto` goes top-down
    nameSize: 14,
    codeSize: 12,
    titleSize: 18,
    headerHeight: 34,     // a state's name row
    lineHeight: 16,       // a state's code lines and edge label lines
    paddingX: 14,
    minStateWidth: 80,
    labelWrap: 32,        // characters in an edge label line
    initialSize: 14,
    titleHeight: 40,
    codeFontFamily: null,
    titleFontFamily: null,
  };

  function wrap(text, width) {
    const out = [];
    let cur = "";
    for (const word of text.split(/\s+/).filter(Boolean)) {
      if (cur && cur.length + 1 + word.length > width) { out.push(cur); cur = word; } else cur = cur ? `${cur} ${word}` : word;
    }
    if (cur || !out.length) out.push(cur);
    return out;
  }

  const prio = (t) => (t.priority === null ? "" : `[${t.priority}] `);

  // A transition's label lines: its guard (with priority), then its actions.
  function transitionLines(t, o, prefix = "") {
    const head = `${prefix}${prio(t)}${t.guard}`.trim();
    const lines = head ? wrap(head, o.labelWrap).map((text) => ({ text, kind: "guard" })) : [];
    for (const a of t.action) lines.push(...wrap(`/ ${a}`, o.labelWrap).map((text) => ({ text, kind: "action" })));
    return lines;
  }

  const describe = (t) => {
    const head = `${prio(t)}${t.guard}`.trim();
    const note = t.note.join(" ");
    return head && note ? `${head}: ${note}` : head || note;
  };

  function buildView(d, o) {
    const names = d.states.map((s) => s.name);
    const known = new Set(names);
    const initial = d.initial ? d.initial.name : names[0];
    const anyTs = d.transitions.filter((t) => t.source === ANY && known.has(t.target));
    const anyTargets = new Set(anyTs.map((t) => t.target));
    const group = anyTs.length
      ? { id: "g_any", label: "any state", children: names.filter((n) => !anyTargets.has(n)).map((n) => `s_${n}`) }
      : null;
    const inGroup = (name) => group && !anyTargets.has(name);
    const byPriority = (a, b) => (a.priority ?? Infinity) - (b.priority ?? Infinity);

    const nodes = [];
    for (const s of d.states) {
      const loops = d.transitions.filter((t) => t.source === s.name && t.target === s.name).sort(byPriority);
      const lines = [];
      for (const key of ["entry", "during", "exit"]) for (const v of s[key]) lines.push(`${key} / ${v}`);
      for (const t of loops) transitionLines(t, o, "↻ ").forEach((ln, i) => lines.push(i ? `  ${ln.text}` : ln.text));
      let tip = s.note.join("\n");
      for (const t of loops) tip += `${tip ? "\n" : ""}↻ ${describe(t)}`;
      const node = { id: `s_${s.name}`, kind: "state", state: s, lines, tooltip: tip, parent: inGroup(s.name) ? group.id : null };
      if (s.name === initial) {
        nodes.push({ id: "initial", kind: "initial", tooltip: `initial state: ${initial}`, parent: node.parent });
      }
      nodes.push(node);
    }

    const edges = [{ id: "e_initial", source: "initial", target: `s_${initial}`, kind: "initial", lines: [], tooltip: "" }];
    const merged = new Map();
    for (const t of d.transitions) {
      if (t.source === ANY || t.source === t.target) continue;
      const key = `${t.source}\u0000${t.target}`;
      if (!merged.has(key)) merged.set(key, []);
      merged.get(key).push(t);
    }
    let i = 0;
    for (const ts of merged.values()) {
      ts.sort(byPriority);
      edges.push({
        id: `e${i++}`, source: `s_${ts[0].source}`, target: `s_${ts[0].target}`, kind: "normal",
        lines: ts.flatMap((t) => transitionLines(t, o)), tooltip: ts.map(describe).join("\n"),
      });
    }
    anyTs.forEach((t, j) => edges.push({
      id: `a${j}`, source: group.id, target: `s_${t.target}`, kind: "any",
      lines: transitionLines(t, o), tooltip: `from any state, ${describe(t)}`,
    }));
    return { nodes, edges, groups: group ? [group] : [], initial };
  }

  // ---- layout (ELK) ------------------------------------------------------------------------------------------
  const LAYOUT_OPTIONS = {
    "elk.algorithm": "layered",
    "elk.edgeRouting": "ORTHOGONAL",
    // Each group is laid out on its own, with the same options, so model order also governs the states in it.
    "elk.hierarchyHandling": "SEPARATE_CHILDREN",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    "elk.layered.cycleBreaking.strategy": "MODEL_ORDER",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.nodePlacement.favorStraightEdges": "true",
    "elk.spacing.nodeNode": "28",
    "elk.layered.spacing.nodeNodeBetweenLayers": "44",
    "elk.spacing.edgeNode": "16",
    "elk.spacing.edgeEdge": "12",
    "elk.layered.spacing.edgeEdgeBetweenLayers": "12",
    "elk.layered.spacing.edgeNodeBetweenLayers": "16",
    "elk.spacing.edgeLabel": "4",
    "elk.edgeLabels.placement": "CENTER",
    "elk.layered.edgeLabels.sideSelection": "SMART_UP",
    "elk.padding": "[top=16,left=16,bottom=16,right=16]",
  };
  const GROUP_PADDING = "[top=34,left=18,bottom=18,right=18]";

  // The ELK input graph; the order of children and edges is model order. An edge between a state in the group
  // and one outside it is split at a port on the group's border: the outer half is laid out with the group's
  // siblings, the inner half inside the group, and place() joins them.
  function toElk(view, direction) {
    const options = { ...LAYOUT_OPTIONS, "elk.direction": direction === "down" ? "DOWN" : "RIGHT" };
    const parent = new Map(view.nodes.map((n) => [n.id, n.parent]));
    for (const g of view.groups) parent.set(g.id, null);
    const groups = new Map(view.groups.map((g) => [g.id, {
      id: g.id, children: [], ports: [], edges: [],
      layoutOptions: { ...options, "elk.padding": GROUP_PADDING, "elk.portConstraints": "FIXED_SIDE" },
    }]));
    const root = [];
    const placed = new Set();
    for (const n of view.nodes) {
      if (n.parent && !placed.has(n.parent)) { root.push(groups.get(n.parent)); placed.add(n.parent); }
      (n.parent ? groups.get(n.parent).children : root).push({ id: n.id, width: n.width, height: n.height });
    }
    for (const [id, g] of groups) if (!placed.has(id)) root.push(g);

    const label = (e) => (e.lines.length ? { labels: [{ id: `${e.id}_label`, text: e.id, width: e.labelW, height: e.labelH,
      layoutOptions: { "elk.edgeLabels.placement": "CENTER" } }] } : {});
    const rootEdges = [];
    for (const e of view.edges) {
      const ps = parent.get(e.source), pt = parent.get(e.target);
      if (ps === pt) {
        (ps ? groups.get(ps).edges : rootEdges).push({ id: e.id, sources: [e.source], targets: [e.target], ...label(e) });
        continue;
      }
      // Incoming edges enter from below, outgoing ones leave on the flow side, so returns read as returns.
      const inner = pt ?? ps, incoming = pt != null, port = `${e.id}_port`;
      const side = incoming || direction === "down" ? "SOUTH" : "EAST";
      groups.get(inner).ports.push({ id: port, width: 1, height: 1, layoutOptions: { "elk.port.side": side } });
      rootEdges.push({ id: `${e.id}__outer`, sources: [incoming ? e.source : port], targets: [incoming ? port : e.target], ...label(e) });
      groups.get(inner).edges.push({ id: `${e.id}__inner`, sources: [incoming ? port : e.source], targets: [incoming ? e.target : port] });
    }
    return { id: "root", layoutOptions: options, children: root, edges: rootEdges };
  }

  // Absolute boxes and edge routes from ELK's output (positions there are relative to the parent, edges' to
  // their container).
  function place(out, view) {
    const offsets = new Map([[out.id, [0, 0]]]);
    const boxes = new Map();
    const walk = (node, ox, oy) => {
      for (const c of node.children || []) {
        const x = ox + (c.x || 0), y = oy + (c.y || 0);
        offsets.set(c.id, [x, y]);
        boxes.set(c.id, { x, y, w: c.width, h: c.height });
        walk(c, x, y);
      }
    };
    walk(out, 0, 0);
    const edges = new Map(), halves = new Map();
    const visit = (node) => {
      for (const e of node.edges || []) {
        const [ox, oy] = offsets.get(e.container ?? node.id) ?? offsets.get(node.id);
        const points = [];
        for (const sec of e.sections || []) {
          for (const p of [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint]) points.push([p.x + ox, p.y + oy]);
        }
        const lb = (e.labels || [])[0];
        const label = lb ? { x: lb.x + ox, y: lb.y + oy, w: lb.width, h: lb.height } : null;
        const split = e.id.indexOf("__");
        if (split < 0) edges.set(e.id, { points, label });
        else {
          const base = e.id.slice(0, split);
          if (!halves.has(base)) halves.set(base, {});
          halves.get(base)[e.id.slice(split + 2)] = { points, label, incoming: e.targets[0].endsWith("_port") };
        }
      }
      for (const c of node.children || []) visit(c);
    };
    visit(out);
    for (const [base, { outer, inner }] of halves) {
      const op = outer?.points ?? [], ip = inner?.points ?? [];
      edges.set(base, { points: outer?.incoming ? [...op, ...ip.slice(1)] : [...ip, ...op.slice(1)], label: outer?.label ?? null });
    }
    return { width: out.width, height: out.height, boxes, edges };
  }

  async function layout(view, direction, maxAutoWidth) {
    const ELK = globalThis.__mdELK?.();
    if (!ELK) throw new Error("state-machine needs mermaid-diag's ELK (globalThis.__mdELK)");
    const elk = new ELK();
    const run = async (dir) => place(await elk.layout(toElk(view, dir)), view);
    if (direction !== "auto") return run(direction);
    const wide = await run("right");
    return wide.width > maxAutoWidth ? run("down") : wide;
  }

  // ---- renderer ----------------------------------------------------------------------------------------------
  const SVG = "http://www.w3.org/2000/svg";
  const r2 = (v) => Math.round(v * 100) / 100;

  function el(parent, tag, attrs) {
    const e = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, String(v));
    parent.appendChild(e);
    return e;
  }

  // An orthogonal route with its corners rounded.
  function roundedPath(points, radius = 6) {
    if (!points.length) return "";
    const f = (v) => r2(v);
    const d = [`M${f(points[0][0])} ${f(points[0][1])}`];
    for (let i = 1; i < points.length - 1; i++) {
      const [x0, y0] = points[i - 1], [x1, y1] = points[i], [x2, y2] = points[i + 1];
      const r = Math.min(radius, Math.abs(x1 - x0 + y1 - y0) / 2, Math.abs(x2 - x1 + y2 - y1) / 2);
      const toward = (bx, by) => {
        const dx = bx - x1, dy = by - y1, len = Math.hypot(dx, dy) || 1;
        return [x1 + (dx / len) * r, y1 + (dy / len) * r];
      };
      const [sx, sy] = toward(x0, y0), [ex, ey] = toward(x2, y2);
      d.push(`L${f(sx)} ${f(sy)}Q${f(x1)} ${f(y1)} ${f(ex)} ${f(ey)}`);
    }
    const [lx, ly] = points[points.length - 1];
    d.push(`L${f(lx)} ${f(ly)}`);
    return d.join("");
  }

  async function draw(_text, id, _version, diagram) {
    const conf = globalThis.mermaid?.mermaidAPI?.getConfig?.() ?? {};
    const o = { ...DEFAULTS, ...(conf.stateMachine || {}) };
    const family = conf.themeVariables?.fontFamily || conf.fontFamily || "sans-serif";
    const mono = o.codeFontFamily || "monospace";
    const titleFamily = o.titleFontFamily || family;
    const svg = document.getElementById(id);
    const d = diagram.db;

    const probe = el(svg, "text", { x: 0, y: 0 });
    const measure = (s, size, weight, fam) => {
      probe.setAttribute("font-family", fam);
      probe.setAttribute("font-size", size);
      probe.setAttribute("font-weight", weight);
      probe.textContent = s;
      return Math.ceil(probe.getComputedTextLength() - 1e-3);  // whole pixels: engines agree
    };

    const view = buildView(d, o);
    for (const n of view.nodes) {
      if (n.kind === "initial") { n.width = n.height = o.initialSize; continue; }
      const widest = Math.max(measure(n.state.name, o.nameSize, 600, family), ...n.lines.map((l) => measure(l, o.codeSize, 400, mono)));
      n.width = Math.max(o.minStateWidth, widest + 2 * o.paddingX);
      n.height = o.headerHeight + (n.lines.length ? 8 + n.lines.length * o.lineHeight : 0);
    }
    for (const e of view.edges) {
      if (!e.lines.length) continue;
      e.labelW = Math.max(...e.lines.map((l) => measure(l.text, o.codeSize, 400, mono))) + 8;
      e.labelH = e.lines.length * o.lineHeight + 4;
    }
    const titleW = d.title ? measure(d.title, o.titleSize, 600, titleFamily) : 0;
    svg.removeChild(probe);

    const lay = await layout(view, d.direction, o.maxAutoWidth);
    const top = d.title ? o.titleHeight : 0;
    const width = Math.max(lay.width, titleW + 32);
    const root = el(svg, "g", { class: "sm-diagram" });
    const body = el(root, "g", { transform: top ? `translate(0 ${top})` : null });
    const text = (parent, s, x, y, size, attrs) => {
      const t = el(parent, "text", { x: r2(x), y: r2(y + size * 0.35), "font-size": size, ...attrs });
      t.textContent = s;
      return t;
    };
    const tooltip = (g, s) => { if (s) el(g, "title").textContent = s; };

    if (d.title) {
      text(root, d.title, width / 2, o.titleHeight / 2 + 4, o.titleSize,
        { class: "sm-title", "text-anchor": "middle", "font-family": titleFamily, "font-weight": 600 });
    }

    const defs = el(body, "defs");
    for (const kind of ["normal", "any"]) {
      const m = el(defs, "marker", {
        id: `${id}-arrow-${kind}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7,
        orient: "auto-start-reverse", markerUnits: "userSpaceOnUse",
      });
      el(m, "path", { d: "M0 0L10 5L0 10z", class: `sm-arrow${kind === "any" ? " any" : ""}` });
    }

    // The group first, so everything else sits on it.
    for (const g of view.groups) {
      const b = lay.boxes.get(g.id);
      if (!b) continue;
      const gg = el(body, "g", { class: "sm-group", "data-group": g.id });
      el(gg, "rect", { x: r2(b.x), y: r2(b.y), width: r2(b.w), height: r2(b.h), rx: 6, ry: 6, class: "sm-group-box" });
      text(gg, g.label.toUpperCase(), b.x + 14, b.y + 17, 11,
        { class: "sm-group-label", "font-family": family, "font-weight": 500, "letter-spacing": r2(0.09 * 11) });
    }

    const labels = [];
    for (const e of view.edges) {
      const geom = lay.edges.get(e.id);
      if (!geom || !geom.points.length) continue;
      const any = e.kind === "any" ? " any" : "";
      const g = el(body, "g", { class: `sm-edge${any}`, "data-edge": e.id });
      tooltip(g, e.tooltip);
      el(g, "path", { d: roundedPath(geom.points), class: `sm-line${any}`, "marker-end": `url(#${id}-arrow-${any ? "any" : "normal"})` });
      if (geom.label && e.lines.length) labels.push([e, geom.label]);
    }

    for (const n of view.nodes) {
      const b = lay.boxes.get(n.id);
      if (!b) continue;
      if (n.kind === "initial") {
        const g = el(body, "g", { class: "sm-initial", "data-state": "initial" });
        tooltip(g, n.tooltip);
        el(g, "circle", { cx: r2(b.x + b.w / 2), cy: r2(b.y + b.h / 2), r: r2(b.w / 2), class: "sm-initial-dot" });
        continue;
      }
      const s = n.state;
      const cls = ["sm-state", ...(s.name === view.initial ? ["initial"] : []), ...s.classes].join(" ");
      const g = el(body, "g", { class: cls, id: `${id}-state-${s.name}`, "data-state": s.name });
      let inner = g;
      if (s.link) {
        inner = el(g, "a", { href: s.link.url, target: s.link.target, class: "sm-link" });
        tooltip(inner, s.link.tooltip || n.tooltip);
      } else tooltip(g, n.tooltip);
      el(inner, "rect", { x: r2(b.x), y: r2(b.y), width: r2(b.w), height: r2(b.h), rx: 6, ry: 6, class: "sm-box" });
      text(inner, s.name, b.x + b.w / 2, b.y + o.headerHeight / 2, o.nameSize,
        { class: "sm-name", "text-anchor": "middle", "font-family": family, "font-weight": 600 });
      if (n.lines.length) {
        const sep = b.y + o.headerHeight;
        el(inner, "line", { x1: r2(b.x), y1: r2(sep), x2: r2(b.x + b.w), y2: r2(sep), class: "sm-sep" });
        n.lines.forEach((ln, i) => {
          const t = text(inner, ln, b.x + o.paddingX, sep + 4 + (i + 0.5) * o.lineHeight, o.codeSize,
            { class: "sm-code", "font-family": mono });
          t.setAttribute("xml:space", "preserve");
        });
      }
    }

    // Edge labels last, on the page colour, so lines passing behind them stay legible.
    for (const [e, lb] of labels) {
      const any = e.kind === "any" ? " any" : "";
      const g = el(body, "g", { class: `sm-label${any}`, "data-edge": e.id });
      tooltip(g, e.tooltip);
      el(g, "rect", { x: r2(lb.x), y: r2(lb.y), width: r2(lb.w), height: r2(lb.h), rx: 3, ry: 3, class: "sm-label-box" });
      e.lines.forEach((ln, i) => {
        text(g, ln.text, lb.x + 4, lb.y + 2 + (i + 0.5) * o.lineHeight, o.codeSize,
          { class: ln.kind === "action" ? "sm-action" : `sm-guard${any}`, "font-family": mono });
      });
    }

    const W = r2(width), H = r2(lay.height + top);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("style", `max-width: ${W}px;`);
    svg.setAttribute("role", "graphics-document document");
  }

  // Default look from Mermaid's theme variables; mermaid-diag's theme adds the "any" colour and tones (theme.py).
  const styles = (t) => `
    .sm-box { fill: ${t.mainBkg}; stroke: ${t.nodeBorder}; stroke-width: 1px; }
    .sm-state.initial > .sm-box, .sm-state.initial > a > .sm-box { stroke: ${t.textColor}; stroke-width: 1.5px; }
    .sm-name { fill: ${t.nodeTextColor || t.textColor}; }
    .sm-code, .sm-action { fill: ${t.lineColor}; }
    .sm-guard { fill: ${t.textColor}; }
    .sm-sep { stroke: ${t.nodeBorder}; stroke-width: 1px; }
    .sm-group-box { fill: ${t.clusterBkg}; stroke: ${t.nodeBorder}; stroke-width: 1px; stroke-dasharray: 6 4; }
    .sm-group-label { fill: ${t.lineColor}; }
    .sm-line { fill: none; stroke: ${t.lineColor}; stroke-width: 1.25px; }
    .sm-line.any { stroke-dasharray: 5 3; }
    .sm-arrow { fill: ${t.lineColor}; }
    .sm-initial-dot { fill: ${t.textColor}; }
    .sm-label-box { fill: ${t.edgeLabelBackground || t.mainBkg}; }
    .sm-title { fill: ${t.titleColor || t.textColor}; }
    .sm-link { cursor: pointer; }
    .sm-state:hover .sm-box { stroke: ${t.textColor}; stroke-width: 2px; }
    .sm-edge:hover .sm-line { stroke-width: 2.25px; }
  `;

  const diagram = {
    db,
    parser: { parse: (text) => parse(text, db) },
    renderer: { draw },
    styles,
  };

  globalThis.__mdStateMachine = {
    id: TYPE,
    detector: (text) => /^\s*state-machine\b/.test(text),
    loader: async () => ({ id: TYPE, diagram }),
  };
})();
