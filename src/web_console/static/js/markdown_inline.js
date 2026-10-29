/* Inline Markdown → DOM nodes: code, links, images, bold, italics and bare URLs. Text always goes through text nodes;
   links must be http(s); signed live-view links are never shown. */
import { LINK_MASK, maskSecrets } from './dom.js';

const SIGNED = /(?:liveview|live-view|#lv=|playwright\.microsoft\.com)/i;
const RULES = [
  ['code', /`([^`\n]+)`/y],
  ['image', /!\[([^\]\n]*)\]\(<?([^)\s>]+)>?(?:\s+"[^"\n]*")?\)/y],
  ['link', /\[([^\]\n]+)\]\(<?([^)\s>]+)>?(?:\s+"[^"\n]*")?\)/y],
  ['strong', /\*\*(?=\S)([^\n]*?\S)\*\*/y],
  ['strong', /__(?=\S)([^\n]*?\S)__(?![A-Za-z0-9])/y],
  ['em', /\*(?=[^\s*])([^*\n]*?[^\s*])\*/y],
  ['em', /_(?=[^\s_])([^_\n]*?[^\s_])_(?![A-Za-z0-9])/y],
  ['url', /https?:\/\/[^\s<>"'`]+/y],
  ['redacted', /<live-view-link-redacted>/y],
];
const TRIGGERS = new Set(['`', '!', '[', '*', '_', 'h', '<']);

export function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function redactedNode() {
  const span = document.createElement('span');
  span.className = 'redacted';
  span.textContent = LINK_MASK;
  return span;
}

function link(href, children) {
  if (SIGNED.test(href)) return redactedNode();
  const safe = safeUrl(href);
  if (!safe) return null;
  const a = document.createElement('a');
  a.href = safe;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.append(...children);
  return a;
}

/* Trailing punctuation belongs to the sentence, not the URL; an unbalanced ")" too. */
function trimUrl(url) {
  let end = url.length;
  while (end > 0 && '.,;:!?\'"'.includes(url[end - 1])) end -= 1;
  let trimmed = url.slice(0, end);
  if (trimmed.endsWith(')') && (trimmed.match(/\(/g) || []).length < (trimmed.match(/\)/g) || []).length) trimmed = trimmed.slice(0, -1);
  return trimmed;
}

function build(kind, match, options, depth) {
  const [, a, b] = match;
  if (kind === 'code') { const code = document.createElement('code'); code.textContent = maskSecrets(a); return [code, match[0].length]; }
  if (kind === 'redacted') return [redactedNode(), match[0].length];
  if (kind === 'image') {
    const node = options.resolveImage ? options.resolveImage(b, a) : null;
    return [node || document.createTextNode(a ? `[${a}]` : ''), match[0].length];
  }
  if (kind === 'link') {
    const node = link(b, inline(a, { ...options, noLinks: true }, depth + 1));
    return node ? [node, match[0].length] : null;
  }
  if (kind === 'url') {
    const url = trimUrl(match[0]);
    if (!url.includes('.')) return null;
    const node = link(url, [document.createTextNode(url)]);
    return node ? [node, url.length] : null;
  }
  const node = document.createElement(kind);
  node.append(...inline(a, options, depth + 1));
  return [node, match[0].length];
}

/* Returns an array of nodes for one line or paragraph of inline Markdown. */
export function inline(text, options = {}, depth = 0) {
  const out = [];
  let plain = '';
  const flush = () => { if (plain) { out.push(document.createTextNode(maskSecrets(plain))); plain = ''; } };
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (text[i] === '\\' && i + 1 < text.length && /[\\`*_[\]()#!|<>-]/.test(text[i + 1])) { plain += text[i + 1]; i += 2; continue; }
    if (ch === '\n') { flush(); out.push(document.createElement('br')); i += 1; continue; }
    let handled = false;
    if (TRIGGERS.has(ch) && depth < 6) {
      const wordBefore = i > 0 && /[A-Za-z0-9]/.test(text[i - 1]);
      for (const [kind, pattern] of RULES) {
        if ((kind === 'link' || kind === 'url') && options.noLinks) continue;
        if (kind === 'url' && wordBefore) continue;
        if (pattern.source.startsWith('_') && wordBefore) continue;
        pattern.lastIndex = i;
        const match = pattern.exec(text);
        if (!match) continue;
        const built = build(kind, match, options, depth);
        if (!built) continue;
        flush();
        out.push(built[0]);
        i += built[1];
        handled = true;
        break;
      }
    }
    if (!handled) { plain += ch; i += 1; }
  }
  flush();
  return out;
}
