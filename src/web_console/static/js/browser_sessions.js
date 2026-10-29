/* Browser IDs are correlation metadata; signed live-view URLs remain hidden. */
import { copyText, el, maskSecrets } from './dom.js';

export function browserSessions(ids = []) {
  return el('div', { class: 'browser-sessions', hidden: !ids.length }, ids.map((id) => {
    const text = maskSecrets(id);
    return el('div', { class: 'run-meta' },
      el('span', { class: 'fine-print' }, 'Browser session ID'),
      el('code', { class: 'browser-session-id' }, text),
      el('button', { type: 'button', class: 'button small', 'aria-label': `Copy browser session ID ${text}`,
        onclick: () => copyText(text, 'Browser session ID copied') }, 'Copy'));
  }));
}
