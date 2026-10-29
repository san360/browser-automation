/* Block Markdown → DOM: headings, paragraphs, nested lists, fenced code, tables, quotes and rules. A deliberately small
   subset (what agents and run reports produce), with no raw HTML: every node is created explicitly. */
import { maskSecrets } from './dom.js';
import { inline } from './markdown_inline.js';

const FENCE = /^\s{0,3}(```+|~~~+)\s*([\w+-]*)\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

const indentOf = (line) => line.match(/^\s*/)[0].replace(/\t/g, '    ').length;
const isBlank = (line) => !line.trim();

function startsBlock(lines, i) {
  const line = lines[i];
  return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || ITEM.test(line)
    || (line.includes('|') && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1]));
}

function cells(row) {
  let text = row.trim();
  if (text.startsWith('|')) text = text.slice(1);
  if (text.endsWith('|') && !text.endsWith('\\|')) text = text.slice(0, -1);
  return text.split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, '|'));
}

function table(lines, i, options) {
  const head = cells(lines[i]);
  const align = cells(lines[i + 1]).map((c) => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : ''));
  const node = document.createElement('table');
  const thead = node.createTHead().insertRow();
  head.forEach((text, n) => {
    const th = document.createElement('th');
    if (align[n]) th.style.textAlign = align[n];
    th.append(...inline(text, options));
    thead.append(th);
  });
  const body = node.createTBody();
  let j = i + 2;
  for (; j < lines.length && lines[j].includes('|') && !isBlank(lines[j]); j += 1) {
    const row = body.insertRow();
    cells(lines[j]).slice(0, Math.max(head.length, 1)).forEach((text, n) => {
      const td = row.insertCell();
      if (align[n]) td.style.textAlign = align[n];
      td.append(...inline(text, options));
    });
  }
  return [node, j];
}

function list(lines, i, options) {
  const first = lines[i].match(ITEM);
  const base = indentOf(first[1]);
  const ordered = /\d/.test(first[2]);
  const node = document.createElement(ordered ? 'ol' : 'ul');
  if (ordered && parseInt(first[2], 10) !== 1) node.start = parseInt(first[2], 10);
  const items = [];
  let item = null;
  let content = 0;
  let j = i;
  for (; j < lines.length; j += 1) {
    const line = lines[j];
    const match = line.match(ITEM);
    if (match && indentOf(match[1]) <= base + 1 && /\d/.test(match[2]) === ordered) {
      item = { lines: [match[3]] };
      items.push(item);
      content = indentOf(match[1]) + match[2].length + 1;
      continue;
    }
    if (isBlank(line)) {
      const next = lines.slice(j + 1).find((l) => !isBlank(l));
      if (next === undefined || indentOf(next) <= base && !(ITEM.test(next) && /\d/.test(next.match(ITEM)[2]) === ordered)) break;
      item.lines.push('');
      continue;
    }
    if (indentOf(line) > base) { item.lines.push(line.slice(Math.min(content, indentOf(line)))); continue; }
    if (!startsBlock(lines, j) && item.lines[item.lines.length - 1] !== '') { item.lines.push(line.trim()); continue; }
    break;
  }
  for (const entry of items) {
    const li = document.createElement('li');
    const inner = blocks(entry.lines, options);
    const tight = inner.childNodes.length === 1 && inner.firstChild.nodeName === 'P';
    li.append(...(tight ? Array.from(inner.firstChild.childNodes) : Array.from(inner.childNodes)));
    node.append(li);
  }
  return [node, j];
}

function blocks(lines, options) {
  const out = document.createDocumentFragment();
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (isBlank(line)) { i += 1; continue; }
    let match;
    if ((match = line.match(FENCE))) {
      const close = lines.findIndex((l, n) => n > i && l.trim().startsWith(match[1]));
      const end = close < 0 ? lines.length : close;
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = maskSecrets(lines.slice(i + 1, end).join('\n'));
      pre.append(code);
      out.append(pre);
      i = end + 1;
    } else if ((match = line.match(HEADING))) {
      const h = document.createElement(`h${Math.min(match[1].length + (options.shiftHeadings || 0), 6)}`);
      h.append(...inline(match[2], options));
      out.append(h);
      i += 1;
    } else if (RULE.test(line)) {
      out.append(document.createElement('hr'));
      i += 1;
    } else if (QUOTE.test(line)) {
      const quoted = [];
      for (; i < lines.length && (match = lines[i].match(QUOTE)); i += 1) quoted.push(match[1]);
      const q = document.createElement('blockquote');
      q.append(blocks(quoted, options));
      out.append(q);
    } else if (line.includes('|') && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
      const [node, next] = table(lines, i, options);
      out.append(node);
      i = next;
    } else if (ITEM.test(line)) {
      const [node, next] = list(lines, i, options);
      out.append(node);
      i = next;
    } else {
      const para = [];
      for (; i < lines.length && !isBlank(lines[i]) && (para.length === 0 || !startsBlock(lines, i)); i += 1) para.push(lines[i].trim());
      const p = document.createElement('p');
      p.append(...inline(para.join('\n'), options));
      out.append(p);
    }
  }
  return out;
}

/* Render Markdown into a new <div class="md">. options.resolveImage(src, alt) may return an <img> for allowed files. */
export function renderMarkdown(text, options = {}) {
  const root = document.createElement('div');
  root.className = 'md';
  root.append(blocks(String(text ?? '').replace(/\r\n?/g, '\n').split('\n'), options));
  return root;
}
