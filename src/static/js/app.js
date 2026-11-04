/* JobHunt frontend helpers: theme, toasts, refresh, hide, PWA install. */
(function () {
  "use strict";

  /* ---------- Toast notifications ---------- */
  function toast(message, type, timeout) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    type = type || "info";
    timeout = timeout == null ? 4000 : timeout;

    var colors = {
      info: "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900",
      success: "bg-emerald-600 text-white",
      error: "bg-rose-600 text-white",
      progress: "bg-brand-600 text-white",
    };
    var el = document.createElement("div");
    el.className =
      "pointer-events-auto flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-lift animate-fade-up " +
      (colors[type] || colors.info);
    if (type === "progress") {
      var spin = document.createElement("span");
      spin.className =
        "h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white";
      el.appendChild(spin);
    }
    var text = document.createElement("span");
    text.textContent = message;
    el.appendChild(text);
    container.appendChild(el);
    if (timeout > 0) {
      setTimeout(function () {
        el.style.transition = "opacity .3s, transform .3s";
        el.style.opacity = "0";
        el.style.transform = "translateY(6px)";
        setTimeout(function () { el.remove(); }, 320);
      }, timeout);
    }
    return el;
  }
  window.toast = toast;

  /* ---------- Dark mode toggle ---------- */
  var themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var dark = document.documentElement.classList.toggle("dark");
      try { localStorage.setItem("jh-theme", dark ? "dark" : "light"); } catch (e) {}
    });
  }

  /* ---------- Hide job ---------- */
  window.hideJob = function (id) {
    fetch("/hide/" + id, { method: "POST" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        var card = document.getElementById("job-" + id);
        if (card) {
          card.style.transition = "opacity .3s, transform .3s";
          card.style.opacity = "0";
          card.style.transform = "scale(.98)";
          setTimeout(function () { card.remove(); }, 320);
        }
        toast("Job hidden", "info");
      })
      .catch(function () { toast("Could not hide job", "error"); });
  };

  /* ---------- Refresh (fetch latest jobs) ---------- */
  var refreshBtn = document.getElementById("refresh-btn");
  var refreshIcon = document.getElementById("refresh-icon");
  var statusText = document.getElementById("fetch-status");
  var sourceList = document.getElementById("source-status");
  var reloadBtn = document.getElementById("reload-jobs");
  var pollTimer = null;
  var watchedRefresh = false;

  function renderRefresh(data) {
    var running = data.status === "running";
    if (refreshBtn) refreshBtn.disabled = running;
    if (refreshIcon) refreshIcon.classList.toggle("animate-spin", running);
    if (statusText) statusText.textContent = running
      ? "Refreshing jobs in the background — you can keep using the app."
      : data.status === "error" ? data.error
      : data.status === "success" ? "Last refresh: " + (data.new_jobs || 0) + " new jobs, " + (data.updated_jobs || 0) + " updated."
      : "Ready to fetch jobs.";
    if (sourceList) {
      sourceList.replaceChildren();
      Object.keys(data.sources || {}).forEach(function (name) {
        var item = document.createElement("li");
        var source = data.sources[name];
        item.textContent = name + ": " + source.status + " (" + source.count + " jobs)";
        sourceList.appendChild(item);
      });
    }
    if (running) watchedRefresh = true;
    if (watchedRefresh && !running) {
      watchedRefresh = false;
      toast(data.ok ? "Job refresh complete" : (data.error || "Job refresh failed"), data.ok ? "success" : "error");
      if (reloadBtn && (location.pathname === "/" || location.pathname === "/bengaluru")) reloadBtn.classList.remove("hidden");
    }
    return running;
  }

  function monitorRefresh() {
    clearTimeout(pollTimer);
    fetch("/api/fetch/status", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("Status unavailable"); return r.json(); })
      .then(function (data) {
        if (renderRefresh(data)) pollTimer = setTimeout(monitorRefresh, 2000);
      })
      .catch(function () {
        if (statusText) statusText.textContent = "Refresh status unavailable. Check your connection or try again.";
        if (refreshBtn) refreshBtn.disabled = false;
        if (refreshIcon) refreshIcon.classList.remove("animate-spin");
      });
  }
  if (reloadBtn) reloadBtn.addEventListener("click", function () { location.reload(); });
  if (refreshBtn) refreshBtn.addEventListener("click", function () {
    if (refreshBtn.disabled) return;
    refreshBtn.disabled = true;
    fetch("/fetch", { method: "POST" })
      .then(function (r) { if (!r.ok) throw new Error("Could not start refresh"); return r.json(); })
      .then(function () { watchedRefresh = true; monitorRefresh(); })
      .catch(function () { refreshBtn.disabled = false; toast("Could not start job refresh", "error"); });
  });
  monitorRefresh();

  /* ---------- PWA install prompt ---------- */
  var deferredPrompt = null;
  var installBtn = document.getElementById("install-btn");
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    if (installBtn) installBtn.classList.remove("hidden");
  });
  if (installBtn) {
    installBtn.addEventListener("click", function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
        installBtn.classList.add("hidden");
      });
    });
  }

  /* ---------- Service worker ---------- */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/static/sw.js", { scope: "/", updateViaCache: "none" }).catch(function () {});
    });
  }
})();
