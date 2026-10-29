/* A large "screen" with the latest image, a caption and a filmstrip of earlier images. New images follow live unless
   the presenter pins an earlier one by clicking its thumbnail. Clicking the screen opens the image full size. */
import { $, clear, el } from './dom.js';

let lightboxReady = false;

export function openLightbox(src, title) {
  const dialog = $('#lightbox');
  if (!dialog) return;
  if (!lightboxReady) {
    $('#lightbox-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
    lightboxReady = true;
  }
  $('#lightbox-image').src = src;
  $('#lightbox-image').alt = title || 'Screenshot';
  $('#lightbox-title').textContent = title || 'Screenshot';
  if (!dialog.open) dialog.showModal();
}

export function createScreen(container, { empty = 'No screenshot yet.', label = 'Screenshot', badge = null } = {}) {
  const items = [];
  let pinned = null;
  const image = el('img', { alt: '', hidden: true });
  const placeholder = el('div', { class: 'screen-empty' }, empty);
  const screen = el('div', { class: 'screen' }, image, placeholder);
  if (badge) screen.append(el('span', { class: 'screen-badge' }, badge));
  const caption = el('div', { class: 'screen-caption' }, el('span', {}, ''), el('span', {}, ''));
  const strip = el('div', { class: 'filmstrip', role: 'list', 'aria-label': `${label} history` });
  clear(container).append(screen, caption, strip);

  image.addEventListener('click', () => {
    const item = pinned ?? items[items.length - 1];
    if (item) openLightbox(item.src, item.caption || label);
  });
  image.addEventListener('error', () => { image.hidden = true; placeholder.hidden = false; placeholder.textContent = 'Image no longer available.'; });

  function show(item) {
    image.hidden = false;
    placeholder.hidden = true;
    if (image.getAttribute('src') !== item.src) image.src = item.src;
    image.alt = item.caption || label;
    caption.firstChild.textContent = item.caption || '';
    caption.lastChild.textContent = item.meta || '';
    for (const button of strip.children) button.setAttribute('aria-current', String(button.dataset.src === item.src));
  }

  return {
    add(item) {
      items.push(item);
      const thumb = el('button', { type: 'button', role: 'listitem', title: item.caption || label, dataset: { src: item.src } },
        el('img', { src: item.src, alt: item.caption || label, loading: 'lazy' }));
      thumb.addEventListener('click', () => {
        pinned = pinned === item ? null : item;
        show(pinned ?? items[items.length - 1]);
      });
      thumb.querySelector('img').addEventListener('error', () => thumb.remove());
      strip.append(thumb);
      if (strip.children.length > 40) strip.firstElementChild.remove();
      if (!pinned) {
        show(item);
        strip.scrollLeft = strip.scrollWidth;
      }
    },
    count: () => items.length,
    setEmpty(text) { if (!items.length) placeholder.textContent = text; },
  };
}
