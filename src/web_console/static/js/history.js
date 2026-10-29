/* Run history: every recorded result.json under runs/, newest first, with filters; the selected run opens on the right. */
import { $, clear, debounce, el, on } from './dom.js';
import { api } from './http.js';
import { MODES, emit, state, subscribe } from './store.js';
import { checksTone, fmtCost, fmtDuration, relTime, statusTone } from './format.js';
import { navigate } from './router.js';
import { renderDetail } from './history_detail.js';

let selected = null;
let loading = null;

export function loadHistory() {
  loading = api('/api/history').then((data) => {
    state.history = data.runs;
    $('#nav-history-count').textContent = data.runs.length ? String(data.runs.length) : '';
    emit('history', data.runs);
    renderList();
    return data.runs;
  }).catch((error) => {
    clear($('#history-list')).append(el('div', { class: 'callout err' }, error.message));
    return [];
  });
  return loading;
}

function row(run) {
  const tone = statusTone(run.status);
  const checks = run.checks_total ? el('span', { class: `badge ${checksTone(run.checks_passed, run.checks_total)}` }, `${run.checks_passed}/${run.checks_total}`) : null;
  const button = el('button', { type: 'button', class: 'history-row', role: 'listitem', 'aria-current': String(run.folder === selected),
    dataset: { folder: run.folder } },
  el('span', { class: `status-dot ${tone === 'muted' ? '' : tone}`, title: run.status }),
  el('span', {}, el('strong', {}, run.title || run.scenario_id),
    el('small', {}, el('span', { class: `badge mode-${run.mode}` }, MODES[run.mode]?.short || run.mode), `${run.scenario_id} · ${run.model}`)),
  el('span', { class: 'row-right' }, el('span', {}, relTime(run.started)), el('span', {}, `${fmtDuration(run.duration_s)} · ${fmtCost(run.est_cost, run.currency)}`), checks));
  button.addEventListener('click', () => navigate(`#/history/${encodeURIComponent(run.folder)}`));
  return button;
}

function renderList() {
  const list = clear($('#history-list'));
  if (!state.history) { list.append(el('p', { class: 'muted small' }, 'Loading runs…')); return; }
  const query = $('#history-search').value.trim().toLowerCase();
  const mode = $('#history-mode').value;
  const runs = state.history.filter((r) => (!mode || r.mode === mode)
    && (!query || `${r.scenario_id} ${r.title} ${r.mode} ${r.model} ${r.status} ${r.folder}`.toLowerCase().includes(query)));
  if (!runs.length) {
    list.append(el('div', { class: 'empty-state' }, el('h3', {}, state.history.length ? 'No run matches' : 'No runs yet'),
      el('p', {}, state.history.length ? 'Clear the filter.' : 'Runs from the console and the CLI are listed here.')));
    return;
  }
  list.append(...runs.slice(0, 300).map(row));
}

async function openRun(folder) {
  selected = folder || null;
  for (const button of $('#history-list').children) {
    if (button.dataset && button.dataset.folder) button.setAttribute('aria-current', String(button.dataset.folder === selected));
  }
  const host = $('#history-detail');
  if (!selected) {
    const latest = state.history && state.history[0];
    if (latest) { navigate(`#/history/${encodeURIComponent(latest.folder)}`); return; }
    clear(host).append(el('div', { class: 'empty-state' }, el('h3', {}, 'Select a run'), el('p', {}, 'Its report, answer, steps and screenshots open here.')));
    return;
  }
  await renderDetail(host, selected);
}

export function initHistory() {
  on('#history-refresh', 'click', () => loadHistory().then(() => openRun(selected)));
  on('#history-search', 'input', debounce(renderList, 120));
  on('#history-mode', 'change', renderList);
  subscribe('job:done', () => loadHistory());
  subscribe('route', async (route) => {
    if (route.page !== 'history') return;
    if (!state.history) await (loading || loadHistory());
    openRun(route.arg);
  });
}
