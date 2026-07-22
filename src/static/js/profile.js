/* JobHunt local-first profile layer.
 *
 * The profile (onboarding answers) is mirrored into localStorage so the app
 * keeps working offline and across devices without an account. The server
 * copy wins when its profile_updated_at is newer; otherwise the local copy
 * is pushed up. This is the seam where per-user cloud sync plugs in later.
 */
(function () {
  "use strict";

  var KEY = "jh-profile";

  function readLocal() {
    try {
      var raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function writeLocal(profile) {
    try {
      localStorage.setItem(KEY, JSON.stringify(profile));
    } catch (e) {}
  }

  function newerThan(a, b) {
    // ISO strings compare lexicographically; missing = oldest.
    return (a || "") > (b || "");
  }

  function sync() {
    var local = readLocal();
    fetch("/api/profile")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (server) {
        if (!server) return;
        if (newerThan(server.profile_updated_at, local && local.profile_updated_at)) {
          // Server is newer → adopt it locally.
          writeLocal(server);
        } else if (local && newerThan(local.profile_updated_at, server.profile_updated_at)) {
          // Local is newer (e.g. saved offline elsewhere) → push up.
          fetch("/api/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(local),
          }).catch(function () {});
        }
      })
      .catch(function () {
        /* Offline — the local copy keeps the app usable. */
      });
  }

  window.JHProfile = {
    get: readLocal,
    set: function (profile) {
      writeLocal(profile);
      return fetch("/api/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (data && data.profile) writeLocal(data.profile);
        return data;
      });
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
