/* How the console talks to its API: one place decides the token header and Content-Type, and turns FastAPI errors
   into readable messages. Run events arrive as Server-Sent Events read with fetch (so the token header can be sent),
   resumable from the last event id. */

let token = '';

export function setToken(value) { token = value || ''; }

function headers(extra = {}, json = false) {
  const h = new Headers(extra);
  if (token) h.set('X-Console-Token', token);
  if (json && !h.has('Content-Type')) h.set('Content-Type', 'application/json');
  return h;
}

export function describeError(body, status) {
  const detail = body && body.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => {
      const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : '';
      return (field ? `${field}: ` : '') + (d.msg || 'invalid value');
    }).join('; ');
  }
  return `HTTP ${status}`;
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = 'GET', body, signal } = {}) {
  const init = { method, signal, headers: headers({}, body !== undefined) };
  if (body !== undefined) init.body = JSON.stringify(body);
  const res = await fetch(path, init);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) throw new ApiError(describeError(data, res.status), res.status);
  return data;
}

export async function bootstrap() {
  const data = await api('/api/bootstrap');
  setToken(data.token);
  return data;
}

export async function fetchText(path) {
  const res = await fetch(path, { headers: headers() });
  if (!res.ok) throw new ApiError(`HTTP ${res.status}`, res.status);
  return res.text();
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseBlock(block) {
  let id = null;
  const data = [];
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue;
    if (line.startsWith('id:')) id = Number(line.slice(3).trim());
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  if (!data.length) return null;
  const event = JSON.parse(data.join('\n'));
  if (id !== null && event.seq === undefined) event.seq = id;
  return event;
}

/* Follow /api/jobs/<id>/events until job_done; reconnects with ?after=<last seq> if the connection drops. */
export async function followJob(jobId, { after = 0, onEvent, signal }) {
  let last = after;
  let failures = 0;
  while (!signal.aborted) {
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/events?after=${last}`, { headers: headers(), signal });
      if (res.status === 404) return 'gone';
      if (!res.ok) throw new ApiError(describeError(await res.json().catch(() => null), res.status), res.status);
      failures = 0;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/g, '\n');
        let cut;
        while ((cut = buffer.indexOf('\n\n')) >= 0) {
          const event = parseBlock(buffer.slice(0, cut));
          buffer = buffer.slice(cut + 2);
          if (!event) continue;
          last = event.seq ?? last;
          onEvent(event);
          if (event.kind === 'job_done') {
            reader.cancel().catch(() => {});
            return 'done';
          }
        }
      }
    } catch (error) {
      if (signal.aborted) return 'aborted';
      failures += 1;
      if (failures > 8) throw error;
    }
    await sleep(Math.min(5000, 600 * (failures + 1)));
  }
  return 'aborted';
}
