/* Hash routing between pages (#/overview, #/run, #/history/<folder>, …) and the sidebar's active state. */
import { $, $$ } from './dom.js';
import { emit } from './store.js';

const PAGES = {
  overview: 'page-overview', scenarios: 'page-scenarios', run: 'page-run', compare: 'page-run',
  history: 'page-history', costs: 'page-costs',
};
const TITLES = { overview: 'Overview', scenarios: 'Scenarios', run: 'Run', compare: 'Compare', history: 'History', costs: 'Costs' };
let current = null;

export function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const page = PAGES[parts[0]] ? parts[0] : 'overview';
  return { page, arg: parts.length > 1 ? decodeURIComponent(parts.slice(1).join('/')) : '' };
}

function show(focus) {
  const route = parseRoute();
  const target = PAGES[route.page];
  for (const id of new Set(Object.values(PAGES))) document.getElementById(id).hidden = id !== target;
  $$('.nav-item').forEach((item) => {
    const active = item.dataset.page === route.page;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
  });
  $('#crumb').textContent = TITLES[route.page];
  document.title = `${TITLES[route.page]} · Browser Automation console`;
  const changedPage = !current || current.page !== route.page;
  current = route;
  emit('route', route);
  if (focus && changedPage) {
    window.scrollTo({ top: 0 });
    $('#main').focus({ preventScroll: true });
  }
}

export function initRouter() {
  window.addEventListener('hashchange', () => show(true));
  show(false);
}

export function navigate(hash) {
  if (location.hash === hash) show(true);
  else location.hash = hash;
}

/* Change the hash without a page switch (for example #/run ↔ #/compare on the same page). */
export function replaceRoute(hash) {
  if (location.hash !== hash) history.replaceState(null, '', hash);
  show(false);
}
