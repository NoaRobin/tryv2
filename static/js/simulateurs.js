// simulateurs.js — les trois questions qu'un gérant se pose avant de chiffrer.
//
//   1. Combien ce mandat rapporte-t-il sur sa durée, s'il grossit ?   → projeter
//   2. Si le client demande un effort, quel levier coûte le moins ?  → leviers
//   3. À ce prix, quelle chance de l'emporter, et quel prix rapporte
//      le plus en espérance ?                                         → modeleGain
//
// Aucun accès au DOM : le module s'exécute aussi sous node, où l'auto-test de
// tarification.py le contrôle. Taux en %, encours en M€, frais en M€ par an.

import * as T from './tarif.js';

/* ------------------------------------------------------------------------- */
/*  1. La valeur du mandat dans le temps                                     */
/* ------------------------------------------------------------------------- */

/**
 * L'encours de chaque année et les frais qu'il paie : l'année 1 est le mandat
 * tel qu'on le chiffre aujourd'hui, puis l'encours croît de `croissance` par an
 * (marchés et flux nets confondus, en fraction : 0,03 = +3 %).
 * `fixe` : ce que paierait le même encours à un taux unique égal au taux moyen
 * d'aujourd'hui — la mesure de ce que la dégressivité rend au client.
 */
export function projeter(tranches, encours, { horizon = 5, croissance = 0 } = {}) {
  const tauxFixe = T.tauxMoyen(tranches, encours);
  const annees = [];
  let cumul = 0; let cumulFixe = 0;
  for (let n = 1; n <= horizon; n++) {
    const a = encours * (1 + croissance) ** (n - 1);
    const f = T.frais(tranches, a);
    const fixe = a * tauxFixe / 100;
    cumul += f; cumulFixe += fixe;
    annees.push({ annee: n, encours: a, frais: f, taux: T.tauxMoyen(tranches, a), fixe, cumul });
  }
  return { annees, total: cumul, totalFixe: cumulFixe, tauxFixe };
}

/** Ce qu'un encours doublé rapporte de plus : +100 % à taux fixe, moins si la grille est dégressive. */
export function elasticite(tranches, encours, facteur = 2) {
  const f = T.frais(tranches, encours);
  return f > 0 ? T.frais(tranches, encours * facteur) / f - 1 : NaN;
}

/** La tranche où tombe le dernier euro du client (celle qui fixe le prix du million suivant). */
export function trancheMarginale(tranches, encours) {
  for (let i = tranches.length - 1; i >= 0; i--) if (encours > tranches[i].minimum) return i;
  return 0;
}

/** La tranche qui facture le million suivant (à 150 M€ pile, celle qui commence à 150). */
export function trancheSuivante(tranches, encours) {
  for (let i = tranches.length - 1; i >= 0; i--) if (encours >= tranches[i].minimum) return i;
  return 0;
}

/* ------------------------------------------------------------------------- */
/*  2. Négocier : la même concession aujourd'hui, un coût très différent     */
/* ------------------------------------------------------------------------- */

const arrondiSeuil = (v) => Math.round(v);

/** La grille telle qu'elle s'écrit : seuils au M€, taux au millième de point. */
export function arrondirGrille(tranches) {
  return T.normaliser(tranches.map(t => ({
    minimum: arrondiSeuil(t.minimum),
    maximum: t.maximum === null || t.maximum === undefined ? null : arrondiSeuil(t.maximum),
    taux: T.arrondiBp(Math.max(0, t.taux)),
  })));
}

/**
 * Quatre façons de concéder `concession` points de taux moyen (0,01 = 1 pb) à la
 * taille d'aujourd'hui, et ce que chacune coûte sur la durée du mandat :
 *   uniforme  — le même effort relatif sur tous les taux ;
 *   marginale — seulement la tranche où tombe l'encours du client ;
 *   premiere  — seulement la première tranche ;
 *   seuils    — les seuils abaissés d'un même facteur, taux inchangés.
 * Le coût est calculé sur la grille ARRONDIE, celle qui s'appliquera : ce que
 * l'écran annonce est ce que « Appliquer » écrira.
 */
export function leviers(tranches, encours, concession, hypotheses = {}) {
  const base = T.normaliser(tranches);
  const F0 = T.frais(base, encours);
  const cible = F0 - concession * encours / 100;
  const projBase = projeter(base, encours, hypotheses);
  const im = trancheMarginale(base, encours);
  const partDe = (i) => Math.max(0, Math.min(encours, i === base.length - 1 ? Infinity : base[i].maximum) - base[i].minimum);
  const resultat = (cle, libelle, grille, detail) => {
    if (!grille) return { cle, libelle, faisable: false, detail };
    const g = arrondirGrille(grille);
    const proj = projeter(g, encours, hypotheses);
    return { cle, libelle, faisable: true, grille: g, detail,
      fraisAujourdhui: T.frais(g, encours), concessionReelle: (F0 - T.frais(g, encours)) / encours * 100,
      total: proj.total, cout: projBase.total - proj.total, annees: proj.annees };
  };
  const out = [];
  if (!(concession > 0) || !(F0 > 0) || cible < 0) {
    return { base: projBase, F0, cible, options: out, meilleur: null, im };
  }

  // Uniforme : chaque taux × k.
  const k = cible / F0;
  out.push(resultat('uniforme', 'Une remise sur tous les taux',
    base.map(t => ({ ...t, taux: t.taux * k })), { remise: 1 - k }));

  // La tranche marginale seule.
  {
    const part = partDe(im);
    const nv = part > 0 ? base[im].taux - (F0 - cible) / part * 100 : -1;
    out.push(resultat('marginale', `La tranche où tombe l’encours (T${im + 1})`,
      nv >= 0 ? base.map((t, i) => (i === im ? { ...t, taux: nv } : t)) : null,
      { tranche: im, avant: base[im].taux, apres: nv }));
  }

  // La première tranche seule (sauf si c'est déjà la marginale).
  if (im > 0) {
    const part = partDe(0);
    const nv = part > 0 ? base[0].taux - (F0 - cible) / part * 100 : -1;
    out.push(resultat('premiere', 'La première tranche (T1)',
      nv >= 0 ? base.map((t, i) => (i === 0 ? { ...t, taux: nv } : t)) : null,
      { tranche: 0, avant: base[0].taux, apres: nv }));
  }

  // Les seuils : facteur f < 1 tel que frais(seuils × f) = cible (dichotomie).
  if (base.length > 1) {
    const fr = (f) => T.frais(T.ajuster(base, 0, f), encours);
    let bas = 0.02; let haut = 1;
    if ((fr(bas) - cible) * (fr(haut) - cible) <= 0 && fr(bas) < fr(haut)) {
      for (let n = 0; n < 60; n++) { const m = (bas + haut) / 2; if (fr(m) > cible) haut = m; else bas = m; }
      const f = (bas + haut) / 2;
      out.push(resultat('seuils', 'Des seuils abaissés', T.ajuster(base, 0, f), { facteur: f }));
    } else {
      out.push(resultat('seuils', 'Des seuils abaissés', null, { facteur: NaN }));
    }
  }

  const faisables = out.filter(o => o.faisable).sort((a, b) => a.cout - b.cout);
  const autres = out.filter(o => !o.faisable);
  return { base: projBase, F0, cible, options: [...faisables, ...autres], meilleur: faisables[0] || null, im };
}

/* ------------------------------------------------------------------------- */
/*  3. Le prix et la chance de gagner                                        */
/* ------------------------------------------------------------------------- */
/*
 * Chaque décision passée (gagnée ou perdue) est ramenée à son écart de prix
 * avec le marché de SON expertise, à SON encours :
 *     x = ln(taux de l'offre / médiane des autres offres de l'expertise)
 * x = 0 : au prix médian ; x = ln 1,2 : 20 % plus cher. Ramener à l'écart rend
 * les expertises comparables, et permet de mettre en commun toutes les décisions.
 *
 * Modèle : P(gagner) = σ(a + b·x), ajusté au maximum a posteriori avec deux
 * a priori faibles (a autour du taux de succès observé, b autour de zéro), et
 * une contrainte économique : b ≤ 0 — toutes choses égales, être plus cher ne
 * fait pas gagner. Si les données disent le contraire, b vaut 0 et l'écran le
 * dit : le prix n'a pas départagé les issues.
 */

const sigma = (z) => 1 / (1 + Math.exp(-z));
const logit = (p) => Math.log(p / (1 - p));

/** Les décisions passées, chacune avec son écart au marché. */
export function decisions(offres, { minPairs = 2 } = {}) {
  const obs = [];
  for (const o of offres) {
    if (o.exclue || !(o.volume > 0) || !(o.issue === 'Gagné' || o.issue === 'Perdu')) continue;
    const pairs = offres.filter(p => !p.exclue && p.expertise_cle === o.expertise_cle && p.id !== o.id);
    if (pairs.length < minPairs) continue;
    const med = T.quantile(pairs.map(p => T.tauxMoyen(p.tranches, o.volume)), 0.5);
    const moi = T.tauxMoyen(o.tranches, o.volume);
    if (!(med > 0) || !(moi > 0)) continue;
    obs.push({ offre: o, x: Math.log(moi / med), gagne: o.issue === 'Gagné' ? 1 : 0, mediane: med, taux: moi });
  }
  return obs;
}

/** Newton sur (a, b) — ou sur a seul si b est imposé. */
function ajuster(obs, { a0, sa = 1.5, sb = 3, bImpose = null }) {
  let a = a0; let b = bImpose ?? 0;
  const libre = bImpose === null;
  for (let it = 0; it < 60; it++) {
    let ga = -(a - a0) / sa ** 2; let gb = libre ? -b / sb ** 2 : 0;
    let haa = -1 / sa ** 2; let hab = 0; let hbb = libre ? -1 / sb ** 2 : -1;
    for (const o of obs) {
      const p = sigma(a + b * o.x);
      const w = p * (1 - p);
      ga += o.gagne - p; haa -= w;
      if (libre) { gb += (o.gagne - p) * o.x; hab -= w * o.x; hbb -= w * o.x * o.x; }
    }
    let da; let db = 0;
    if (libre) {
      const det = haa * hbb - hab * hab;
      da = -(hbb * ga - hab * gb) / det;
      db = -(-hab * ga + haa * gb) / det;
    } else da = -ga / haa;
    a += da; b += db;
    if (Math.abs(da) < 1e-10 && Math.abs(db) < 1e-10) break;
  }
  // Covariance a posteriori (approximation de Laplace) : l'inverse de −Hessien.
  let haa = 1 / sa ** 2; let hab = 0; let hbb = libre ? 1 / sb ** 2 : 0;
  for (const o of obs) {
    const w = sigma(a + b * o.x) * (1 - sigma(a + b * o.x));
    haa += w; if (libre) { hab += w * o.x; hbb += w * o.x * o.x; }
  }
  let cov;
  if (libre) {
    const det = haa * hbb - hab * hab;
    cov = [[hbb / det, -hab / det], [-hab / det, haa / det]];
  } else cov = [[1 / haa, 0], [0, 0]];
  return { a, b, cov };
}

/** Les hypothèses de sensibilité : de combien de points la chance baisse à +20 % au-dessus du marché. */
export const SENSIBILITES = {
  donnees: { libelle: 'D’après vos décisions', b: null },
  faible: { libelle: 'Faible', b: -1.2, texte: 'environ 5 points de chance perdus à +20 % au-dessus du marché' },
  moyenne: { libelle: 'Moyenne', b: -2.8, texte: 'environ 12 points perdus à +20 %' },
  forte: { libelle: 'Forte', b: -6, texte: 'environ 25 points perdus à +20 %' },
};

/**
 * Le modèle, ajusté sur les décisions. `sensibilite` : 'donnees' (b estimé)
 * ou une hypothèse (b imposé, a recalé sur le taux de succès observé).
 */
export function modeleGain(obs, sensibilite = 'donnees') {
  const n = obs.length;
  const gagnes = obs.reduce((s, o) => s + o.gagne, 0);
  const pBase = (gagnes + 1) / (n + 2);                 // Laplace : jamais 0 ni 100 %
  const a0 = logit(pBase);
  const hyp = SENSIBILITES[sensibilite] || SENSIBILITES.donnees;
  let m; let contraint = false;
  if (hyp.b === null) {
    m = ajuster(obs, { a0 });
    if (m.b > 0) { m = ajuster(obs, { a0, bImpose: 0 }); contraint = true; }
  } else {
    m = ajuster(obs, { a0, bImpose: hyp.b });
  }
  const sb = Math.sqrt(Math.max(0, m.cov[1][1]));
  // Le prix « départage » si, même au bord favorable de l'incertitude, b reste négatif.
  const demontre = hyp.b === null && !contraint && m.b + 1.64 * sb < 0;
  const xs = obs.map(o => o.x);
  return { ...m, n, gagnes, pBase, contraint, demontre, sensibilite: hyp.b === null ? 'donnees' : sensibilite,
    xMin: xs.length ? Math.min(...xs) : 0, xMax: xs.length ? Math.max(...xs) : 0 };
}

/** P(gagner) à l'écart x, et sa bande à 90 % (sur l'échelle logit). */
export function probabilite(m, x) {
  const eta = m.a + m.b * x;
  const v = m.cov[0][0] + 2 * x * m.cov[0][1] + x * x * m.cov[1][1];
  const e = 1.64 * Math.sqrt(Math.max(0, v));
  return { p: sigma(eta), bas: sigma(eta - e), haut: sigma(eta + e) };
}

/**
 * Le revenu espéré selon le prix : chance de gagner × frais sur la durée.
 * La grille garde sa forme, tous ses taux suivent le même facteur ; le prix se
 * lit en écart à la médiane du marché à la taille du client.
 * On ne cherche l'optimum que là où des décisions existent : au-delà, le modèle
 * extrapolerait, et l'écran le montre hachuré.
 */
export function revenuEspere(m, { xActuel, valeurActuelle, domaine = null, pas = 121 }) {
  const lo = domaine ? domaine[0] : Math.max(Math.log(0.5), m.xMin - 0.15);
  const hi = domaine ? domaine[1] : Math.min(Math.log(2), m.xMax + 0.15);
  const points = [];
  for (let i = 0; i < pas; i++) {
    const x = lo + (hi - lo) * i / (pas - 1);
    const pr = probabilite(m, x);
    const valeur = valeurActuelle * Math.exp(x - xActuel);
    points.push({ x, ...pr, valeur, espere: pr.p * valeur });
  }
  const dans = points.filter(p => p.x >= m.xMin - 1e-9 && p.x <= m.xMax + 1e-9);
  const meilleur = (dans.length ? dans : points).reduce((a, b) => (b.espere > a.espere ? b : a));
  const aLaBorne = dans.length > 1 && (meilleur.x >= m.xMax - 1e-9 || meilleur.x <= m.xMin + 1e-9);
  const actuel = probabilite(m, xActuel);
  return { points, meilleur, aLaBorne, actuel: { x: xActuel, ...actuel, valeur: valeurActuelle,
    espere: actuel.p * valeurActuelle }, domaine: [lo, hi] };
}
