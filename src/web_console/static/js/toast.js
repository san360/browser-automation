/* Transient notifications (polite live region). */
import { $, el } from './dom.js';
import { icon } from './icons.js';

const ICON = { ok: 'check', err: 'error', info: 'info', warn: 'warning' };

export function toast(message, tone = 'info', ms = 4500) {
  const host = $('#toasts');
  if (!host) return;
  const node = el('div', { class: `toast ${tone}`, role: tone === 'err' ? 'alert' : 'status' }, icon(ICON[tone] || 'info'),
    el('span', {}, message));
  host.append(node);
  setTimeout(() => node.remove(), ms);
}
