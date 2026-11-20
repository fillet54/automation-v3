/* Starts one render in a fresh page: what mermaid-cli does in its browser page for one diagram.
 *
 * __mdRender(id, source, config) resets the document, initializes Mermaid and renders. When the returned promise
 * settles it leaves the SVG in globalThis.__mdResult or the error in globalThis.__mdError; the host keeps the
 * page's event loop turning (promise jobs, then __runNextTimer()) until one of them is set.
 *
 * The SVG goes through the HTML parser and XMLSerializer, as in mermaid-cli, so the result is well-formed XML
 * (self-closing <br/>, namespaces declared) that works inline in HTML and as a standalone .svg file.
 */
globalThis.mermaid = globalThis.__esbuild_esm_mermaid_nm.mermaid.default || globalThis.__esbuild_esm_mermaid_nm.mermaid;

globalThis.__mdDone = () => globalThis.__mdResult !== null || globalThis.__mdError !== null;

// Mermaid draws some shapes with roughjs, which jitters them with Math.random(). A fixed sequence for every
// render makes the output the same in every engine and between the light and dark renders of a diagram.
function seededRandom(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

globalThis.__mdRender = function (id, source, config) {
  globalThis.__mdResult = null;
  globalThis.__mdError = null;
  Math.random = seededRandom(0x6d65726d);
  // Iconify (architecture diagrams' icons) makes element ids from the time: a fixed clock keeps them the same.
  Date.now = () => 1767225600000;
  __resetDocument();
  (async function () {
    // mermaid-diag's own diagram types (layered_software.js, state_machine.js), registered once per page.
    if (!globalThis.__mdRegistered) {
      await mermaid.registerExternalDiagrams([globalThis.__mdLayeredSoftware, globalThis.__mdStateMachine]);
      globalThis.__mdRegistered = true;
    }
    mermaid.initialize(config);
    const container = document.getElementById("container");
    const { svg } = await mermaid.render(id, source, container);
    container.innerHTML = svg;
    const el = container.getElementsByTagName("svg")[0];
    if (!el) throw new Error("Mermaid produced no SVG");
    return new XMLSerializer().serializeToString(el);
  })().then(
    (svg) => { globalThis.__mdResult = svg; },
    (e) => {
      const message = e && e.message ? e.message : String(e);
      globalThis.__mdError = (e && e.name && e.name !== "Error" ? e.name + ": " : "") + message;
    },
  );
};
