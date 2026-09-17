// figures.js — rendu des figures Plotly du moteur et petits graphes SVG.
//
// Une figure arrive du serveur telle que core.py l'a construite (données,
// mise en page, gabarit). Ici : la poser dans son conteneur, la rendre
// réactive à la largeur, transformer un clic sur une catégorie en filtre, et
// ne jamais la peindre avant qu'elle soit visible (les écrans sont longs).

const CONFIG = { displayModeBar: false, responsive: true, displaylogo: false, scrollZoom: false,
  doubleClick: false, showTips: false };

let plotlyPret = null;

/** Charge Plotly une seule fois, à la demande (4,8 Mo servis hors ligne). */
export function chargerPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (plotlyPret) return plotlyPret;
  plotlyPret = new Promise((resoudre, rejeter) => {
    const s = document.createElement('script');
    s.src = '/vendor/plotly.min.js';
    s.async = true;
    s.onload = () => resoudre(window.Plotly);
    s.onerror = () => rejeter(new Error('Plotly indisponible'));
    document.head.appendChild(s);
  });
  return plotlyPret;
}

const observateurs = new WeakMap();

/**
 * Rend une figure dans `conteneur`.
 * @param {HTMLElement} conteneur
 * @param {object} figure — { data, layout } tel que servi par /api/analyse
 * @param {object} options — { dimension, surClic(dim, valeur), hauteur }
 */
export async function rendreFigure(conteneur, figure, options = {}) {
  const Plotly = await chargerPlotly();
  const layout = { ...(figure.layout || {}) };
  layout.autosize = true;
  delete layout.width;
  if (options.hauteur) layout.height = options.hauteur;
  layout.margin = { ...(layout.margin || {}) };
  // Une figure cliquable le dit par le curseur, pas par un bouton.
  const cliquable = Boolean(options.dimension && options.surClic);
  if (cliquable) {
    layout.clickmode = 'event';
    layout.dragmode = false;
  }
  layout.hoverlabel = { ...(layout.hoverlabel || {}), namelength: -1 };
  conteneur.classList.add('figure');
  conteneur.classList.toggle('figure--cliquable', cliquable);
  await Plotly.react(conteneur, figure.data || [], layout, CONFIG);

  if (cliquable) {
    conteneur.removeAllListeners?.('plotly_click');
    conteneur.on('plotly_click', (ev) => {
      const p = ev.points && ev.points[0];
      if (!p) return;
      const etiquette = p.label ?? (typeof p.y === 'string' ? p.y : (typeof p.x === 'string' ? p.x : null));
      if (typeof etiquette !== 'string' || etiquette.startsWith('Autres')) return;
      options.surClic(options.dimension, etiquette);
    });
    conteneur.on('plotly_hover', () => { conteneur.style.cursor = 'pointer'; });
    conteneur.on('plotly_unhover', () => { conteneur.style.cursor = ''; });
  }
  if (!observateurs.has(conteneur) && 'ResizeObserver' in window) {
    let dernier = conteneur.clientWidth;
    const obs = new ResizeObserver(() => {
      if (conteneur.clientWidth && conteneur.clientWidth !== dernier) {
        dernier = conteneur.clientWidth;
        try { Plotly.Plots.resize(conteneur); } catch (e) { /* conteneur masqué */ }
      }
    });
    obs.observe(conteneur);
    observateurs.set(conteneur, obs);
  }
  return conteneur;
}

/** Détruit une figure et libère son observateur. */
export function detruireFigure(conteneur) {
  const obs = observateurs.get(conteneur);
  if (obs) { obs.disconnect(); observateurs.delete(conteneur); }
  if (window.Plotly && conteneur.data) {
    try { window.Plotly.purge(conteneur); } catch (e) { /* déjà retiré */ }
  }
}

/**
 * Rendu différé : la figure n'est peinte que lorsqu'elle approche de l'écran.
 * Retourne une fonction d'annulation.
 */
export function rendreQuandVisible(conteneur, figure, options = {}) {
  if (!('IntersectionObserver' in window)) {
    rendreFigure(conteneur, figure, options);
    return () => {};
  }
  const obs = new IntersectionObserver((entrees) => {
    for (const e of entrees) {
      if (e.isIntersecting) {
        obs.disconnect();
        rendreFigure(conteneur, figure, options);
      }
    }
  }, { rootMargin: '320px 0px' });
  obs.observe(conteneur);
  return () => obs.disconnect();
}

/**
 * Mini-tendance en SVG : la forme d'une série, sans axes ni promesse de
 * précision. `ton` : couleur CSS (par défaut currentColor).
 */
export function sparkline(valeurs, { largeur = 96, hauteur = 24, ton = 'currentColor', aire = false } = {}) {
  const v = (valeurs || []).map(Number).filter(x => Number.isFinite(x));
  if (v.length < 3) return '';
  const mini = Math.min(...v), maxi = Math.max(...v);
  const etendue = (maxi - mini) || 1;
  const pas = largeur / (v.length - 1);
  const pts = v.map((x, i) => [i * pas, hauteur - 2 - (x - mini) / etendue * (hauteur - 5)]);
  const trace = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const [fx, fy] = pts[pts.length - 1];
  const zone = aire ? `<polygon points="0,${hauteur} ${trace} ${largeur},${hauteur}" fill="${ton}" opacity=".08"/>` : '';
  return `<svg class="spark" width="${largeur}" height="${hauteur}" viewBox="0 0 ${largeur} ${hauteur}" aria-hidden="true">${zone}`
    + `<polyline points="${trace}" fill="none" stroke="${ton}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>`
    + `<circle cx="${fx.toFixed(1)}" cy="${fy.toFixed(1)}" r="2.2" fill="${ton}"/></svg>`;
}

/**
 * Barre de proportion en SVG : segments à plat, un ton par segment, libellés
 * portés par le HTML voisin (jamais par la couleur seule).
 * @param {Array<{cle:string, n:number, ton:string}>} segments
 */
export function ruban(segments, { hauteur = 8, ecart = 2 } = {}) {
  const total = segments.reduce((s, x) => s + (x.n || 0), 0);
  if (!total) return '';
  let x = 0;
  const morceaux = [];
  const largeur = 1000;
  const visibles = segments.filter(s => s.n > 0);
  const libre = largeur - ecart * (visibles.length - 1);
  for (const s of visibles) {
    const w = Math.max(3, libre * s.n / total);
    morceaux.push(`<rect x="${x.toFixed(1)}" y="0" width="${w.toFixed(1)}" height="${hauteur}" fill="${s.ton}" data-cle="${s.cle}"><title>${s.libelle || s.cle} : ${s.n}</title></rect>`);
    x += w + ecart;
  }
  return `<svg class="ruban" viewBox="0 0 ${largeur} ${hauteur}" preserveAspectRatio="none" height="${hauteur}" width="100%" aria-hidden="true">${morceaux.join('')}</svg>`;
}

/** Tableau HTML depuis { colonnes, lignes } ; nombres alignés à droite.
 *  `triable` : les en-têtes deviennent des boutons de tri (voir activerTri). */
export function tableau(t, { max = 200, classe = 'tableau', triable = false } = {}) {
  if (!t || !t.colonnes || !t.colonnes.length) return '';
  const estNombre = (v) => typeof v === 'number' || v === '—' || (typeof v === 'string' && /^[−\-+]?[\d\s  ]+([,.]\d+)?\s?(%|M€|Md€|j|pt)?$/.test(v.trim()));
  const th = t.colonnes.map(c => `<th scope="col"${triable ? ' role="button" tabindex="0" title="Trier"' : ''}>${echapper(c)}</th>`).join('');
  const lignes = t.lignes.slice(0, max).map(l =>
    `<tr>${l.map((v, i) => `<td class="${estNombre(v) ? 'num' : ''}${i === 0 ? ' premiere' : ''}">${v === null || v === undefined ? '—' : echapper(v)}</td>`).join('')}</tr>`).join('');
  const reste = t.lignes.length > max ? `<caption class="tableau__reste">${t.lignes.length - max} lignes supplémentaires non affichées</caption>` : '';
  // Les tableaux du moteur portent la même feuille que les listes de dossiers.
  return `<div class="${classe}"><table class="donnees${triable ? ' triable' : ''}">${reste}<thead><tr>${th}</tr></thead><tbody>${lignes}</tbody></table></div>`;
}

/**
 * La valeur de tri d'une cellule : un nombre quand le texte en est un
 * (« 1 384 », « 5,6 Md€ » → 5600, « 28 % », « 18 j », « 15/05/2026 »), sinon
 * le texte lui-même. Même règle que dans le rapport HTML (export.py).
 */
export function valeurTri(texte) {
  const t = String(texte ?? '').replace(/[\s\u00a0\u202f]/g, '').replace('−', '-');
  if (t === '' || t === '—') return { n: -Infinity, s: '' };
  const date = t.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (date) return { n: Number(date[3] + date[2] + date[1]), s: t };
  const m = t.match(/^([-+]?\d+(?:[.,]\d+)?)(%|M€|Md€|j|pt)?/);
  if (!m) return { n: null, s: t.toLowerCase() };
  let n = Number(m[1].replace(',', '.'));
  if (m[2] === 'Md€') n *= 1000;
  return { n, s: t.toLowerCase() };
}

export function comparerTri(a, b) {
  if (a.n !== null && b.n !== null) return a.n - b.n;
  if (a.n !== null) return 1;
  if (b.n !== null) return -1;
  return a.s.localeCompare(b.s, 'fr');
}

/** Rend triables les tableaux `table.triable` d'un conteneur : un clic sur un
 *  en-tête trie, un second inverse. */
export function activerTri(racine) {
  for (const table of racine.querySelectorAll('table.triable')) {
    const ths = Array.from(table.querySelectorAll('thead th'));
    ths.forEach((th, i) => {
      const trier = () => {
        // Une colonne de nombres se lit d'abord du plus grand au plus petit,
        // une colonne de texte de A à Z ; un second clic inverse.
        const numerique = Array.from(table.tBodies[0].rows)
          .some(tr => tr.cells[i] && valeurTri(tr.cells[i].textContent).n !== null);
        const actuel = th.getAttribute('aria-sort');
        const sens = actuel ? (actuel === 'descending' ? 'ascending' : 'descending')
          : (numerique ? 'descending' : 'ascending');
        ths.forEach(x => x.removeAttribute('aria-sort'));
        th.setAttribute('aria-sort', sens);
        const tbody = table.tBodies[0];
        const lignes = Array.from(tbody.rows);
        const cle = (tr) => valeurTri(tr.cells[i] ? tr.cells[i].textContent : '');
        lignes.sort((a, b) => comparerTri(cle(a), cle(b)) * (sens === 'ascending' ? 1 : -1));
        for (const l of lignes) tbody.append(l);
      };
      th.addEventListener('click', trier);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); trier(); } });
    });
  }
}

export function echapper(v) {
  return String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
