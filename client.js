/* Herbarium Sheet: the plants in flower around the panel, as a sheet of pressed
   specimens. The server hands over the species with their pictures, dates and
   credits; this file draws the paper, the mounts with their tape, the label
   slips, the institutional label block and the stamp.

   The page is the cell: paper edge to edge, no shell. Structure changes by
   size class (sm: one specimen and a two-line label), everything else scales
   with clamp() from cqmin. */

const esc = (s) =>
  String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const PAPER = { cream: '#f3ead6', white: '#ffffff', aged: '#e8d9b8' };

/* A rubber stamp: two rings, the place round the top, HERBARIUM round the
   bottom, a leaf in the middle. Drawn in SVG so it scales and dithers as line
   work rather than as a raster. */
function stampSvg(place, word) {
  const top = (place || '').toUpperCase();
  const bottom = (word || 'HERBARIUM').toUpperCase();
  return `<svg class="stamp" viewBox="0 0 200 200" aria-hidden="true">
    <defs>
      <path id="hs-arc-t" d="M 32 100 A 68 68 0 0 1 168 100"/>
      <path id="hs-arc-b" d="M 32 100 A 68 68 0 0 0 168 100"/>
    </defs>
    <circle cx="100" cy="100" r="94" fill="none" stroke="currentColor" stroke-width="5"/>
    <circle cx="100" cy="100" r="84" fill="none" stroke="currentColor" stroke-width="1.6"/>
    <circle cx="100" cy="100" r="48" fill="none" stroke="currentColor" stroke-width="1.6"/>
    <text class="stamp-t" font-size="${top.length > 14 ? 15 : 19}"><textPath href="#hs-arc-t" startOffset="50%" text-anchor="middle">${esc(top)}</textPath></text>
    <text class="stamp-t" font-size="${bottom.length > 14 ? 15 : 19}"><textPath href="#hs-arc-b" startOffset="50%" text-anchor="middle">${esc(bottom)}</textPath></text>
    <circle cx="24" cy="100" r="2.6" fill="currentColor"/><circle cx="176" cy="100" r="2.6" fill="currentColor"/>
    <g transform="translate(100 100)">
      <path d="M0 -30 C 20 -22 26 2 16 22 C 8 36 -8 36 -16 22 C -26 2 -20 -22 0 -30 Z" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linejoin="round"/>
      <path d="M0 -24 L0 32" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
      <path d="M0 -8 L10 -16 M0 4 L-10 -4 M0 16 L10 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/>
    </g>
  </svg>`;
}

function picHtml(s, d, i) {
  const painted = s.state === 'painted' && s.pic;
  const src = painted ? s.pic : s.photo;
  const blue = painted && d.blue;
  const kind = !src ? 'none' : painted ? (blue ? 'paint blue' : 'paint') : 'oval';
  const tilt = i % 2 ? 'alt' : '';
  const img = src ? `<img src="${esc(src)}" alt="" decoding="sync">` : '';
  return `<div class="pic"><div class="pic-box ${kind} ${tilt}"${blue ? ` style="--blue:${esc(d.blue)}"` : ''}>${img}<span class="tape tape-t"></span><span class="tape tape-b"></span></div></div>`;
}

function slipHtml(s, d) {
  const bits = [];
  if (s.latest_text) bits.push(`Latest ${esc(s.latest_text)}`);
  if (s.count) bits.push(`${esc(s.count)} record${s.count === 1 ? '' : 's'}`);
  const pend = s.state === 'painting' || s.state === 'waiting' ? '<span class="pend">painting</span>' : '';
  return `<figcaption class="slip">
    <span class="nm">${esc(s.common)}</span>
    <span class="sci">${esc(s.sci)}</span>
    ${bits.length ? `<span class="meta">${bits.join(' · ')}${pend}</span>` : pend}
  </figcaption>`;
}

function creditsText(d) {
  const rows = d.species || [];
  const painted = rows.filter((s) => s.state === 'painted' && s.credit);
  const photos = rows.filter((s) => !(s.state === 'painted' && s.pic) && s.photo);
  const who = (s) => `${s.by || 'an observer'}${s.licence ? ` (${s.licence})` : ''}`;
  const parts = [];
  if (painted.length) {
    const model = painted[0].credit.replace(/^AI painting \(([^)]*)\).*$/, '$1');
    parts.push(`AI painting${painted.length === 1 ? '' : 's'} (${model}) from ${painted.length === 1 ? 'a photo' : 'photos'} by ${painted.map(who).join(', ')}`);
  }
  if (photos.length) parts.push(`Photograph${photos.length === 1 ? '' : 's'} by ${photos.map(who).join(', ')}`);
  if (parts.length) parts[parts.length - 1] += ' · iNaturalist';
  return parts.concat(d.notes || []).join('. ');
}

function blockHtml(d) {
  return `<div class="block">
    <div class="b1">${esc(d.title)} · ${esc(d.head)}</div>
    <div class="bl">${esc(d.where)}</div>
    <div class="bl">${esc(d.month)}</div>
    <div class="bl">Accession No. ${esc(d.accession)}</div>
  </div>`;
}

function footHtml(d) {
  const credits = d.credits !== false ? creditsText(d) : (d.notes || []).join('. ');
  return `<div class="foot">
    <div class="credits">${esc(credits)}</div>
    <div class="seal">${stampSvg(d.head, d.title === 'HERBARIUM' ? 'Herbarium' : d.title)}${blockHtml(d)}</div>
  </div>`;
}

function emptyHtml(d) {
  const where = d.where ? d.where.replace(/^Collected /, '') : '';
  const when = d.window === 'month' ? 'this month' : d.window === '30d' ? 'in the last 30 days' : 'in the last 90 days';
  return `<div class="empty">
    <div class="empty-ring"></div>
    <div class="empty-t">No plants recorded ${esc(where)} ${esc(when)}</div>
    <div class="empty-s">Research-grade iNaturalist records with an openly licensed photo</div>
  </div>`;
}

function errorHtml(msg) {
  return `<link rel="stylesheet" href="/static/icons/phosphor/bold/style.css">
    <div class="err"><i class="ph-bold ph-warning-circle" aria-hidden="true"></i><div class="err-t">${esc(msg)}</div></div>`;
}

export default async function render(shadow, ctx) {
  const d = (ctx && ctx.data) || {};
  const size = (ctx && ctx.cell && ctx.cell.size) || 'md';
  const paper = PAPER[d.paper] || PAPER.cream;
  const panel = d.panel || 'colour';
  const layout = d.layout === 'plate' ? 'plate' : 'mounted';
  const rows = Array.isArray(d.species) ? d.species : [];
  const shown = size === 'sm' || layout === 'plate' ? rows.slice(0, 1) : rows;
  const n = shown.length;

  let body;
  if (d.error) {
    body = errorHtml(d.error);
  } else if (!n) {
    body = `<div class="mount n0">${emptyHtml(d)}</div>${size === 'sm' ? '' : footHtml(d)}`;
  } else {
    const specs = shown.map((s, i) => `<figure class="spec">${picHtml(s, d, i)}${slipHtml(s, d)}</figure>`).join('');
    body = `<div class="mount n${n}">${specs}</div>${size === 'sm' ? '' : footHtml(d)}`;
  }

  shadow.innerHTML = `
    <link rel="stylesheet" href="/plugins/herbarium_sheet/client.css">
    <div class="hs size-${esc(size)} lv-${esc(panel)} lay-${layout} n${n}" style="--paper:${paper}">${body}</div>`;
}
