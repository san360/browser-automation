/* Comparison table for a multi-mode job: one row per mode, filled as each run finishes (like demo_cli compare). */
import { $, clear, el } from './dom.js';
import { MODES } from './store.js';
import { checksTone, fmtCost, fmtDuration, fmtInt, statusTone } from './format.js';

function row(step, current, onSelect, withKey) {
  const r = step.result;
  const tone = statusTone(step.status);
  const dot = el('span', { class: `status-dot ${step.status === 'running' ? 'running' : tone === 'muted' ? '' : tone}` });
  const cells = [
    el('td', {}, el('span', { class: `badge mode-${step.mode}` }, MODES[step.mode]?.label || step.mode),
      el('span', { class: 'cell-sub' }, step.model)),
    el('td', {}, el('span', { class: 'nowrap' }, dot, ' ', step.status)),
    el('td', { class: 'num' }, r ? fmtDuration(r.duration_s) : '–'),
    el('td', { class: 'num' }, r ? fmtInt(r.tool_calls) : '–'),
    el('td', { class: 'num' }, r ? `${fmtInt(r.input_tokens)} / ${fmtInt(r.output_tokens)}` : '–'),
    el('td', { class: 'num' }, r && r.checks_total ? el('span', { class: `badge ${checksTone(r.checks_passed, r.checks_total)}` },
      `${r.checks_passed}/${r.checks_total}`) : '–'),
    withKey ? el('td', { class: 'num' }, r && r.answer_key_recall !== null && r.answer_key_recall !== undefined
      ? `${Math.round(r.answer_key_recall * 100)}%` : '–') : null,
    el('td', { class: 'num' }, r ? fmtCost(r.est_cost, r.currency) : '–'),
  ];
  const tr = el('tr', { class: step.index === current ? 'current' : '', dataset: { step: step.index }, tabindex: 0,
    title: 'Show this run\u2019s answer and checks' }, cells);
  tr.addEventListener('click', () => onSelect(step.index));
  tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') onSelect(step.index); });
  return tr;
}

export function renderCompare(job, current, onSelect) {
  const card = $('#compare-card');
  card.hidden = !job || job.steps.length < 2;
  if (card.hidden) return;
  const done = job.steps.filter((s) => s.result || s.error).length;
  $('#compare-note').textContent = job.finished
    ? `${done} of ${job.steps.length} runs finished${job.comparison ? ` · saved as runs/${job.comparison}` : ''}. Click a row to see its answer.`
    : `Run ${Math.min(done + 1, job.steps.length)} of ${job.steps.length}: modes run one after another.`;
  const withKey = job.steps.some((s) => s.result && s.result.answer_key_recall !== null && s.result.answer_key_recall !== undefined);
  const columns = ['Mode', 'Status', 'Time', 'Tools', 'Tokens in / out', 'Checks', withKey ? 'Key' : null, 'Cost']
    .filter(Boolean);
  const table = el('table', { class: 'data compare-table' },
    el('thead', {}, el('tr', {}, columns.map((c, i) => el('th', { class: i >= 2 ? 'num' : '' }, c)))),
    el('tbody', {}, job.steps.map((step) => row(step, current, onSelect, withKey))));
  clear($('#compare-table')).append(table);
}
