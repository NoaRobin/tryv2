// graphes-tarif.js — les figures du simulateur, en SVG natif.
//
// Elles se redessinent à chaque frappe dans la grille : ni Plotly ni délai.
// Une seule teinte, ses tons ; l'issue d'une offre se lit par la FORME
// (plein = gagnée, creux = perdue, moitié = en cours), jamais par le ton seul.

import * as T from './tarif.js';
import { NBSP, entier, decimal } from './format.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const MOINS = '−';

function s(tag, attrs = {}, ...enfants) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, String(v));
  }
  for (const e of enfants.flat()) if (e !== null && e !== undefined) el.append(e instanceof Node ? e : document.createTextNode(String(e)));
  return el;
}

function div(classe, texte) {
  const el = document.createElement('div');
  if (classe) el.className = classe;
  if (texte !== undefined) el.textContent = texte;
  return el;
}

/* ------------------------------------------------------------ formats --- */

/** 0,12 % · 0,093 % · 0,105 % : au dixième de point de base, sans zéro superflu. */
export function fmtTaux(x, { unite = true } = {}) {
  if (x === null || x === undefined || !Number.isFinite(x)) return '—';
  let t = x.toFixed(3);
  if (t.endsWith('0')) t = x.toFixed(2);
  t = t.replace('.', ',').replace('-', MOINS);
  return unite ? `${t}${NBSP}%` : t;
}

/** Un écart de taux en points de base : « −2,7 pb ». */
export function fmtPb(ecartPct) {
  if (ecartPct === null || ecartPct === undefined || !Number.isFinite(ecartPct)) return '—';
  const pb = ecartPct * 100;
  const signe = pb > 0.05 ? '+' : (pb < -0.05 ? MOINS : '');
  return `${signe}${decimal(Math.abs(pb), 1)}${NBSP}pb`;
}

/** Des frais annuels en M€ : « 140 k€ » sous le million, « 1,25 M€ » au-delà. */
export function fmtFrais(m) {
  if (m === null || m === undefined || !Number.isFinite(m)) return '—';
  return Math.abs(m) < 1 ? `${entier(m * 1000)}${NBSP}k€` : `${decimal(m, 2)}${NBSP}M€`;
}

/** Un écart de frais signé, au vrai signe moins : « −28 k€ », « +12 k€ ». */
export function fmtEcartFrais(m) {
  if (m === null || m === undefined || !Number.isFinite(m)) return '—';
  const signe = m > 0.0005 ? '+' : (m < -0.0005 ? MOINS : '');
  return `${signe}${fmtFrais(Math.abs(m))}`;
}

export function fmtM(x) {
  if (x === null || x === undefined || !Number.isFinite(x)) return '—';
  return `${entier(x)}${NBSP}M€`;
}

/** Le rang d'une offre en toutes lettres : « 38e centile ». */
export function fmtCentile(c) {
  if (!Number.isFinite(c)) return '—';
  const n = Math.round(c);
  return `${n === 1 ? '1er' : `${n}e`} centile`;
}

/* ------------------------------------------------------------ échelles --- */

function pasJoli(etendue, n) {
  const brut = etendue / Math.max(1, n);
  const p = 10 ** Math.floor(Math.log10(brut));
  for (const m of [1, 2, 2.5, 5, 10]) if (brut <= m * p) return m * p;
  return 10 * p;
}

export function plafondJoli(max, n = 5) {
  if (!(max > 0)) return 1;
  const pas = pasJoli(max, n);
  return Math.ceil(max / pas) * pas;
}

function graduations(max, n = 5) {
  const pas = pasJoli(max, n);
  const out = [];
  for (let v = 0; v <= max + pas * 1e-6; v += pas) out.push(+v.toFixed(10));
  return out;
}

/* --------------------------------------------------- marques d'une issue --- */

/** Carré plein (gagnée), creux (perdue), à moitié (en cours) ; anneau de surface. */
function marque(issue, x, y, taille = 9, attrs = {}) {
  const d = taille / 2;
  const g = s('g', { class: 'marque-offre', ...attrs });
  g.append(s('rect', { x: x - d - 2, y: y - d - 2, width: taille + 4, height: taille + 4, fill: 'var(--blanc)' }));
  if (issue === 'Gagné') {
    g.append(s('rect', { x: x - d, y: y - d, width: taille, height: taille, fill: 'var(--b-100)' }));
  } else if (issue === 'En cours') {
    g.append(s('rect', { x: x - d + 0.75, y: y - d + 0.75, width: taille - 1.5, height: taille - 1.5,
      fill: 'var(--blanc)', stroke: 'var(--b-72)', 'stroke-width': 1.5 }));
    g.append(s('rect', { x: x - d + 0.75, y: y - d + 0.75, width: (taille - 1.5) / 2, height: taille - 1.5,
      fill: 'var(--b-72)' }));
  } else {
    g.append(s('rect', { x: x - d + 0.75, y: y - d + 0.75, width: taille - 1.5, height: taille - 1.5,
      fill: 'var(--blanc)', stroke: 'var(--b-72)', 'stroke-width': 1.5 }));
  }
  return g;
}

export function legendeIssues() {
  const l = div('legende-tarif');
  for (const [issue, texte] of [['Gagné', 'offre gagnée'], ['Perdu', 'offre perdue'], ['En cours', 'en cours']]) {
    const item = div('legende-tarif__item');
    const svg = s('svg', { width: 14, height: 14, viewBox: '0 0 14 14', 'aria-hidden': 'true' }, marque(issue, 7, 7, 9));
    item.append(svg, document.createTextNode(texte));
    l.append(item);
  }
  return l;
}

/* ----------------------------------------------------------- info-bulle --- */

function infobulle(hote) {
  const b = div('infobulle');
  b.hidden = true;
  hote.append(b);
  return {
    montrer(lignes, x, y) {
      b.replaceChildren(...lignes.map((l, i) => {
        const p = div(i === 0 ? 'infobulle__titre' : 'infobulle__ligne');
        if (Array.isArray(l)) { p.append(div('infobulle__c', l[0]), div('infobulle__v', l[1])); } else p.textContent = l;
        return p;
      }));
      b.hidden = false;
      const lh = hote.clientWidth;
      const bw = b.offsetWidth;
      const gauche = x + 14 + bw > lh ? x - 14 - bw : x + 14;
      b.style.left = `${Math.max(0, gauche)}px`;
      b.style.top = `${Math.max(0, y - 10)}px`;
    },
    cacher() { b.hidden = true; },
  };
}

/* ======================================================================= */
/*  La courbe : taux moyen selon la taille du mandat                       */
/* ======================================================================= */
/**
 * La grille simulée contre ce qui a déjà été fait : fourchette min–max et
 * écart interquartile des offres passées, leur médiane, leur moyenne (la
 * mesure d'origine), et chaque offre à son propre encours.
 */
export function courbeTarif(options) {
  const hote = div('figure-tarif');
  const bulle = infobulle(hote);
  const svg = s('svg', { class: 'figure-tarif__svg', role: 'img' });
  hote.prepend(svg);
  let courant = null;

  function dessiner(o) {
    courant = o;
    const L = o.largeur || 660; const H = o.hauteur || 300;
    const m = { g: 52, d: o.compact ? 16 : 118, h: 14, b: 40 };
    const lp = L - m.g - m.d; const hp = H - m.h - m.b;
    svg.setAttribute('viewBox', `0 0 ${L} ${H}`);
    svg.setAttribute('aria-label', o.titre || 'Taux moyen selon la taille du mandat');
    svg.replaceChildren();

    const xMax = o.xMax;
    const n = 140;
    const xs = Array.from({ length: n + 1 }, (_, i) => Math.max(xMax / 400, (xMax * i) / n));
    const stats = xs.map(x => T.resume(o.eligibles.map(g => T.tauxMoyen(g.tranches, x))));
    const moi = o.grille ? xs.map(x => T.tauxMoyen(o.grille, x)) : [];
    const pts = (o.points || []).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y) && p.x <= xMax);
    let yHaut = 0;
    for (const st of stats) if (st.n) yHaut = Math.max(yHaut, st.max);
    for (const v of moi) if (Number.isFinite(v)) yHaut = Math.max(yHaut, v);
    for (const p of pts) yHaut = Math.max(yHaut, p.y);
    const yMax = plafondJoli(yHaut * 1.08 || 0.2, 5);
    const X = (v) => m.g + (v / xMax) * lp;
    const Y = (v) => m.h + hp - (v / yMax) * hp;

    // Grille et axes : filets pleins, un ton au-dessus de la surface.
    const fond = s('g', { class: 'axes' });
    for (const t of graduations(yMax, 5)) {
      fond.append(s('line', { x1: m.g, x2: m.g + lp, y1: Y(t), y2: Y(t), stroke: 'var(--b-6)', 'stroke-width': 1 }));
      fond.append(s('text', { x: m.g - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'graduation' }, fmtTaux(t)));
    }
    for (const t of graduations(xMax, o.compact ? 4 : 6)) {
      fond.append(s('text', { x: X(t), y: m.h + hp + 18, 'text-anchor': 'middle', class: 'graduation' }, entier(t)));
    }
    fond.append(s('line', { x1: m.g, x2: m.g + lp, y1: m.h + hp, y2: m.h + hp, stroke: 'var(--b-22)', 'stroke-width': 1 }));
    fond.append(s('text', { x: m.g + lp, y: H - 4, 'text-anchor': 'end', class: 'titre-axe' }, 'Taille du mandat (M€)'));
    svg.append(fond);

    // Fourchettes : min–max en ton clair, écart interquartile en ton moyen.
    const aire = (haut, bas) => {
      let d = '';
      xs.forEach((x, i) => { if (stats[i].n) d += `${d ? 'L' : 'M'}${X(x).toFixed(1)},${Y(haut(stats[i])).toFixed(1)}`; });
      for (let i = xs.length - 1; i >= 0; i--) if (stats[i].n) d += `L${X(xs[i]).toFixed(1)},${Y(bas(stats[i])).toFixed(1)}`;
      return d ? `${d}Z` : '';
    };
    const ligne = (vals) => {
      let d = '';
      xs.forEach((x, i) => { const v = vals[i]; if (Number.isFinite(v)) d += `${d ? 'L' : 'M'}${X(x).toFixed(1)},${Y(v).toFixed(1)}`; });
      return d;
    };
    const avecHistoire = stats.some(st => st.n);
    if (avecHistoire) {
      svg.append(s('path', { d: aire(st => st.max, st => st.min), fill: 'var(--b-6)' }));
      if (o.eligibles.length >= 3) svg.append(s('path', { d: aire(st => st.p75, st => st.p25), fill: 'var(--b-12)' }));
      svg.append(s('path', { d: ligne(stats.map(st => st.mediane)), fill: 'none', stroke: 'var(--b-52)', 'stroke-width': 1.5 }));
      if (!o.compact) {
        svg.append(s('path', { d: ligne(stats.map(st => st.moyenne)), fill: 'none', stroke: 'var(--b-52)',
          'stroke-width': 1, 'stroke-dasharray': '1.5 3', 'stroke-linecap': 'round' }));
      }
    }

    // Repère de l'encours visé.
    if (Number.isFinite(o.encours) && o.encours <= xMax) {
      svg.append(s('line', { x1: X(o.encours), x2: X(o.encours), y1: m.h, y2: m.h + hp,
        stroke: 'var(--b-36)', 'stroke-width': 1 }));
      svg.append(s('text', { x: X(o.encours), y: m.h + 10, 'text-anchor': X(o.encours) > m.g + lp - 60 ? 'end' : 'start',
        dx: X(o.encours) > m.g + lp - 60 ? -6 : 6, class: 'etiquette-repere' }, `${entier(o.encours)} M€`));
    }

    // La grille simulée, trait plein et épais : c'est elle qu'on lit.
    if (moi.length) {
      svg.append(s('path', { d: ligne(moi), fill: 'none', stroke: 'var(--b-100)', 'stroke-width': 2.5,
        'stroke-linejoin': 'round' }));
      if (Number.isFinite(o.encours) && o.encours <= xMax) {
        const yv = T.tauxMoyen(o.grille, o.encours);
        svg.append(s('circle', { cx: X(o.encours), cy: Y(yv), r: 6, fill: 'var(--blanc)' }));
        svg.append(s('circle', { cx: X(o.encours), cy: Y(yv), r: 4.5, fill: 'var(--b-100)' }));
      }
    }

    // Étiquettes directes en bout de courbe, écartées si elles se touchent.
    if (!o.compact) {
      const fin = [];
      if (moi.length) fin.push({ y: Y(moi[moi.length - 1]), t: o.libelleGrille || 'Votre grille', c: 'etiquette-fin etiquette-fin--forte' });
      const der = stats[stats.length - 1];
      if (der.n) fin.push({ y: Y(der.mediane), t: `Médiane ${o.libelleExpertise || ''}`.trim(), c: 'etiquette-fin' });
      fin.sort((a, b) => a.y - b.y);
      for (let i = 1; i < fin.length; i++) if (fin[i].y - fin[i - 1].y < 14) fin[i].y = fin[i - 1].y + 14;
      for (const e of fin) svg.append(s('text', { x: m.g + lp + 8, y: e.y + 4, class: e.c }, e.t));
    }

    // Réticule et info-bulle sur toute la surface du tracé.
    const reticule = s('line', { y1: m.h, y2: m.h + hp, stroke: 'var(--b-72)', 'stroke-width': 1, visibility: 'hidden' });
    const pointMoi = s('circle', { r: 4, fill: 'var(--b-100)', stroke: 'var(--blanc)', 'stroke-width': 2, visibility: 'hidden' });
    const pointMed = s('circle', { r: 3.5, fill: 'var(--b-52)', stroke: 'var(--blanc)', 'stroke-width': 2, visibility: 'hidden' });
    svg.append(reticule, pointMoi, pointMed);
    const capte = s('rect', { x: m.g, y: m.h, width: lp, height: hp, fill: 'transparent' });
    const echelle = () => svg.getBoundingClientRect().width / L;
    capte.addEventListener('pointermove', (e) => {
      const r = svg.getBoundingClientRect();
      const px = (e.clientX - r.left) / echelle();
      const i = Math.max(0, Math.min(n, Math.round(((px - m.g) / lp) * n)));
      const x = xs[i]; const st = stats[i];
      reticule.setAttribute('x1', X(x)); reticule.setAttribute('x2', X(x)); reticule.setAttribute('visibility', 'visible');
      const lignes = [`À ${entier(x)} M€`];
      if (moi.length) {
        lignes.push([o.libelleGrille || 'Votre grille', fmtTaux(moi[i])]);
        pointMoi.setAttribute('cx', X(x)); pointMoi.setAttribute('cy', Y(moi[i])); pointMoi.setAttribute('visibility', 'visible');
      }
      if (st.n) {
        lignes.push(['Médiane', fmtTaux(st.mediane)], ['Moyenne', fmtTaux(st.moyenne)],
          ['Fourchette', `${fmtTaux(st.min, { unite: false })} – ${fmtTaux(st.max)}`],
          ['Offres comparées', entier(st.n)]);
        pointMed.setAttribute('cx', X(x)); pointMed.setAttribute('cy', Y(st.mediane)); pointMed.setAttribute('visibility', 'visible');
      }
      bulle.montrer(lignes, X(x) * echelle(), Y(moi.length ? moi[i] : st.mediane) * echelle());
    });
    capte.addEventListener('pointerleave', () => {
      bulle.cacher();
      for (const el of [reticule, pointMoi, pointMed]) el.setAttribute('visibility', 'hidden');
    });
    svg.append(capte);

    // Les offres passées, chacune à son propre encours : cliquables.
    for (const p of pts) {
      const g = marque(p.issue, X(p.x), Y(p.y), 9, { tabindex: o.surPoint ? 0 : null, role: o.surPoint ? 'button' : null,
        'aria-label': o.surPoint ? `${p.titre} : ${fmtTaux(p.y)} à ${entier(p.x)} M€` : null });
      g.append(s('circle', { cx: X(p.x), cy: Y(p.y), r: 12, fill: 'transparent' }));
      if (p.fort) g.append(s('rect', { x: X(p.x) - 9, y: Y(p.y) - 9, width: 18, height: 18, fill: 'none', stroke: 'var(--b-100)', 'stroke-width': 1.5 }));
      g.addEventListener('pointerenter', () => bulle.montrer([p.titre, ['Encours', `${entier(p.x)} M€`],
        ['Taux moyen', fmtTaux(p.y)], ['Issue', p.issue]], X(p.x) * echelle(), Y(p.y) * echelle()));
      g.addEventListener('pointerleave', () => bulle.cacher());
      if (o.surPoint) {
        g.style.cursor = 'pointer';
        g.addEventListener('click', () => o.surPoint(p));
        g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); o.surPoint(p); } });
      }
      svg.append(g);
    }
  }

  dessiner(options);
  return { el: hote, maj: (o) => dessiner({ ...courant, ...o }) };
}

/* ======================================================================= */
/*  Le prix dans le marché : où tombe la grille, à la taille du mandat     */
/* ======================================================================= */
/**
 * Chaque offre passée est appliquée à l'encours visé : c'est le prix qu'elle
 * aurait donné à CE client. La grille simulée se lit contre ce nuage.
 */
export function jaugeMarche(options) {
  const hote = div('figure-tarif');
  const bulle = infobulle(hote);
  const svg = s('svg', { class: 'figure-tarif__svg', role: 'img' });
  hote.prepend(svg);
  let courant = null;

  function dessiner(o) {
    courant = o;
    const L = o.largeur || 660; const H = 150;
    const m = { g: 16, d: 16 };
    const lp = L - m.g - m.d;
    svg.setAttribute('viewBox', `0 0 ${L} ${H}`);
    svg.setAttribute('aria-label', 'Position de la grille parmi les offres passées');
    svg.replaceChildren();
    const f = o.marche;
    const valeurs = f.valeurs.filter(v => Number.isFinite(v.v));
    const haut = Math.max(o.moi || 0, ...valeurs.map(v => v.v), 0.05);
    const xMax = plafondJoli(haut * 1.12, 5);
    const X = (v) => m.g + (v / xMax) * lp;
    const yPiste = 92;

    for (const t of graduations(xMax, 6)) {
      svg.append(s('line', { x1: X(t), x2: X(t), y1: yPiste + 16, y2: yPiste + 20, stroke: 'var(--b-36)' }));
      svg.append(s('text', { x: X(t), y: yPiste + 34, 'text-anchor': 'middle', class: 'graduation' }, fmtTaux(t)));
    }
    svg.append(s('line', { x1: m.g, x2: m.g + lp, y1: yPiste + 16, y2: yPiste + 16, stroke: 'var(--b-22)' }));
    if (f.n) {
      svg.append(s('rect', { x: X(f.min), y: yPiste - 7, width: Math.max(2, X(f.max) - X(f.min)), height: 14, fill: 'var(--b-6)' }));
      if (f.n >= 3) svg.append(s('rect', { x: X(f.p25), y: yPiste - 7, width: Math.max(2, X(f.p75) - X(f.p25)), height: 14, fill: 'var(--b-12)' }));
      svg.append(s('line', { x1: X(f.mediane), x2: X(f.mediane), y1: yPiste - 12, y2: yPiste + 12, stroke: 'var(--b-52)', 'stroke-width': 2 }));
    }

    // Nuage d'offres : trois rangées pour que deux prix voisins ne se cachent pas.
    const tri = [...valeurs].sort((a, b) => a.v - b.v);
    const derniers = [-1e9, -1e9, -1e9];
    const rangees = [yPiste - 22, yPiste - 36, yPiste - 50];
    for (const v of tri) {
      const x = X(v.v);
      let r = derniers.findIndex(d => x - d >= 13);
      if (r < 0) r = derniers.indexOf(Math.min(...derniers));
      derniers[r] = x;
      const g = marque(v.g.issue, x, rangees[r], 9, { tabindex: 0, role: 'button',
        'aria-label': `${v.titre} : ${fmtTaux(v.v)}` });
      g.append(s('circle', { cx: x, cy: rangees[r], r: 12, fill: 'transparent' }));
      g.addEventListener('pointerenter', () => {
        const e = svg.getBoundingClientRect().width / L;
        bulle.montrer([v.titre, [`Sa grille à ${entier(o.encours)} M€`, fmtTaux(v.v)], ['Issue', v.g.issue],
          ['Encours réel du mandat', v.g.volume ? `${entier(v.g.volume)} M€` : '—']], x * e, rangees[r] * e);
      });
      g.addEventListener('pointerleave', () => bulle.cacher());
      if (o.surOffre) {
        g.style.cursor = 'pointer';
        g.addEventListener('click', () => o.surOffre(v.g));
        g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); o.surOffre(v.g); } });
      }
      svg.append(g);
    }

    // La grille simulée : un trait d'encre qui traverse la piste.
    if (Number.isFinite(o.moi)) {
      const x = X(o.moi);
      svg.append(s('line', { x1: x, x2: x, y1: 18, y2: yPiste + 16, stroke: 'var(--b-100)', 'stroke-width': 2.5 }));
      svg.append(s('circle', { cx: x, cy: yPiste, r: 6, fill: 'var(--b-100)', stroke: 'var(--blanc)', 'stroke-width': 2 }));
      const aDroite = x < m.g + lp - 150;
      svg.append(s('text', { x: x + (aDroite ? 8 : -8), y: 22, 'text-anchor': aDroite ? 'start' : 'end',
        class: 'etiquette-fin etiquette-fin--forte' }, `${o.libelle || 'Votre grille'} · ${fmtTaux(o.moi)}`));
    }
  }

  dessiner(options);
  return { el: hote, maj: (o) => dessiner({ ...courant, ...o }) };
}

/* ======================================================================= */
/*  La fourchette d'une tranche, dans sa cellule                           */
/* ======================================================================= */
export function bandeTranche(resume, taux, domaine) {
  const L = 132; const H = 18;
  const svg = s('svg', { width: L, height: H, viewBox: `0 0 ${L} ${H}`, class: 'bande-tranche', 'aria-hidden': 'true' });
  const X = (v) => 3 + Math.min(1, Math.max(0, v / domaine)) * (L - 6);
  svg.append(s('line', { x1: 3, x2: L - 3, y1: H / 2, y2: H / 2, stroke: 'var(--b-12)', 'stroke-width': 1 }));
  if (resume.n) {
    svg.append(s('rect', { x: X(resume.min), y: H / 2 - 4, width: Math.max(2, X(resume.max) - X(resume.min)), height: 8, fill: 'var(--b-12)' }));
    if (resume.n >= 3) svg.append(s('rect', { x: X(resume.p25), y: H / 2 - 4, width: Math.max(2, X(resume.p75) - X(resume.p25)), height: 8, fill: 'var(--b-22)' }));
    svg.append(s('line', { x1: X(resume.mediane), x2: X(resume.mediane), y1: H / 2 - 6, y2: H / 2 + 6, stroke: 'var(--b-52)', 'stroke-width': 2 }));
  }
  if (Number.isFinite(taux)) {
    svg.append(s('circle', { cx: X(taux), cy: H / 2, r: 5, fill: 'var(--b-100)', stroke: 'var(--blanc)', 'stroke-width': 2 }));
  }
  return svg;
}

/* ======================================================================= */
/*  Le prix et la chance de gagner : deux panneaux, un même axe des prix   */
/* ======================================================================= */
/**
 * En haut, la chance de l'emporter selon l'écart au prix médian du marché, avec
 * sa bande d'incertitude et chaque décision passée (gagnée en haut, perdue en
 * bas). En bas, le revenu espéré : chance × frais sur la durée. Les deux
 * panneaux partagent l'axe des prix — jamais deux échelles sur un même tracé.
 */
export function courbeGain(options) {
  const hote = div('figure-tarif');
  const bulle = infobulle(hote);
  const svg = s('svg', { class: 'figure-tarif__svg', role: 'img' });
  hote.prepend(svg);
  let courant = null;

  function dessiner(o) {
    courant = o;
    const L = o.largeur || 1040;
    const m = { g: 64, d: 170, h: 48, b: 40 };
    const h1 = 200; const ecart = 44; const h2 = 150;
    const H = m.h + h1 + ecart + h2 + m.b;
    const lp = L - m.g - m.d;
    svg.setAttribute('viewBox', `0 0 ${L} ${H}`);
    svg.setAttribute('aria-label', 'Chance de gagner et revenu espéré selon le prix');
    svg.replaceChildren();
    const c = o.courbe; const [lo, hi] = c.domaine;
    const X = (x) => m.g + ((x - lo) / (hi - lo)) * lp;
    const y1 = (p) => m.h + h1 - p * h1;
    const top2 = m.h + h1 + ecart;
    const eMax = plafondJoli(Math.max(...c.points.map(p => p.espere), c.actuel.espere) * 1.1, 4);
    const y2 = (v) => top2 + h2 - (v / eMax) * h2;
    const md = o.modele;

    // Zones sans décision : hachurées, le modèle y extrapole.
    const motif = s('pattern', { id: 'hachure-gain', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' },
      s('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: 'var(--b-12)', 'stroke-width': 2 }));
    svg.append(s('defs', {}, motif));
    for (const [a, b] of [[lo, md.xMin], [md.xMax, hi]]) {
      if (b - a <= 0) continue;
      for (const [t, hh] of [[m.h, h1], [top2, h2]]) svg.append(s('rect', { x: X(a), y: t, width: X(b) - X(a), height: hh, fill: 'url(#hachure-gain)' }));
    }

    // Axes.
    const ticksX = [0.5, 0.75, 1, 1.25, 1.5, 2].map(Math.log).filter(x => x >= lo - 1e-9 && x <= hi + 1e-9);
    for (const x of ticksX) {
      for (const [t, hh] of [[m.h, h1], [top2, h2]]) svg.append(s('line', { x1: X(x), x2: X(x), y1: t, y2: t + hh, stroke: x === 0 ? 'var(--b-22)' : 'var(--b-6)' }));
      const pct = Math.round((Math.exp(x) - 1) * 100);
      svg.append(s('text', { x: X(x), y: top2 + h2 + 18, 'text-anchor': 'middle', class: 'graduation' },
        pct === 0 ? 'médiane' : `${pct > 0 ? '+' : MOINS}${Math.abs(pct)}${NBSP}%`));
    }
    svg.append(s('text', { x: m.g + lp, y: H - 4, 'text-anchor': 'end', class: 'titre-axe' }, 'Votre prix, en écart au prix médian du marché'));
    for (const p of [0, 0.25, 0.5, 0.75, 1]) {
      svg.append(s('line', { x1: m.g, x2: m.g + lp, y1: y1(p), y2: y1(p), stroke: 'var(--b-6)' }));
      svg.append(s('text', { x: m.g - 8, y: y1(p) + 4, 'text-anchor': 'end', class: 'graduation' }, `${Math.round(p * 100)}${NBSP}%`));
    }
    for (const v of graduations(eMax, 3)) {
      svg.append(s('line', { x1: m.g, x2: m.g + lp, y1: y2(v), y2: y2(v), stroke: 'var(--b-6)' }));
      svg.append(s('text', { x: m.g - 8, y: y2(v) + 4, 'text-anchor': 'end', class: 'graduation' }, fmtFrais(v)));
    }
    for (const t of [m.h + h1, top2 + h2]) svg.append(s('line', { x1: m.g, x2: m.g + lp, y1: t, y2: t, stroke: 'var(--b-22)' }));

    // La bande et la courbe de la chance de gagner.
    let dBande = ''; let dHaut = '';
    c.points.forEach((p, i) => { dBande += `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${y1(p.haut).toFixed(1)}`; });
    for (let i = c.points.length - 1; i >= 0; i--) dBande += `L${X(c.points[i].x).toFixed(1)},${y1(c.points[i].bas).toFixed(1)}`;
    svg.append(s('path', { d: `${dBande}Z`, fill: 'var(--b-12)' }));
    c.points.forEach((p, i) => { dHaut += `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${y1(p.p).toFixed(1)}`; });
    svg.append(s('path', { d: dHaut, fill: 'none', stroke: 'var(--b-100)', 'stroke-width': 2.5 }));
    let dE = '';
    c.points.forEach((p, i) => { dE += `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${y2(p.espere).toFixed(1)}`; });
    svg.append(s('path', { d: dE, fill: 'none', stroke: 'var(--b-100)', 'stroke-width': 2.5 }));

    // Les décisions passées : gagnées sur la ligne des 100 %, perdues sur celle des 0 %.
    const places = { 1: [], 0: [] };
    for (const d of [...o.decisions].sort((a, b) => a.x - b.x)) {
      const x = X(Math.max(lo, Math.min(hi, d.x)));
      const rang = places[d.gagne];
      let k = 0;
      while (rang.some(r => r.k === k && Math.abs(r.x - x) < 12)) k++;
      rang.push({ x, k });
      const y = d.gagne ? y1(1) - 9 - k * 12 : y1(0) + 9 + k * 12;
      const g = marque(d.offre.issue, x, y, 9, { tabindex: 0, role: 'button', 'aria-label': `${d.titre} : ${d.gagne ? 'gagnée' : 'perdue'}, ${fmtEcartPct(d.x)} vs marché` });
      g.append(s('circle', { cx: x, cy: y, r: 11, fill: 'transparent' }));
      g.addEventListener('pointerenter', () => {
        const e = svg.getBoundingClientRect().width / L;
        bulle.montrer([d.titre, ['Issue', d.offre.issue], ['Son prix', fmtTaux(d.taux)], ['Médiane du marché à sa taille', fmtTaux(d.mediane)],
          ['Écart', fmtEcartPct(d.x)]], x * e, y * e);
      });
      g.addEventListener('pointerleave', () => bulle.cacher());
      if (o.surDecision) {
        g.style.cursor = 'pointer';
        g.addEventListener('click', () => o.surDecision(d.offre));
        g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); o.surDecision(d.offre); } });
      }
      svg.append(g);
    }

    // Votre prix, et le prix qui rapporte le plus en espérance.
    const repere = (x, texte, fort, cote) => {
      const px = X(Math.max(lo, Math.min(hi, x)));
      svg.append(s('line', { x1: px, x2: px, y1: m.h, y2: top2 + h2, stroke: 'var(--b-100)', 'stroke-width': fort ? 1.5 : 1,
        'stroke-dasharray': fort ? null : '4 3' }));
      const aGauche = cote === 'gauche' || px > m.g + lp - 120;
      svg.append(s('line', { x1: px, x2: px, y1: m.h - 34, y2: m.h, stroke: 'var(--b-100)', 'stroke-width': fort ? 1.5 : 1,
        'stroke-dasharray': fort ? null : '4 3' }));
      svg.append(s('text', { x: px + (aGauche ? -6 : 6), y: m.h - 26, 'text-anchor': aGauche ? 'end' : 'start',
        class: fort ? 'etiquette-fin etiquette-fin--forte' : 'etiquette-fin' }, texte));
    };
    const a = c.actuel;
    if (o.montrerOptimum && Math.abs(c.meilleur.x - a.x) > 0.01) {
      repere(c.meilleur.x, `meilleur espoir · ${fmtTaux(o.tauxDe(c.meilleur.x))}`, false, c.meilleur.x < a.x ? 'gauche' : 'droite');
      svg.append(s('circle', { cx: X(c.meilleur.x), cy: y2(c.meilleur.espere), r: 5, fill: 'var(--blanc)', stroke: 'var(--b-100)', 'stroke-width': 2 }));
      svg.append(s('circle', { cx: X(c.meilleur.x), cy: y1(c.meilleur.p), r: 5, fill: 'var(--blanc)', stroke: 'var(--b-100)', 'stroke-width': 2 }));
    }
    repere(a.x, `votre grille · ${fmtTaux(o.tauxDe(a.x))}`, true, o.montrerOptimum && c.meilleur.x > a.x ? 'gauche' : 'droite');
    for (const [cy, v] of [[y1(a.p), `${Math.round(a.p * 100)}${NBSP}%`], [y2(a.espere), fmtFrais(a.espere)]]) {
      svg.append(s('circle', { cx: X(a.x), cy, r: 6, fill: 'var(--b-100)', stroke: 'var(--blanc)', 'stroke-width': 2 }));
      svg.append(s('text', { x: X(a.x) + 10, y: cy - 8, class: 'etiquette-fin etiquette-fin--forte' }, v));
    }
    // Étiquettes de fin de courbe.
    const der = c.points[c.points.length - 1];
    svg.append(s('text', { x: m.g + lp + 8, y: y1(der.p) + 4, class: 'etiquette-fin' }, 'chance de gagner'));
    svg.append(s('text', { x: m.g + lp + 8, y: y2(der.espere) + 4, class: 'etiquette-fin' }, `revenu espéré sur ${o.horizon} an${o.horizon > 1 ? 's' : ''}`));

    // Réticule : la lecture à n'importe quel prix.
    const ret = s('line', { y1: m.h, y2: top2 + h2, stroke: 'var(--b-72)', visibility: 'hidden', 'pointer-events': 'none' });
    svg.append(ret);
    const capte = s('rect', { x: m.g, y: m.h + 14, width: lp, height: h1 - 28, fill: 'transparent' });
    const capte2 = s('rect', { x: m.g, y: top2, width: lp, height: h2, fill: 'transparent' });
    const lire = (ev) => {
      const r = svg.getBoundingClientRect(); const e = r.width / L;
      const px = (ev.clientX - r.left) / e;
      const i = Math.max(0, Math.min(c.points.length - 1, Math.round(((px - m.g) / lp) * (c.points.length - 1))));
      const p = c.points[i];
      ret.setAttribute('x1', X(p.x)); ret.setAttribute('x2', X(p.x)); ret.setAttribute('visibility', 'visible');
      bulle.montrer([`À ${fmtTaux(o.tauxDe(p.x))} (${fmtEcartPct(p.x)} vs médiane)`,
        ['Chance de gagner', `${Math.round(p.p * 100)}${NBSP}% (${Math.round(p.bas * 100)}–${Math.round(p.haut * 100)})`],
        [`Frais sur ${o.horizon} ans si gagné`, fmtFrais(p.valeur)], ['Revenu espéré', fmtFrais(p.espere)],
        ...(p.x < md.xMin || p.x > md.xMax ? [['', 'hors des décisions passées']] : [])], X(p.x) * e, (ev.clientY - r.top));
    };
    for (const k of [capte, capte2]) {
      k.addEventListener('pointermove', lire);
      k.addEventListener('pointerleave', () => { bulle.cacher(); ret.setAttribute('visibility', 'hidden'); });
      svg.insertBefore(k, svg.querySelector('.marque-offre'));
    }
  }

  dessiner(options);
  return { el: hote, maj: (o) => dessiner({ ...courant, ...o }) };
}

/** Un écart de prix : x = ln(ratio) → « +18 % », « −27 % ». */
export function fmtEcartPct(x) {
  if (!Number.isFinite(x)) return '—';
  const p = Math.round((Math.exp(x) - 1) * 100);
  return p === 0 ? 'au prix médian' : `${p > 0 ? '+' : MOINS}${Math.abs(p)}${NBSP}%`;
}

/* ======================================================================= */
/*  La valeur du mandat : les frais année après année                      */
/* ======================================================================= */
export function courbeValeur(options) {
  const hote = div('figure-tarif');
  const bulle = infobulle(hote);
  const svg = s('svg', { class: 'figure-tarif__svg', role: 'img' });
  hote.prepend(svg);
  let courant = null;

  function dessiner(o) {
    courant = o;
    const L = o.largeur || 660; const H = 262;
    const m = { g: 56, d: 16, h: 14, b: 48 };
    const lp = L - m.g - m.d; const hp = H - m.h - m.b;
    svg.setAttribute('viewBox', `0 0 ${L} ${H}`);
    svg.setAttribute('aria-label', 'Frais annuels du mandat, année par année');
    svg.replaceChildren();
    const an = o.projection.annees;
    const yMax = plafondJoli(Math.max(...an.map(a => Math.max(a.frais, a.fixe))) * 1.08, 4);
    const Y = (v) => m.h + hp - (v / yMax) * hp;
    const pasX = lp / an.length;
    const lb = Math.min(64, pasX * 0.6);
    svg.append(s('defs', {}, s('pattern', { id: 'hachure-valeur', width: 5, height: 5, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' },
      s('line', { x1: 0, y1: 0, x2: 0, y2: 5, stroke: 'var(--b-36)', 'stroke-width': 1.5 }))));
    for (const v of graduations(yMax, 4)) {
      svg.append(s('line', { x1: m.g, x2: m.g + lp, y1: Y(v), y2: Y(v), stroke: 'var(--b-6)' }));
      svg.append(s('text', { x: m.g - 8, y: Y(v) + 4, 'text-anchor': 'end', class: 'graduation' }, fmtFrais(v)));
    }
    an.forEach((a, i) => {
      const cx = m.g + pasX * (i + 0.5);
      const x0 = cx - lb / 2;
      // La barre des frais, arrondie côté données, ancrée à la ligne de base.
      const yt = Y(a.frais); const r = Math.min(3, Y(0) - yt);
      svg.append(s('path', { d: `M${x0},${Y(0)}V${yt + r}Q${x0},${yt} ${x0 + r},${yt}H${x0 + lb - r}Q${x0 + lb},${yt} ${x0 + lb},${yt + r}V${Y(0)}Z`,
        fill: 'var(--b-52)' }));
      // Au-dessus, hachuré : ce que le même encours paierait au taux fixe d'aujourd'hui.
      if (a.fixe - a.frais > yMax * 0.002) {
        svg.append(s('rect', { x: x0, y: Y(a.fixe), width: lb, height: Math.max(1, yt - Y(a.fixe) - 2), fill: 'url(#hachure-valeur)',
          stroke: 'var(--b-72)', 'stroke-width': 1, 'stroke-dasharray': '2 2' }));
      }
      svg.append(s('text', { x: cx, y: H - 28, 'text-anchor': 'middle', class: 'etiquette-repere etiquette-repere--fort' }, fmtFrais(a.frais)));
      svg.append(s('text', { x: cx, y: H - 12, 'text-anchor': 'middle', class: 'graduation' }, `an ${a.annee}`));
      const zone = s('rect', { x: cx - pasX / 2, y: m.h, width: pasX, height: hp, fill: 'transparent' });
      zone.addEventListener('pointerenter', () => {
        const e = svg.getBoundingClientRect().width / L;
        bulle.montrer([`Année ${a.annee}`, ['Encours', `${entier(a.encours)} M€`], ['Taux moyen', fmtTaux(a.taux)],
          ['Frais', fmtFrais(a.frais)], ['Au taux fixe d’aujourd’hui', fmtFrais(a.fixe)], ['Cumul', fmtFrais(a.cumul)]], cx * e, Y(a.frais) * e);
      });
      zone.addEventListener('pointerleave', () => bulle.cacher());
      svg.append(zone);
    });
    svg.append(s('line', { x1: m.g, x2: m.g + lp, y1: Y(0), y2: Y(0), stroke: 'var(--b-22)' }));
  }

  dessiner(options);
  return { el: hote, maj: (o) => dessiner({ ...courant, ...o }) };
}
