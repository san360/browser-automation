/* The live run's header and the global run banner (visible on every page while a run is in progress). */
import { $, clear, el, replace } from './dom.js';
import { MODES } from './store.js';
import { fmtClock, statusTone } from './format.js';
import { browserSessions } from './browser_sessions.js';

let timer = null;
let startedAt = 0;
let endedAt = null;

const LABELS = { running: 'Running', completed: 'Completed', stopped: 'Stopped', failed: 'Failed', incomplete: 'Incomplete',
  blocked: 'Blocked', error: 'Error' };

function tick() {
  const text = fmtClock((endedAt ?? Date.now()) - startedAt);
  $('#live-elapsed').textContent = text;
  $('#banner-elapsed').textContent = text;
}

export function startClock(createdSeconds, finishedSeconds = null) {
  startedAt = createdSeconds * 1000;
  endedAt = finishedSeconds ? finishedSeconds * 1000 : null;
  clearInterval(timer);
  tick();
  if (!endedAt) timer = setInterval(tick, 1000);
}

export function stopClock(finishedSeconds) {
  endedAt = finishedSeconds ? finishedSeconds * 1000 : Date.now();
  clearInterval(timer);
  tick();
}

export function renderHeader(job, viewStep) {
  const status = job.finished ? (job.steps.length === 1 ? job.steps[0].status : job.status) : 'running';
  const badge = $('#live-status');
  badge.className = `badge ${status === 'running' ? 'info' : statusTone(status)}`;
  replace(badge, status === 'running' ? el('span', { class: 'spinner small' }) : null, LABELS[status] || status);
  $('#live-title').textContent = job.scenario_id === 'adhoc' ? 'Ad-hoc task' : job.title;
  const step = job.steps[viewStep] || job.steps[0];
  const meta = clear($('#live-meta'));
  meta.append(el('span', { class: `badge level l${job.level || 1}` }, job.scenario_id === 'adhoc' ? 'ad-hoc' : job.scenario_id));
  for (const s of job.steps) meta.append(el('span', { class: `badge mode-${s.mode}` }, `${MODES[s.mode]?.label || s.mode} · ${s.model}`));
  if (job.site) meta.append(el('span', { class: 'badge info' }, `demo site ${job.site}`));
  meta.append(el('span', { class: 'fine-print' }, step ? `viewing ${MODES[step.mode]?.short || step.mode}` : ''));
  replace($('#live-sessions'), browserSessions(step?.result?.browser_session_ids || step?.browser_session_ids || []));
  $('#live-stop').hidden = job.finished || job.steps.length < 2 || job.stop_requested;
  $('#live-again').hidden = !job.finished;
}

export function banner(job, detail) {
  const on = !!job && !job.finished;
  $('#run-banner').hidden = !on;
  document.body.classList.toggle('banner-on', on);
  $('#busy-pill').hidden = !on;
  $('#nav-live').hidden = !on;
  if (!on) return;
  const running = job.steps.find((s) => s.status === 'running') || job.steps[0];
  const position = job.steps.length > 1 ? ` (${running.index + 1}/${job.steps.length})` : '';
  $('#banner-title').textContent = `Running ${job.scenario_id === 'adhoc' ? 'an ad-hoc task' : job.scenario_id} · ${MODES[running.mode]?.label || running.mode}${position}`;
  if (detail) $('#banner-detail').textContent = detail;
  $('#banner-stop').hidden = job.steps.length < 2 || job.stop_requested;
}
