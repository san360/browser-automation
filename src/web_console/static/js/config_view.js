/* Presentation pieces of the run configuration: scenario options, the scenario summary, the last-result hint and the
   collapsed configuration bar shown during a run. */
import { $, clear, el, replace } from './dom.js';
import { icon } from './icons.js';
import { MODES, scenarioById, state } from './store.js';
import { checksTone, fmtCost, fmtDuration, relTime } from './format.js';

const LEVELS = { 1: 'Level 1 · Basics', 2: 'Level 2 · Filters and forms', 3: 'Level 3 · Complex forms', 4: 'Level 4 · QA', 5: 'Level 5 · Security' };

export function scenarioOptions(adhocValue) {
  const groups = new Map();
  for (const s of state.scenarios) {
    if (!groups.has(s.level)) groups.set(s.level, []);
    groups.get(s.level).push(el('option', { value: s.id }, `${s.id.split('-')[0]} · ${s.title}`));
  }
  const nodes = [el('optgroup', { label: 'Your own task' }, el('option', { value: adhocValue }, 'Ad-hoc task against any URL'))];
  for (const [level, options] of [...groups.entries()].sort((a, b) => a[0] - b[0])) {
    nodes.push(el('optgroup', { label: LEVELS[level] || `Level ${level}` }, options));
  }
  return nodes;
}

export function scenarioBadges(s) {
  return [
    el('span', { class: `badge level l${s.level}` }, `L${s.level}`),
    el('span', { class: 'badge muted' }, s.category),
    ...s.modes.map((m) => el('span', { class: `badge mode-${m}` }, MODES[m]?.short || m)),
    s.answer_key ? el('span', { class: 'badge warn' }, 'answer key') : null,
    s.allowed_domains.length ? el('span', { class: 'badge err' }, icon('shield'), 'allow-listed') : null,
  ];
}

function latestRun(id, mode) {
  return (state.history || []).find((r) => r.scenario_id === id && (!mode || r.mode === mode)) || null;
}

export function renderSummary({ id, modes }) {
  const s = scenarioById(id);
  const box = clear($('#scenario-summary'));
  if (s) {
    box.append(el('div', { class: 'badges' }, scenarioBadges(s)), el('p', {}, s.summary));
    if (s.checks.length) box.append(el('p', { class: 'fine-print' }, `Automatic checks: ${s.checks.join(' · ')}`));
  } else {
    box.append(el('p', {}, 'Run any task against any URL. Security-style reviews belong in the security scenarios, which enforce a domain allow-list.'));
  }
  const hint = clear($('#last-result'));
  const run = latestRun(id === '__adhoc__' ? 'adhoc' : id, modes && modes.length === 1 ? modes[0] : null);
  if (run) {
    const tone = checksTone(run.checks_passed, run.checks_total);
    hint.append(el('span', { class: `status-dot ${tone === 'muted' ? '' : tone}` }), 'Last run ',
      el('a', { href: `#/history/${encodeURIComponent(run.folder)}` }, relTime(run.started)), ': ',
      run.checks_total ? `${run.checks_passed}/${run.checks_total} checks · ` : '',
      `${fmtDuration(run.duration_s)} · ${fmtCost(run.est_cost, run.currency)} (${run.mode})`);
  }
}

export function collapse(job) {
  const modes = job.steps.map((s) => el('span', { class: `badge mode-${s.mode}` }, `${MODES[s.mode]?.short || s.mode} · ${s.model}`));
  replace($('#config-summary-text'), el('strong', {}, job.scenario_id === 'adhoc' ? 'Ad-hoc task' : `${job.scenario_id.split('-')[0]} · ${job.title}`),
    modes, job.site ? el('span', { class: 'badge info' }, `site ${job.site}`) : null);
  $('#config-summary').hidden = false;
  $('#config').hidden = true;
}

export function expand() {
  $('#config-summary').hidden = true;
  $('#config').hidden = false;
}
