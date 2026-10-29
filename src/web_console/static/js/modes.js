/* Agent mode cards (radio in a single run, checkboxes when comparing) and the options of the selected modes. */
import { $, clear, el } from './dom.js';
import { MODE_ICONS, icon } from './icons.js';
import { MODES, MODE_ORDER, state, usesLiveView } from './store.js';
import { preference, remember } from './theme.js';

let multi = false;
let supported = MODE_ORDER.slice();
let onChange = () => {};
const prefs = {
  mode: preference('mode', 'prompt'),
  compare: preference('compare-modes', ['prompt', 'hosted', 'cua']),
  prompt_model: preference('prompt-model', null),
  cua_model: preference('cua-model', null),
  options: { remote_browser: false, headed: false, auto_ack: false, mirror: true, ...preference('options', {}) },
  autoOpen: preference('auto-live-view', true),
};

const TAGS = {
  prompt: [['Azure browser', 'info'], ['Live view', 'live']],
  hosted: [['Azure browser', 'info'], ['Live view', 'live'], ['HTTP tools', 'muted']],
  local: [['Your PC', 'ok'], ['localhost', 'muted']],
  cua: [['Your PC', 'ok'], ['Screenshots', 'warn']],
};

function selectedModes() {
  const modes = multi ? prefs.compare : [prefs.mode];
  return modes.filter((m) => supported.includes(m));
}

function changed() {
  remember('mode', prefs.mode);
  remember('compare-modes', prefs.compare);
  remember('options', prefs.options);
  remember('auto-live-view', prefs.autoOpen);
  renderOptions();
  onChange(selection());
}

function card(mode) {
  const info = MODES[mode];
  const enabled = supported.includes(mode);
  const checked = selectedModes().includes(mode);
  const input = el('input', { type: multi ? 'checkbox' : 'radio', name: 'agent-mode', value: mode, checked, disabled: !enabled,
    'aria-label': info.label, 'aria-describedby': `mode-detail-${mode}` });
  input.addEventListener('change', () => {
    if (multi) prefs.compare = MODE_ORDER.filter((m) => (m === mode ? input.checked : prefs.compare.includes(m)));
    else prefs.mode = mode;
    renderCards();
    changed();
  });
  const tags = enabled ? TAGS[mode].map(([text, tone]) => el('span', { class: `badge ${tone}` }, text))
    : [el('span', { class: 'badge muted' }, 'Not designed for this scenario')];
  return el('label', { class: `mode-card${checked ? ' selected' : ''}${enabled ? '' : ' unsupported'}`, dataset: { mode },
    title: enabled ? info.detail : 'This scenario does not list this mode' },
  input, el('span', { class: 'mode-icon' }, icon(MODE_ICONS[mode])), el('strong', {}, info.label),
  el('small', { id: `mode-detail-${mode}` }, info.tool), el('span', { class: 'mode-tags' }, tags));
}

function renderCards() {
  clear($('#mode-grid')).append(...MODE_ORDER.map(card));
  const count = selectedModes().length;
  $('#mode-hint').textContent = multi ? `${count} selected · run one after another` : MODES[prefs.mode]?.browser || '';
}

function toggle(label, key, { disabled = false, note } = {}) {
  const input = el('input', { type: 'checkbox', checked: !!prefs.options[key], disabled });
  input.addEventListener('change', () => { prefs.options[key] = input.checked; changed(); });
  return el('label', { class: `toggle${disabled ? ' disabled' : ''}`, title: note || '' }, input, label);
}

function modelSelect(kind, models, current) {
  const select = el('select', { 'aria-label': 'Prompt agent model' },
    models.map((m, i) => el('option', { value: m, selected: m === current }, i === 0 ? `${m} (default)` : m)));
  select.addEventListener('change', () => { prefs[`${kind}_model`] = select.value; remember(`${kind}-model`, select.value); onChange(selection()); });
  return el('label', { class: 'field' }, el('span', { class: 'field-label' }, 'Model deployment'), select);
}

/* Computer Use takes any deployment of a computer-use capable model, so it is free text with suggestions. */
function modelInput(models, current) {
  const input = el('input', { type: 'text', list: 'cua-models', value: current, spellcheck: 'false', autocomplete: 'off',
    pattern: '[A-Za-z0-9._-]+', maxlength: 64, 'aria-label': 'Computer Use model deployment' });
  input.addEventListener('change', () => {
    const value = input.value.trim() || models[0];
    input.value = value;
    prefs.cua_model = value;
    remember('cua-model', value);
    onChange(selection());
  });
  return el('label', { class: 'field' }, el('span', { class: 'field-label' }, 'Model deployment',
    el('span', { class: 'field-hint' }, 'GA computer-use model')), input,
  el('datalist', { id: 'cua-models' }, models.map((m) => el('option', { value: m }))));
}

function group(mode, ...children) {
  return el('div', { class: 'option-group' }, el('h3', {}, icon(MODE_ICONS[mode]), MODES[mode].label), ...children);
}

function renderOptions() {
  const modes = selectedModes();
  const o = prefs.options;
  const s = state.settings || {};
  const groups = [];
  if (modes.includes('prompt')) {
    const models = state.models.prompt.length ? state.models.prompt : [s.prompt_model];
    groups.push(group('prompt', modelSelect('prompt', models, selection().prompt_model),
      el('p', { class: 'note' }, 'Each model has its own agent version (created on first use).')));
  }
  if (modes.includes('hosted')) {
    groups.push(group('hosted', el('p', { class: 'note' },
      `Agent ${s.hosted_agent_name || 'web-qa-agent'} on Foundry Agent Service · model ${s.hosted_model || ''} · toolbox ${s.toolbox_name || ''}.`)));
  }
  if (modes.includes('local')) {
    groups.push(group('local', el('div', { class: 'option-row' },
      toggle('Use the cloud browser (toolbox)', 'remote_browser', { note: 'Off: Playwright MCP drives Edge on this PC and can reach localhost.' }),
      toggle('Show the browser window', 'headed', { disabled: o.remote_browser }),
      toggle('Mirror the browser in the console', 'mirror', { disabled: o.remote_browser, note: 'Screenshots via Playwright MCP --init-page; no extra tokens.' })),
    el('p', { class: 'note' }, `Model ${s.hosted_model || ''} in your Foundry project; the agent loop runs on 127.0.0.1.`)));
  }
  if (modes.includes('cua')) {
    const models = state.models.cua.length ? state.models.cua : [s.computer_use_model];
    groups.push(group('cua', modelInput(models, selection().cua_model), el('div', { class: 'option-row' },
      toggle('Show the browser window', 'headed'),
      toggle('Auto-acknowledge safety checks (demo only)', 'auto_ack', { note: 'Normally a human must review pending safety checks.' }))));
  }
  if (modes.some((m) => usesLiveView(m, o))) {
    const input = el('input', { type: 'checkbox', checked: prefs.autoOpen });
    input.addEventListener('change', () => { prefs.autoOpen = input.checked; changed(); });
    groups.push(el('div', { class: 'option-group' }, el('h3', {}, icon('live'), 'Live view'),
      el('label', { class: 'toggle' }, input, 'Open the live view beside the console automatically'),
      el('p', { class: 'note' }, 'The live-view page cannot be embedded, so it opens in a side window placed next to this console.')));
  }
  clear($('#mode-options')).append(...groups);
}

export function initModes({ change }) {
  onChange = change;
  renderCards();
  renderOptions();
}

export function setMulti(value) {
  multi = value;
  renderCards();
  renderOptions();
  onChange(selection());
}

export function setSupported(modes) {
  supported = modes && modes.length ? modes.slice() : MODE_ORDER.slice();
  if (!multi && !supported.includes(prefs.mode)) prefs.mode = supported[0];
  renderCards();
  renderOptions();
}

export function selection() {
  const s = state.settings || {};
  const promptModels = state.models.prompt;
  const cuaModels = state.models.cua;
  return {
    modes: selectedModes(),
    prompt_model: promptModels.includes(prefs.prompt_model) ? prefs.prompt_model : (promptModels[0] || s.prompt_model),
    cua_model: /^[A-Za-z0-9._-]{1,64}$/.test(prefs.cua_model || '') ? prefs.cua_model : (cuaModels[0] || s.computer_use_model),
    options: { ...prefs.options },
    autoOpen: prefs.autoOpen,
  };
}
