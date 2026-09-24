// escalier.js — l'escalier des frais : la grille, telle que le client la paie.
//
// Chaque marche est une tranche : sa LARGEUR est la part d'encours qu'elle
// couvre, sa HAUTEUR son taux. La surface pleine, sous la marche et à gauche
// du curseur d'encours, est exactement ce que paie le client (largeur × hauteur
// = M€ × % = frais). Derrière chaque marche, la bande de ce que le marché a
// facturé sur la même part d'encours.
//
// Tout se manipule à la souris ou au clavier : le haut d'une marche change son
// taux, son bord déplace le seuil, le curseur change la taille du mandat.
// « Faire grandir le mandat » fait courir le curseur : la surface se remplit,
// le compteur de frais monte, le taux moyen descend marche après marche.

import * as T from './tarif.js';
import { fmtTaux, fmtFrais, plafondJoli } from './graphes-tarif.js';
import { entier } from './format.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const L = 1040; const H = 360;
const M = { g: 58, d: 132, h: 54, b: 46 };
const LP = L - M.g - M.d; const HP = H - M.h - M.b;
const PAS_TAUX = 0.005; const PAS_SEUIL = 5;

function s(tag, attrs = {}, ...enfants) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined && v !== false) el.setAttribute(k, String(v));
  for (const e of enfants.flat()) if (e !== null && e !== undefined) el.append(e instanceof Node ? e : document.createTextNode(String(e)));
  return el;
}

function pasJoli(etendue, n) {
  const brut = etendue / Math.max(1, n);
  const p = 10 ** Math.floor(Math.log10(brut));
  for (const m of [1, 2, 2.5, 5, 10]) if (brut <= m * p) return m * p;
  return 10 * p;
}

const reduit = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const lisse = (u) => (u < 0.5 ? 4 * u ** 3 : 1 - (-2 * u + 2) ** 3 / 2);

/**
 * @param {object} rappels surEncours(v), surTaux(i, v), surSeuil(i, v) : la
 *   figure propose, l'écran décide (et rappelle maj avec l'état retenu).
 */
export function creerEscalier({ surEncours, surTaux, surSeuil } = {}) {
  const hote = document.createElement('div');
  hote.className = 'escalier';
  const svg = s('svg', { class: 'escalier__svg', viewBox: `0 0 ${L} ${H}`, role: 'group',
    'aria-label': 'L’escalier des frais : chaque marche est une tranche, la surface pleine est ce que paie le client' });
  const bulle = document.createElement('div');
  bulle.className = 'infobulle';
  bulle.hidden = true;
  hote.append(svg, bulle);

  // Ce qui est demandé (cible) et ce qui est dessiné (affiche) : entre les deux,
  // une transition courte, pour que l'œil suive ce qui change.
  let cible = null;
  let affiche = null;
  let transition = null;
  let course = null;          // l'animation « faire grandir le mandat »
  let geste = null;           // la poignée tenue
  let survol = null;
  let xMaxFige = null;
  let focusCle = null;

  const echelles = (etat) => {
    const derniere = etat.seuils.length ? etat.seuils[etat.seuils.length - 1] : 0;
    const xMax = xMaxFige || plafondJoli(Math.max(etat.encours * 1.6, derniere * 1.35, 100), 6);
    let yHaut = Math.max(...etat.taux, 0.02);
    for (const c of etat.marche || []) if (c && c.n) yHaut = Math.max(yHaut, c.max);
    const yMax = plafondJoli(yHaut * 1.12, 5);
    return { xMax, yMax, X: (v) => M.g + (Math.min(v, xMax) / xMax) * LP, Y: (v) => M.h + HP - (v / yMax) * HP };
  };

  const etatDe = (o) => ({
    encours: o.encours,
    seuils: o.grille.slice(1).map(t => t.minimum),       // début des tranches 2…n
    taux: o.grille.map(t => t.taux),
    marche: o.marche || [],
  });
  const grilleDe = (e) => e.taux.map((taux, i) => ({ minimum: i ? e.seuils[i - 1] : 0,
    maximum: i < e.taux.length - 1 ? e.seuils[i] : null, taux }));

  /* ------------------------------------------------------------ dessin --- */
  function dessiner() {
    const e = affiche;
    if (!e) return;
    const { xMax, yMax, X, Y } = echelles(e);
    const grille = grilleDe(e);
    const A = e.encours;
    const fraisA = T.frais(grille, A);
    const n = grille.length;
    const bornes = grille.map((t, i) => [t.minimum, i < n - 1 ? t.maximum : xMax]);
    const base = M.h + HP;
    const out = [];

    // Axes : filets pleins, recessifs.
    const pasY = pasJoli(yMax, 5);
    for (let v = 0; v <= yMax + 1e-9; v += pasY) {
      out.push(s('line', { x1: M.g, x2: M.g + LP, y1: Y(v), y2: Y(v), stroke: 'var(--b-6)' }));
      out.push(s('text', { x: M.g - 8, y: Y(v) + 4, 'text-anchor': 'end', class: 'graduation' }, fmtTaux(v)));
    }
    const pasX = pasJoli(xMax, 7);
    for (let v = 0; v <= xMax + 1e-9; v += pasX) {
      out.push(s('line', { x1: X(v), x2: X(v), y1: base, y2: base + 4, stroke: 'var(--b-36)' }));
      out.push(s('text', { x: X(v), y: base + 18, 'text-anchor': 'middle', class: 'graduation' }, entier(v)));
    }
    out.push(s('text', { x: M.g + LP, y: H - 6, 'text-anchor': 'end', class: 'titre-axe' }, 'Encours du mandat (M€)'));
    out.push(s('text', { x: M.g - 8, y: M.h - 16, 'text-anchor': 'end', class: 'titre-axe' }, 'Taux'));

    // Le marché, derrière chaque marche.
    grille.forEach((t, i) => {
      const c = e.marche[i];
      if (!c || !c.n) return;
      const [a, b] = bornes[i];
      const x1 = X(a) + 1; const x2 = X(b) - 1;
      if (x2 - x1 < 2) return;
      out.push(s('rect', { x: x1, y: Y(c.max), width: x2 - x1, height: Math.max(1, Y(c.min) - Y(c.max)), fill: 'var(--b-6)' }));
      if (c.n >= 3) out.push(s('rect', { x: x1, y: Y(c.p75), width: x2 - x1, height: Math.max(1, Y(c.p25) - Y(c.p75)), fill: 'var(--b-12)' }));
      out.push(s('line', { x1, x2, y1: Y(c.mediane), y2: Y(c.mediane), stroke: 'var(--b-52)', 'stroke-width': 1.5, 'stroke-dasharray': '5 4' }));
    });

    // Ce que paie le client : la surface sous chaque marche, jusqu'à l'encours.
    grille.forEach((t, i) => {
      const [a, b] = bornes[i];
      const fin = Math.min(b, A);
      if (fin <= a) return;
      const x1 = X(a) + (i ? 1 : 0); const x2 = X(fin) - 1;
      if (x2 <= x1) return;
      out.push(s('rect', { x: x1, y: Y(t.taux), width: x2 - x1, height: base - Y(t.taux),
        fill: i % 2 ? 'var(--b-36)' : 'var(--b-22)', class: 'escalier__paye' }));
      const f = (fin - a) * t.taux / 100;
      if (x2 - x1 > 46 && base - Y(t.taux) > 30) {
        out.push(s('text', { x: (x1 + x2) / 2, y: base - 10, 'text-anchor': 'middle', class: 'escalier__frais' }, fmtFrais(f)));
      }
    });

    // Le profil de la grille : un trait d'encre continu, marches et contremarches.
    let d = '';
    grille.forEach((t, i) => {
      const [a, b] = bornes[i];
      d += `${i ? 'L' : 'M'}${X(a).toFixed(1)},${Y(t.taux).toFixed(1)}L${X(b).toFixed(1)},${Y(t.taux).toFixed(1)}`;
    });
    out.push(s('path', { d, fill: 'none', stroke: 'var(--b-100)', 'stroke-width': 2.5, 'stroke-linejoin': 'miter' }));

    // L'étiquette de chaque marche, au-dessus d'elle.
    grille.forEach((t, i) => {
      const [a, b] = bornes[i];
      if (X(b) - X(a) < 58) return;
      // Sous le nez de la marche quand elle est assez haute : aucun trait ne la traverse.
      const dedans = base - Y(t.taux) > 44;
      out.push(s('text', { x: (X(a) + X(b)) / 2, y: dedans ? Y(t.taux) + 18 : Y(t.taux) - 9, 'text-anchor': 'middle', class: 'escalier__marche' },
        s('tspan', { class: 'escalier__marche-nom' }, `T${i + 1}  `), fmtTaux(t.taux)));
    });

    // Le taux moyen : ce que devient le prix quand l'encours grossit.
    let dm = '';
    const nPts = 160;
    for (let k = 1; k <= nPts; k++) {
      const x = (xMax * k) / nPts;
      dm += `${k > 1 ? 'L' : 'M'}${X(x).toFixed(1)},${Y(T.tauxMoyen(grille, x)).toFixed(1)}`;
    }
    out.push(s('path', { d: dm, fill: 'none', stroke: 'var(--b-72)', 'stroke-width': 1.5, 'stroke-dasharray': '1.5 3.5', 'stroke-linecap': 'round' }));
    out.push(s('text', { x: M.g + LP + 8, y: Y(T.tauxMoyen(grille, xMax)) + 4, class: 'etiquette-fin' }, 'taux moyen'));
    const yFin = Y(grille[n - 1].taux);
    if (Math.abs(yFin - Y(T.tauxMoyen(grille, xMax))) > 13) {
      out.push(s('text', { x: M.g + LP + 8, y: yFin + 4, class: 'etiquette-fin etiquette-fin--forte' }, 'votre grille'));
    }

    // Le curseur d'encours : la ligne, la poignée au pied, la lecture au sommet.
    const xa = X(A);
    const tm = T.tauxMoyen(grille, A);
    out.push(s('line', { x1: xa, x2: xa, y1: M.h - 6, y2: base, stroke: 'var(--b-100)', 'stroke-width': 1.25 }));
    out.push(s('circle', { cx: xa, cy: Y(tm), r: 5.5, fill: 'var(--b-100)', stroke: 'var(--blanc)', 'stroke-width': 2 }));
    const im = (() => { for (let i = n - 1; i >= 0; i--) if (A >= grille[i].minimum) return i; return 0; })();
    const texte = `${entier(A)} M€ · ${fmtFrais(fraisA)} HT par an · ${fmtTaux(tm)} en moyenne`;
    const droite = xa > M.g + LP * 0.62;
    const eti = s('text', { x: xa + (droite ? -10 : 10), y: M.h - 30, 'text-anchor': droite ? 'end' : 'start', class: 'escalier__lecture' }, texte);
    const sous = s('text', { x: xa + (droite ? -10 : 10), y: M.h - 13, 'text-anchor': droite ? 'end' : 'start', class: 'escalier__sous' },
      `le million suivant paie ${fmtTaux(grille[im].taux)} (T${im + 1})`);
    out.push(eti, sous);

    // Poignées : zones de prise plus grandes que le trait, et atteignables au clavier.
    const poignees = [];
    grille.forEach((t, i) => {
      const [a, b] = bornes[i];
      poignees.push(s('rect', { x: X(a) + 6, y: Y(t.taux) - 8, width: Math.max(4, X(b) - X(a) - 12), height: 16,
        class: 'escalier__poignee escalier__poignee--taux', 'data-poignee': 'taux', 'data-i': i, tabindex: 0, role: 'slider',
        'aria-label': `Taux de la tranche ${i + 1}`, 'aria-valuetext': fmtTaux(t.taux) }));
      if (i < n - 1) {
        const yb = Math.min(Y(t.taux), Y(grille[i + 1].taux));
        poignees.push(s('rect', { x: X(b) - 7, y: yb - 4, width: 14, height: base - yb + 4,
          class: 'escalier__poignee escalier__poignee--seuil', 'data-poignee': 'seuil', 'data-i': i, tabindex: 0, role: 'slider',
          'aria-label': `Seuil entre les tranches ${i + 1} et ${i + 2}`, 'aria-valuetext': `${entier(b)} M€` }));
      }
    });
    // Le curseur d'encours : toute la hauteur est une prise, la poignée au pied se voit.
    poignees.push(s('rect', { x: xa - 8, y: M.h - 4, width: 16, height: HP + 4,
      class: 'escalier__poignee escalier__poignee--encours', 'data-poignee': 'encours', tabindex: 0, role: 'slider',
      'aria-label': 'Taille du mandat', 'aria-valuetext': `${entier(A)} M€` }));
    out.push(s('rect', { x: xa - 9, y: base - 9, width: 18, height: 18, rx: 2, fill: 'var(--b-100)', stroke: 'var(--blanc)', 'stroke-width': 2, 'pointer-events': 'none' }));
    out.push(s('path', { d: `M${xa - 3},${base - 3}L${xa - 6},${base}L${xa - 3},${base + 3}M${xa + 3},${base - 3}L${xa + 6},${base}L${xa + 3},${base + 3}`,
      stroke: 'var(--blanc)', 'stroke-width': 1.5, fill: 'none', 'pointer-events': 'none' }));

    // La poignée survolée ou tenue se montre : un trait plus épais.
    const actif = geste || survol;
    if (actif) {
      if (actif.type === 'taux') {
        const [a, b] = bornes[actif.i];
        out.push(s('line', { x1: X(a), x2: X(b), y1: Y(grille[actif.i].taux), y2: Y(grille[actif.i].taux), stroke: 'var(--b-100)', 'stroke-width': 5, 'pointer-events': 'none' }));
      } else if (actif.type === 'seuil') {
        const b = bornes[actif.i][1];
        out.push(s('line', { x1: X(b), x2: X(b), y1: Math.min(Y(grille[actif.i].taux), Y(grille[actif.i + 1].taux)), y2: base, stroke: 'var(--b-100)', 'stroke-width': 4, 'pointer-events': 'none' }));
      }
    }

    svg.replaceChildren(...out, ...poignees);
    if (focusCle) {
      const el = svg.querySelector(focusCle);
      if (el) el.focus({ preventScroll: true });
    }
  }

  /* ------------------------------------------------------------ boucle --- */
  let rafId = null;
  function boucle(t) {
    rafId = null;
    if (!hote.isConnected && cible) return;       // l'écran a été quitté
    let encore = false;
    if (course) {
      const u = Math.min(1, (t - course.debut) / course.duree);
      if (course.phase === 'aller') {
        affiche = { ...affiche, encours: course.de + (course.a - course.de) * lisse(u) };
        if (u >= 1) { course = { ...course, phase: 'pause', debut: t, duree: reduit() ? 1 : 900 }; }
      } else if (course.phase === 'pause') {
        if (u >= 1) course = { ...course, phase: 'retour', debut: t, duree: reduit() ? 1 : 1100, depuis: affiche.encours };
      } else {
        affiche = { ...affiche, encours: course.depuis + (cible.encours - course.depuis) * lisse(u) };
        if (u >= 1) { const fin = course.fin; course = null; xMaxFige = null; affiche = { ...cible }; if (fin) fin(); }
      }
      if (course && course.surPas) course.surPas(affiche.encours);
      encore = !!course;
    } else if (transition) {
      const u = Math.min(1, (t - transition.debut) / transition.duree);
      const k = lisse(u);
      const mel = (a, b) => a + (b - a) * k;
      affiche = { ...cible, encours: mel(transition.de.encours, cible.encours),
        seuils: cible.seuils.map((v, i) => mel(transition.de.seuils[i], v)),
        taux: cible.taux.map((v, i) => mel(transition.de.taux[i], v)) };
      if (u >= 1) { transition = null; affiche = { ...cible }; }
      encore = !!transition;
    }
    dessiner();
    if (encore) rafId = requestAnimationFrame(boucle);
  }
  const relancer = () => { if (!rafId) rafId = requestAnimationFrame(boucle); };

  /* ------------------------------------------------------------ gestes --- */
  const versSvg = (ev) => {
    const r = svg.getBoundingClientRect();
    return { x: (ev.clientX - r.left) * (L / r.width), y: (ev.clientY - r.top) * (H / r.height) };
  };
  const proposer = (type, i, p) => {
    const { xMax, yMax } = echelles(affiche);
    if (type === 'encours') {
      const v = Math.max(1, Math.min(xMax, ((p.x - M.g) / LP) * xMax));
      surEncours?.(v < 100 ? Math.round(v) : Math.round(v / 5) * 5);
    } else if (type === 'taux') {
      const v = Math.max(0, ((M.h + HP - p.y) / HP) * yMax);
      surTaux?.(i, Math.round(v / PAS_TAUX) * PAS_TAUX);
    } else if (type === 'seuil') {
      const v = ((p.x - M.g) / LP) * xMax;
      surSeuil?.(i, Math.round(v / PAS_SEUIL) * PAS_SEUIL);
    }
  };
  svg.addEventListener('pointerdown', (ev) => {
    const el = ev.target.closest('[data-poignee]');
    if (!el || course) return;
    ev.preventDefault();
    geste = { type: el.dataset.poignee, i: Number(el.dataset.i) };
    svg.setPointerCapture(ev.pointerId);
    hote.classList.add('escalier--geste', `escalier--geste-${geste.type}`);
    bulle.hidden = true;
    proposer(geste.type, geste.i, versSvg(ev));
  });
  svg.addEventListener('pointermove', (ev) => {
    if (geste) { proposer(geste.type, geste.i, versSvg(ev)); return; }
    const el = ev.target.closest('[data-poignee]');
    const nouveau = el ? { type: el.dataset.poignee, i: Number(el.dataset.i) } : null;
    if (JSON.stringify(nouveau) !== JSON.stringify(survol)) { survol = nouveau; relancer(); }
    montrerBulle(ev);
  });
  const lacher = (ev) => {
    if (!geste) return;
    geste = null;
    hote.classList.remove('escalier--geste', 'escalier--geste-taux', 'escalier--geste-seuil', 'escalier--geste-encours');
    try { svg.releasePointerCapture(ev.pointerId); } catch (e) { /* déjà relâché */ }
    relancer();
  };
  svg.addEventListener('pointerup', lacher);
  svg.addEventListener('pointercancel', lacher);
  svg.addEventListener('pointerleave', () => { bulle.hidden = true; if (!geste && survol) { survol = null; relancer(); } });

  // Clavier : flèches sur la poignée qui a le focus.
  svg.addEventListener('keydown', (ev) => {
    const el = ev.target.closest('[data-poignee]');
    if (!el || !cible) return;
    const sens = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1 }[ev.key];
    if (!sens) return;
    ev.preventDefault();
    const type = el.dataset.poignee; const i = Number(el.dataset.i);
    focusCle = type === 'encours' ? '[data-poignee="encours"]' : `[data-poignee="${type}"][data-i="${i}"]`;
    const fois = ev.shiftKey ? 5 : 1;
    if (type === 'encours') surEncours?.(Math.max(1, cible.encours + sens * fois * (cible.encours < 100 ? 1 : 5)));
    else if (type === 'taux') surTaux?.(i, Math.max(0, Math.round((cible.taux[i] + sens * fois * PAS_TAUX) / PAS_TAUX) * PAS_TAUX));
    else surSeuil?.(i, cible.seuils[i] + sens * fois * PAS_SEUIL);
  });
  svg.addEventListener('focusout', () => { focusCle = null; });

  function montrerBulle(ev) {
    if (!affiche || course) { bulle.hidden = true; return; }
    const p = versSvg(ev);
    const { xMax, Y } = echelles(affiche);
    if (p.x < M.g || p.x > M.g + LP || p.y < M.h - 10 || p.y > M.h + HP) { bulle.hidden = true; return; }
    const v = ((p.x - M.g) / LP) * xMax;
    const grille = grilleDe(affiche);
    let i = 0;
    for (let k = grille.length - 1; k >= 0; k--) if (v >= grille[k].minimum) { i = k; break; }
    const t = grille[i];
    const haut = i < grille.length - 1 ? t.maximum : null;
    const c = affiche.marche[i];
    const part = Math.max(0, Math.min(affiche.encours, haut ?? Infinity) - t.minimum);
    const lignes = [[`T${i + 1} · ${entier(t.minimum)} → ${haut === null ? 'au-delà' : `${entier(haut)} M€`}`],
      ['Votre taux', fmtTaux(t.taux)],
      ['Encours du client ici', part > 0 ? `${entier(part)} M€` : 'aucun'],
      ['Frais de la tranche', part > 0 ? fmtFrais(part * t.taux / 100) : '—']];
    if (c && c.n) lignes.push(['Marché sur cette part', `${fmtTaux(c.min, { unite: false })}–${fmtTaux(c.max)}`], ['Médiane', fmtTaux(c.mediane)]);
    else lignes.push(['Marché sur cette part', 'aucune offre']);
    bulle.replaceChildren(...lignes.map((l, k) => {
      const d = document.createElement('div');
      d.className = k ? 'infobulle__ligne' : 'infobulle__titre';
      if (k) { const a = document.createElement('span'); a.className = 'infobulle__c'; a.textContent = l[0];
        const b = document.createElement('span'); b.className = 'infobulle__v'; b.textContent = l[1]; d.append(a, b); } else d.textContent = l[0];
      return d;
    }));
    bulle.hidden = false;
    const r = svg.getBoundingClientRect();
    const px = ev.clientX - r.left; const py = (Y(t.taux) / H) * r.height;
    const bw = bulle.offsetWidth;
    bulle.style.left = `${px + 16 + bw > r.width ? px - 16 - bw : px + 16}px`;
    bulle.style.top = `${Math.max(0, py - 8)}px`;
  }

  /* ------------------------------------------------------------ public --- */
  return {
    el: hote,
    /** Nouvel état : grille, encours, fourchettes du marché par tranche. */
    maj(o) {
      const nv = etatDe(o);
      const memeForme = cible && cible.taux.length === nv.taux.length;
      cible = nv;
      if (course) { affiche = { ...affiche, seuils: nv.seuils, taux: nv.taux, marche: nv.marche }; return; }
      if (!affiche || !memeForme || geste || reduit()) { affiche = { ...nv }; transition = null; relancer(); return; }
      transition = { de: { ...affiche }, debut: performance.now(), duree: 260 };
      relancer();
    },
    /** Le curseur court de zéro à la droite de la figure, puis revient. */
    grandir({ surPas, fin } = {}) {
      if (!cible || course) return;
      const { xMax } = echelles(cible);
      xMaxFige = xMax;
      transition = null;
      affiche = { ...cible, encours: 1 };
      course = { phase: 'aller', de: 1, a: xMax * 0.97, debut: performance.now(), duree: reduit() ? 1 : 6500, surPas, fin };
      relancer();
    },
    arreter() {
      if (!course) return;
      course = { ...course, phase: 'retour', debut: performance.now(), duree: reduit() ? 1 : 700, depuis: affiche.encours };
      relancer();
    },
    enCourse: () => !!course,
  };
}
