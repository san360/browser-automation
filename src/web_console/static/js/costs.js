/* Costs: estimated totals from recorded runs (like `demo_cli costs`) and, on request, actual month-to-date Azure spend. */
import { $, clear, el, on, setBusy } from './dom.js';
import { api } from './http.js';
import { icon } from './icons.js';
import { MODES, subscribe } from './store.js';
import { fmtCompact, fmtCost, fmtInt } from './format.js';

function metric(label, value, sub) {
  return el('div', { class: 'metric' }, el('span', {}, label), el('strong', {}, value), el('small', {}, sub));
}

function table(rows, keyLabel, labelFor = (k) => k) {
  if (!rows.length) return el('p', { class: 'muted small' }, 'No recorded runs yet.');
  const max = Math.max(...rows.map((r) => r.cost), 0.000001);
  return el('table', { class: 'data' },
    el('thead', {}, el('tr', {}, [keyLabel, 'Runs', 'Tokens in', 'Tokens out', 'Browser min', 'Est. cost', ''].map((c, i) =>
      el('th', { class: i && i < 6 ? 'num' : '' }, c)))),
    el('tbody', {}, rows.map((r) => el('tr', {},
      el('td', {}, labelFor(r.key)), el('td', { class: 'num' }, fmtInt(r.runs)), el('td', { class: 'num' }, fmtCompact(r.input_tokens)),
      el('td', { class: 'num' }, fmtCompact(r.output_tokens)), el('td', { class: 'num' }, fmtInt(r.browser_minutes)),
      el('td', { class: 'num' }, fmtCost(r.cost, r.currency)),
      el('td', {}, el('div', { class: 'bar', title: `${Math.round((r.cost / max) * 100)}% of the largest` }, el('i', { style: null, dataset: { w: r.cost / max } })))))));
}

/* Bar widths are set through the CSSOM (allowed by the CSP), never through style attributes. */
function sizeBars(root) {
  for (const bar of root.querySelectorAll('.bar > i')) bar.style.width = `${Math.max(2, Number(bar.dataset.w) * 100)}%`;
}

export async function loadCosts() {
  try {
    const data = await api('/api/costs');
    const t = data.totals;
    const cachedShare = t.input_tokens ? Math.round((t.cached_tokens / t.input_tokens) * 100) : 0;
    clear($('#costs-metrics')).append(
      metric('Estimated total', fmtCost(t.cost, data.currency), `${fmtInt(t.runs)} recorded runs`),
      metric('Input tokens', fmtCompact(t.input_tokens), `${cachedShare}% served from the prompt cache`),
      metric('Output tokens', fmtCompact(t.output_tokens), 'all modes'),
      metric('Cloud-browser minutes', fmtInt(t.browser_minutes), 'Playwright Workspaces (prompt, hosted)'));
    const modeLabel = (k) => el('span', { class: `badge mode-${k}` }, MODES[k]?.label || k);
    clear($('#costs-by-mode')).append(table(data.by_mode, 'Mode', modeLabel));
    clear($('#costs-by-model')).append(table(data.by_model, 'Model'));
    clear($('#costs-by-scenario')).append(table(data.by_scenario, 'Scenario', (k) => el('code', {}, k)));
    sizeBars($('#page-costs'));
  } catch (error) {
    clear($('#costs-metrics')).append(el('div', { class: 'callout err' }, icon('error'), el('div', {}, error.message)));
  }
}

async function loadAzure() {
  const button = $('#azure-load');
  const host = clear($('#azure-costs'));
  setBusy(button, true, 'Querying Cost Management…');
  try {
    const data = await api('/api/costs/azure');
    if (data.error) {
      host.append(el('div', { class: 'callout warn' }, icon('warning'), el('div', {}, el('strong', {}, 'Cost Management query failed. '), data.error,
        el('div', { class: 'fine-print' }, data.hint))));
      return;
    }
    for (const group of data.groups) {
      const total = group.rows.reduce((sum, r) => sum + r.cost, 0);
      const currency = group.rows[0]?.currency || '';
      const body = group.error
        ? el('div', { class: 'callout warn' }, icon('warning'), el('div', {}, group.error, el('div', { class: 'fine-print' }, data.hint)))
        : group.rows.length ? el('table', { class: 'data' }, el('thead', {}, el('tr', {}, el('th', {}, 'Service'), el('th', { class: 'num' }, 'Cost'))),
          el('tbody', {}, group.rows.map((r) => el('tr', {}, el('td', {}, r.service), el('td', { class: 'num' }, `${r.cost.toFixed(4)} ${r.currency}`)))))
          : el('p', { class: 'muted small' }, 'No charges yet this month.');
      host.append(el('div', { class: 'azure-group' }, el('h3', {}, icon('folder'), group.resource_group,
        group.error ? null : el('span', { class: 'badge info' }, `${total.toFixed(2)} ${currency}`)), body));
    }
  } catch (error) {
    host.append(el('div', { class: 'callout err' }, icon('error'), el('div', {}, error.message)));
  } finally {
    setBusy(button, false);
  }
}

export function initCosts() {
  on('#costs-refresh', 'click', loadCosts);
  on('#azure-load', 'click', loadAzure);
  subscribe('route', (route) => { if (route.page === 'costs') loadCosts(); });
  subscribe('job:done', () => { if (!$('#page-costs').hidden) loadCosts(); });
}
