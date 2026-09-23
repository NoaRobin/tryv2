// tarif.js — le calcul du prix, en miroir exact de tarification.py.
//
// Aucun accès au DOM : le module s'exécute aussi sous node, où l'auto-test du
// moteur Python vérifie que les deux calculs donnent les mêmes nombres.
// Taux en pour cent (0,12 veut dire 0,12 %), encours en M€, frais en M€ par an.
// La dernière tranche d'une grille s'applique au-delà de son plafond.

/** Frais annuels en M€ pour un encours en M€ (barème progressif). */
export function frais(tranches, encours) {
  if (encours === null || encours === undefined || !Number.isFinite(encours) || encours <= 0
      || !tranches || !tranches.length) return 0;
  let total = 0;
  const dernier = tranches.length - 1;
  for (let i = 0; i < tranches.length; i++) {
    const t = tranches[i];
    const haut = (i === dernier || t.maximum === null || t.maximum === undefined) ? Infinity : t.maximum;
    const part = Math.min(encours, haut) - t.minimum;
    if (part > 0) total += part * t.taux / 100;
  }
  return total;
}

/** Taux moyen en % ; à encours nul, le taux de la tranche qui contient zéro. */
export function tauxMoyen(tranches, encours) {
  if (!tranches || !tranches.length) return NaN;
  if (encours === null || encours === undefined || !Number.isFinite(encours) || encours <= 0) {
    return tranches[0].minimum <= 0 ? tranches[0].taux : 0;
  }
  return frais(tranches, encours) / encours * 100;
}

/** Taux appliqué à la seule part d'encours comprise entre bas et haut. */
export function tauxMarginal(tranches, bas, haut) {
  if (haut <= bas) return tauxMoyen(tranches, bas);
  return (frais(tranches, haut) - frais(tranches, bas)) / (haut - bas) * 100;
}

/** Tranche de comparaison d'une tranche ouverte « au-delà de bas ». */
export function hautDeTrancheOuverte(bas, encoursClient) {
  return Math.max(2 * bas, bas + 50, encoursClient || 0);
}

/** Interpolation linéaire, comme numpy.quantile. */
export function quantile(valeurs, q) {
  const x = valeurs.filter(v => v !== null && v !== undefined && Number.isFinite(v)).sort((a, b) => a - b);
  if (!x.length) return NaN;
  const h = (x.length - 1) * q;
  const bas = Math.floor(h);
  const haut = Math.min(bas + 1, x.length - 1);
  return x[bas] + (h - bas) * (x[haut] - x[bas]);
}

/** Part des valeurs sous v, les égalités comptant pour moitié (0 à 100). */
export function centile(valeurs, v) {
  const x = valeurs.filter(u => u !== null && u !== undefined && Number.isFinite(u));
  if (!x.length || v === null || v === undefined || !Number.isFinite(v)) return NaN;
  let dessous = 0; let egales = 0;
  for (const u of x) {
    if (u < v - 1e-12) dessous++;
    else if (Math.abs(u - v) <= 1e-12) egales++;
  }
  return 100 * (dessous + 0.5 * egales) / x.length;
}

export function resume(valeurs) {
  const x = valeurs.filter(v => v !== null && v !== undefined && Number.isFinite(v));
  if (!x.length) return { n: 0 };
  return { n: x.length, min: Math.min(...x), p25: quantile(x, 0.25), mediane: quantile(x, 0.5),
    p75: quantile(x, 0.75), max: Math.max(...x), moyenne: x.reduce((s, v) => s + v, 0) / x.length };
}

/* ------------------------------------------------------------------------- */
/*  La grille simulée                                                        */
/* ------------------------------------------------------------------------- */

/**
 * Une grille saisie devient une grille calculable : tranches triées, bornes
 * jointives (chaque tranche commence où finit la précédente), dernière ouverte.
 */
export function normaliser(lignes) {
  const t = lignes
    .map(l => ({ minimum: +l.minimum || 0, maximum: l.maximum === null || l.maximum === '' ? null : +l.maximum,
      taux: Math.max(0, +l.taux || 0) }))
    .sort((a, b) => a.minimum - b.minimum);
  if (!t.length) return [{ minimum: 0, maximum: null, taux: 0 }];
  t[0].minimum = 0;
  for (let i = 0; i < t.length - 1; i++) t[i].maximum = t[i + 1].minimum;
  t[t.length - 1].maximum = null;
  return t;
}

/** Les deux leviers de négociation : taux × (1 + remise), seuils × facteur. */
export function ajuster(tranches, remise, facteurSeuils) {
  const k = 1 + remise;
  return tranches.map(t => ({
    minimum: t.minimum * facteurSeuils,
    maximum: t.maximum === null || t.maximum === undefined ? null : t.maximum * facteurSeuils,
    taux: t.taux * k,
  }));
}

/* ------------------------------------------------------------------------- */
/*  Ce qui a déjà été fait                                                   */
/* ------------------------------------------------------------------------- */

/** Le taux moyen de chaque offre passée, à un encours donné. */
export function fourchetteTaille(grilles, encours) {
  const valeurs = grilles.map(g => ({ g, v: tauxMoyen(g.tranches, encours) }));
  const toutes = valeurs.map(x => x.v);
  const par = (issue) => valeurs.filter(x => x.g.issue === issue).map(x => x.v);
  return { ...resume(toutes), valeurs, gagnes: resume(par('Gagné')), perdus: resume(par('Perdu')),
    enCours: resume(par('En cours')) };
}

/** Ce que les offres passées facturaient sur la même part d'encours. */
export function fourchetteTranche(grilles, bas, haut) {
  return resume(grilles.map(g => tauxMarginal(g.tranches, bas, haut)));
}

/** Bornes de comparaison de chaque tranche d'une grille (la dernière est ouverte). */
export function tranchesDeComparaison(tranches, encoursClient) {
  return tranches.map((t, i) => {
    const ouverte = i === tranches.length - 1;
    return { bas: t.minimum, haut: ouverte ? hautDeTrancheOuverte(t.minimum, encoursClient) : t.maximum, ouverte };
  });
}

/**
 * Grille de référence d'une expertise : aux seuils donnés, le taux médian que
 * les offres passées appliquaient sur chaque tranche.
 */
export function grilleReference(grilles, seuils, encoursClient) {
  const s = [...seuils].sort((a, b) => a - b);
  return s.map((bas, i) => {
    const ouverte = i === s.length - 1;
    const haut = ouverte ? hautDeTrancheOuverte(bas, encoursClient) : s[i + 1];
    const r = fourchetteTranche(grilles, bas, haut);
    return { minimum: bas, maximum: ouverte ? null : s[i + 1], taux: r.n ? arrondiBp(r.mediane) : 0 };
  });
}

/** Au dixième de point de base : 0,093 % se lit dans une grille, 0,09342 % non. */
export function arrondiBp(taux) {
  return Math.round(taux * 1000) / 1000;
}
