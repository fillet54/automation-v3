/* Draws the page's .. mermaid:: diagrams in the web UI's look.
 *
 * Colours and fonts come from the page's ui.css tokens (--ui-paper, --ui-ink, --ui-accent...), read when a
 * diagram is drawn, so diagrams follow the site's light or dark theme; they are drawn again when the system
 * theme changes. Layout is ELK's, loaded on demand; where it can't load (a page opened as a file) Mermaid's
 * own layout is used instead.
 *
 * Node classes for the site's tones, e.g. A[Server]:::accent: accent, success, danger, warning, info, review,
 * and ghost for something outside the system (dashed).
 */
(function () {
  "use strict";

  const mermaid = window.mermaid;
  const here = document.currentScript.src;
  const TONES = ["accent", "success", "danger", "warning", "info", "review"];
  let drawn = 0;

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue("--ui-" + name).trim();
  }

  /* a mix of two #rrggbb colours: `amount` of a, the rest b (Mermaid computes from colours, not var()s) */
  function mix(a, b, amount) {
    const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    const [x, y] = [rgb(a), rgb(b)];
    return "#" + x.map((v, i) => Math.round(v * amount + y[i] * (1 - amount)).toString(16).padStart(2, "0")).join("");
  }

  function themeCSS(t) {
    const tones = TONES.map((tone) => `
      .node.${tone} > :is(rect, polygon, circle, ellipse, path), .node.${tone} > g > :is(rect, path) {
        fill: ${mix(t[tone], t.paper, 0.1)} !important; stroke: ${t[tone]} !important; }
      .node.${tone} .nodeLabel, .node.${tone} .nodeLabel p { color: ${t.ink} !important; }`).join("");
    return `
      .node > :is(rect, polygon, circle, ellipse, path), .node > g > :is(rect, path) { stroke-width: 1px; }
      .node > rect, .node > g > rect { rx: 3px; ry: 3px; }
      .node .nodeLabel, .node .nodeLabel p { line-height: 1.35; }
      .node.ghost > :is(rect, polygon, path), .node.ghost > g > :is(rect, path) {
        fill: ${t.paper} !important; stroke: ${t.faint} !important; stroke-dasharray: 4 3; }
      .node.ghost .nodeLabel, .node.ghost .nodeLabel p { color: ${t.muted} !important; }
      ${tones}
      .cluster > rect { rx: 3px; ry: 3px; stroke-width: 1px; }
      .cluster-label .nodeLabel, .cluster-label .nodeLabel p, .cluster-label span {
        font-size: 11px; font-weight: 500; letter-spacing: 0.09em; text-transform: uppercase; color: ${t.muted} !important; }
      .edgeLabel, .edgeLabel p, .edgeLabel span { font-size: 12px; color: ${t.muted} !important; }
      .edgeLabel rect, .labelBkg { fill: ${t.paper} !important; background: ${t.paper} !important; opacity: 1 !important; }
      .flowchart-link, .transition { stroke-width: 1.25px; }
      .marker, marker path { fill: ${t.muted} !important; stroke: ${t.muted} !important; }
      .actor { stroke-width: 1px; }
      .messageText, .loopText, .loopText > tspan, .labelText, .labelText > tspan, .noteText, .noteText > tspan { font-family: ${t.font}; }
      .messageText { fill: ${t.ink} !important; }
      .labelText, .labelText > tspan { font-size: 11px; font-weight: 500; }
      .loopLine { stroke-dasharray: 3 3; stroke: ${t.rule_strong} !important; }
      .statediagram-state rect.basic, .statediagram-state rect.divider { rx: 3px; ry: 3px; }
      .stateGroup rect, .statediagram-cluster rect.outer { rx: 3px; ry: 3px; }
      .state-start, .state-end { fill: ${t.ink} !important; stroke: ${t.ink} !important; }
    `;
  }

  function config(layout) {
    const t = {};
    for (const name of ["paper", "soft", "ink", "muted", "faint", "rule", "rule-strong", ...TONES]) {
      t[name.replace("-", "_")] = token(name);
    }
    t.font = token("font-body") || "sans-serif";
    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches
      ? document.documentElement.dataset.uiTheme !== "light"
      : document.documentElement.dataset.uiTheme === "dark";
    return {
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      look: "classic",
      layout: layout,
      fontFamily: t.font,
      themeCSS: themeCSS(t),
      themeVariables: {
        darkMode: dark,
        background: t.paper,
        fontFamily: t.font,
        fontSize: "13px",
        primaryColor: t.paper,
        primaryBorderColor: t.rule_strong,
        primaryTextColor: t.ink,
        secondaryColor: t.soft,
        secondaryBorderColor: t.rule_strong,
        secondaryTextColor: t.ink,
        tertiaryColor: t.soft,
        tertiaryBorderColor: t.rule,
        tertiaryTextColor: t.ink,
        lineColor: t.muted,
        textColor: t.ink,
        titleColor: t.ink,
        mainBkg: t.paper,
        nodeBorder: t.rule_strong,
        clusterBkg: mix(t.soft, t.paper, 0.6),
        clusterBorder: t.rule,
        edgeLabelBackground: t.paper,
        noteBkgColor: mix(t.info, t.paper, 0.07),
        noteBorderColor: mix(t.info, t.paper, 0.45),
        noteTextColor: t.ink,
        actorBkg: t.paper,
        actorBorder: t.rule_strong,
        actorTextColor: t.ink,
        actorLineColor: t.rule_strong,
        signalColor: t.muted,
        signalTextColor: t.ink,
        labelBoxBkgColor: t.soft,
        labelBoxBorderColor: t.rule_strong,
        labelTextColor: t.ink,
        loopTextColor: t.muted,
        activationBkgColor: t.soft,
        activationBorderColor: t.rule_strong,
        sequenceNumberColor: t.paper,
        stateBkg: t.paper,
        stateBorder: t.rule_strong,
        stateLabelColor: t.ink,
        compositeBackground: mix(t.soft, t.paper, 0.6),
        compositeTitleBackground: t.soft,
        altBackground: t.soft,
        transitionColor: t.muted,
        transitionLabelColor: t.muted,
        labelBackgroundColor: t.paper,
        specialStateColor: t.ink,
        innerEndBackground: t.ink,
        errorBkgColor: mix(t.danger, t.paper, 0.1),
        errorTextColor: t.danger,
      },
      flowchart: { htmlLabels: true, curve: "basis", padding: 12, wrappingWidth: 240, nodeSpacing: 36, rankSpacing: 44, diagramPadding: 8 },
      sequence: { useMaxWidth: true, mirrorActors: false, actorMargin: 56, messageMargin: 30, boxMargin: 8,
                  noteMargin: 8, width: 120, height: 40, actorFontSize: 13, messageFontSize: 13, noteFontSize: 12,
                  actorFontFamily: t.font, messageFontFamily: t.font, noteFontFamily: t.font },
      state: { padding: 10 },
      elk: { mergeEdges: false, nodePlacementStrategy: "BRANDES_KOEPF", considerModelOrder: "NODES_AND_EDGES" },
    };
  }

  async function elkLayout() {
    try {
      const elk = await import(new URL("mermaid/elk/mermaid-layout-elk.esm.min.mjs", here));
      mermaid.registerLayoutLoaders(elk.default);
      return "elk";
    } catch (e) {
      console.info("Diagrams: the ELK layout couldn't load, using Mermaid's own", e);
      return "dagre";
    }
  }

  async function draw(canvases, layout) {
    mermaid.initialize(config(layout));
    for (const canvas of canvases) {
      if (!canvas.dataset.source) canvas.dataset.source = canvas.querySelector("pre").textContent;
      try {
        const { svg } = await mermaid.render("ui-diagram-" + ++drawn, canvas.dataset.source);
        canvas.innerHTML = svg;
        canvas.classList.add("ui-diagram__canvas--drawn");
        canvas.classList.remove("ui-diagram__canvas--error");
      } catch (e) {
        canvas.classList.add("ui-diagram__canvas--error");
        canvas.innerHTML = "";
        const message = document.createElement("p");
        message.className = "ui-diagram__error";
        message.textContent = "This diagram couldn't be drawn: " + (e && e.message ? e.message : e);
        const pre = document.createElement("pre");
        pre.className = "ui-diagram__source";
        pre.textContent = canvas.dataset.source;
        canvas.append(message, pre);
        document.querySelectorAll('[id^="dui-diagram-"]').forEach((el) => el.remove());  // Mermaid's leftovers
      }
    }
  }

  async function start() {
    const canvases = [...document.querySelectorAll("[data-diagram]")];
    if (!mermaid || !canvases.length) return;
    // Labels are measured as they are drawn: wait for the site's fonts
    const font = token("font-body") || "sans-serif";
    await Promise.allSettled([document.fonts.load("13px " + font), document.fonts.load("500 11px " + font)]);
    const layout = await elkLayout();
    await draw(canvases, layout);
    if (!document.documentElement.dataset.uiTheme) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => draw(canvases, layout));
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
