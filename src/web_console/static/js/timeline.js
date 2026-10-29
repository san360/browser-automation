/* The step timeline: one row per runner event, with an icon per kind and a readable summary of browser actions. */
import { clear, el, maskSecrets } from './dom.js';
import { KIND_ICONS, icon } from './icons.js';
import { fmtOffset, shortUrl } from './format.js';

const HIDDEN = new Set(['text_delta', 'frame', 'run_folder', 'step_start', 'step_done', 'job_done', 'usage']);
const VERBS = {
  create_browser_session: 'Start a cloud browser session', close_browser_session: 'Close the browser session',
  browser_close: 'Close the browser', browser_navigate: 'Open', browser_navigate_back: 'Go back',
  browser_snapshot: 'Read the page (accessibility snapshot)', browser_find: 'Find', browser_click: 'Click',
  browser_type: 'Type', browser_fill_form: 'Fill the form', browser_select_option: 'Select', browser_press_key: 'Press',
  browser_wait_for: 'Wait for', browser_handle_dialog: 'Handle a dialog', browser_console_messages: 'Read console messages',
  browser_network_requests: 'Read network requests', browser_tabs: 'Tabs', inspect_http_security: 'Inspect HTTP security headers',
  scan_page_source: 'Scan the page source', check_links: 'Check links',
};

export function toolName(name) {
  return String(name || '').replace(/^[a-z0-9]+___/i, '');
}

const short = (value, max = 90) => {
  const text = maskSecrets(typeof value === 'string' ? value : JSON.stringify(value));
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
};

/* A sentence for an action event, e.g. Type “water damage” into e24. */
export function describeAction(event) {
  const name = toolName(event.name);
  const args = event.arguments || {};
  const target = args.element || args.target || args.ref || args.selector;
  if (name.startsWith('computer.')) {
    const what = name.slice(9);
    const at = args.x !== undefined ? ` at (${args.x}, ${args.y})` : '';
    if (what === 'type') return `Type “${short(args.text, 60)}”`;
    if (what === 'keypress') return `Press ${(args.keys || []).join('+')}`;
    if (what === 'scroll') return `Scroll${at} by ${args.scroll_y ?? args.scrollY ?? 0}px`;
    return `${what.charAt(0).toUpperCase()}${what.slice(1)}${at}`;
  }
  const verb = VERBS[name] || name;
  if (name === 'browser_navigate' || args.url) return `${verb} ${shortUrl(maskSecrets(args.url || ''), 70)}`.trim();
  if (name === 'browser_type') return `Type “${short(args.text, 50)}” into ${short(target || 'a field', 30)}`;
  if (name === 'browser_fill_form') {
    const fields = Array.isArray(args.fields) ? args.fields : [];
    return `${verb}: ${fields.map((f) => `${f.name || f.target} = “${short(f.value, 24)}”`).join(', ') || 'fields'}`;
  }
  if (name === 'browser_select_option') return `Select ${short(args.values || args.value || '', 40)} in ${short(target || 'a list', 30)}`;
  if (name === 'browser_press_key') return `Press ${args.key || ''}`;
  if (name === 'browser_wait_for') return `Wait for ${short(args.text || args.textGone || `${args.time}s`, 50)}`;
  if (target) return `${verb} ${short(target, 60)}`;
  return verb;
}

function body(event, shotUrl) {
  const kind = event.kind;
  if (kind === 'action') {
    return [el('span', { class: 'tl-title' }, describeAction(event)),
      el('span', { class: 'tl-sub' }, el('b', {}, toolName(event.name)))];
  }
  if (kind === 'live_view') {
    return [el('span', { class: 'tl-title' }, 'Live view of the cloud browser is available'),
      el('span', { class: 'tl-sub' }, 'Shown beside the console; the signed link is never displayed or saved.')];
  }
  const message = maskSecrets(event.message || '');
  if (kind === 'message') {
    const plain = message.replace(/\*\*|__|`/g, '').replace(/^#+\s*/, '');
    return [el('span', { class: 'tl-title' }, plain || 'Answer'), el('span', { class: 'tl-sub' }, `${event.chars || 0} characters of answer`)];
  }
  if (kind === 'screenshot') {
    const nodes = [el('span', { class: 'tl-title' }, message.replace(/\s*->\s*step-\d+\.png$/, ''))];
    const src = shotUrl && shotUrl(event);
    if (src) nodes.push(el('img', { class: 'tl-thumb', src, alt: event.file || 'screenshot', loading: 'lazy' }));
    return nodes;
  }
  return [el('span', { class: 'tl-title' }, message || kind)];
}

export function createTimeline(list, { onSelect, follow = () => true, shotUrl } = {}) {
  let count = 0;
  let start = null;
  let selected = null;
  const empty = () => el('li', { class: 'timeline-empty' }, 'Waiting for the agent…');

  function select(row, event) {
    if (selected) selected.classList.remove('selected');
    selected = row;
    row.classList.add('selected');
    if (onSelect) onSelect(event);
  }

  return {
    reset(message) {
      clear(list).append(message ? el('li', { class: 'timeline-empty' }, message) : empty());
      count = 0;
      start = null;
      selected = null;
    },
    divider(label, ts) {
      list.querySelector('.timeline-empty')?.remove();
      list.append(el('li', { class: 'divider', role: 'presentation' }, el('span', {}, label)));
      if (ts) start = new Date(ts).getTime();
    },
    add(event) {
      if (HIDDEN.has(event.kind)) return null;
      list.querySelector('.timeline-empty')?.remove();
      const at = event.ts ? new Date(event.ts).getTime() : null;
      if (start === null && at) start = at;
      const row = el('li', { class: `kind-${event.kind}`, tabindex: 0, 'aria-label': `${event.kind}` },
        el('span', { class: 'tl-icon' }, icon(KIND_ICONS[event.kind] || 'info')),
        el('span', { class: 'tl-body' }, body(event, shotUrl)),
        el('span', { class: 'tl-time' }, at && start ? fmtOffset(at - start) : ''));
      row.addEventListener('click', () => select(row, event));
      row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(row, event); } });
      list.append(row);
      count += 1;
      if (follow()) list.scrollTop = list.scrollHeight;
      return row;
    },
    count: () => count,
  };
}
