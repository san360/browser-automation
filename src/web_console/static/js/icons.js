/* Small stroke icons (24×24 grid, drawn for this console), created with DOM APIs. */

const SVG = 'http://www.w3.org/2000/svg';
const ICONS = {
  info: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M12 11v6M12 7.5v.5' }]],
  action: [['path', { d: 'M5 3l13 7-6 1.5L9.5 18z' }], ['path', { d: 'M12.5 12.5L18 18' }]],
  tool: [['path', { d: 'M14.5 6.5a4 4 0 0 0-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2.5-.5-.5-2.5z' }]],
  message: [['path', { d: 'M4 5h16v11H9l-5 4z' }], ['path', { d: 'M8 9.5h8M8 12.5h5' }]],
  usage: [['path', { d: 'M5 20V11M12 20V5M19 20v-6' }]],
  screenshot: [['path', { d: 'M4 8h3l2-3h6l2 3h3v11H4z' }], ['circle', { cx: 12, cy: 13, r: 3.5 }]],
  warning: [['path', { d: 'M12 4l9 16H3z' }], ['path', { d: 'M12 10v4.5M12 17v.5' }]],
  error: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M9 9l6 6M15 9l-6 6' }]],
  live: [['circle', { cx: 12, cy: 12, r: 3, fill: 'currentColor' }], ['path', { d: 'M7 7a7 7 0 0 0 0 10M17 7a7 7 0 0 1 0 10M4.5 4.5a10.5 10.5 0 0 0 0 15M19.5 4.5a10.5 10.5 0 0 1 0 15' }]],
  check: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M8 12.5l3 3 5-6' }]],
  cross: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M9 9l6 6M15 9l-6 6' }]],
  minus: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M8 12h8' }]],
  safety: [['path', { d: 'M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z' }], ['path', { d: 'M9 12l2 2 4-4' }]],
  play: [['path', { d: 'M8 5l11 7-11 7z' }]],
  stop: [['rect', { x: 6, y: 6, width: 12, height: 12, rx: 2 }]],
  copy: [['rect', { x: 8, y: 8, width: 12, height: 12, rx: 2 }], ['path', { d: 'M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3' }]],
  external: [['path', { d: 'M14 4h6v6M20 4l-9 9' }], ['path', { d: 'M18 14v5H5V6h5' }]],
  refresh: [['path', { d: 'M20 12a8 8 0 1 1-2.3-5.6' }], ['path', { d: 'M20 4v5h-5' }]],
  search: [['circle', { cx: 11, cy: 11, r: 6.5 }], ['path', { d: 'M16 16l4.5 4.5' }]],
  sun: [['circle', { cx: 12, cy: 12, r: 4 }], ['path', { d: 'M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4' }]],
  moon: [['path', { d: 'M19 14.5A8 8 0 0 1 9.5 5a8 8 0 1 0 9.5 9.5z' }]],
  clock: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M12 7v5l3 2' }]],
  globe: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18' }]],
  cloud: [['path', { d: 'M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z' }]],
  hosted: [['rect', { x: 4, y: 4, width: 16, height: 6, rx: 1.5 }], ['rect', { x: 4, y: 14, width: 16, height: 6, rx: 1.5 }], ['path', { d: 'M8 7h.5M8 17h.5' }]],
  laptop: [['rect', { x: 5, y: 5, width: 14, height: 10, rx: 1.5 }], ['path', { d: 'M3 19h18' }]],
  eye: [['path', { d: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z' }], ['circle', { cx: 12, cy: 12, r: 3 }]],
  cursor: [['path', { d: 'M6 3l12 9-5.5 1L10 19z' }]],
  folder: [['path', { d: 'M3 6h6l2 2h10v11H3z' }]],
  list: [['path', { d: 'M9 6h11M9 12h11M9 18h11M4.5 6h.5M4.5 12h.5M4.5 18h.5' }]],
  dollar: [['path', { d: 'M12 3v18M16.5 7.5c0-1.7-2-3-4.5-3s-4.5 1.3-4.5 3S9.5 10.5 12 11s4.5 1.3 4.5 3.5-2 3-4.5 3-4.5-1.3-4.5-3' }]],
  key: [['circle', { cx: 8, cy: 15, r: 4 }], ['path', { d: 'M11 12l8-8M16 7l2 2' }]],
  beaker: [['path', { d: 'M9 3h6M10 3v6l-5 10h14l-5-10V3' }], ['path', { d: 'M7.5 14h9' }]],
  compare: [['rect', { x: 3, y: 5, width: 7.5, height: 14, rx: 1.5 }], ['rect', { x: 13.5, y: 5, width: 7.5, height: 14, rx: 1.5 }]],
  shield: [['path', { d: 'M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z' }]],
  lock: [['rect', { x: 5, y: 11, width: 14, height: 9, rx: 2 }], ['path', { d: 'M8 11V8a4 4 0 0 1 8 0v3' }]],
  chevron: [['path', { d: 'M9 6l6 6-6 6' }]],
  close: [['path', { d: 'M6 6l12 12M18 6L6 18' }]],
};

export const MODE_ICONS = { prompt: 'cloud', hosted: 'hosted', local: 'laptop', cua: 'eye' };
export const KIND_ICONS = {
  info: 'info', action: 'action', tool: 'tool', message: 'message', usage: 'usage', screenshot: 'screenshot',
  warning: 'warning', error: 'error', live_view: 'live', check: 'check', safety: 'safety',
};

export function icon(name, className = '') {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  if (className) svg.setAttribute('class', className);
  for (const [tag, attrs] of ICONS[name] || ICONS.info) {
    const part = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attrs)) part.setAttribute(key, String(value));
    svg.appendChild(part);
  }
  return svg;
}
