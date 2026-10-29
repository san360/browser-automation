/* A job (one run, or a comparison of modes) from the Run click to its last event: starts it, follows its event stream
   and routes every event to the timeline, answer, comparison table, preview and banner. */
import { $, maskSecrets, on } from './dom.js';
import { api, followJob } from './http.js';
import { emit, state, subscribe, usesLiveView } from './store.js';
import { toast } from './toast.js';
import * as liveview from './liveview.js';
import * as preview from './preview.js';
import { createTimeline, describeAction } from './timeline.js';
import { initAnswer, resetAnswer, showResult, showStreaming } from './answer.js';
import { renderCompare } from './compare.js';
import { banner, renderHeader, startClock, stopClock } from './run_header.js';
import { collapse, expand } from './config_view.js';
import { resetEvents, showEvent, showTask } from './inspector.js';
import { MODES } from './store.js';
import { requestRun } from './config.js';

let controller = null;
let job = null;
let texts = [];
let viewStep = 0;
let timeline = null;

function shotUrl(event) {
  const step = job && job.steps[event.step];
  return step && step.folder && event.file ? `/api/history/${encodeURIComponent(step.folder)}/files/${encodeURIComponent(event.file)}` : null;
}

function setRunning(running) {
  state.running = running;
  emit('running', running);
}

function showStep(index) {
  viewStep = index;
  const step = job.steps[index];
  if (step.result || step.error) showResult(step.result, step.error);
  else if (texts[index]) showStreaming(texts[index]);
  else resetAnswer(step.status === 'pending' ? 'This mode has not run yet.' : undefined);
  renderHeader(job, viewStep);
  renderCompare(job, viewStep, showStep);
}

function handle(event) {
  const index = event.step;
  const step = index !== null && index !== undefined ? job.steps[index] : null;
  switch (event.kind) {
    case 'step_start':
      step.status = 'running';
      if (job.steps.length > 1) timeline.divider(`${index + 1} · ${MODES[event.mode]?.label || event.mode} · ${event.model}`, event.ts);
      preview.startStep({ jobId: job.id, index, mode: event.mode, options: job.options });
      showStep(index);
      banner(job, 'Starting…');
      return;
    case 'run_folder':
      step.folder = event.folder;
      preview.onEvent(event);
      return;
    case 'frame':
      preview.onEvent(event);
      return;
    case 'text_delta':
      texts[index] = (texts[index] || '') + (event.message || '');
      if (index === viewStep && !step.result) showStreaming(texts[index]);
      return;
    case 'browser_session':
      step.browser_session_ids = [...new Set([...(step.browser_session_ids || []), event.browserSessionId])];
      if (index === viewStep) renderHeader(job, viewStep);
      break;
    case 'step_done':
      Object.assign(step, { status: event.status, result: event.result, error: event.error, folder: event.result?.folder || step.folder });
      preview.stepDone(event);
      if (index === viewStep) showStep(index);
      else renderCompare(job, viewStep, showStep);
      return;
    case 'job_done':
      finish(event);
      return;
    default:
      break;
  }
  timeline.add(event);
  preview.onEvent(event);
  showEvent(event);
  if (!job.finished) banner(job, event.kind === 'action' ? describeAction(event) : maskSecrets(event.message || ''));
}

function finish(event) {
  const ended = job.finished || (event.ts ? Date.parse(event.ts) / 1000 : Date.now() / 1000);
  Object.assign(job, { status: event.status, finished: ended, comparison: event.comparison });
  event.steps.forEach((s, i) => Object.assign(job.steps[i], s));
  stopClock(job.finished);
  setRunning(false);
  liveview.jobEnded();
  banner(null);
  renderHeader(job, viewStep);
  renderCompare(job, viewStep, showStep);
  emit('job:done', job);
}

export function attach(summary, { fresh = false } = {}) {
  if (controller) controller.abort();
  controller = new AbortController();
  job = { ...summary, steps: summary.steps.map((s) => ({ ...s })) };
  texts = [];
  viewStep = 0;
  timeline.reset();
  resetAnswer();
  resetEvents();
  showTask(job);
  if (fresh || !job.finished) collapse(job);
  else expand();
  $('#live-run').hidden = false;
  renderHeader(job, 0);
  renderCompare(job, 0, showStep);
  startClock(job.created, job.finished);
  const active = !job.finished;
  setRunning(active);
  banner(active ? job : null, 'Starting…');
  if (fresh) {
    $('#live-run').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#live-title').focus({ preventScroll: true });
  }
  const signal = controller.signal;
  const current = job;
  followJob(job.id, { after: 0, signal, onEvent: (event) => { if (job === current) handle(event); } })
    .then((outcome) => {
      if (outcome === 'gone' && job === current && !job.finished) {
        setRunning(false);
        banner(null);
      }
    })
    .catch((error) => { if (job === current) toast(`Lost the run's event stream: ${error.message}`, 'err', 8000); });
}

/* Runs synchronously inside the Run click so the live-view window is allowed to open. */
function start({ body, autoOpen }) {
  if (state.running) return;
  const live = autoOpen && body.modes.some((mode) => usesLiveView(mode, body.options));
  if (live) liveview.prepare();
  setRunning(true);
  api('/api/jobs', { method: 'POST', body })
    .then(({ job: summary }) => {
      attach(summary, { fresh: true });
      if (live && liveview.liveStatus().status === 'blocked') toast('Pop-ups are blocked: use “Open live view” in the preview.', 'info', 7000);
    })
    .catch((error) => {
      setRunning(false);
      liveview.cancel();
      toast(error.message, 'err', 9000);
      emit('run:error', error.message);
    });
}

async function stop() {
  if (!job || job.finished) return;
  try {
    const { job: summary } = await api(`/api/jobs/${encodeURIComponent(job.id)}/stop`, { method: 'POST', body: {} });
    job.stop_requested = summary.stop_requested;
    renderHeader(job, viewStep);
    banner(job);
    toast('The current run finishes; the remaining modes are skipped.', 'info');
  } catch (error) {
    toast(error.message, 'err');
  }
}

export function initJob() {
  timeline = createTimeline($('#timeline'), {
    onSelect: (event) => showEvent(event, { userSelected: true }),
    follow: () => $('#timeline-follow').checked,
    shotUrl,
  });
  timeline.reset();
  initAnswer();
  subscribe('run:request', start);
  subscribe('run:busy', () => toast('A run is already in progress. Runs use real Azure resources, so only one runs at a time.', 'info'));
  on('#live-stop', 'click', stop);
  on('#banner-stop', 'click', stop);
  on('#live-again', 'click', () => { expand(); requestRun(); });
  on('#config-edit', 'click', () => { expand(); $('#scenario-select').focus(); });
}

export function currentJob() {
  return job;
}
