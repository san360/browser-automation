/* The preview column before a run: what will appear here for the selected mode(s), and how to get the best view. */
import { clear, el } from './dom.js';
import { MODE_ICONS, icon } from './icons.js';
import { MODES, usesLiveView } from './store.js';
import { EMBEDDED } from './liveview.js';

function expectation(mode, options) {
  if (usesLiveView(mode, options)) {
    if (EMBEDDED) {
      return `This console is embedded in an app panel, which usually cannot open windows, and the live-view page cannot be embedded. Open ${location.origin} in Edge or Chrome to watch the cloud browser beside the console; the steps, answer and checks stream here either way.`;
    }
    return options.autoOpen === false
      ? 'A button opens the cloud browser\u2019s live view when the agent starts its session.'
      : 'The cloud browser\u2019s live view opens in a window beside the console as soon as the agent starts its session (a few seconds after Run). Allow pop-ups for this console if your browser asks.';
  }
  if (mode === 'local') {
    const window = options.headed ? ' A real Edge window also opens on this PC.' : '';
    return options.mirror === false
      ? `The agent drives Edge on this PC through Playwright MCP.${window} Turn on mirroring to see screenshots here.`
      : `Screenshots of the agent\u2019s browser on this PC appear here about once a second, with the current page and actions.${window}`;
  }
  return 'Each screenshot the model acts on appears here, with a filmstrip of every step. Click one to enlarge it.';
}

export function renderIdle(root, selection = {}) {
  const modes = selection.modes && selection.modes.length ? selection.modes : ['prompt'];
  const options = { ...(selection.options || {}), autoOpen: selection.autoOpen };
  const cards = modes.map((mode) => el('div', { class: 'callout info' }, icon(MODE_ICONS[mode] || 'info'),
    el('div', {}, el('strong', {}, `${MODES[mode].label}: `), expectation(mode, options))));
  clear(root).append(el('div', { class: 'preview-state' },
    el('div', { class: 'empty-state' },
      el('span', { class: 'empty-icon' }, icon('eye')),
      el('h3', {}, 'The browser preview appears here'),
      el('p', {}, 'Nothing to click: it loads automatically when the run starts and follows the agent step by step.')),
    el('div', { class: 'mode-explain' }, cards),
    el('p', { class: 'privacy-note' }, icon('info'),
      'Press Ctrl+Enter to run. The Task tab shows the exact prompt sent to the agent; the Event tab shows the raw event behind any step.')));
}
