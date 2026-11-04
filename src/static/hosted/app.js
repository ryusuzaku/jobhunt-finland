(() => {
  'use strict';
  const configElement = document.getElementById('app-config');
  const config = configElement ? JSON.parse(configElement.textContent) : {};
  const storageKey = 'jh-public-jobs-v1';
  let installEvent = null;
  let refreshRunning = false;
  let deleteResolver = null;
  const $ = selector => document.querySelector(selector);
  function toast(message, error = false) {
    const node = document.createElement('div');
    node.className = `toast${error ? ' error' : ''}`;
    node.setAttribute('role', error ? 'alert' : 'status');
    node.textContent = message;
    $('#toasts')?.append(node);
    setTimeout(() => node.remove(), error ? 7000 : 4500);
  }
  function messageFor(data, fallback) {
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) return data.detail.map(item => item.msg || 'Check your input').join('. ');
    return data?.error || fallback;
  }
  async function request(path, data, method = 'POST') {
    if (!navigator.onLine) throw new Error('You’re offline. Reconnect before saving changes.');
    const options = {method, credentials: 'same-origin', headers: {'X-CSRF-Token': config.csrf_token || ''}};
    if (data !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(data);
    }
    const response = await fetch(path, options);
    let result;
    try { result = await response.json(); } catch (_) { throw new Error('The server returned an unreadable response. Try again.'); }
    if (!response.ok || result.ok === false) {
      const error = new Error(messageFor(result, 'Could not save this change.'));
      error.status = response.status;
      throw error;
    }
    if (result.csrf_token) config.csrf_token = result.csrf_token;
    return result;
  }
  async function signIn(button) {
    if (button.getAttribute('aria-busy') === 'true') return;
    button.setAttribute('aria-busy', 'true');
    try {
      const result = await request('/auth/start', {origin: window.location.origin});
      const url = new URL(result.authorize_url);
      if (url.protocol !== 'https:') throw new Error('The sign-in service returned an unsafe address.');
      location.assign(url.href);
    } catch (error) { toast(error.message, true); button.removeAttribute('aria-busy'); }
  }
  function setSaved(jobId, saved) {
    document.querySelectorAll('[data-save-job]').forEach(button => {
      if (button.dataset.saveJob !== String(jobId)) return;
      button.setAttribute('aria-pressed', String(saved));
      button.classList.toggle('is-saved', saved);
      const original = button.getAttribute('aria-label') || 'Save job';
      button.setAttribute('aria-label', original.replace(/^(Save|Unsave)/, saved ? 'Unsave' : 'Save'));
    });
  }
  async function saveJob(button) {
    const jobId = button.dataset.saveJob;
    const desired = button.getAttribute('aria-pressed') !== 'true';
    button.disabled = true;
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(jobId)}/save`, {saved: desired});
      setSaved(jobId, Boolean(result.saved));
      toast(result.saved ? 'Added to your shortlist.' : 'Removed from your shortlist.');
      if (config.page === 'saved' && !result.saved) {
        button.closest('[data-job-card]')?.remove();
        if (!$('[data-saved-list] [data-job-card]')) location.reload();
      }
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; }
  }
  async function saveApplication(form) {
    const submit = form.querySelector('[type="submit"]');
    const errorNode = form.querySelector('[data-form-error]');
    const values = Object.fromEntries(new FormData(form).entries());
    const data = {status: values.status, applied_at: values.applied_at || null, closing_date: values.closing_date || null, notes: values.notes || '', outcome: values.outcome || ''};
    if (errorNode) errorNode.hidden = true;
    if (submit) submit.disabled = true;
    try {
      await request(`/api/jobs/${encodeURIComponent(form.dataset.jobId)}/application`, data);
      toast('Your tracker is up to date.');
      location.assign('/tracker');
    } catch (error) {
      if (errorNode) { errorNode.textContent = error.message; errorNode.hidden = false; }
      else toast(error.message, true);
    } finally { if (submit) submit.disabled = false; }
  }
  function confirmDeletion() {
    const dialog = $('#confirm-dialog');
    if (!dialog?.showModal) return Promise.resolve(window.confirm('Remove this tracker entry and its notes?'));
    dialog.showModal();
    return new Promise(resolve => { deleteResolver = resolve; });
  }
  function settleDeletion(confirmed) {
    $('#confirm-dialog')?.close();
    if (deleteResolver) { deleteResolver(confirmed); deleteResolver = null; }
  }
  async function deleteApplication(button) {
    if (!await confirmDeletion()) return;
    button.disabled = true;
    try {
      await request(`/api/applications/${encodeURIComponent(button.dataset.deleteApplication)}`, undefined, 'DELETE');
      toast('Tracker entry removed.');
      location.reload();
    } catch (error) { toast(error.message, true); button.disabled = false; }
  }
  function sourceHealth(state) {
    const root = $('#source-health');
    if (!root) return;
    root.replaceChildren();
    const names = {academicwork:'Academic Work', companycareers:'Company careers', duunitori:'Duunitori', englishjobs:'EnglishJobs', hasjob:'Hasjob', internshala:'Internshala', jobly:'Jobly', linkedin:'LinkedIn', remoteok:'Remote OK', remotive:'Remotive', shine:'Shine', thehub:'The Hub', weworkremotely:'We Work Remotely', workingnomads:'Working Nomads'};
    const labels = {fresh:'Fetched', cached:'Cached', error:'Unavailable', empty:'No matches', disabled:'Disabled', queued:'Waiting', running:'Checking'};
    for (const [name, value] of Object.entries(state.sources || {})) {
      const row = document.createElement('div'); row.className = 'source-item';
      const label = document.createElement('span'); label.textContent = names[name] || name.replaceAll('_', ' ');
      const status = document.createElement('span');
      status.className = value.status === 'error' ? 'error' : 'success';
      status.textContent = `${labels[value.status] || value.status || 'Unknown'}${value.count !== undefined ? ` · ${value.count}` : ''}`;
      if (value.error) {
        row.title = value.error;
        status.textContent += value.error === 'SourceLayoutError' ? ' · Page layout changed' : value.error === 'TimeoutError' ? ' · Timed out' : ' · Request failed';
      }
      row.append(label, status); root.append(row);
    }
  }
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function refresh() {
    if (refreshRunning) return;
    refreshRunning = true;
    document.querySelectorAll('[data-refresh]').forEach(button => { button.disabled = true; button.setAttribute('aria-busy', 'true'); });
    const status = $('#refresh-status');
    if (status) status.textContent = 'Checking connected job sources…';
    try {
      const pending = request('/api/fetch', {});
      // Poll while the refresh request is still alive; do not erase open drafts.
      let responseSettled = false;
      let responseError = null;
      let run = null;
      pending.then(result => { run = result; responseSettled = true; }).catch(error => { responseError = error; responseSettled = true; });
      const deadline = Date.now() + 900000;
      while (Date.now() < deadline) {
        await pause(1500);
        if (responseError) throw responseError;
        const state = await request('/api/fetch/status', undefined, 'GET');
        sourceHealth(state);
        const values = Object.values(state.sources || {});
        const complete = values.filter(item => ['fresh', 'cached', 'empty', 'error', 'disabled'].includes(item.status)).length;
        if (status) status.textContent = values.length ? `Checked ${complete} of ${values.length} sources…` : 'Checking connected job sources…';
        if (responseSettled && ['success', 'error'].includes(state.status)) { run = state; break; }
        if (responseSettled && run && ['success', 'error'].includes(run.status)) break;
      }
      if (!run || !['success', 'error'].includes(run.status)) throw new Error('The refresh has not finished. Check source health again shortly.');
      if (run.status === 'error') throw new Error(run.error || 'No source completed successfully. Your existing jobs are kept.');
      const count = run.new_jobs ?? run.new ?? 0;
      if (status) {
        status.replaceChildren(document.createTextNode(`Refresh complete · ${count} new roles. `));
        const link = document.createElement('a'); link.href = location.pathname + location.search; link.className = 'text-link'; link.textContent = 'Show updated list'; status.append(link);
      }
      toast(`Refresh complete. ${count} new roles. Reopen the list when you’re ready.`);
    } catch (error) { if (status) status.textContent = error.message; toast(error.message, true); }
    finally {
      refreshRunning = false;
      document.querySelectorAll('[data-refresh]').forEach(button => { button.disabled = false; button.removeAttribute('aria-busy'); });
    }
  }
  function openInstall() {
    if (installEvent) {
      installEvent.prompt();
      installEvent.userChoice.finally(() => { installEvent = null; });
      return;
    }
    const area = $('#install-instructions');
    if (!area) return;
    area.replaceChildren();
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isAndroid = /Android/.test(navigator.userAgent);
    const lines = isIOS ? ['Open JobHunt in your phone browser.', 'Tap the Share button, then “Add to Home Screen”.', 'Confirm the name and tap Add.'] : isAndroid ? ['Open JobHunt in Chrome or Samsung Internet.', 'Open the browser menu and choose “Install app” or “Add to Home screen”.', 'Confirm installation. Other browsers may add a shortcut instead.'] : ['Use the browser’s install icon or app menu if available.', 'On a phone, open the hosted HTTPS address—not this computer’s localhost.', 'If installation is unavailable, bookmark the site; the web app still works.'];
    if (location.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(location.hostname)) lines.unshift('Installation requires the hosted HTTPS address.');
    const list = document.createElement('ol');
    for (const line of lines) { const item = document.createElement('li'); item.textContent = line; list.append(item); }
    area.append(list); $('#install-dialog')?.showModal();
  }
  function cachePublicJob() {
    const node = $('#public-job-cache');
    if (!node) return;
    try {
      const item = JSON.parse(node.textContent);
      const existing = JSON.parse(localStorage.getItem(storageKey) || '[]');
      const data = [item, ...existing.filter(job => job.id !== item.id)].slice(0, 12);
      localStorage.setItem(storageKey, JSON.stringify(data));
    } catch (_) { /* Optional local caching must not prevent using the app. */ }
  }
  function renderOfflineJobs() {
    const area = $('#offline-jobs');
    if (!area) return;
    let jobs = [];
    try { jobs = JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch (_) { return; }
    for (const job of jobs) {
      const card = document.createElement('article'); card.className = 'offline-job';
      const title = document.createElement('h2'); title.textContent = job.title || 'Previously viewed role';
      const metadata = document.createElement('p'); metadata.textContent = `${job.company || ''} · ${job.location || ''}`;
      const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Read cached description';
      const description = document.createElement('p'); description.textContent = job.description || 'No description was provided.';
      details.append(summary, description); card.append(title, metadata, details); area.append(card);
    }
  }
  async function logout(button) {
    button.disabled = true;
    try {
      await request('/auth/logout', {});
      localStorage.removeItem(storageKey);
      if (config.user_id !== null) localStorage.removeItem(`jh-setup-v1-${config.user_id}`);
      location.assign('/');
    } catch (error) { toast(error.message, true); button.disabled = false; }
  }
  function connectionChanged() { const banner = $('#connectivity'); if (banner) banner.hidden = navigator.onLine; }
  document.addEventListener('click', event => {
    const button = event.target.closest('button, a');
    if (!button) return;
    if (button.hasAttribute('data-signin')) { event.preventDefault(); signIn(button); }
    else if (button.hasAttribute('data-save-job')) saveJob(button);
    else if (button.hasAttribute('data-open-filters')) $('#filter-dialog')?.showModal();
    else if (button.hasAttribute('data-close-dialog')) button.closest('dialog')?.close();
    else if (button.hasAttribute('data-refresh')) refresh();
    else if (button.hasAttribute('data-install')) openInstall();
    else if (button.hasAttribute('data-delete-application')) deleteApplication(button);
    else if (button.hasAttribute('data-cancel-confirm')) settleDeletion(false);
    else if (button.hasAttribute('data-accept-confirm')) settleDeletion(true);
    else if (button.hasAttribute('data-logout')) logout(button);
  });
  document.addEventListener('submit', event => { if (event.target.matches('[data-application-form]')) { event.preventDefault(); saveApplication(event.target); } });
  document.addEventListener('change', event => { if (event.target.matches('[data-auto-submit]')) event.target.form.requestSubmit(); });
  $('#confirm-dialog')?.addEventListener('cancel', () => settleDeletion(false));
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    if (dialog.id === 'confirm-dialog') settleDeletion(false); else dialog.close();
  }));
  window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); installEvent = event; });
  window.addEventListener('online', connectionChanged); window.addEventListener('offline', connectionChanged); connectionChanged();
  cachePublicJob(); renderOfflineJobs();
  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/service-worker.js').catch(() => { /* Install help remains available if worker registration fails. */ });
  window.JobHunt = {request, toast, config};
  if (config.page === 'discover' && new URLSearchParams(location.search).get('refresh') === '1') {
    const url = new URL(location.href); url.searchParams.delete('refresh'); history.replaceState(null, '', url.pathname + url.search);
    refresh();
  } else if (config.page === 'discover') {
    request('/api/fetch/status', undefined, 'GET').then(state => {
      sourceHealth(state);
      const status = $('#refresh-status');
      if (status && state.finished_at) {
        const checked = new Date(state.finished_at);
        status.textContent = `Last checked ${checked.toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}`;
      } else if (status && state.status === 'running') status.textContent = 'A refresh is running. Tap Refresh to follow its progress.';
    }).catch(() => { const status = $('#refresh-status'); if (status) status.textContent = 'Source status is unavailable. Your existing jobs are kept.'; });
  }
})();
