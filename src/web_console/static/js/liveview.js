/* The cloud browser's live view (live.playwright.microsoft.com) sends X-Frame-Options: DENY, so it cannot be embedded.
   Instead the console opens a named window beside itself. It must be opened synchronously inside the Run click (popup
   blockers only allow windows opened by a user gesture), then navigated when the live_view event arrives.

   The signed link lets anyone with it watch or take over the browser session: it is only ever put into that window's
   location, never shown as text, logged or stored. The console stays the window's opener on purpose: only an opener
   may navigate a window that shows a cross-origin page, which is how a comparison moves the same window from one
   run's live view to the next. The window only ever shows this console's blank page or Microsoft's live-view page. */
import { emit } from './store.js';

const NAME = 'foundry-live-view';
let win = null;
let status = 'idle';
let lastUrl = null;

function set(next) {
  status = next;
  emit('liveview', { status, hasUrl: !!lastUrl });
}

/* Beside the console when there is room on the right of its window; otherwise the right half of the screen, at least
   900 px wide (the live-view page has a 320 px session list next to the browser). */
function placement() {
  const screenLeft = window.screen.availLeft ?? 0;
  const screenTop = window.screen.availTop ?? 0;
  const screenRight = screenLeft + window.screen.availWidth;
  const right = window.screenX + window.outerWidth;
  if (screenRight - right >= 800) {
    return { left: right, top: window.screenY, width: screenRight - right, height: window.outerHeight };
  }
  const width = Math.min(window.screen.availWidth, Math.max(900, Math.round(window.screen.availWidth / 2)));
  return { left: screenRight - width, top: screenTop, width, height: window.screen.availHeight };
}

function features() {
  const p = placement();
  return `popup=yes,width=${Math.round(p.width)},height=${Math.round(p.height)},left=${Math.round(p.left)},top=${Math.round(p.top)}`;
}

function placeholder(target, text) {
  try {
    const doc = target.document;
    doc.title = 'Live view · Foundry Browser Automation';
    const body = doc.body || doc.documentElement.appendChild(doc.createElement('body'));
    body.replaceChildren();
    Object.assign(body.style, { margin: '0', display: 'grid', placeItems: 'center', height: '100vh', background: '#0d1017',
      color: '#c2c8d5', font: '15px "Segoe UI", system-ui, sans-serif', textAlign: 'center' });
    const box = doc.createElement('div');
    const title = doc.createElement('strong');
    title.textContent = 'Cloud browser live view';
    const line = doc.createElement('p');
    line.textContent = text;
    box.append(title, line);
    body.append(box);
  } catch {
    /* the window already left about:blank */
  }
}

function usable() {
  return win && !win.closed;
}

let noWindows = false; /* learned when even a click could not open a window */
/* Embedded in an app (WebView2): such hosts often refuse new windows, so a refused window is not a pop-up blocker. */
export const EMBEDDED = !!(window.chrome && window.chrome.webview);
const stuck = () => status === 'blocked' || status === 'unsupported';

/* Call synchronously from the Run click handler. */
export function prepare() {
  lastUrl = null;
  try {
    win = window.open('', NAME, features());
  } catch {
    win = null;
  }
  if (!win) { set(noWindows || EMBEDDED ? 'unsupported' : 'blocked'); return false; }
  placeholder(win, 'Waiting for the agent to start its browser session…');
  set('waiting');
  return true;
}

export function navigate(url) {
  if (!url || !url.startsWith('https://')) return;
  lastUrl = url;
  if (usable()) {
    try {
      win.location.replace(url);
      set('open');
      return;
    } catch { /* fall through to the button */ }
  }
  set(stuck() ? status : 'ready');
}

/* The fallback button: a user gesture, so a normal browser always allows the window here. */
export function openNow() {
  if (!lastUrl) return;
  if (usable()) {
    win.location.replace(lastUrl);
    win.focus();
    set('open');
    return;
  }
  try {
    win = window.open(lastUrl, NAME, features());
  } catch {
    win = null;
  }
  // Still no window after a click: this view cannot open windows at all (an app's embedded browser panel, for example).
  noWindows = !win;
  set(win ? 'open' : 'unsupported');
}

function stillBlank() {
  try {
    return usable() && win.location.href === 'about:blank';
  } catch {
    return false; /* cross-origin: it shows (or showed) the live view */
  }
}

/* A step that uses the cloud browser is starting: its link will arrive with its live_view event. */
export function expect() {
  lastUrl = null;
  if (!stuck()) set('waiting');
  if (stillBlank()) placeholder(win, 'Waiting for the agent to start its browser session…');
}

/* The step is over: its browser session is gone, so the link is useless and is forgotten. */
export function stepEnded() {
  const hadLink = !!lastUrl || status === 'open';
  lastUrl = null;
  if (stillBlank()) placeholder(win, 'This step did not open a cloud browser session.');
  set(hadLink ? 'ended' : 'idle');
}

/* The whole run is over: close the window if it never showed a live view. */
export function jobEnded() {
  if (stillBlank()) win.close();
  if (!usable()) win = null;
  lastUrl = null;
  if (status === 'waiting') set('idle');
}

export function cancel() {
  if (stillBlank()) win.close();
  win = null;
  lastUrl = null;
  set('idle');
}

export function liveStatus() {
  return { status, hasUrl: !!lastUrl, windowOpen: usable() };
}
