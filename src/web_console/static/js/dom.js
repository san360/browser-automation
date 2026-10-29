/* DOM helpers. Everything the console shows from runs (model output, page text, URLs) is untrusted, so nodes are
   built with textContent and attributes, never with innerHTML. */

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

/* el('div', { class: 'x', onclick: fn, dataset: { a: 1 } }, 'text', childNode, [more]) */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  while (node && node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function replace(node, ...children) {
  clear(node);
  return append(node, children);
}

export function on(target, event, handler, options) {
  const node = typeof target === 'string' ? $(target) : target;
  if (!node) {
    console.warn(`[console] ${target} not found; ${event} listener skipped`);
    return null;
  }
  node.addEventListener(event, handler, options);
  return node;
}

export function debounce(fn, wait = 300) {
  let timer = null;
  const debounced = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
  debounced.flush = (...args) => { clearTimeout(timer); fn(...args); };
  return debounced;
}

/* Signed Playwright links (live view, recordings) let anyone watch or take over the browser session: never show them
   as text. Mirrors demo_common.reporting.redact. */
const SIGNED_LINK = /https:\/\/[^\s)\]"'<>]*(?:liveview|live-view|#lv=|playwright\.microsoft\.com)[^\s)\]"'<>]*/gi;
export const LINK_MASK = '[live-view link hidden]';
export function maskSecrets(text) {
  return String(text ?? '').replace(SIGNED_LINK, LINK_MASK);
}

export async function copyText(text, label = 'Copied') {
  const { toast } = await import('./toast.js');
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label} to the clipboard.`, 'ok');
  } catch {
    toast('The clipboard is blocked in this browser.', 'err');
  }
}

export function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.dataset.label || button.textContent;
    button.disabled = true;
    if (label) button.textContent = label;
  } else {
    button.disabled = false;
    if (button.dataset.label) button.textContent = button.dataset.label;
  }
}

/* Roving tabs: arrow keys move between tabs, Enter/Space or click selects. */
export function tablist(root, onSelect) {
  const tabs = $$('[role="tab"]', root);
  const select = (tab, focus = false) => {
    tabs.forEach((t) => {
      const active = t === tab;
      t.setAttribute('aria-selected', String(active));
      t.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(t.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
    });
    if (focus) tab.focus();
    if (onSelect) onSelect(tab);
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', (e) => {
      const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (step) { e.preventDefault(); select(tabs[(i + step + tabs.length) % tabs.length], true); }
    });
  });
  return { select: (id) => { const tab = tabs.find((t) => t.id === id || t.dataset.tab === id); if (tab) select(tab); } };
}

/* Segmented radio groups built from buttons with role="radio". */
export function segmented(root, onChange) {
  const buttons = $$('[role="radio"]', root);
  const set = (button, notify = true) => {
    buttons.forEach((b) => {
      b.setAttribute('aria-checked', String(b === button));
      b.tabIndex = b === button ? 0 : -1;
    });
    if (notify && onChange) onChange(button);
  };
  buttons.forEach((button, i) => {
    button.addEventListener('click', () => set(button));
    button.addEventListener('keydown', (e) => {
      const step = ['ArrowRight', 'ArrowDown'].includes(e.key) ? 1 : ['ArrowLeft', 'ArrowUp'].includes(e.key) ? -1 : 0;
      if (step) { e.preventDefault(); const next = buttons[(i + step + buttons.length) % buttons.length]; next.focus(); set(next); }
    });
  });
  return {
    value: () => (buttons.find((b) => b.getAttribute('aria-checked') === 'true') || {}).dataset,
    set: (predicate, notify = false) => { const b = buttons.find(predicate); if (b) set(b, notify); },
  };
}
