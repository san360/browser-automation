/* Number, time, cost and URL formatting. */

export function fmtInt(n) {
  return n === null || n === undefined || Number.isNaN(Number(n)) ? '–' : Number(n).toLocaleString('en-US');
}

export function fmtCompact(n) {
  if (n === null || n === undefined) return '–';
  const v = Number(n);
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}M`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e3).toFixed(0)}K`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

export function fmtCost(value, currency = 'USD') {
  if (value === null || value === undefined) return 'n/a';
  const v = Number(value);
  const symbol = currency === 'USD' ? '$' : '';
  const digits = v === 0 ? 2 : v < 0.01 ? 4 : v < 1 ? 3 : 2;
  return `${symbol}${v.toFixed(digits)}${symbol ? '' : ` ${currency}`}`;
}

/* Seconds as "8.4s", "2m 14s" or "1h 3m". */
export function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '–';
  const total = Math.max(0, Number(seconds));
  if (total < 60) return `${Number(total.toFixed(1))}s`;
  const whole = Math.round(total);
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = whole % 60;
  return [h ? `${h}h` : '', `${m}m`, s && !h ? `${s}s` : ''].filter(Boolean).join(' ');
}

/* Elapsed clock for a running job: 0:07, 2:31, 1:02:09. */
export function fmtClock(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

export function fmtOffset(ms) {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '';
  return `+${(Math.max(0, ms) / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
}

export function relTime(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  const diff = (Date.now() - then) / 1000;
  if (Number.isNaN(diff)) return '';
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

export function fmtDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/* host + path, shortened for labels. */
export function shortUrl(url, max = 60) {
  try {
    const u = new URL(url);
    const text = `${u.host}${u.pathname === '/' ? '' : u.pathname}${u.search}`;
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  } catch {
    const text = String(url || '');
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  }
}

export function pathOf(url) {
  try { const u = new URL(url); return `${u.pathname}${u.search}` || '/'; } catch { return String(url || ''); }
}

export function plural(n, word, many = `${word}s`) {
  return `${fmtInt(n)} ${n === 1 ? word : many}`;
}

export function statusTone(status) {
  return { completed: 'ok', passed: 'ok', running: 'info', incomplete: 'warn', blocked: 'warn', stopped: 'warn',
    skipped: 'muted', pending: 'muted', failed: 'err', error: 'err' }[status] || 'muted';
}

export function checksTone(passed, total) {
  if (!total) return 'muted';
  return passed === total ? 'ok' : passed ? 'warn' : 'err';
}
