/* Scenario catalog: cards with level, category and mode badges; search and filters; open in Run or Compare. */
import { $, clear, debounce, el, on } from './dom.js';
import { icon } from './icons.js';
import { MODE_ORDER, state } from './store.js';
import { scenarioBadges } from './config_view.js';
import { ADHOC, selectScenario } from './config.js';
import { navigate } from './router.js';
import { pathOf } from './format.js';

let level = 0;

function matches(s, query, category, mode) {
  if (level && s.level !== level) return false;
  if (category && s.category !== category) return false;
  if (mode && !s.modes.includes(mode)) return false;
  if (!query) return true;
  const text = `${s.id} ${s.title} ${s.category} ${s.summary} ${s.modes.join(' ')}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).every((word) => text.includes(word));
}

function open(id, compare) {
  selectScenario(id);
  navigate(compare ? '#/compare' : '#/run');
}

function card(s) {
  const facts = [
    el('span', {}, icon('globe'), s.url_template.includes('${DEMO_SITE_URL') ? `demo site ${pathOf(s.url_template.replace(/\$\{DEMO_SITE_URL[^}]*\}/, 'https://x'))}` : 'public web'),
    el('span', {}, icon('check'), `${s.checks.length} check${s.checks.length === 1 ? '' : 's'}`),
    el('span', {}, icon('action'), `≤ ${s.limits.max_tool_calls} tool calls`),
    el('span', {}, icon('clock'), `${Math.round(s.limits.timeout_seconds / 60)} min limit`),
  ];
  const run = el('button', { type: 'button', class: 'button small primary' }, icon('play'), 'Run');
  run.addEventListener('click', () => open(s.id, false));
  const compare = el('button', { type: 'button', class: 'button small' }, icon('compare'), 'Compare modes');
  compare.addEventListener('click', () => open(s.id, true));
  return el('article', { class: 'scenario-card', 'aria-label': s.title },
    el('div', { class: 'card-top' }, scenarioBadges(s).slice(0, 2), el('span', { class: 'scenario-id' }, s.id)),
    el('h3', {}, s.title),
    el('p', {}, s.summary),
    el('div', { class: 'mode-dots' }, scenarioBadges(s).slice(2)),
    el('div', { class: 'facts' }, facts),
    el('div', { class: 'card-actions' }, run, compare));
}

function adhocCard() {
  const run = el('button', { type: 'button', class: 'button small primary' }, icon('play'), 'Write a task');
  run.addEventListener('click', () => open(ADHOC, false));
  return el('article', { class: 'scenario-card adhoc', 'aria-label': 'Ad-hoc task' },
    el('div', { class: 'card-top' }, el('span', { class: 'badge info' }, 'any URL'), el('span', { class: 'scenario-id' }, 'adhoc')),
    el('h3', {}, 'Ad-hoc task against any URL'),
    el('p', {}, 'Describe a task in your own words and point the agent at any public page, or at localhost with the local agent.'),
    el('div', { class: 'mode-dots' }, MODE_ORDER.map((m) => el('span', { class: `badge mode-${m}` }, m))),
    el('div', { class: 'card-actions' }, run));
}

function render() {
  const query = $('#catalog-search').value.trim();
  const category = $('#catalog-category').value;
  const mode = $('#catalog-mode').value;
  const cards = state.scenarios.filter((s) => matches(s, query, category, mode)).map(card);
  const grid = clear($('#catalog-grid'));
  if (!query && !category && !level) grid.append(adhocCard());
  grid.append(...cards);
  if (!cards.length) grid.append(el('div', { class: 'empty-state' }, el('h3', {}, 'No scenario matches'), el('p', {}, 'Clear the search or the filters.')));
}

export function initCatalog() {
  const levels = [...new Set(state.scenarios.map((s) => s.level))].sort();
  const chips = clear($('#catalog-levels'));
  for (const value of [0, ...levels]) {
    const chip = el('button', { type: 'button', class: 'chip', 'aria-pressed': String(value === level) }, value ? `L${value}` : 'All levels');
    chip.addEventListener('click', () => {
      level = value;
      for (const c of chips.children) c.setAttribute('aria-pressed', String(c === chip));
      render();
    });
    chips.append(chip);
  }
  const categories = [...new Set(state.scenarios.map((s) => s.category))].sort();
  $('#catalog-category').append(...categories.map((c) => el('option', { value: c }, c)));
  on('#catalog-search', 'input', debounce(render, 120));
  on('#catalog-category', 'change', render);
  on('#catalog-mode', 'change', render);
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
    const target = !$('#page-scenarios').hidden ? '#catalog-search' : !$('#page-history').hidden ? '#history-search' : null;
    if (target) { e.preventDefault(); $(target).focus(); }
  });
  render();
}
