/* Run configuration: scenario, start URL, demo-site target, inputs and modes; live task preview; the Run request. */
import { $, clear, debounce, el, on, segmented } from './dom.js';
import { api } from './http.js';
import { icon } from './icons.js';
import { emit, scenarioById, state, subscribe } from './store.js';
import { preference, remember } from './theme.js';
import * as inputs from './inputs_form.js';
import * as modes from './modes.js';
import { showTask } from './inspector.js';
import { renderSummary, scenarioOptions } from './config_view.js';

export const ADHOC = '__adhoc__';
let urlDirty = false;
let site = null;
let preview = null;
let previewError = null;
let previewSeq = 0;
const schedule = debounce(refreshPreview, 300);

function scenarioId() { return $('#scenario-select').value; }

function siteUrl() {
  const custom = site && site.value()?.site === 'custom';
  const value = $('#site-url').value.trim();
  return custom && value ? value : null;
}

export function renderPayload() {
  const selection = modes.selection();
  const body = { modes: selection.modes, options: selection.options, site_url: siteUrl() };
  if (scenarioId() === ADHOC) {
    body.adhoc = { url: $('#start-url').value.trim(), task: $('#adhoc-task').value };
  } else {
    body.scenario_id = scenarioId();
    if (urlDirty && $('#start-url').value.trim()) body.url = $('#start-url').value.trim();
    Object.assign(body, inputs.overrides());
  }
  return body;
}

export function jobPayload() {
  const selection = modes.selection();
  const body = renderPayload();
  if (body.modes.includes('prompt')) body.prompt_model = selection.prompt_model;
  if (body.modes.includes('cua')) body.cua_model = selection.cua_model;
  return { body, autoOpen: selection.autoOpen };
}

function messages(notes = [], allowlistError = null, error = null) {
  const host = clear($('#config-messages'));
  if (error) host.append(el('div', { class: 'callout err', role: 'alert' }, icon('error'), el('div', {}, error)));
  if (allowlistError) {
    host.append(el('div', { class: 'callout err', role: 'alert' }, icon('shield'),
      el('div', {}, el('strong', {}, 'Allow-list: '), allowlistError)));
  }
  for (const note of notes) host.append(el('div', { class: 'callout warn' }, icon('warning'), el('div', {}, note)));
}

export function canRun() {
  const selection = modes.selection();
  const enough = state.runType === 'compare' ? selection.modes.length >= 2 : selection.modes.length === 1;
  return !state.running && enough && !!preview && !previewError && !preview.allowlist_error;
}

function updateRunButton() {
  const button = $('#run-button');
  const count = modes.selection().modes.length;
  button.disabled = !canRun();
  button.textContent = state.running ? 'Run in progress…'
    : state.runType === 'compare' ? `Compare ${count} mode${count === 1 ? '' : 's'}` : 'Run scenario';
  if (state.runType === 'compare' && count < 2) button.title = 'Select at least two modes to compare.';
  else button.title = state.running ? 'Runs use real Azure resources, so only one runs at a time.' : '';
  renderSummary(lastHint());
}

function lastHint() {
  return { id: scenarioId(), modes: modes.selection().modes };
}

async function refreshPreview() {
  const seq = ++previewSeq;
  const body = renderPayload();
  if (body.adhoc && !body.adhoc.url) {
    preview = null;
    previewError = 'Enter the URL the agent should start from.';
    messages([], null, previewError);
    updateRunButton();
    return;
  }
  try {
    const data = await api('/api/render', { method: 'POST', body });
    if (seq !== previewSeq) return;
    preview = data;
    previewError = null;
    if (!urlDirty && scenarioId() !== ADHOC) $('#start-url').value = data.url;
    inputs.setValues(data.defaults, data.inputs, data.inputs_yaml);
    showTask(data);
    messages(data.warnings, data.allowlist_error);
  } catch (error) {
    if (seq !== previewSeq) return;
    preview = null;
    previewError = error.message;
    messages([], null, error.message);
  }
  updateRunButton();
}

export function selectScenario(id) {
  const scenario = id === ADHOC ? null : scenarioById(id) || state.scenarios[0];
  const value = scenario ? scenario.id : ADHOC;
  $('#scenario-select').value = value;
  state.scenarioId = value;
  remember('scenario', value);
  urlDirty = false;
  $('#url-reset').hidden = true;
  $('#adhoc-task-wrap').hidden = !!scenario;
  if (!scenario) $('#start-url').value = $('#start-url').value || state.settings.demo_site_url || 'https://learn.microsoft.com/azure/foundry/';
  inputs.build(scenario);
  modes.setSupported(scenario ? scenario.modes : null);
  emit('scenario:change', scenario);
  preview = null;
  schedule.flush();
}

async function checkSite() {
  const status = $('#site-status');
  const url = siteUrl() || state.settings.demo_site_url;
  clear(status).append(el('span', { class: 'spinner small' }), 'Checking (the deployed site may need a minute to wake up)…');
  try {
    const data = await api(`/api/site-health?url=${encodeURIComponent(url)}`);
    clear(status).append(el('span', { class: `status-dot ${data.ok ? 'ok' : 'err'}` }),
      data.ok ? `Healthy (${data.detail.version ? `v${data.detail.version}` : 'ok'})` : `Not healthy: ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`);
  } catch (error) {
    clear(status).append(el('span', { class: 'status-dot err' }), error.message);
  }
}

function requestRun() {
  if (!canRun()) {
    if (state.running) emit('run:busy');
    return;
  }
  const { body, autoOpen } = jobPayload();
  emit('run:request', { body, autoOpen, scenario: scenarioById(scenarioId()) });
}

export function initConfig() {
  const select = $('#scenario-select');
  clear(select).append(...scenarioOptions(ADHOC));
  on(select, 'change', () => selectScenario(select.value));
  on('#start-url', 'input', () => { urlDirty = scenarioId() !== ADHOC; $('#url-reset').hidden = !urlDirty; schedule(); });
  on('#url-reset', 'click', () => { urlDirty = false; $('#url-reset').hidden = true; schedule.flush(); });
  site = segmented($('.site-target .segmented'), (button) => {
    const custom = button.dataset.site === 'custom';
    $('#site-url').hidden = !custom;
    if (custom) $('#site-url').focus();
    remember('site', { custom, url: $('#site-url').value.trim() });
    schedule();
  });
  const saved = preference('site', { custom: false, url: '' });
  $('#site-url').value = saved.url || '';
  if (saved.custom) { site.set((b) => b.dataset.site === 'custom'); $('#site-url').hidden = false; }
  on('#site-url', 'input', () => { remember('site', { custom: true, url: $('#site-url').value.trim() }); schedule(); });
  on('#site-check', 'click', checkSite);
  on('#adhoc-task', 'input', schedule);
  // Runs cost money: Enter in a field must never start one, only the button or Ctrl+Enter.
  on('#config', 'submit', (e) => e.preventDefault());
  on('#run-button', 'click', requestRun);
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !$('#page-run').hidden) { e.preventDefault(); requestRun(); }
  });
  inputs.initInputs({ change: schedule });
  modes.initModes({ change: (selection) => { emit('modes:change', selection); schedule(); updateRunButton(); } });
  subscribe('running', updateRunButton);
  subscribe('history', updateRunButton);
  subscribe('run:error', (message) => messages(preview?.warnings || [], preview?.allowlist_error, message));
  subscribe('runtype', () => { modes.setMulti(state.runType === 'compare'); updateRunButton(); });
  selectScenario(preference('scenario', null) || '02-site-search');
}

export { requestRun };
