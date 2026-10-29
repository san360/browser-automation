/* Scenario inputs as form fields. Only inputs the presenter changed are sent as overrides, so untouched inputs keep
   their templates (for example ${DEMO_SITE_URL} follows the demo-site target). "Edit as YAML" sends all of them as-is. */
import { $, clear, el } from './dom.js';

let specs = [];
let defaults = {};
let current = {};
let latestYaml = '';
let dirty = new Set();
let yamlMode = false;
let onChange = () => {};

const LABELS = { dob: 'Date of birth', zip_code: 'ZIP code', url: 'URL', hardened_url: 'Hardened URL' };
const label = (key) => LABELS[key] || key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

function valueOf(spec, node) {
  if (spec.kind === 'boolean') return node.checked;
  if (spec.kind === 'number') {
    const n = Number(node.value);
    return node.value.trim() !== '' && Number.isFinite(n) ? n : node.value;
  }
  if (spec.kind === 'yaml') {
    try { return JSON.parse(node.value); } catch { return node.value; }
  }
  return node.value;
}

function setValue(spec, node, value) {
  if (spec.kind === 'boolean') node.checked = !!value;
  else if (spec.kind === 'yaml') node.value = value === undefined ? '' : JSON.stringify(value);
  else node.value = value === undefined || value === null ? '' : String(value);
}

function refreshFoot() {
  $('#inputs-reset').hidden = yamlMode || !dirty.size;
  $('#inputs-note').textContent = yamlMode ? 'All inputs in the YAML are sent as overrides.'
    : dirty.size ? `${dirty.size} input${dirty.size === 1 ? '' : 's'} changed from the scenario defaults.` : '';
}

function field(spec) {
  const id = `input-${spec.key}`;
  const attrs = { id, dataset: { input: spec.key }, spellcheck: 'false', autocomplete: 'off' };
  let control;
  if (spec.kind === 'boolean') control = el('input', { ...attrs, type: 'checkbox' });
  else if (spec.kind === 'number') control = el('input', { ...attrs, type: 'number', step: 'any' });
  else if (spec.kind === 'text' || spec.kind === 'yaml') control = el('textarea', { ...attrs, rows: spec.kind === 'text' ? 3 : 2 });
  else control = el('input', { ...attrs, type: 'text' });
  control.addEventListener(spec.kind === 'boolean' ? 'change' : 'input', () => {
    dirty.add(spec.key);
    control.classList.add('dirty');
    refreshFoot();
    onChange();
  });
  if (spec.kind === 'boolean') {
    return el('label', { class: 'field toggle' }, control, label(spec.key));
  }
  const wide = spec.kind === 'text' || spec.kind === 'yaml';
  const hint = spec.key.includes('_') || LABELS[spec.key] ? el('span', { class: 'field-hint' }, spec.key) : null;
  return el('label', { class: `field${wide ? ' wide' : ''}`, for: id }, el('span', { class: 'field-label' }, label(spec.key), hint), control);
}

export function initInputs({ change }) {
  onChange = change;
  $('#inputs-yaml-toggle').addEventListener('click', () => setYamlMode(!yamlMode));
  $('#inputs-yaml').addEventListener('input', () => onChange());
  $('#inputs-reset').addEventListener('click', reset);
}

export function build(scenario) {
  specs = scenario ? scenario.inputs : [];
  defaults = {};
  current = {};
  dirty = new Set();
  yamlMode = false;
  clear($('#inputs-form')).append(...specs.map(field));
  $('#inputs-yaml-wrap').hidden = true;
  $('#inputs-form').hidden = false;
  $('#inputs-yaml-toggle').hidden = !specs.length;
  $('#inputs-yaml-toggle').setAttribute('aria-pressed', 'false');
  $('#inputs-yaml-toggle').textContent = 'Edit inputs as YAML';
  refreshFoot();
}

/* After each task preview: the scenario's defaults for the current target, and the effective values. */
export function setValues(newDefaults, effective, yamlText) {
  defaults = newDefaults || {};
  current = effective || {};
  latestYaml = yamlText || '';
  for (const spec of specs) {
    const node = document.getElementById(`input-${spec.key}`);
    if (node && !dirty.has(spec.key) && document.activeElement !== node) setValue(spec, node, defaults[spec.key]);
  }
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function setYamlMode(on) {
  yamlMode = on;
  if (on) {
    $('#inputs-yaml').value = latestYaml;
  } else {
    for (const spec of specs) {
      const node = document.getElementById(`input-${spec.key}`);
      if (!node || !(spec.key in current)) continue;
      setValue(spec, node, current[spec.key]);
      const changed = !same(current[spec.key], defaults[spec.key]);
      node.classList.toggle('dirty', changed);
      if (changed) dirty.add(spec.key); else dirty.delete(spec.key);
    }
  }
  $('#inputs-yaml-wrap').hidden = !on;
  $('#inputs-form').hidden = on;
  $('#inputs-yaml-toggle').setAttribute('aria-pressed', String(on));
  $('#inputs-yaml-toggle').textContent = on ? 'Edit inputs as fields' : 'Edit inputs as YAML';
  refreshFoot();
  onChange();
}

export function reset() {
  dirty = new Set();
  for (const spec of specs) {
    const node = document.getElementById(`input-${spec.key}`);
    if (!node) continue;
    node.classList.remove('dirty');
    setValue(spec, node, defaults[spec.key]);
  }
  refreshFoot();
  onChange();
}

/* What to send: {inputs_yaml} in YAML mode, else {inputs} with the changed fields only. */
export function overrides() {
  if (yamlMode) return { inputs_yaml: $('#inputs-yaml').value };
  const inputs = {};
  for (const spec of specs) {
    const node = document.getElementById(`input-${spec.key}`);
    if (node && dirty.has(spec.key)) inputs[spec.key] = valueOf(spec, node);
  }
  return Object.keys(inputs).length ? { inputs } : {};
}

export function changedCount() {
  return yamlMode ? null : dirty.size;
}
