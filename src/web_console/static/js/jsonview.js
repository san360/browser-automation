/* JSON with syntax colours, built from spans. Signed live-view links are masked, long strings shortened. */
import { LINK_MASK, maskSecrets } from './dom.js';

const MAX_STRING = 4000;

function span(cls, text) {
  const node = document.createElement('span');
  node.className = cls;
  node.textContent = text;
  return node;
}

function stringNode(value) {
  const masked = maskSecrets(value);
  if (masked !== value && masked.trim() === LINK_MASK) return span('masked', `"${LINK_MASK}"`);
  const text = masked.length > MAX_STRING ? `${masked.slice(0, MAX_STRING)}… (${masked.length} chars)` : masked;
  return span('s', JSON.stringify(text));
}

function write(out, value, indent) {
  const pad = '  '.repeat(indent);
  if (value === null || value === undefined) { out.append(span('z', 'null')); return; }
  if (typeof value === 'string') { out.append(stringNode(value)); return; }
  if (typeof value === 'number') { out.append(span('n', String(value))); return; }
  if (typeof value === 'boolean') { out.append(span('b', String(value))); return; }
  const isArray = Array.isArray(value);
  const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);
  if (!entries.length) { out.append(isArray ? '[]' : '{}'); return; }
  out.append(isArray ? '[\n' : '{\n');
  entries.forEach(([key, item], n) => {
    out.append(`${pad}  `);
    if (!isArray) { out.append(span('k', JSON.stringify(String(key)))); out.append(': '); }
    write(out, item, indent + 1);
    out.append(n < entries.length - 1 ? ',\n' : '\n');
  });
  out.append(`${pad}${isArray ? ']' : '}'}`);
}

export function renderJson(target, value) {
  const fragment = document.createDocumentFragment();
  write(fragment, value, 0);
  target.replaceChildren(fragment);
}

export function jsonText(value) {
  return maskSecrets(JSON.stringify(value, null, 2));
}
