/* Overview: what the demo is, the four modes, the environment, health checks (doctor) and the project's agents. */
import { $, clear, copyText, el, on, setBusy } from './dom.js';
import { MODE_ICONS, icon } from './icons.js';
import { api } from './http.js';
import { MODES, MODE_ORDER, state, subscribe } from './store.js';
import { fmtCost, fmtInt } from './format.js';

const HOW = {
  prompt: [['Where', 'Foundry Agent Service'], ['Browser', 'Azure (Playwright Workspaces)'], ['Preview', 'Live view']],
  hosted: [['Where', 'Container on Agent Service'], ['Browser', 'Azure via the toolbox'], ['Preview', 'Live view']],
  local: [['Where', 'This PC, 127.0.0.1'], ['Browser', 'Edge here, or Azure'], ['Preview', 'Screenshots / live view']],
  cua: [['Where', 'Loop on this PC'], ['Browser', 'Chromium here'], ['Preview', 'Model screenshots']],
};

function metric(label, value, sub) {
  return el('div', { class: 'metric' }, el('span', {}, label), el('strong', {}, value), el('small', {}, sub));
}

function renderMetrics() {
  const runs = state.history || [];
  const cost = runs.reduce((sum, r) => sum + (r.est_cost || 0), 0);
  const withChecks = runs.filter((r) => r.checks_total);
  const passed = withChecks.filter((r) => r.checks_passed === r.checks_total).length;
  clear($('#overview-metrics')).append(
    metric('Scenarios', fmtInt(state.scenarios.length), `levels 1–${Math.max(...state.scenarios.map((s) => s.level), 1)}`),
    metric('Recorded runs', state.history ? fmtInt(runs.length) : '…', 'runs/*/result.json'),
    metric('Runs with all checks passing', withChecks.length ? `${Math.round((passed / withChecks.length) * 100)}%` : '–', `${passed} of ${withChecks.length} with checks`),
    metric('Estimated spend', state.history ? fmtCost(cost, runs[0]?.currency || 'USD') : '…', 'tokens + cloud-browser minutes'));
}

function renderModes() {
  clear($('#mode-explainers')).append(...MODE_ORDER.map((mode) => el('article', { class: 'mode-explainer', dataset: { mode } },
    el('span', { class: 'mode-icon' }, icon(MODE_ICONS[mode])), el('h3', {}, MODES[mode].label), el('p', {}, MODES[mode].detail),
    el('dl', {}, HOW[mode].flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)])))));
}

function copyable(text) {
  const button = el('button', { type: 'button', class: 'copy-inline', 'aria-label': 'Copy', title: 'Copy' }, icon('copy'));
  button.addEventListener('click', () => copyText(text, 'Copied'));
  return [el('span', {}, text), button];
}

function renderEnv() {
  const s = state.settings;
  const rows = [
    ['Foundry project', s.project_endpoint ? copyable(s.project_endpoint) : el('span', { class: 'badge err' }, 'not configured')],
    ['Demo site', s.demo_site_url ? [el('span', { class: 'status-dot', id: 'env-site-inline' }), el('a', { href: s.demo_site_url, target: '_blank', rel: 'noopener noreferrer' }, s.demo_site_url)] : 'not deployed'],
    ['Prompt agent', `${s.prompt_agent_name} · ${s.prompt_model} (strong: ${s.strong_model})`],
    ['Hosted agent', `${s.hosted_agent_name} · ${s.hosted_model}`],
    ['Computer Use model', s.computer_use_model],
    ['Toolbox / connection', `${s.toolbox_name} · ${s.connection_name || '–'}`],
    ['Resource groups', (s.resource_groups || []).join(', ') || '–'],
    ...state.local.map((c) => [c.label.replace('Local mode: ', 'Local mode · '), [el('span', { class: `status-dot ${c.passed ? 'ok' : ''}` }), c.detail || (c.passed ? 'ready' : 'missing')]]),
  ];
  clear($('#env-list')).append(...rows.flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
}

function checkRow(c) {
  const name = c.passed ? 'check' : c.optional ? 'minus' : 'cross';
  const tone = c.passed ? 'ok' : c.optional ? 'optional' : 'err';
  return el('li', {}, icon(name, `check-icon ${tone}`), el('div', {}, c.label, c.detail ? el('span', { class: 'detail' }, c.detail) : null));
}

function renderAgents(data) {
  const host = clear($('#agents-table'));
  if (data.agents_error) { host.append(el('div', { class: 'callout err' }, icon('error'), el('div', {}, data.agents_error))); return; }
  if (!data.agents.length) { host.append(el('p', { class: 'muted small' }, 'No agents in the project yet.')); return; }
  const s = state.settings;
  const mine = (name) => name === s.hosted_agent_name || name.startsWith(s.prompt_agent_name);
  host.append(el('table', { class: 'data' }, el('thead', {}, el('tr', {}, ['Name', 'Kind', 'Latest version', 'Model'].map((c) => el('th', {}, c)))),
    el('tbody', {}, data.agents.map((a) => el('tr', {}, el('td', {}, a.name, mine(a.name) ? el('span', { class: 'badge info' }, ' demo') : null),
      el('td', {}, a.kind), el('td', {}, a.version), el('td', {}, a.model))))));
}

export function setEnvDot(id, tone, title) {
  const dot = document.getElementById(id);
  if (!dot) return;
  dot.className = `status-dot ${tone}`;
  if (title) dot.title = title;
}

async function runDoctor() {
  const button = $('#doctor-run');
  setBusy(button, true, 'Checking…');
  clear($('#doctor-list')).append(el('li', {}, el('span', { class: 'spinner small' }), el('div', {}, 'Calling Azure and waking the demo site (up to a minute)…')));
  try {
    const data = await api('/api/doctor');
    clear($('#doctor-list')).append(...data.checks.map(checkRow));
    $('#env-badge').className = `badge ${data.ok ? 'ok' : 'err'}`;
    $('#env-badge').textContent = data.ok ? 'all required checks pass' : 'some checks fail';
    setEnvDot('env-project-dot', data.checks.some((c) => c.label.startsWith('Project') && c.passed) ? 'ok' : 'err');
    renderAgents(data);
  } catch (error) {
    clear($('#doctor-list')).append(el('li', {}, icon('cross', 'check-icon err'), el('div', {}, error.message)));
  } finally {
    setBusy(button, false);
  }
}

export function initOverview() {
  renderModes();
  renderEnv();
  renderMetrics();
  on('#doctor-run', 'click', runDoctor);
  subscribe('history', renderMetrics);
  subscribe('site-health', (data) => setEnvDot('env-site-inline', data.ok ? 'ok' : 'err'));
  let checked = false;
  subscribe('route', (route) => {
    if (route.page === 'overview' && !checked) {
      checked = true;
      runDoctor();
    }
  });
}
