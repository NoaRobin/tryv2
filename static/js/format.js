// format.js — nombres, dates et accords en français. Aucune dépendance.
// Les chiffres AFFICHÉS viennent du moteur déjà formatés (kpi.affichage) ;
// ces fonctions servent aux compléments calculés côté écran (listes, fiches).

const NBSP = ' ';       // espace insécable : avant les unités
const FINE = ' ';       // espace fine insécable : séparateur de milliers, avant %

export function entier(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  return Math.round(Number(x)).toLocaleString('fr-FR').replace(/[\s  ]/g, FINE);
}

export function decimal(x, n = 1, unite = '') {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  const s = Number(x).toLocaleString('fr-FR', { minimumFractionDigits: n, maximumFractionDigits: n })
    .replace(/[\s  ]/g, FINE);
  return unite ? `${s}${NBSP}${unite}` : s;
}

export function pourcent(x, n = 0) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  return `${decimal(Number(x) * 100, n)}${FINE}%`;
}

export function euros(x, court = true) {
  // Les montants du moteur sont en millions d'euros.
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  const v = Number(x);
  if (court && Math.abs(v) >= 1000) return decimal(v / 1000, v >= 10000 ? 0 : 1, 'Md€');
  return decimal(v, 0, 'M€');
}

export function jours(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  return `${entier(x)}${NBSP}j`;
}

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONG = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
  'septembre', 'octobre', 'novembre', 'décembre'];

export function date(iso) {
  if (!iso) return '—';
  const [a, m, j] = String(iso).slice(0, 10).split('-').map(Number);
  if (!a || !m || !j) return '—';
  return `${String(j).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}`;
}

export function dateCourte(iso) {
  if (!iso) return '—';
  const [a, m, j] = String(iso).slice(0, 10).split('-').map(Number);
  if (!a || !m || !j) return '—';
  return `${j} ${MOIS[m - 1]} ${a}`;
}

export function dateLongue(iso) {
  if (!iso) return '—';
  const [a, m, j] = String(iso).slice(0, 10).split('-').map(Number);
  if (!a || !m || !j) return '—';
  return `${j === 1 ? '1er' : j} ${MOIS_LONG[m - 1]} ${a}`;
}

export function pluriel(n, mot, formePluriel = null) {
  const v = Math.round(Number(n) || 0);
  const forme = v > 1 ? (formePluriel || `${mot}s`) : mot;
  return `${entier(v)}${NBSP}${forme}`;
}

export function accord(n) {
  return Math.round(Number(n) || 0) > 1 ? 's' : '';
}

// Clé de comparaison tolérante : minuscules, sans accent, sans ponctuation de
// séparation. Même règle que core._cle, pour que la commande comprenne
// « leman » comme le moteur.
export function cle(texte) {
  return String(texte ?? '')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().trim()
    .replace(/[\s_\-./']+/g, ' ')
    .replace(/\s+/g, ' ').trim();
}

export { NBSP, FINE, MOIS, MOIS_LONG };
