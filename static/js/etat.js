// etat.js — l'état de l'application vit dans l'URL.
//
// ?ecran=rfp&periode=2025&pays=France&pays=Suisse&q=leman&dossier=1667
// Un lien copié rouvre exactement le même écran, le même périmètre, la même
// fiche. Le bouton « précédent » du navigateur fonctionne.

export const ECRANS = ['lecture', 'activite', 'rfp', 'dd', 'aum', 'esg', 'diagnostic', 'dossiers', 'donnees'];
const CLES_RESERVEES = new Set(['ecran', 'periode', 'date_min', 'date_max', 'q', 'dossier',
  'granularite', 'esg_mode', 'attention', 'bloc', 'section']);

export function etatVide() {
  return {
    ecran: 'lecture',
    periode: '12m',            // '12m' | '24m' | '36m' | 'tout' | '2025' | 'perso'
    date_min: null,            // pour 'perso'
    date_max: null,
    dims: {},                  // dimension → [valeurs]
    q: '',                     // recherche plein texte (écran dossiers)
    attention: false,          // liste « à relancer » seulement
    dossier: null,             // identifiant d'une fiche ouverte
    granularite: null,         // null = décidée par la durée
    esg_mode: 'part',
  };
}

/** Lit l'URL courante. `dimensions` : clés de dimension connues (meta.dimensions). */
export function lireURL(dimensions) {
  const e = etatVide();
  const p = new URLSearchParams(window.location.search);
  const ecran = p.get('ecran');
  if (ecran && ECRANS.includes(ecran)) e.ecran = ecran;
  if (p.get('periode')) e.periode = p.get('periode');
  e.date_min = p.get('date_min') || null;
  e.date_max = p.get('date_max') || null;
  if (e.date_min || e.date_max) e.periode = 'perso';
  e.q = p.get('q') || '';
  e.attention = p.get('attention') === '1';
  e.dossier = p.get('dossier') ? Number(p.get('dossier')) : null;
  e.granularite = p.get('granularite') || null;
  e.esg_mode = p.get('esg_mode') || 'part';
  for (const dim of Object.keys(dimensions || {})) {
    const valeurs = p.getAll(dim).filter(Boolean);
    if (valeurs.length) e.dims[dim] = [...new Set(valeurs)];
  }
  return e;
}

/** Paramètres d'URL pour un état (écran et périmètre). */
export function versParams(e, { sansEcran = false } = {}) {
  const p = new URLSearchParams();
  if (!sansEcran && e.ecran && e.ecran !== 'lecture') p.set('ecran', e.ecran);
  if (e.periode === 'perso') {
    if (e.date_min) p.set('date_min', e.date_min);
    if (e.date_max) p.set('date_max', e.date_max);
    p.set('periode', 'perso');
  } else if (e.periode && e.periode !== '12m') {
    p.set('periode', e.periode);
  }
  for (const [dim, valeurs] of Object.entries(e.dims || {})) {
    for (const v of valeurs) p.append(dim, v);
  }
  if (e.q) p.set('q', e.q);
  if (e.attention) p.set('attention', '1');
  if (e.dossier !== null && e.dossier !== undefined) p.set('dossier', String(e.dossier));
  if (e.granularite) p.set('granularite', e.granularite);
  if (e.esg_mode && e.esg_mode !== 'part') p.set('esg_mode', e.esg_mode);
  return p;
}

/** Paramètres pour /api/analyse, /api/dossiers, /api/rapport : le périmètre seul. */
export function paramsAPI(e) {
  const p = new URLSearchParams();
  p.set('periode', e.periode || '12m');
  if (e.periode === 'perso') {
    if (e.date_min) p.set('date_min', e.date_min);
    if (e.date_max) p.set('date_max', e.date_max);
  }
  for (const [dim, valeurs] of Object.entries(e.dims || {})) {
    for (const v of valeurs) p.append(dim, v);
  }
  if (e.granularite) p.set('granularite', e.granularite);
  if (e.esg_mode && e.esg_mode !== 'part') p.set('esg_mode', e.esg_mode);
  return p;
}

/** Signature du périmètre : change quand une nouvelle analyse est nécessaire. */
export function signaturePerimetre(e) {
  return paramsAPI(e).toString();
}

export function ecrireURL(e, { remplacer = false } = {}) {
  const p = versParams(e);
  const url = `${window.location.pathname}${p.toString() ? '?' + p.toString() : ''}`;
  if (url === window.location.pathname + window.location.search) return;
  if (remplacer) window.history.replaceState(null, '', url);
  else window.history.pushState(null, '', url);
}

/** Copie profonde minimale. */
export function cloner(e) {
  return { ...e, dims: Object.fromEntries(Object.entries(e.dims || {}).map(([k, v]) => [k, [...v]])) };
}

export function ajouterFiltre(e, dim, valeur) {
  const n = cloner(e);
  const liste = n.dims[dim] || (n.dims[dim] = []);
  if (!liste.includes(valeur)) liste.push(valeur);
  return n;
}

export function retirerFiltre(e, dim, valeur) {
  const n = cloner(e);
  if (!n.dims[dim]) return n;
  n.dims[dim] = valeur === undefined ? [] : n.dims[dim].filter(v => v !== valeur);
  if (!n.dims[dim].length) delete n.dims[dim];
  return n;
}

export function sansFiltres(e) {
  const n = cloner(e);
  n.dims = {};
  n.q = '';
  n.attention = false;
  return n;
}

export function nbFiltres(e) {
  return Object.values(e.dims || {}).reduce((s, v) => s + v.length, 0);
}

export { CLES_RESERVEES };
