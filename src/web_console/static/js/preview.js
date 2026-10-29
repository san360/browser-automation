/* The Preview tab of the right column. It follows the running step automatically:
   cloud browser (prompt, hosted, local with the cloud browser) → live-view window status and controls;
   local browser (Playwright MCP) → mirrored screenshots; Computer Use → the screenshots the model acts on. */
import { $, clear, el, replace } from './dom.js';
import { icon } from './icons.js';
import { MODES, state, subscribe, usesLiveView } from './store.js';
import * as liveview from './liveview.js';
import { createScreen } from './filmstrip.js';
import { describeAction } from './timeline.js';
import { fmtOffset, shortUrl } from './format.js';
import { renderIdle } from './preview_idle.js';

let step = null;
let parts = {};

const LIVE_TEXT = {
  idle: ['info', 'No live view for this step.'],
  waiting: ['live', 'Waiting for the agent to start its cloud browser session. The live view opens beside the console automatically.'],
  open: ['live', 'Live view open in the side window. The agent drives it while you watch; avoid taking control mid-run.'],
  ready: ['live', 'The live view is ready. Open it with the button (the side window was closed).'],
  blocked: ['warn', 'The browser blocked the side window. Open the live view with the button, and allow pop-ups for this console to open it automatically next time.'],
  ended: ['ok', 'The browser session has ended, and its live-view link has expired.'],
  unsupported: ['warn', 'This view cannot open windows (an app\u2019s embedded browser panel, for example), and the live-view page cannot be embedded. Open the console in Edge or Chrome to watch the live view beside it. Local and Computer Use previews work here.'],
};

function hero(name, title, subtitle) {
  return el('div', { class: 'preview-hero' }, el('span', { class: 'empty-icon' }, icon(name)),
    el('div', {}, el('h3', {}, title), el('p', {}, subtitle)));
}

function section(title, ...children) {
  return el('div', { class: 'preview-section' }, el('h4', {}, title), ...children);
}

function renderLiveStatus() {
  if (!parts.status) return;
  const { status, hasUrl } = liveview.liveStatus();
  const [tone, text] = LIVE_TEXT[status] || LIVE_TEXT.idle;
  const dot = el('span', { class: `status-dot ${tone === 'live' ? (status === 'open' ? 'live' : 'running') : tone}` });
  clear(parts.status).append(dot, el('span', {}, text));
  parts.status.className = `preview-status ${status === 'open' ? 'live' : ''}`;
  parts.open.disabled = !hasUrl;
  parts.open.hidden = ['ended', 'idle', 'unsupported'].includes(status);
  parts.open.textContent = status === 'open' ? 'Bring the live view to the front' : 'Open live view';
  if (status === 'unsupported') parts.status.append(el('code', {}, location.origin));
}

function currentPage() {
  if (!parts.page) return;
  const page = step.page;
  let host = '';
  let rest = '';
  try {
    const url = new URL(page.url);
    host = url.host;
    rest = `${url.pathname}${url.search}`;
  } catch { host = page ? page.url : ''; }
  replace(parts.page, page
    ? [el('strong', {}, page.title || host), el('span', {}, page.title ? shortUrl(page.url, 110) : rest || '/')]
    : el('span', {}, 'No page yet.'));
}

function recentActions() {
  if (!parts.actions) return;
  const rows = step.actions.slice(-7).reverse();
  replace(parts.actions, rows.length
    ? rows.map((a) => el('li', {}, el('b', {}, a.when), el('span', { title: a.text }, a.text)))
    : el('li', {}, el('span', {}, 'No browser actions yet.')));
}

function render() {
  const root = $('#side-preview');
  parts = {};
  const mode = MODES[step.mode];
  const nodes = [];
  if (step.live) {
    const where = step.mode === 'local' ? 'Local agent with the cloud browser (toolbox)' : `${mode.label} · ${mode.tool}`;
    nodes.push(hero('live', 'Cloud browser live view', where));
    parts.status = el('div', { class: 'preview-status' });
    parts.open = el('button', { type: 'button', class: 'button primary' }, 'Open live view');
    parts.open.addEventListener('click', () => liveview.openNow());
    nodes.push(parts.status, el('div', { class: 'preview-actions' }, parts.open));
    nodes.push(el('p', { class: 'privacy-note' }, icon('lock'),
      'The signed live-view link lets anyone watch or take control of the session. It is opened directly and never shown, logged or saved.'));
  } else if (step.mode === 'local') {
    const headed = step.options.headed ? 'a visible Edge window on this PC' : 'headless Edge on this PC';
    nodes.push(hero('laptop', 'Browser on this PC', `Playwright MCP drives ${headed}. It can reach localhost and intranet sites.`));
    parts.screen = el('div', {});
    nodes.push(parts.screen);
  } else {
    nodes.push(hero('eye', 'What the model sees', 'Computer Use: every screenshot the model acts on, from Chromium on this PC.'));
    parts.screen = el('div', {});
    nodes.push(parts.screen);
  }
  parts.page = el('div', { class: 'current-page' });
  parts.actions = el('ul', { class: 'recent-actions' });
  nodes.push(section('Current page', parts.page), section('Latest actions', parts.actions));
  if (step.mode === 'local' && !step.live) {
    nodes.push(el('p', { class: 'privacy-note' }, icon('info'), step.options.mirror
      ? 'Screenshots come from Playwright MCP\u2019s init-page hook in the agent\u2019s browser. The agent never sees them, so tokens and behaviour are unchanged.'
      : 'Live screenshots are off for this run (enable “Mirror the browser in the console” in the local options).'));
  }
  clear(root).append(el('div', { class: 'preview-state' }, nodes));
  if (parts.screen) {
    const empty = step.mode === 'cua' ? 'The first screenshot arrives when the browser opens the start page.'
      : step.options.mirror ? 'Screenshots appear when the browser opens a page.' : 'Live screenshots are off for this run.';
    parts.film = createScreen(parts.screen, { empty, label: step.mode === 'cua' ? 'Screenshot' : 'Browser on this PC' });
    for (const shot of step.shots) parts.film.add(shot);
  }
  renderLiveStatus();
  currentPage();
  recentActions();
}

export function initPreview() {
  subscribe('liveview', () => { if (step && step.live) renderLiveStatus(); });
  // Choosing another mode after a run prepares the next one: show what that mode will preview.
  subscribe('modes:change', (selection) => { if (!state.running) showIdle(selection); });
}

export function showIdle(selection) {
  step = null;
  renderIdle($('#side-preview'), selection);
}

export function startStep({ jobId, index, mode, options }) {
  step = { jobId, index, mode, options: options || {}, live: usesLiveView(mode, options || {}), folder: null,
    page: null, actions: [], shots: [], start: null };
  if (step.live) liveview.expect();
  render();
}

export function onEvent(event) {
  if (!step || event.step !== step.index) return;
  const at = event.ts ? new Date(event.ts).getTime() : null;
  if (at && step.start === null) step.start = at;
  if (event.kind === 'run_folder') step.folder = event.folder;
  else if (event.kind === 'action') {
    step.actions.push({ text: describeAction(event), when: at ? fmtOffset(at - step.start) : '' });
    if (event.arguments && typeof event.arguments.url === 'string') step.page = { url: event.arguments.url, title: '' };
    recentActions();
    currentPage();
  } else if (event.kind === 'live_view') {
    liveview.navigate(event.url);
  } else if (event.kind === 'screenshot' && step.folder && event.file) {
    const page = (event.message || '').match(/https?:\/\/\S+/);
    const label = (event.message || '').split(' ').slice(0, 2).join(' ');
    const shot = { src: `/api/history/${encodeURIComponent(step.folder)}/files/${encodeURIComponent(event.file)}`,
      caption: `${label} · ${event.file}`, meta: page ? shortUrl(page[0], 50) : '' };
    step.shots.push(shot);
    if (page) { step.page = { url: page[0], title: '' }; currentPage(); }
    if (parts.film) parts.film.add(shot);
  } else if (event.kind === 'frame') {
    const shot = { src: `/api/jobs/${encodeURIComponent(step.jobId)}/frames/${event.frame}`, caption: event.title || 'Browser on this PC',
      meta: shortUrl(event.url, 50) };
    step.shots.push(shot);
    if (step.shots.length > 40) step.shots.shift();
    step.page = { url: event.url, title: event.title };
    currentPage();
    if (parts.film) parts.film.add(shot);
  }
}

export function stepDone(event) {
  if (!step || event.step !== step.index) return;
  if (step.live) liveview.stepEnded();
}

export function previewMode() {
  return step ? step.mode : null;
}
