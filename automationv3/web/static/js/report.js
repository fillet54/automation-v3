/* A report's pages (templates/reports/page.html).

   On the Runs page, a subsystem, requirement or script in the navigation
   filters the page to its subsystem in place, then scrolls to it; the URL
   follows (?subsystem=...#anchor), so links can be shared and back and
   forward work. The navigation remembers, per report and per reader, which
   branches are open and the "Issues only" switch. While runs are in
   progress htmx refreshes the page and the navigation; all of this is
   applied again after each refresh. */
(function () {
  "use strict";

  function nav() { return document.getElementById("report-nav"); }
  function onRunsPage() {
    var main = document.getElementById("report-main");
    return main && main.dataset.page === "runs";
  }
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
    markCurrent(new URL(window.location.href));
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

  // The Runs page's filter
  function markCurrent(url) {
    var root = nav();
    if (!root || !onRunsPage()) return;
    var subsystem = url.searchParams.get("subsystem");
    var hash = url.hash.slice(1);
    root.querySelectorAll("a[data-nav]").forEach(function (link) {
      var target = new URL(link.href, window.location.href);
      var current = target.pathname === url.pathname &&
        (target.searchParams.get("subsystem") || "") === (subsystem || "") &&
        target.hash.slice(1) === hash;
      if (current) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function applyFilter(url, scroll) {
    if (!onRunsPage()) return;
    var subsystem = url.searchParams.get("subsystem");
    document.querySelectorAll(".report-group[data-subsystem]").forEach(function (group) {
      group.hidden = !!subsystem && group.dataset.subsystem !== subsystem;
    });
    var filter = document.getElementById("report-filter");
    if (filter) {
      filter.hidden = !subsystem;
      var name = filter.querySelector("[data-filter-name]");
      if (name) name.textContent = subsystem || "";
    }
    markCurrent(url);

    document.querySelectorAll(".report-target").forEach(function (el) {
      el.classList.remove("report-target");
    });
    var hash = decodeURIComponent(url.hash.slice(1));
    var target = hash && document.getElementById(hash);
    if (!target) {
      if (scroll) window.scrollTo({ top: 0 });
      return;
    }
    var marked = target.matches("tr[data-script]")
      ? document.querySelectorAll('tr[data-script="' + CSS.escape(hash) + '"]')
      : [target];
    marked.forEach(function (el) { el.classList.add("report-target"); });
    if (scroll) target.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-nav]");
    if (!link || !onRunsPage() || event.metaKey || event.ctrlKey || event.shiftKey) return;
    var url = new URL(link.href, window.location.href);
    if (url.pathname !== window.location.pathname) return;
    event.preventDefault();
    history.pushState({}, "", url);
    applyFilter(url, true);
  });

  window.addEventListener("popstate", function () {
    applyFilter(new URL(window.location.href), true);
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
    applyFilter(new URL(window.location.href), false);
  });

  function start() {
    restoreNav();
    applyFilter(new URL(window.location.href), !!window.location.hash);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
