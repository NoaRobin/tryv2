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
