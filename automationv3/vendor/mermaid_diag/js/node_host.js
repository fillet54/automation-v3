/* Renders diagrams for mermaid-diag in Node: one JSON request per line on stdin, one JSON reply per line on stdout.
 *
 *   request: {"id": 1, "svgId": "md-1a2b3c", "source": "flowchart LR ...", "config": {...}}
 *   reply:   {"id": 1, "svg": "<svg ..."}  or  {"id": 1, "error": "Parse error on line 2 ..."}
 *
 * Every render gets a fresh context (a browser page starts from zero: Mermaid keeps counters between renders),
 * but the scripts are compiled once, so a new context costs only running them.
 *
 * Usage: node node_host.js <js directory> <fonts.json>
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const readline = require("readline");

const [jsDir, fontsJson] = process.argv.slice(2);
const MAX_STEPS = 200000;

// The same as engines/base.py's expose_elk(): mermaid.min.js with its ELK class reachable as globalThis.__mdELK().
function exposeElk(bundle) {
  const m = /new (\w+)\.default;\w+\.log\.info\("Drawing flowchart using v4 renderer"/.exec(bundle);
  if (!m) throw new Error("mermaid.min.js: can't find where Mermaid creates its ELK (see expose_elk)");
  const load = new RegExp(`[,;{]${m[1]}=(\\w+)\\((\\w+)\\(\\),1\\)`).exec(bundle);
  const decl = [...bundle.matchAll(new RegExp(`(?<![\\w$])var ${m[1]},`, "g"))];
  if (!load || decl.length !== 1) throw new Error("mermaid.min.js: can't find Mermaid's ELK module (see expose_elk)");
  const at = decl[0].index;
  return bundle.slice(0, at) + `globalThis.__mdELK=()=>${load[1]}(${load[2]}(),1).default;` + bundle.slice(at);
}

const PAGE = ["prelude.js", "metrics.js", "path_bbox.js", "dom_shim.js", "mermaid.min.js", "layered_software.js",
  "state_machine.js", "driver.js"];
const scripts = [
  ["fonts.json", "globalThis.__MD_FONTS = " + fs.readFileSync(fontsJson, "utf8") + ";"],
  ...PAGE.map((name) => {
    const code = fs.readFileSync(path.join(jsDir, name), "utf8");
    return [name, name === "mermaid.min.js" ? exposeElk(code) : code];
  }),
].map(([filename, code]) => new vm.Script(code, { filename }));

function newPage() {
  const sandbox = { __log: (s) => process.stderr.write(`[mermaid-diag] ${s}\n`) };
  const context = vm.createContext(sandbox);
  for (const script of scripts) script.runInContext(context);
  return context;
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function render(page, req) {
  page.__mdRender(req.svgId, req.source, req.config);
  for (let i = 0; i < MAX_STEPS; i++) {
    await tick(); // runs the page's promise jobs
    if (page.__mdDone()) break;
    if (!page.__runNextTimer()) {
      await tick();
      if (!page.__mdDone()) throw new Error("the render stopped before it finished");
      break;
    }
  }
  if (!page.__mdDone()) throw new Error(`the render did not finish in ${MAX_STEPS} steps`);
  if (page.__mdError !== null) throw new Error(page.__mdError);
  return page.__mdResult;
}

let next = newPage();
const queue = [];
let busy = false;

async function work() {
  if (busy) return;
  busy = true;
  while (queue.length) {
    const req = queue.shift();
    let reply;
    try {
      const page = next || newPage();
      next = null;
      reply = { id: req.id, svg: await render(page, req) };
    } catch (e) {
      reply = { id: req.id, error: e && e.message ? e.message : String(e) };
    }
    process.stdout.write(JSON.stringify(reply) + "\n");
    next = newPage(); // ready for the next request
  }
  busy = false;
}

process.stdout.write(JSON.stringify({ ready: true, node: process.versions.node }) + "\n");
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  if (!line.trim()) return;
  queue.push(JSON.parse(line));
  work();
});
