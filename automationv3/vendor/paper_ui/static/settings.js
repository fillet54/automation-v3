/* paper-ui's settings menu: a gear in the header that opens the reader's settings for the page.
 *
 * - Color scheme, on every page: Auto (the system's), Light or Dark. It is <html data-ui-theme> (ui.css), the
 *   reader's choice kept in the browser (localStorage "paper-ui-theme") and put on the page in its <head>, before
 *   it is drawn (a few lines in ui/layout.html and the docs theme; they keep the app's own default as
 *   data-ui-theme-default). Every change is announced as a "ui-theme" event on the document.
 * - Layout, where the page has a <select data-ui-layout-switch> (the docs: layout.js does the rest): its options,
 *   each with a small picture and its data-note. Choosing one changes the select.
 *
 * The gear goes in the header's [data-ui-settings] (app_header(..., settings=True) makes one; so does the docs
 * theme's header), or else at the header's end, before the user. A page without a header (.ui-header) has no
 * menu: the docs keep the select in their side column.
 */
(() => {
  const KEY = "paper-ui-theme";
  const SCHEMES = [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]];
  const root = document.documentElement;

  const svg = (body, size, box) => `<svg class="ui-icon" width="${size}" height="${size}" viewBox="${box}" fill="none" ` +
    `stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  // the gear, and the schemes' monitor, sun and moon: Lucide's (ISC licence)
  const GEAR = svg('<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>', 16, "0 0 24 24");
  const SCHEME_ICONS = {
    auto: svg('<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>', 16, "0 0 24 24"),
    light: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>', 16, "0 0 24 24"),
    dark: svg('<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>', 16, "0 0 24 24"),
  };
  // each layout in miniature: the page, its lines of text, a figure, a margin
  const lines = (to, n = 3, y = 5) => Array.from({ length: n }, (_, i) => `<path d="M5 ${y + i * 2.5}H${i === n - 1 ? to - 3 : to}"/>`).join("");
  const FIGURE = '<rect x="5" y="13.5" width="18" height="3" rx=".5"/>';
  const PICTURES = {
    narrow: lines(14) + FIGURE,
    medium: lines(17) + FIGURE,
    full: lines(23) + FIGURE,
    tufte: lines(15) + FIGURE + '<path d="M18 5H23M18 7.5H22"/>',
  };
  const picture = (value) => `<span class="ui-settings__picture">${svg('<rect x="2" y="2" width="24" height="17" rx="1.5"/>' +
    (PICTURES[value] || lines(23)), 28, "0 0 28 21")}</span>`;
  const escape = (text) => text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // ---------------------------------------------------------------------------------------- colour scheme

  const scheme = () => {
    let kept = null;
    try { kept = localStorage.getItem(KEY); } catch (e) { /* no storage */ }
    if (SCHEMES.some(([value]) => value === kept)) return kept;
    return root.getAttribute("data-ui-theme-default") || root.getAttribute("data-ui-theme") || "auto";
  };
  function setScheme(value) {
    if (value === "auto") root.removeAttribute("data-ui-theme");
    else root.setAttribute("data-ui-theme", value);
    try { localStorage.setItem(KEY, value); } catch (e) { /* private window: this page only */ }
    document.dispatchEvent(new CustomEvent("ui-theme", { detail: value }));
  }

  // ---------------------------------------------------------------------------------------- the menu

  function build() {
    const header = document.querySelector(".ui-header");
    const select = document.querySelector("select[data-ui-layout-switch]");
    const source = select && select.closest("[data-ui-settings-source]");
    if (!header) {
      if (source) source.removeAttribute("data-ui-settings-source");     // no header: the select stays
      return;
    }
    const slot = header.querySelector("[data-ui-settings]");
    if (slot && slot.childElementCount) return;                       // made already
    const menu = slot || document.createElement("div");
    menu.className = "ui-settings";

    const schemes = SCHEMES.map(([value, label]) => `
      <label class="ui-settings__choice">
        <input type="radio" name="ui-settings-scheme" value="${value}">${SCHEME_ICONS[value]}<span>${label}</span>
      </label>`).join("");
    const layouts = select ? [...select.options].map((o) => `
      <label class="ui-settings__option">
        <input type="radio" name="ui-settings-layout" value="${escape(o.value)}">
        ${picture(o.value)}
        <span class="ui-settings__text"><span class="ui-settings__label">${escape(o.text)}</span>` +
        (o.dataset.note ? `<span class="ui-settings__note">${escape(o.dataset.note)}</span>` : "") + `</span>
      </label>`).join("") : "";
    menu.innerHTML = `
      <button type="button" class="ui-settings__button" aria-expanded="false" aria-controls="ui-settings-panel"
              title="Settings">${GEAR}<span class="ui-sr-only">Settings</span></button>
      <div class="ui-settings__panel" id="ui-settings-panel" role="group" aria-label="Settings" hidden>
        <div class="ui-settings__heading" id="ui-settings-scheme">Color scheme</div>
        <div class="ui-settings__choices" role="radiogroup" aria-labelledby="ui-settings-scheme">${schemes}</div>` +
        (select ? `
        <div class="ui-settings__heading" id="ui-settings-layout">Layout</div>
        <div role="radiogroup" aria-labelledby="ui-settings-layout">${layouts}</div>` : "") + `
      </div>`;

    const button = menu.querySelector("button"), panel = menu.querySelector(".ui-settings__panel");
    const schemeRadios = [...menu.querySelectorAll('input[name="ui-settings-scheme"]')];
    const layoutRadios = [...menu.querySelectorAll('input[name="ui-settings-layout"]')];
    const sync = () => {
      const now = scheme();
      schemeRadios.forEach((r) => { r.checked = r.value === now; });
      layoutRadios.forEach((r) => { r.checked = r.value === root.getAttribute("data-ui-layout"); });
    };
    const open = (yes) => {
      panel.hidden = !yes;
      button.setAttribute("aria-expanded", String(yes));
      if (yes) {
        sync();
        (schemeRadios.find((r) => r.checked) || schemeRadios[0]).focus();
      }
    };
    button.addEventListener("click", () => open(panel.hidden));
    for (const radio of schemeRadios) radio.addEventListener("change", () => setScheme(radio.value));
    for (const radio of layoutRadios) {
      radio.addEventListener("change", () => {
        select.value = radio.value;
        select.dispatchEvent(new Event("change"));                     // layout.js changes the layout
      });
    }
    menu.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !panel.hidden) {
        open(false);
        button.focus();
      }
    });
    document.addEventListener("pointerdown", (e) => { if (!panel.hidden && !menu.contains(e.target)) open(false); });
    menu.addEventListener("focusout", (e) => { if (e.relatedTarget && !menu.contains(e.relatedTarget)) open(false); });
    document.addEventListener("ui-layout", sync);
    document.addEventListener("ui-theme", sync);
    sync();

    if (!slot) {
      // no place made for it: at the end of the header, before the user (after the spacer, if there is one)
      const after = header.querySelector(":scope > .ui-spacer") || header.querySelector(":scope > .ui-nav");
      const user = header.querySelector(":scope > .ui-user");
      if (user) user.before(menu);
      else if (after) after.after(menu);
      else header.append(menu);
    }
    if (source) source.hidden = true;
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})();
