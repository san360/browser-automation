/* Right-column tabs: Preview, Task (the exact prompt sent to the agent) and Event (raw JSON of a timeline step). */
import { $, clear, copyText, el, on, tablist } from './dom.js';
import { jsonText, renderJson } from './jsonview.js';
import { fmtDuration } from './format.js';

let tabs = null;
let following = true;
let current = null;
let taskText = '';

function updateFollow() {
  const button = $('#event-follow');
  button.setAttribute('aria-pressed', String(following));
  button.textContent = following ? 'Following' : 'Follow latest';
}

export function initInspector() {
  tabs = tablist($('.side-tabs'));
  on('#task-copy', 'click', () => { if (taskText) copyText(taskText, 'Task copied'); });
  on('#event-copy', 'click', () => { if (current) copyText(jsonText(current), 'Event copied'); });
  on('#event-follow', 'click', () => { following = !following; updateFollow(); });
  updateFollow();
}

export function selectTab(id) {
  if (tabs) tabs.select(id);
}

export function showTask(data) {
  if (!data) return;
  taskText = data.task || '';
  $('#task-code').textContent = taskText || 'No task.';
  const limits = data.limits || {};
  const rows = [
    ['Start URL', data.url],
    ['Allowed domains', (data.allowed_domains || []).join(', ') || 'any (no allow-list)'],
    ['Max tool calls', limits.max_tool_calls],
    ['Max output tokens', limits.max_output_tokens],
    ['Timeout', limits.timeout_seconds ? fmtDuration(limits.timeout_seconds) : null],
    ['Computer Use steps', limits.max_cua_steps],
    ['Recoveries (prompt)', limits.max_recoveries],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '');
  clear($('#task-meta')).append(...rows.flatMap(([key, value]) => [el('dt', {}, key), el('dd', {}, String(value))]));
}

export function showEvent(event, { userSelected = false } = {}) {
  if (!event) return;
  if (userSelected) {
    following = false;
    updateFollow();
    selectTab('tab-event');
  } else if (!following) {
    return;
  }
  current = event;
  $('#event-label').textContent = `${String(event.kind || 'event').toUpperCase()} · #${event.seq ?? ''}`;
  renderJson($('#event-code'), event);
}

export function resetEvents() {
  current = null;
  following = true;
  updateFollow();
  $('#event-label').textContent = 'SELECTED EVENT';
  $('#event-code').textContent = 'Select a step in the timeline to inspect its event.';
}
