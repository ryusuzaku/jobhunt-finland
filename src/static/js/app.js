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

  function skeletonCard() {
    var el = document.createElement("article");
    el.className = "card p-4 sm:p-5 skeleton-card";
    el.innerHTML =
      '<div class="flex items-start gap-4">' +
      '<div class="flex-1 space-y-2">' +
      '<div class="skeleton h-3 w-24 rounded-full"></div>' +
      '<div class="skeleton h-5 w-3/4 rounded-lg"></div>' +
      '<div class="skeleton h-3 w-1/3 rounded-full"></div>' +
      '<div class="flex gap-2 pt-1">' +
      '<div class="skeleton h-5 w-16 rounded-full"></div>' +
      '<div class="skeleton h-5 w-20 rounded-full"></div>' +
      "</div></div>" +
      '<div class="skeleton h-14 w-14 rounded-full"></div>' +
      "</div>";
    return el;
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      if (refreshBtn.disabled) return;
      refreshBtn.disabled = true;
      if (refreshIcon) refreshIcon.classList.add("animate-spin");
      var progress = toast("Fetching the latest jobs from all sources…", "progress", 0);

      var list = document.getElementById("job-list");
      var skeletons = [];
      if (list) {
        for (var i = 0; i < 3; i++) {
          var sk = skeletonCard();
          list.insertBefore(sk, list.firstChild);
          skeletons.push(sk);
        }
      }

      fetch("/fetch", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (progress) progress.remove();
          var msg = data && data.ok
            ? "Done — " + (data.new_jobs || 0) + " new jobs. Reloading…"
            : "Fetch finished. Reloading…";
          toast(msg, "success", 2000);
          setTimeout(function () { location.reload(); }, 900);
        })
        .catch(function () {
          if (progress) progress.remove();
          skeletons.forEach(function (sk) { sk.remove(); });
          toast("Fetch failed — check the server logs", "error");
          refreshBtn.disabled = false;
          if (refreshIcon) refreshIcon.classList.remove("animate-spin");
        });
    });
  }

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
      navigator.serviceWorker.register("/static/sw.js").catch(function () {});
    });
  }
})();
