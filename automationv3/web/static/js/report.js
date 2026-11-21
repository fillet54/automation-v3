/* A report's pages (templates/reports/page.html).

   The navigation remembers, per report and per reader, which branches are
   open and the "Issues only" switch. While runs are in progress htmx
   refreshes the page and the navigation; all of this is applied again
   after each refresh. */
(function () {
  "use strict";

  function nav() { return document.getElementById("report-nav"); }
  function storageKey() { return "report-nav:" + (nav() ? nav().dataset.report : ""); }

  function load() {
    try { return JSON.parse(localStorage.getItem(storageKey())) || {}; } catch (e) { return {}; }
  }
  function save(state) {
    try { localStorage.setItem(storageKey(), JSON.stringify(state)); } catch (e) { /* not kept */ }
  }

  // The navigation: what a reader opened or closed, and the switch
  function restoreNav() {
    var root = nav();
    if (!root) return;
    var state = load(), open = state.open || {};
    root.querySelectorAll("details[data-key]").forEach(function (details) {
      if (details.dataset.key in open) details.open = open[details.dataset.key];
    });
    var issues = root.querySelector("[data-issues-only]");
    if (issues) issues.checked = !!state.issuesOnly;
    root.classList.toggle("report-nav--issues", !!state.issuesOnly);
  }

  // Only a reader's own toggles are kept: details rendered open fire
  // "toggle" too, and those are the page's defaults
  var toggling = null;
  document.addEventListener("click", function (event) {
    var summary = event.target.closest("#report-nav details[data-key] > summary");
    if (summary && !event.target.closest("a")) toggling = summary.parentElement;
  });

  document.addEventListener("toggle", function (event) {
    var details = event.target;
    if (details !== toggling) return;
    toggling = null;
    var state = load();
    state.open = state.open || {};
    state.open[details.dataset.key] = details.open;
    save(state);
  }, true);

  document.addEventListener("change", function (event) {
    if (!event.target.matches("[data-issues-only]")) return;
    var state = load();
    state.issuesOnly = event.target.checked;
    save(state);
    nav().classList.toggle("report-nav--issues", state.issuesOnly);
  });

  // Rename in place
  document.addEventListener("click", function (event) {
    var header = event.target.closest(".report-title");
    if (!header) return;
    var form = header.querySelector(".report-title__form");
    var show = header.querySelector(".report-title__show");
    if (event.target.closest("[data-rename]")) {
      form.hidden = false;
      show.hidden = true;
      var input = form.querySelector("input[name=name]");
      input.focus();
      input.select();
    } else if (event.target.closest("[data-rename-cancel]")) {
      form.hidden = true;
      show.hidden = false;
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || !event.target.matches(".report-title__input")) return;
    var cancel = event.target.form.querySelector("[data-rename-cancel]");
    if (cancel) cancel.click();
  });
  document.addEventListener("submit", function (event) {
    if (!event.target.matches(".report-title__form")) return;
    var next = event.target.querySelector("input[name=next]");
    if (next) next.value = window.location.pathname + window.location.search + window.location.hash;
  });

  // Refreshes while runs are in progress: ask for the page as filtered now,
  // and don't refresh under a reader renaming the report
  document.addEventListener("htmx:configRequest", function (event) {
    if (event.detail.elt && event.detail.elt.id === "report-main") {
      event.detail.path = window.location.pathname + window.location.search;
    }
  });
  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = document.querySelector(".report-title__form");
    if (event.detail.elt && event.detail.elt.id === "report-main" && form && !form.hidden) {
      event.preventDefault();
    }
  });
  document.addEventListener("htmx:afterSettle", function () {
    restoreNav();
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", restoreNav);
  else restoreNav();
})();
