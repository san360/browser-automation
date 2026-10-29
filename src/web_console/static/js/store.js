/* Shared console state and a tiny publish/subscribe bus between modules. */

export const state = {
  boot: null,
  settings: {},
  models: { prompt: [], cua: [] },
  local: [],
  scenarios: [],
  scenarioId: null,
  runType: 'single',
  job: null,
  running: false,
  history: null,
};

const listeners = new Map();

export function subscribe(name, fn) {
  if (!listeners.has(name)) listeners.set(name, new Set());
  listeners.get(name).add(fn);
  return () => listeners.get(name).delete(fn);
}

export function emit(name, data) {
  for (const fn of listeners.get(name) || []) {
    try {
      fn(data);
    } catch (error) {
      console.error(`[console] ${name} handler failed`, error);
    }
  }
}

export const MODES = {
  prompt: {
    label: 'Prompt agent', short: 'Prompt', tool: 'Browser Automation tool',
    detail: 'Foundry prompt agent with the GA Browser Automation tool. The browser runs in Azure (Playwright Workspaces).',
    browser: 'Cloud browser', preview: 'Live view of the cloud browser, opened beside the console',
  },
  hosted: {
    label: 'Hosted agent', short: 'Hosted', tool: 'Agent Framework + Foundry Toolbox',
    detail: 'web-qa-agent on Foundry Agent Service: Browser Automation through a toolbox, plus HTTP and page-source tools.',
    browser: 'Cloud browser', preview: 'Live view of the cloud browser, opened beside the console',
  },
  local: {
    label: 'Local agent', short: 'Local', tool: 'Hosted agent code on this PC',
    detail: 'The hosted agent\u2019s code on 127.0.0.1. Edge on this PC through Playwright MCP (reaches localhost), or the cloud browser.',
    browser: 'Browser on this PC', preview: 'Screenshots of the browser on this PC (or the live view with the cloud browser)',
  },
  cua: {
    label: 'Computer Use', short: 'CUA', tool: 'Screenshots + Playwright',
    detail: 'The GA computer tool: the model sees screenshots and returns clicks and keystrokes, executed with Playwright here.',
    browser: 'Chromium on this PC', preview: 'Every screenshot the model acts on, with a filmstrip',
  },
};

export const MODE_ORDER = ['prompt', 'hosted', 'local', 'cua'];

export function modeLabel(mode) {
  return (MODES[mode] || {}).label || mode;
}

/* Is the cloud browser (and so a live view) used by this mode with these options? */
export function usesLiveView(mode, options = {}) {
  return mode === 'prompt' || mode === 'hosted' || (mode === 'local' && !!options.remote_browser);
}

export function scenarioById(id) {
  return state.scenarios.find((s) => s.id === id) || null;
}
