/* One recorded run: header, metrics and tabs for its report (safe Markdown), answer, steps, screenshots, task and log. */
import { $, clear, el, maskSecrets, tablist } from './dom.js';
import { api, fetchText } from './http.js';
import { icon } from './icons.js';
import { renderMarkdown } from './markdown.js';
import { MODES } from './store.js';
import { createTimeline } from './timeline.js';
import { metricsFor, renderChecks } from './answer.js';
import { openLightbox } from './filmstrip.js';
import { fmtDateTime, statusTone } from './format.js';
import { browserSessions } from './browser_sessions.js';

const fileUrl = (folder, name) => `/api/history/${encodeURIComponent(folder)}/files/${encodeURIComponent(name)}`;
let request = 0;

function image(folder) {
  return (src, alt) => {
    if (!/^step-\d{3,4}\.png$/.test(src)) return null;
    const img = el('img', { src: fileUrl(folder, src), alt: alt || src, loading: 'lazy' });
    img.addEventListener('click', () => openLightbox(img.src, src));
    return img;
  };
}

function panel(id, ...children) {
  return el('div', { class: 'detail-body', id: `detail-${id}`, role: 'tabpanel', 'aria-labelledby': `detail-tab-${id}`, hidden: true }, ...children);
}

function steps(data) {
  const list = el('ol', { class: 'timeline', 'aria-label': 'Recorded steps' });
  const timeline = createTimeline(list, { follow: () => false, shotUrl: (e) => (e.file ? fileUrl(data.folder, e.file) : null) });
  timeline.reset('No events were recorded.');
  data.events.forEach((event) => timeline.add(event));
  return list;
}

function screenshots(data, result) {
  const shots = result?.screenshots || [];
  if (!shots.length) return el('p', { class: 'muted small' }, 'This run has no screenshots (only Computer Use records them).');
  return el('div', { class: 'shot-grid' }, shots.map((name) => {
    const img = el('img', { src: fileUrl(data.folder, name), alt: name, loading: 'lazy' });
    img.addEventListener('click', () => openLightbox(img.src, name));
    return el('figure', {}, img, el('figcaption', {}, name));
  }));
}

async function log(folder, host) {
  try {
    const text = await fetchText(fileUrl(folder, 'local-agent.log'));
    host.textContent = maskSecrets(text.length > 200000 ? `… (showing the last 200 KB)\n${text.slice(-200000)}` : text);
  } catch (error) {
    host.textContent = `Could not load the log: ${error.message}`;
  }
}

export async function renderDetail(host, folder) {
  const ticket = ++request;
  clear(host).append(el('div', { class: 'card' }, el('p', { class: 'muted' }, el('span', { class: 'spinner small' }), ' Loading the run…')));
  let data;
  try {
    data = await api(`/api/history/${encodeURIComponent(folder)}`);
  } catch (error) {
    if (ticket === request) clear(host).append(el('div', { class: 'callout err' }, icon('error'), el('div', {}, error.message)));
    return;
  }
  if (ticket !== request) return;
  const r = data.result;
  const tabs = [['report', 'Report'], ['answer', 'Answer'], ['steps', `Steps (${data.events.length})`]];
  if (r?.screenshots?.length) tabs.push(['shots', `Screenshots (${r.screenshots.length})`]);
  tabs.push(['task', 'Task']);
  if (r?.has_log) tabs.push(['log', 'Agent log']);
  const tabBar = el('div', { class: 'detail-tabs', role: 'tablist', 'aria-label': 'Run details' }, tabs.map(([id, label], i) =>
    el('button', { type: 'button', role: 'tab', id: `detail-tab-${id}`, 'aria-controls': `detail-${id}`, 'aria-selected': String(i === 0), tabindex: i ? -1 : 0 }, label)));
  const checks = el('ul', { class: 'check-list' });
  const badge = el('span', {});
  const keyHost = el('div', {});
  const answer = el('div', {}, r?.final_text ? renderMarkdown(r.final_text) : el('p', { class: 'muted' }, 'No answer was recorded.'));
  if (r) { renderChecks(r, checks, badge, keyHost); answer.append(el('h3', { class: 'small' }, 'Automatic checks ', badge), checks, keyHost); }
  const logBox = el('pre', { class: 'code-block log-view' }, 'Loading…');
  const panels = {
    report: panel('report', data.report ? renderMarkdown(data.report, { resolveImage: image(folder) }) : el('p', { class: 'muted' }, 'No report.md (the run may still be in progress or have crashed).')),
    answer: panel('answer', answer), steps: panel('steps', steps(data)), shots: panel('shots', screenshots(data, r)),
    task: panel('task', renderMarkdown(data.task || '')), log: panel('log', logBox),
  };
  const mode = r?.mode || folder.split('-').pop();
  clear(host).append(el('article', { class: 'card' },
    el('div', { class: 'detail-head' }, el('div', {},
      el('h2', {}, r?.title || folder),
      el('div', { class: 'run-meta' }, el('span', { class: `badge ${statusTone(r?.status)}` }, r?.status || 'no result'),
        el('span', { class: `badge mode-${mode}` }, MODES[mode]?.label || mode), r ? el('span', { class: 'badge muted' }, r.model) : null,
        el('span', { class: 'fine-print' }, fmtDateTime(data.started)))),
    el('code', { class: 'small', title: r?.run_path || '' }, `runs/${folder}/`)),
    browserSessions(r?.browser_session_ids || []),
    r ? el('div', { class: 'metric-grid compact' }, metricsFor(r)) : null,
    tabBar, ...tabs.map(([id]) => panels[id])));
  panels.report.hidden = false;
  tablist(tabBar, (tab) => { if (tab.id === 'detail-tab-log' && logBox.textContent === 'Loading…') log(folder, logBox); });
}
