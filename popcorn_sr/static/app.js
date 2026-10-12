const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const bytes = (n) => n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
const engineNames = {'resize':'Conventional resizing', 'realesrgan':'Real-ESRGAN AI upscaling', 'rtx-vsr':'RTX Video Super Resolution', 'dlss-sr':'DLSS video upscaling · experimental', 'dlss5':'DLSS 5 neural rendering · experimental'};
let state = null, view = 'overview', directory = '.', offset = 0, total = 0, selected = null, refreshing = false, workerSignature = '', jobSignature = '';

async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options, headers: {'Content-Type':'application/json', ...options.headers}});
  const data = await response.json().catch(() => ({detail:'The manager returned an unexpected response.'}));
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') showLogin();
    throw new Error(Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('. ') : data.detail || 'Request failed. Try again.');
  }
  return data;
}
function notice(text, error = false) { $('#notice').textContent = text; $('#notice').hidden = !text; $('#notice').className = `message ${error ? 'error':'success'}`; }
function showLogin() { $('#app').hidden = true; $('#login').hidden = false; state = null; }
function showView(next, focus = true) {
  view = next;
  for (const section of document.querySelectorAll('.view')) section.hidden = section.id !== `${next}-view`;
  for (const nav of document.querySelectorAll('.nav')) nav.setAttribute('aria-current', nav.dataset.view === next ? 'page' : 'false');
  notice('');
  if (next === 'library') loadLibrary();
  if (focus) $('#main').focus();
}
function empty(title, copy, action = '') { return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(copy)}</p>${action}</div>`; }
function jobRows(jobs) {
  if (!jobs.length) return empty('Your first copy starts here', 'Choose a video, try a preview, and let your worker handle the rest.', '<button class="button" data-view="library">Browse library</button>');
  return jobs.map(job => {
    const running = job.status === 'running';
    const actions = job.status === 'completed' ? `<a class="button" href="/api/jobs/${esc(job.id)}/download">Download ${job.recipe.preview_seconds ? 'preview':'copy'}</a>` : ['failed','cancelled'].includes(job.status) ? `<button class="button" data-action="retry" data-id="${esc(job.id)}">Retry</button>` : `<button class="button quiet" data-action="cancel" data-id="${esc(job.id)}">Cancel</button>`;
    return `<div class="row"><div><div class="row-name">${esc(job.path.split('/').pop())}${job.recipe.preview_seconds ? ' <span class="tag">Preview</span>' : ''}</div><p class="row-meta">${esc(engineNames[job.recipe.engine])} · ${esc(job.recipe.codec.toUpperCase())} / ${job.recipe.scale}×</p><p class="row-meta">${esc(job.stage)}${running ? ` / ${Math.floor(job.progress)}%` : ''}${job.status === 'queued' ? ' · Waiting for a compatible worker' : ''}</p>${job.error ? `<p class="message error">${esc(job.error)}</p>` : ''}${job.result ? `<p class="row-meta">${esc(job.result.path)} / ${bytes(job.result.bytes)}</p>` : ''}${running ? `<progress value="${job.progress}" max="100" aria-label="Processing ${esc(job.path)}"></progress>` : ''}</div><div class="actions">${actions}</div></div>`;
  }).join('');
}
function renderWorkers() {
  const active = state.workers.filter(w => !w.revoked);
  $('#workers').innerHTML = active.length ? active.map(w => `<article class="panel panel-pad"><div class="section-head mt-0"><h2>${esc(w.name)}</h2><span class="tag"><span class="dot ${w.online ? 'online':'warning'}"></span>${w.online ? 'Connected':'Offline'}</span></div><p class="hint">${esc(w.capabilities.device)}<br>${esc(w.capabilities.platform)} / ${esc(w.capabilities.architecture)}</p><div class="chips">${(w.capabilities.encoders || []).map(c => `<span class="tag">${esc(c.replace('_nvidia',' · NVIDIA').replace('_cpu',' · CPU').toUpperCase())}</span>`).join('')}</div><div class="worker-detail"><span>Temporary drive</span><strong>${bytes(w.scratch.free_bytes || 0)} free</strong></div><p class="row-meta">${esc(w.scratch.path)}</p><div class="worker-detail"><span>Enhancement</span><strong>${(w.capabilities.engines || []).includes('rtx-vsr') ? 'RTX Video ready':'Conventional resizing'}</strong></div>${Object.entries(w.capabilities.notes || {}).map(([engine, text]) => `<p class="message">${esc(engineNames[engine])}: ${esc(text)}</p>`).join('')}<button class="button quiet mt-4" data-action="revoke" data-id="${esc(w.id)}">Disconnect worker</button></article>`).join('') : `<div class="panel span-2">${empty('Bring your processing power', 'Connect your Spark, desktop or another computer. You can also run a worker beside this manager.')}</div>`;
  const previous = $('#worker').value;
  $('#worker').innerHTML = '<option value="">Any compatible worker</option>' + active.map(w => `<option value="${esc(w.id)}">${esc(w.name)}${w.online ? '':' (offline)'}</option>`).join('');
  if (active.some(w => w.id === previous)) $('#worker').value = previous;
  updateCapabilities();
}
function availableWorkers() { return state ? state.workers.filter(w => !w.revoked && (!$('#worker').value || w.id === $('#worker').value)) : []; }
function updateCapabilities() {
  const workers = availableWorkers();
  const engines = new Set(workers.flatMap(w => w.capabilities.engines || []));
  const previous = $('#engine').value;
  $('#engine').innerHTML = [...engines].map(engine => `<option value="${esc(engine)}">${esc(engineNames[engine] || engine)}</option>`).join('') || '<option value="resize">Conventional resizing</option>';
  if (engines.has(previous)) $('#engine').value = previous;
  $('#worker-hint').textContent = workers.length ? 'Jobs start when a compatible device is connected.' : 'Connect a worker in Processing to start jobs.';
  $('#recipe-form').querySelectorAll('button[type=submit]').forEach(b => b.disabled = !workers.length);
  updateEngine();
}
function updateEngine() {
  const engine = $('#engine').value;
  $('#engine-hint').textContent = state?.engine_notes[engine] || '';
  $('#ai-note').hidden = engine === 'resize';
  $('#cleanup').querySelectorAll('input').forEach(input => { input.disabled = engine !== 'resize'; if (input.disabled) input.checked = false; });
  for (const option of $('#scale').options) option.disabled = engine === 'dlss5' ? option.value !== '1' : engine === 'dlss-sr' && option.value === '4';
  if ($('#scale').selectedOptions[0]?.disabled) $('#scale').value = engine === 'dlss5' ? '1' : '2';
  updateEncoders();
}
function updateEncoders() {
  const workers = availableWorkers().filter(w => (w.capabilities.engines || []).includes($('#engine').value));
  const codecs = new Set(workers.flatMap(w => w.capabilities.encoders || []).filter(c => $('#engine').value === 'resize' || c.endsWith('_nvidia')).map(c => c.split('_')[0]));
  for (const option of $('#codec').options) option.disabled = !codecs.has(option.value);
  if ($('#codec').selectedOptions[0]?.disabled) $('#codec').value = [...codecs][0] || 'h264';
  const available = new Set(workers.flatMap(w => w.capabilities.encoders || []));
  for (const option of $('#encoder').options) option.disabled = !available.has(`${$('#codec').value}_${option.value}`) || ($('#engine').value !== 'resize' && option.value !== 'nvidia');
  if ($('#encoder').selectedOptions[0]?.disabled) $('#encoder').value = !$('#encoder').options[1].disabled ? 'nvidia' : 'cpu';
  $('#recipe-form').querySelectorAll('button[type=submit]').forEach(b => b.disabled = !codecs.size);
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    state = await api('/api/state');
    $('#login').hidden = true; $('#app').hidden = false;
    const online = state.workers.filter(w => w.online).length;
    $('#connection').innerHTML = `<span class="dot ${online ? 'online':''}"></span>${online ? `${online} worker${online === 1 ? '' : 's'} connected` : 'Manager ready'}`;
    $('#overview-workers').textContent = online ? `${online} connected` : 'No worker';
    $('#version').textContent = `Version ${state.version}`;
    $('#settings-library').textContent = state.storage.library;
    $('#settings-output').textContent = `${state.storage.output} / ${bytes(state.storage.free_bytes)} available`;
    // Omit last_seen so heartbeat timestamps do not rebuild controls while the user edits.
    const stable = JSON.stringify(state.workers.map(({last_seen, ...rest}) => rest));
    if (stable !== workerSignature) { workerSignature = stable; renderWorkers(); }
    const js = JSON.stringify(state.jobs);
    if (js !== jobSignature) { jobSignature = js; $('#jobs').innerHTML = jobRows(state.jobs); $('#recent-jobs').innerHTML = jobRows(state.jobs.slice(0,3)); }
    const waiting = state.jobs.some(j => j.status === 'queued');
    $('#queue-hint').hidden = !waiting || online > 0;
    $('#queue-hint').textContent = 'Jobs are waiting. Connect a compatible worker in Processing to continue.';
  } catch (error) {
    if (state) { $('#connection').innerHTML = '<span class="dot warning"></span>Connection interrupted'; notice(`${error.message} Reconnecting automatically.`, true); }
    else { showLogin(); if (!error.message.includes('Sign in')) { $('#login-error').textContent = error.message; $('#login-error').hidden = false; } }
  } finally { refreshing = false; }
}
async function loadLibrary() {
  try {
    const data = await api(`/api/library?directory=${encodeURIComponent(directory)}&offset=${offset}`);
    total = data.total;
    $('#library-path').textContent = directory === '.' ? state.storage.library : `${state.storage.library}/${directory}`;
    $('#parent-folder').hidden = directory === '.';
    $('#library-items').innerHTML = data.items.length ? data.items.map(item => `<div class="row"><button class="file-button" data-action="${item.directory ? 'folder':'select'}" data-path="${esc(item.path)}"><span class="row-name">${item.directory ? '<span class="folder-label">Folder</span>':''}${esc(item.name)}</span>${!item.directory ? `<p class="row-meta">${bytes(item.size)}</p>`:''}</button>${!item.directory ? '<span class="hint">Choose to enhance</span>' : ''}</div>`).join('') : empty('No videos in this folder', 'Check the library mount or open a different folder. Supported formats include MKV, MP4, MOV and WebM.');
    $('#pagination').hidden = total <= 100;
    $('#previous-page').disabled = offset === 0; $('#next-page').disabled = offset + 100 >= total;
    $('#page-count').textContent = `${offset + 1}–${Math.min(offset + 100,total)} of ${total}`;
  } catch (error) { $('#library-items').innerHTML = empty('Library unavailable', error.message); }
}
document.addEventListener('click', async event => {
  const navigation = event.target.closest('[data-view]');
  if (navigation) return showView(navigation.dataset.view);
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const {action, id, path} = button.dataset;
  if (action === 'folder') { directory = path; offset = 0; return loadLibrary(); }
  if (action === 'select') {
    selected = path; $('#selected-file').textContent = path; $('#recipe-panel').hidden = false; $('#recipe-error').hidden = true;
    updateCapabilities(); $('#recipe-panel').scrollIntoView({block:'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant':'smooth'}); $('#worker').focus({preventScroll:true}); return;
  }
  button.disabled = true;
  try {
    if (action === 'revoke') await api(`/api/workers/${id}/revoke`, {method:'POST'});
    else await api(`/api/jobs/${id}/${action}`, {method:'POST'});
    await refresh();
  } catch (error) { notice(error.message, true); button.disabled = false; }
});
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; button.textContent = 'Opening…';
  try { await api('/api/login', {method:'POST', body:JSON.stringify({token:$('#access-key').value})}); $('#access-key').value = ''; workerSignature = ''; jobSignature = ''; await refresh(); $('#login-error').hidden = true; }
  catch (error) { $('#login-error').textContent = error.message; $('#login-error').hidden = false; }
  finally { button.disabled = false; button.textContent = 'Open Popcorn SR'; }
});
async function logout() { await api('/api/logout', {method:'POST'}); showLogin(); }
$('#logout').addEventListener('click', logout); $('#settings-logout').addEventListener('click', logout);
$('#refresh-library').addEventListener('click', loadLibrary);
$('#parent-folder').addEventListener('click', () => { const parts = directory.split('/'); parts.pop(); directory = parts.join('/') || '.'; offset = 0; loadLibrary(); });
$('#previous-page').addEventListener('click', () => { offset = Math.max(0,offset - 100); loadLibrary(); });
$('#next-page').addEventListener('click', () => { offset += 100; loadLibrary(); });
$('#close-recipe').addEventListener('click', () => { $('#recipe-panel').hidden = true; selected = null; });
$('#worker').addEventListener('change', updateCapabilities); $('#engine').addEventListener('change', updateEngine); $('#codec').addEventListener('change', updateEncoders);
$('#recipe-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!selected) return;
  const form = new FormData(event.currentTarget), recipe = {};
  for (const key of ['engine','codec','encoder','output_directory']) recipe[key] = form.get(key);
  for (const key of ['scale','quality']) recipe[key] = Number(form.get(key));
  for (const key of ['denoise','deinterlace','sharpen','interpolate']) recipe[key] = form.get(key) === 'on';
  recipe.preview_seconds = Number(event.submitter.value);
  const buttons = [...event.currentTarget.querySelectorAll('button[type=submit]')]; buttons.forEach(b => b.disabled = true);
  const old = event.submitter.textContent; event.submitter.textContent = 'Checking video…';
  try { await api('/api/jobs', {method:'POST', body:JSON.stringify({path:selected, recipe, worker_id:form.get('worker_id') || null})}); $('#recipe-panel').hidden = true; selected = null; await refresh(); showView('queue'); notice(recipe.preview_seconds ? 'Preview queued. Download it when it is ready.' : 'Video queued. Your original is preserved.'); }
  catch (error) { $('#recipe-error').textContent = error.message; $('#recipe-error').hidden = false; }
  finally { event.submitter.textContent = old; buttons.forEach(b => b.disabled = false); }
});
$('#new-pair-code').addEventListener('click', async event => {
  event.currentTarget.disabled = true;
  try { const data = await api('/api/pair-codes', {method:'POST'}); $('#pair-code').textContent = data.code; $('#manager-address').textContent = location.origin; $('#pair-panel').hidden = false; $('#copy-code').textContent = 'Copy pairing code'; }
  catch (error) { notice(error.message, true); }
  finally { $('#new-pair-code').disabled = false; }
});
$('#close-pair').addEventListener('click', () => $('#pair-panel').hidden = true);
$('#copy-code').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#pair-code').textContent); $('#copy-code').textContent = 'Copied'; }
  catch { notice('Select the pairing code and copy it manually. Automatic copying requires HTTPS or localhost.'); }
});
await refresh();
setInterval(() => { if (state && !document.hidden) refresh(); }, 3000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && state) refresh(); });
