'use strict';
const $ = id => document.getElementById(id);
const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
let activeCollection = '', account = '', selectedReport = '';
let sessionEpoch = 0, collectionEpoch = 0, reportEpoch = 0;
const requests = new Set();
const authChannel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('ragvanta-auth');
class StaleAction extends Error {}
const stale = error => error instanceof StaleAction || error.name === 'AbortError';
const showError = error => { if (!stale(error)) status(error.message); };
function status(message) { $('status').textContent = message; }
function clearEvidence() {
  for (const id of ['answer', 'citations', 'trace', 'chunk-preview']) $(id).replaceChildren();
}
function selectCollection(id) {
  if (id !== activeCollection) { collectionEpoch++; clearEvidence(); }
  activeCollection = id;
  $('delete-collection').disabled = !id;
}
function resetAccount(message = '') {
  sessionEpoch++; collectionEpoch++; reportEpoch++;
  for (const controller of requests) controller.abort();
  requests.clear();
  activeCollection = account = selectedReport = '';
  for (const id of ['identity', 'health', 'collection-select', 'collection-usage', 'document-list',
    'answer', 'citations', 'trace', 'chunk-preview', 'experiment-result', 'run-list', 'report']) $(id).replaceChildren();
  document.querySelectorAll('form').forEach(form => { form.reset(); form.submission = null; form.querySelector('button').disabled = false; });
  $('delete-collection').disabled = true;
  $('workspace').hidden = true; $('login').hidden = false; $('logout').hidden = true;
  document.querySelectorAll('.view').forEach(view => view.hidden = view.id !== 'documents');
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === 'documents'));
  $('menu-toggle').setAttribute('aria-expanded', 'false'); $('workspace-nav').classList.remove('is-open');
  document.title = 'Sign in · RAGVanta';
  status(message);
}
authChannel?.addEventListener('message', () => resetAccount('Account access changed in another tab. Sign in or reload to continue.'));
$('copyright-year').textContent = new Date().getFullYear();
$('menu-toggle').onclick = () => {
  const open = $('menu-toggle').getAttribute('aria-expanded') !== 'true';
  $('menu-toggle').setAttribute('aria-expanded', String(open)); $('workspace-nav').classList.toggle('is-open', open);
};
function csrf() { return document.cookie.split('; ').find(c => c.startsWith('ragvanta_csrf='))?.split('=').slice(1).join('=') || ''; }
async function api(path, options = {}) {
  const epoch = sessionEpoch, controller = new AbortController(); requests.add(controller);
  try {
    const headers = { ...options.headers };
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    if (options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrf();
    const response = await fetch(path, {...options, headers, credentials: 'same-origin', signal: controller.signal});
    if (epoch !== sessionEpoch) throw new StaleAction();
    if (response.status === 401 && path !== '/auth/login') {
      resetAccount('Sign in to continue.'); throw new StaleAction();
    }
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 300);
      if (epoch !== sessionEpoch) throw new StaleAction();
      throw new Error(`${response.status}: ${detail}`);
    }
    const value = response.status === 204 ? null : await response.json();
    if (epoch !== sessionEpoch) throw new StaleAction();
    return value;
  } finally { requests.delete(controller); }
}
function handle(form, action, success) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button'), token = Symbol(), epoch = sessionEpoch;
    form.submission = token; button.disabled = true; status('Working…');
    try {
      await action();
      if (form.submission === token && epoch === sessionEpoch) status(success);
    } catch (error) {
      if (form.submission === token && epoch === sessionEpoch) showError(error);
    } finally { if (form.submission === token) button.disabled = false; }
  });
}
async function documents() {
  const id = activeCollection, selection = collectionEpoch;
  $('document-list').replaceChildren(); $('chunk-preview').replaceChildren();
  if (!id) { $('document-list').textContent = 'Create a collection to add documents.'; return; }
  const docs = await api(`/v1/documents?collection_id=${encodeURIComponent(id)}`);
  if (selection !== collectionEpoch || id !== activeCollection) return;
  for (const doc of docs) {
    const row = text('p', `${doc.filename} · ${doc.chunk_count} chunks · SHA-256 ${doc.sha256.slice(0,16)}… `);
    const preview = text('button', 'Preview evidence');
    preview.onclick = async () => {
      try {
        const chunks = await api(`/v1/documents/${encodeURIComponent(doc.id)}/chunks`);
        if (selection !== collectionEpoch) return;
        $('chunk-preview').textContent = chunks.map(c => `${c.id} · page ${c.page} · ${c.start}–${c.end}\n${c.text}`).join('\n\n');
      } catch (error) { showError(error); }
    };
    const remove = text('button', 'Delete document');
    remove.onclick = async () => {
      if (!confirm('Permanently delete this document and its chunks?')) return;
      try {
        await api(`/v1/documents/${encodeURIComponent(doc.id)}`, {method:'DELETE'});
        if (selection !== collectionEpoch) return;
        clearEvidence(); await documents(); status('Document deleted.');
      } catch (error) { showError(error); }
    };
    row.append(preview, text('span', ' '), remove); $('document-list').append(row);
  }
  if (!docs.length) $('document-list').textContent = 'No documents yet.';
}
async function collections() {
  const rows = await api('/v1/collections'), select = $('collection-select'); select.replaceChildren();
  for (const collection of rows) { const option = text('option', collection.name); option.value = collection.id; select.append(option); }
  if (rows.some(c => c.id === activeCollection)) select.value = activeCollection;
  selectCollection(select.value);
  $('collection-usage').textContent = `${rows.length} collection${rows.length === 1 ? '' : 's'}. Delete an unused collection to free capacity.`;
  await documents();
}
function table(rows) {
  if (!rows.length) return text('p', 'No cases yet.');
  const result = document.createElement('table'), keys = Object.keys(rows[0]), head = document.createElement('tr');
  keys.forEach(key => head.append(text('th', key.replaceAll('_', ' ')))); result.append(head);
  for (const row of rows) {
    const tr = document.createElement('tr');
    keys.forEach(key => tr.append(text('td', typeof row[key] === 'object' ? JSON.stringify(row[key]) : String(row[key] ?? 'Not exercised')))); result.append(tr);
  }
  return result;
}
function reportView(report, target) {
  target.replaceChildren(text('h2', `Run ${report.id.slice(0,8)} · ${report.status}`)); target.dataset.runId = report.id;
  for (const limitation of report.limitations) target.append(text('p', limitation));
  const rows = Object.entries(report.metrics).map(([mode, data]) => {
    const row = {mode};
    for (const key of ['retrieval_exposure','conditional_attack_success','end_to_end_attack_success','legitimate_answer_success','false_block']) {
      const metric = data[key]; row[key] = metric.rate === null ? 'Not exercised' : `${metric.numerator}/${metric.denominator} (${(100*metric.rate).toFixed(1)}%)`;
    }
    row.incomplete = data.incomplete; return row;
  });
  target.append(table(rows));
  for (const format of ['json','csv']) {
    const link = text('a', `Download ${format.toUpperCase()} `); link.href = `/v1/reports/${report.id}?format=${format}`; link.download = ''; target.append(link, text('span', ' · '));
  }
  const details = document.createElement('details');
  details.append(text('summary', 'Cases and category breakdowns'), text('pre', JSON.stringify({cases:report.cases, breakdowns:report.breakdowns}, null, 2))); target.append(details);
}
async function runs() {
  const rows = await api('/v1/experiments'); $('run-list').replaceChildren();
  for (const run of rows) {
    const row = document.createElement('p'), open = text('button', `${new Date(run.created*1000).toLocaleString()} · ${run.status}`);
    open.onclick = async () => {
      const selection = ++reportEpoch; selectedReport = run.id;
      try { const report = await api(`/v1/experiments/${run.id}`); if (selection === reportEpoch) reportView(report, $('report')); }
      catch (error) { showError(error); }
    };
    row.append(open);
    if (!['queued','running'].includes(run.status)) {
      const remove = text('button', 'Delete run');
      remove.onclick = async () => {
        if (!confirm('Permanently delete this saved run and its isolated test corpus?')) return;
        try {
          await api(`/v1/experiments/${run.id}`, {method:'DELETE'});
          if (selectedReport === run.id) { reportEpoch++; selectedReport = ''; $('report').replaceChildren(); }
          if ($('experiment-result').dataset.runId === run.id) $('experiment-result').replaceChildren();
          await runs(); status('Run deleted.');
        } catch (error) { showError(error); }
      };
      row.append(text('span',' '), remove);
    }
    $('run-list').append(row);
  }
  if (!rows.length) $('run-list').textContent = 'No measured runs yet.';
}
async function initialize() {
  const me = await api('/auth/me');
  if (account && account !== me.username) resetAccount();
  account = me.username;
  const health = await api('/health');
  $('identity').textContent = me.username; $('health').textContent = `${health.provider || 'configured provider'} · ${health.retrieval || 'retrieval'}`;
  document.title = 'Documents · RAGVanta'; $('login').hidden = true; $('workspace').hidden = false; $('logout').hidden = me.deployment !== 'hosted'; await collections();
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = $('login-form'), username = $('username').value, password = $('password').value;
  resetAccount();
  const epoch = sessionEpoch, token = Symbol(), button = form.querySelector('button');
  form.submission = token; button.disabled = true; $('username').value = username; status('Signing in…');
  try {
    await api('/auth/login', {method:'POST', body:JSON.stringify({username,password})});
    authChannel?.postMessage('changed'); await initialize();
    if (epoch === sessionEpoch) status('Signed in.');
  } catch (error) { if (epoch === sessionEpoch) showError(error); }
  finally { if (form.submission === token) button.disabled = false; }
});
handle($('collection-form'), async () => {
  const collection = await api('/v1/collections', {method:'POST',body:JSON.stringify({name:$('collection-name').value})});
  selectCollection(collection.id); $('collection-name').value = ''; await collections();
}, 'Collection created.');
handle($('upload-form'), async () => {
  if (!activeCollection) throw new Error('Create a collection first.');
  const selection = collectionEpoch, file = $('upload').files[0];
  if (file.size > 10*1024*1024) throw new Error('File exceeds 10 MB.');
  const body = new FormData(); body.append('collection_id', activeCollection); body.append('file', file); body.append('synthetic', String($('synthetic').checked));
  await api('/v1/documents', {method:'POST', body});
  if (selection !== collectionEpoch) throw new StaleAction();
  await documents();
}, 'Document uploaded and indexed.');
handle($('chat-form'), async () => {
  if (!activeCollection) throw new Error('Create a collection first.');
  const selection = collectionEpoch;
  const result = await api('/v1/chat', {method:'POST',body:JSON.stringify({question:$('question').value,collection_id:activeCollection,mode:$('mode').value})});
  if (selection !== collectionEpoch) throw new StaleAction();
  $('answer').textContent = result.answer; $('citations').replaceChildren(table(result.citations));
  $('trace').textContent = JSON.stringify({retrieved:result.retrieved,decisions:result.decisions,included:result.included_ids,output_reasons:result.output_reasons},null,2);
}, 'Answer ready.');
handle($('experiment-form'), async () => {
  const epoch = sessionEpoch;
  let report = await api('/v1/experiments', {method:'POST',body:JSON.stringify({split:$('split').value,limit:Number($('limit').value),offset:Number($('offset').value)})});
  while (['queued','running'].includes(report.status)) {
    if (epoch !== sessionEpoch) throw new StaleAction();
    status('Experiment running. You can also view progress in Runs & Reports.');
    await new Promise(resolve => setTimeout(resolve,10000));
    if (epoch !== sessionEpoch) throw new StaleAction();
    report = await api(`/v1/experiments/${report.id}`);
  }
  reportView(report, $('experiment-result'));
}, 'Comparison finished. Review the run status and results below.');
$('delete-collection').onclick = async () => {
  const id = activeCollection;
  if (!id || !confirm('Permanently delete this collection, all its documents, and indexed evidence?')) return;
  try { await api(`/v1/collections/${encodeURIComponent(id)}`, {method:'DELETE'}); await collections(); status('Collection deleted. Capacity is available again.'); }
  catch (error) { showError(error); }
};
$('collection-select').onchange = async () => { selectCollection($('collection-select').value); try { await documents(); } catch (error) { showError(error); } };
$('logout').onclick = async () => { try { await api('/auth/logout', {method:'POST'}); resetAccount('Signed out.'); authChannel?.postMessage('changed'); } catch (error) { showError(error); } };
$('refresh-runs').onclick = () => runs().catch(showError);
document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => {
  document.querySelectorAll('.view').forEach(view => view.hidden = view.id !== button.dataset.view);
  document.querySelectorAll('[data-view]').forEach(item => item.classList.toggle('active', item === button));
  document.title = `${button.textContent} · RAGVanta`;
  document.querySelector('meta[name=description]').content = {
    documents:'Manage collections and upload synthetic evidence in the RAGVanta Document Lab.',
    chat:'Ask questions about your evidence and inspect retrieval, citations, and defense decisions in RAGVanta.',
    experiments:'Compare baseline and protected modes against controlled synthetic prompt injection scenarios in RAGVanta.',
    reports:'Review measured RAGVanta experiment runs and export detailed JSON or CSV reports.'
  }[button.dataset.view];
  $('menu-toggle').setAttribute('aria-expanded', 'false'); $('workspace-nav').classList.remove('is-open');
  if (button.dataset.view === 'reports') runs().catch(showError);
});
document.querySelector('[data-view=documents]').classList.add('active');
initialize().catch(showError);
