/* Light/dark theme (dark by default), remembered per browser. Toasts. */
import { $, clear, el } from './dom.js';
import { icon } from './icons.js';

const KEY = 'ba-console-theme';

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  const button = $('#theme-toggle');
  if (!button) return;
  const next = theme === 'dark' ? 'light' : 'dark';
  clear(button).append(icon(theme === 'dark' ? 'sun' : 'moon'));
  button.setAttribute('aria-label', `Switch to ${next} theme`);
  button.title = `Switch to ${next} theme`;
}

export function initTheme() {
  let theme = 'dark';
  try { theme = localStorage.getItem(KEY) || 'dark'; } catch { /* storage blocked */ }
  apply(theme === 'light' ? 'light' : 'dark');
  $('#theme-toggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    apply(next);
    try { localStorage.setItem(KEY, next); } catch { /* storage blocked */ }
  });
}

export function preference(name, fallback) {
  try {
    const value = localStorage.getItem(`ba-console-${name}`);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function remember(name, value) {
  try { localStorage.setItem(`ba-console-${name}`, JSON.stringify(value)); } catch { /* storage blocked */ }
}
