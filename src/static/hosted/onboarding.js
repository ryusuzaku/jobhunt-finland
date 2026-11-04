(() => {
  'use strict';
  const element = document.getElementById('setup-config');
  if (!element || !window.JobHunt) return;
  const setup = JSON.parse(element.textContent);
  const api = window.JobHunt;
  const profile = setup.profile || {};
  const key = `jh-setup-v1-${api.config.user_id}`;
  const names = ['job_profiles','experience_level','preferred_tech','preferred_locations','remote_ok','hybrid_ok','alert_threshold'];
  const state = {};
  names.forEach(name => { state[name] = profile[name]; });
  state.job_profiles = [...(state.job_profiles || [])];
  state.preferred_tech = [...(state.preferred_tech || [])];
  state.preferred_locations = [...(state.preferred_locations || [])];
  state.experience_level ||= 'junior';
  state.remote_ok = state.remote_ok !== false;
  state.hybrid_ok = state.hybrid_ok !== false;
  state.alert_threshold = Number(state.alert_threshold ?? 60);
  Object.assign(state, profile.draft || {});
  let step = Object.keys(profile.draft || {}).length ? Number(profile.draft_step || 1) : 1;
  let revision = Number(profile.revision || 0);
  let pendingSave = Promise.resolve();
  let saveTimer = null;
  let completing = false;
  const $ = selector => document.querySelector(selector);
  try {
    const local = JSON.parse(localStorage.getItem(key) || 'null');
    if (local && local.revision >= revision && Date.now() - local.saved_at < 30 * 86400000) {
      Object.assign(state, local.values); step = local.step || step;
    }
  } catch (_) { /* Server draft remains authoritative when local storage is unavailable. */ }
  step = Math.max(1, Math.min(6, step));
  function normalize(value) { return value.trim().toLowerCase(); }
  function values() { return Object.fromEntries(names.map(name => [name, state[name]])); }
  function error(message) { const area = $('#setup-error'); area.textContent = message || ''; area.hidden = !message; }
  function localSave() {
    try { localStorage.setItem(key, JSON.stringify({values:values(), step, revision, saved_at:Date.now()})); }
    catch (_) { /* Draft still saves to the account when connected. */ }
  }
  function queueSave() {
    localSave();
    $('#draft-status').textContent = navigator.onLine ? 'Saving your progress…' : 'Saved on this device · offline';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      const payload = {...values(), step};
      pendingSave = pendingSave.then(async () => {
        if (!navigator.onLine || completing) return;
        try {
          const result = await api.request('/api/profile/draft', {...payload, revision});
          revision = Number(result.profile.revision);
          localSave(); $('#draft-status').textContent = 'Progress saved to your account';
        } catch (failure) {
          $('#draft-status').textContent = 'Saved on this device · not synced';
          if (failure.status === 409) error('Your profile changed on another device. Reload before completing setup; this device’s draft is kept.');
          else if (failure.status && failure.status !== 401) error(failure.message);
        }
      });
    }, 550);
  }
  function toggle(name, value) {
    const collection = state[name];
    const position = collection.indexOf(value);
    if (position >= 0) collection.splice(position, 1); else collection.push(value);
    updateSelections(); queueSave();
  }
  function option(label, value, name) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'selection-button';
    button.textContent = label; button.dataset.selection = name; button.dataset.value = value;
    button.setAttribute('aria-pressed', String(state[name].includes(value)));
    return button;
  }
  function renderFields() {
    const groups = new Map();
    for (const [value, metadata] of Object.entries(setup.catalog || {})) {
      const group = metadata.group || 'Other fields';
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push({value, label:metadata.label || value});
    }
    const root = $('#field-choices'); root.replaceChildren();
    for (const [name, choices] of groups) {
      const details = document.createElement('details'); details.className = 'category-group';
      details.open = name === 'Tech' || choices.some(choice => state.job_profiles.includes(choice.value));
      const summary = document.createElement('summary'); summary.textContent = name;
      const area = document.createElement('div'); area.className = 'selection-options';
      choices.forEach(choice => area.append(option(choice.label, choice.value, 'job_profiles')));
      details.append(summary, area); root.append(details);
    }
  }
  function removable(value, name) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'removable-chip';
    button.dataset.selection = name; button.dataset.value = value; button.setAttribute('aria-label', `Remove ${value}`);
    const label = document.createElement('span'); label.textContent = value;
    const close = document.createElement('span'); close.textContent = '×'; close.setAttribute('aria-hidden', 'true');
    button.append(label, close); return button;
  }
  function updateSelections() {
    document.querySelectorAll('[data-selection]').forEach(button => button.setAttribute('aria-pressed', String(state[button.dataset.selection].includes(button.dataset.value))));
    document.querySelectorAll('[data-level]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.level === state.experience_level)));
    document.querySelectorAll('[data-location]').forEach(button => button.setAttribute('aria-pressed', String(state.preferred_locations.includes(button.dataset.location))));
    const skills = $('#selected-skills'); skills.replaceChildren(); state.preferred_tech.forEach(value => skills.append(removable(value, 'preferred_tech')));
    const suggestions = new Set();
    state.job_profiles.forEach(field => (setup.skills[field] || setup.catalog[field]?.skill_presets || []).forEach(skill => suggestions.add(skill)));
    const suggestionRoot = $('#skill-suggestions'); suggestionRoot.replaceChildren();
    [...suggestions].filter(value => !state.preferred_tech.includes(value)).slice(0, 24).forEach(value => suggestionRoot.append(option(value, value, 'preferred_tech')));
    if (!suggestionRoot.childElementCount) { const note = document.createElement('p'); note.className = 'field-help'; note.textContent = 'Add any skills that matter to your search.'; suggestionRoot.append(note); }
    const predefined = new Set([...document.querySelectorAll('[data-location]')].map(button => button.dataset.location));
    const custom = $('#custom-locations'); custom.replaceChildren(); state.preferred_locations.filter(value => !predefined.has(value)).forEach(value => custom.append(removable(value, 'preferred_locations')));
    $('#remote-ok').checked = state.remote_ok; $('#hybrid-ok').checked = state.hybrid_ok;
    $('#match-threshold').value = String(state.alert_threshold); $('#threshold-output').textContent = String(state.alert_threshold);
    renderReview();
  }
  function renderReview() {
    const levels = {student:'Studying / exploring',graduate:'Recently graduated',junior:'Early career',mid:'Some experience'};
    const work = [state.remote_ok ? 'Remote-friendly is a plus' : '', state.hybrid_ok ? 'Hybrid works for me' : ''].filter(Boolean).join(' · ') || 'Location-first search';
    const rows = [
      ['Fields',state.job_profiles.map(value => setup.catalog[value]?.label || value).join(' · ') || 'Choose a field',1],
      ['Experience',levels[state.experience_level],2],
      ['Skills',state.preferred_tech.join(' · ') || 'No specific skills selected',3],
      ['Places & work',`${state.preferred_locations.join(' · ') || 'Choose a location'} · ${work}`,4],
      ['Match threshold',`${state.alert_threshold}% · saved preference`,5]
    ];
    const root = $('#setup-review'); root.replaceChildren();
    rows.forEach(([title, value, target]) => {
      const row = document.createElement('div'); row.className = 'review-row';
      const copy = document.createElement('div'); const heading = document.createElement('strong'); heading.textContent = title;
      const text = document.createElement('p'); text.textContent = value; copy.append(heading, text);
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'text-button'; edit.textContent = 'Edit'; edit.dataset.goStep = String(target); edit.setAttribute('aria-label', `Edit ${title.toLowerCase()}`);
      row.append(copy, edit); root.append(row);
    });
  }
  function showStep(target, focus = true) {
    step = target;
    document.querySelectorAll('[data-step]').forEach(section => { section.hidden = Number(section.dataset.step) !== step; });
    document.querySelectorAll('[data-step-label]').forEach(label => { label.classList.toggle('active', Number(label.dataset.stepLabel) === step); label.classList.toggle('completed', Number(label.dataset.stepLabel) < step); });
    document.querySelectorAll('[data-step-bar]').forEach(bar => bar.classList.toggle('active', Number(bar.dataset.stepBar) <= step));
    $('#step-counter').textContent = `STEP ${String(step).padStart(2,'0')} / 06`;
    $('#setup-back').hidden = step === 1;
    $('#setup-next span').textContent = step === 6 ? 'Find my direction' : 'Continue';
    renderReview(); error('');
    if (focus) {
      const heading = $(`[data-step="${step}"] h1`); heading.setAttribute('tabindex','-1'); heading.focus({preventScroll:true}); window.scrollTo({top:0,behavior:'instant'});
    }
    queueSave();
  }
  function validStep() {
    if (step === 1 && !state.job_profiles.length) { error('Choose at least one field to give your search a direction.'); return false; }
    if (step === 4 && !state.preferred_locations.length) { error('Choose at least one place you would consider.'); return false; }
    return true;
  }
  async function complete() {
    if (completing) return;
    completing = true; clearTimeout(saveTimer); error('');
    const next = $('#setup-next'); next.disabled = true; next.setAttribute('aria-busy','true');
    try {
      await pendingSave;
      const result = await api.request('/api/profile/complete', {...values(), revision});
      if (!result.profile.onboarding_completed) throw new Error('Your profile was not completed. Try again.');
      try { localStorage.removeItem(key); } catch (_) { /* Successful server save does not depend on local storage. */ }
      location.assign('/discover?refresh=1');
    } catch (failure) {
      error(failure.status === 409 ? 'Your profile changed on another device. Reload to review the latest version; this device’s draft is kept.' : failure.message);
      completing = false; next.disabled = false; next.removeAttribute('aria-busy');
    }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.selection) toggle(button.dataset.selection, button.dataset.value);
    else if (button.dataset.level) { state.experience_level = button.dataset.level; updateSelections(); queueSave(); }
    else if (button.dataset.location) toggle('preferred_locations', button.dataset.location);
    else if (button.dataset.goStep) showStep(Number(button.dataset.goStep));
  });
  $('#setup-next').addEventListener('click', () => { if (validStep()) { if (step === 6) complete(); else showStep(step + 1); } });
  $('#setup-back').addEventListener('click', () => showStep(Math.max(1,step - 1)));
  $('#skill-form').addEventListener('submit', event => { event.preventDefault(); const input = $('#custom-skill'); const value = normalize(input.value); if (value && !state.preferred_tech.includes(value)) { state.preferred_tech.push(value); input.value = ''; updateSelections(); queueSave(); } });
  $('#location-form').addEventListener('submit', event => { event.preventDefault(); const input = $('#custom-location'); const value = normalize(input.value); if (value && !state.preferred_locations.includes(value)) { state.preferred_locations.push(value); input.value = ''; updateSelections(); queueSave(); } });
  ['remote','hybrid'].forEach(kind => $(`#${kind}-ok`).addEventListener('change', event => { state[`${kind}_ok`] = event.target.checked; queueSave(); renderReview(); }));
  $('#match-threshold').addEventListener('input', event => { state.alert_threshold = Number(event.target.value); $('#threshold-output').textContent = String(state.alert_threshold); queueSave(); renderReview(); });
  window.addEventListener('online', queueSave);
  renderFields(); updateSelections(); showStep(step,false);
})();
