/* Onboarding configuration is JSON text, never JavaScript embedded in an HTML attribute. */
(function () {
  "use strict";
  document.addEventListener("alpine:init", function () {
    Alpine.data("onboarding", function () {
      var config = JSON.parse(document.getElementById("onboarding-config").textContent);
      var prefs = config.prefs;
      return {
        step: 1,
        tracks: prefs.job_profiles.length ? prefs.job_profiles : (prefs.role_tracks || []),
        level: prefs.experience_level || "junior",
        techs: prefs.preferred_tech || [],
        techSearch: "",
        locations: prefs.preferred_locations || [],
        remoteOk: prefs.remote_ok,
        hybridOk: prefs.hybrid_ok,
        threshold: prefs.alert_threshold,
        saving: false,
        error: "",
        skillMap: config.skillMap,
        labelMap: config.labelMap,
        defaultPresets: ["python", "javascript", "typescript", "react", "node.js", "java", "c#", "c++", "go", "rust", "php", "ruby", "swift", "kotlin", "sql", "postgresql", "mysql", "mongodb", "redis", "docker", "kubernetes", "aws", "azure", "gcp", "terraform", "linux", "git", "html", "css", "vue", "angular", "django", "flask", "fastapi", "spring", ".net", "graphql", "tensorflow", "pytorch", "pandas"],
        get filteredPresets() {
          var pool = this.defaultPresets.slice();
          for (var track of this.tracks) {
            if (this.skillMap[track]) pool.push.apply(pool, this.skillMap[track]);
          }
          var query = this.techSearch.toLowerCase().trim();
          return Array.from(new Set(pool)).filter(t => !this.techs.includes(t) && (!query || t.includes(query))).slice(0, 14);
        },
        toggleTrack(track) {
          this.tracks = this.tracks.includes(track) ? this.tracks.filter(t => t !== track) : this.tracks.concat(track);
        },
        toggleLocation(location) {
          this.locations = this.locations.includes(location) ? this.locations.filter(t => t !== location) : this.locations.concat(location);
        },
        addTech(skill) {
          skill = skill.toLowerCase().trim();
          if (skill && !this.techs.includes(skill)) this.techs.push(skill);
          this.techSearch = "";
        },
        removeTech(skill) { this.techs = this.techs.filter(t => t !== skill); },
        async finish(skipped) {
          if (this.saving) return;
          this.saving = true;
          this.error = "";
          var profile = skipped ? { onboarding_completed: true } : {
            job_profiles: this.tracks,
            experience_level: this.level,
            preferred_tech: this.techs,
            preferred_locations: this.locations,
            remote_ok: this.remoteOk,
            hybrid_ok: this.hybridOk,
            alert_threshold: Number(this.threshold),
            onboarding_completed: true,
          };
          try {
            var response = await fetch("/api/profile", {
              method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(profile),
            });
            var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || "Could not save profile. Please try again.");
            if (window.JHProfile) window.JHProfile.remember(data.profile);
            window.location.assign("/");
          } catch (error) {
            this.error = error.message || "Could not save profile. Check your connection and try again.";
            this.saving = false;
          }
        },
      };
    });
  });
})();
