/* Console entry point: bootstrap (token, settings, catalog), wire the pages, re-attach to a run after a reload. */
import { $, clear, el, segmented } from './dom.js';
import { api, bootstrap } from './http.js';
import { icon } from './icons.js';
import { emit, state, subscribe } from './store.js';
import { initTheme } from './theme.js';
import { initRouter, replaceRoute } from './router.js';
import { initInspector } from './inspector.js';
import { initPreview, showIdle } from './preview.js';
import { initConfig } from './config.js';
import { selection } from './modes.js';
import { attach, initJob } from './job.js';
import { initCatalog } from './catalog.js';
import { initOverview, setEnvDot } from './overview.js';
import { initHistory, loadHistory } from './history.js';
import { initCosts } from './costs.js';

const HEADINGS = {
  single: ['SINGLE RUN', 'Run a scenario', 'Pick a scenario, choose how the agent runs, and watch it work. The preview loads on the right as soon as the browser starts.'],
  compare: ['COMPARE MODES', 'Compare agent modes', 'Run one scenario with several modes, one after another, and compare duration, tool calls, tokens, checks and cost.'],
};

function initRunType() {
  const control = segmented($('#page-run .segmented'), (button) => replaceRoute(button.dataset.runType === 'compare' ? '#/compare' : '#/run'));
  subscribe('route', (route) => {
    if (route.page !== 'run' && route.page !== 'compare') return;
    const type = route.page === 'compare' ? 'compare' : 'single';
    control.set((b) => b.dataset.runType === type);
    const [eyebrow, title, lead] = HEADINGS[type];
    $('#run-eyebrow').textContent = eyebrow;
    $('#run-title').textContent = title;
    $('#run-lead').textContent = lead;
    $('#agent-heading').textContent = type === 'compare' ? 'Agents to compare' : 'Agent';
    if (state.runType !== type) {
      state.runType = type;
      emit('runtype', type);
    }
  });
}

async function checkSite() {
  if (!state.settings.demo_site_url) { setEnvDot('env-site-dot', 'err', 'Demo site not deployed'); return; }
  setEnvDot('env-site-dot', 'running', 'Checking the demo site…');
  try {
    const data = await api('/api/site-health');
    setEnvDot('env-site-dot', data.ok ? 'ok' : 'err', data.ok ? 'Demo site healthy' : 'Demo site not healthy');
    emit('site-health', data);
  } catch {
    setEnvDot('env-site-dot', 'err', 'Demo site check failed');
  }
}

function fatal(message) {
  clear($('#main')).append(el('div', { class: 'card' }, el('div', { class: 'callout err' }, icon('error'),
    el('div', {}, el('strong', {}, 'The console could not start. '), message))));
}

async function main() {
  initTheme();
  let boot;
  try {
    boot = await bootstrap();
    state.boot = boot;
    state.settings = boot.settings;
    state.models = boot.models;
    state.local = boot.local;
    state.scenarios = (await api('/api/scenarios')).scenarios;
  } catch (error) {
    fatal(error.message);
    return;
  }
  const s = state.settings;
  $('#env-project').textContent = s.project_host || 'Foundry project not configured';
  $('#env-site').textContent = s.demo_site_host || 'Demo site not deployed';
  $('#project-pill').textContent = s.project_host ? `${s.project_host.split('.')[0]} · ${s.project_endpoint.split('/').pop()}` : 'No project';
  $('#project-pill').title = s.project_endpoint || '';
  setEnvDot('env-project-dot', s.project_endpoint ? 'ok' : 'err', s.project_endpoint ? 'Configured (run the health checks to verify)' : 'Not configured');

  initInspector();
  initPreview();
  initConfig();
  initJob();
  initRunType();
  initCatalog();
  initOverview();
  initHistory();
  initCosts();
  initRouter();
  if (boot.job) attach(boot.job);
  else showIdle(selection());
  loadHistory();
  checkSite();
}

main();
