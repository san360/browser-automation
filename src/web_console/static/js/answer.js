/* The run's answer (streamed, then rendered as safe Markdown), its metrics, automatic checks and artifacts. */
import { $, clear, copyText, el, maskSecrets } from './dom.js';
import { icon } from './icons.js';
import { renderMarkdown } from './markdown.js';
import { checksTone, fmtCost, fmtDuration, fmtInt, statusTone } from './format.js';

let answerText = '';

export function initAnswer() {
  $('#answer-copy').addEventListener('click', () => { if (answerText) copyText(answerText, 'Answer copied'); });
}

export function resetAnswer(message = 'The answer streams here as the agent writes it.') {
  answerText = '';
  clear($('#answer')).append(el('p', { class: 'placeholder' }, message));
  $('#answer-copy').disabled = true;
  $('#checks-card').hidden = true;
  clear($('#run-metrics'));
  clear($('#artifacts'));
}

export function showStreaming(text) {
  const box = $('#answer');
  let node = box.querySelector('.streaming');
  if (!node) {
    clear(box);
    node = el('div', { class: 'streaming', 'aria-live': 'off' });
    box.append(node);
  }
  node.textContent = maskSecrets(text);
}

function metric(label, value, sub, tone = '') {
  return el('div', { class: `metric ${tone}` }, el('span', {}, label), el('strong', { title: String(value) }, value), sub ? el('small', {}, sub) : null);
}

export function metricsFor(r) {
  const checks = r.checks_total ? `${r.checks_passed}/${r.checks_total}` : '–';
  const browser = r.est_browser_minutes ? `${r.est_browser_minutes} browser min` : 'no browser minutes';
  return [
    metric('Status', r.status, r.error ? 'see the error below' : r.model, statusTone(r.status) === 'ok' ? 'ok' : statusTone(r.status)),
    metric('Duration', fmtDuration(r.duration_s), `${fmtInt(r.tool_calls)} tool calls`),
    metric('Tokens in / out', `${fmtInt(r.input_tokens)} / ${fmtInt(r.output_tokens)}`, `${fmtInt(r.cached_tokens)} cached`),
    metric('Checks', checks, r.answer_key_recall !== null && r.answer_key_recall !== undefined
      ? `answer key ${Math.round(r.answer_key_recall * 100)}%` : 'automatic checks', checksTone(r.checks_passed, r.checks_total) === 'ok' ? 'ok'
      : r.checks_total ? 'warn' : ''),
    metric('Est. cost', fmtCost(r.est_cost, r.currency), browser),
  ];
}

function checkItem(passed, title, detail) {
  return el('li', {}, icon(passed ? 'check' : 'cross', `check-icon ${passed ? 'ok' : 'err'}`),
    el('div', {}, title, detail ? el('span', { class: 'detail' }, maskSecrets(detail)) : null));
}

export function renderChecks(r, list, badge, keyHost) {
  clear(list).append(...(r.checks || []).map((c) => checkItem(c.passed, c.name, c.detail)));
  if (!(r.checks || []).length) list.append(el('li', {}, icon('minus', 'check-icon optional'), el('div', {}, 'This scenario has no automatic checks.')));
  badge.className = `badge ${checksTone(r.checks_passed, r.checks_total)}`;
  badge.textContent = r.checks_total ? `${r.checks_passed}/${r.checks_total} passed` : 'none';
  clear(keyHost);
  if (r.answer_key) {
    const k = r.answer_key;
    keyHost.append(el('h3', { class: 'small' }, `Answer key (heuristic): ${k.found} of ${k.total} planted issues reported`),
      el('ul', { class: 'check-list' }, k.items.map((item) => checkItem(item.reported, `${item.id} · ${item.title}`))));
  }
}

export function showResult(result, error) {
  const box = clear($('#answer'));
  if (!result) {
    box.append(el('div', { class: 'callout err' }, icon('error'), el('div', {}, maskSecrets(error || 'The run failed before it produced a result.'))));
    return;
  }
  answerText = result.final_text || '';
  box.append(answerText ? renderMarkdown(answerText) : el('p', { class: 'placeholder' }, 'No answer.'));
  if (result.error) box.append(el('div', { class: 'callout err' }, icon('error'), el('div', {}, maskSecrets(result.error))));
  $('#answer-copy').disabled = !answerText;
  clear($('#run-metrics')).append(...metricsFor(result));
  renderChecks(result, $('#checks-list'), $('#checks-badge'), $('#answer-key'));
  $('#checks-card').hidden = false;
  const artifacts = clear($('#artifacts'));
  if (result.folder) {
    const copy = el('button', { type: 'button', class: 'copy-inline', title: 'Copy the folder path', 'aria-label': 'Copy the folder path' }, icon('copy'));
    copy.addEventListener('click', () => copyText(result.run_path || `runs/${result.folder}`, 'Folder path copied'));
    artifacts.append(icon('folder'), 'Artifacts:', el('code', { title: result.run_path || '' }, `runs/${result.folder}/`), copy,
      el('a', { href: `#/history/${encodeURIComponent(result.folder)}` }, 'Open the report →'));
    if (result.cost_detail) artifacts.append(el('span', { class: 'fine-print' }, `Cost: ${result.cost_detail}`));
  }
}
