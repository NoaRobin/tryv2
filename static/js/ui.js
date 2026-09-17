// ui.js — fabrique d'éléments et composants partagés par les écrans.
// Aucun framework : des fonctions qui rendent des nœuds DOM.

import { entier, decimal, pourcent, euros, date as fmtDate, dateCourte, pluriel, NBSP } from './format.js';
import { sparkline } from './figures.js';

/** h('div.classe', {attr}, enfants…) — l'unique fabrique d'éléments. */
export function h(selecteur, attributs, ...enfants) {
  const [balise, ...classes] = String(selecteur).split('.');
  const el = document.createElement(balise || 'div');
  if (classes.length) el.className = classes.join(' ');
  if (attributs && (typeof attributs !== 'object' || attributs instanceof Node || Array.isArray(attributs))) {
    enfants.unshift(attributs);
  } else if (attributs) {
    for (const [k, v] of Object.entries(attributs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'html') el.innerHTML = v;
      else if (k === 'texte') el.textContent = v;
      else if (k === 'classe') el.className += ' ' + v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  for (const enfant of enfants.flat(3)) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    el.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return el;
}

export function vider(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

/** Un nombre cliquable dans la prose : filet sous le chiffre, jamais une couleur. */
export function nombre(texte, action, titre) {
  if (!action) return h('span.num', { texte });
  return h('button.nombre', { type: 'button', texte, title: titre || undefined, onclick: action });
}

/** Assemble une phrase : chaînes et nœuds mêlés. */
export function phrase(...morceaux) {
  return h('span', {}, ...morceaux);
}

/* ------------------------------------------------------------- faits ----- */
/**
 * Liste de faits : libellé, valeur, variation avec son mot, définition.
 * Une variation ne se lit pas à sa couleur — signe, flèche et mot.
 */
export function faits(kpis, { surClic, colonnes = 2 } = {}) {
  const liste = h('div.faits', { style: colonnes === 1 ? { gridTemplateColumns: 'minmax(0,1fr)' } : null });
  for (const k of kpis) {
    const cliquable = surClic && k.cible;
    const el = h(cliquable ? 'a.fait' : 'div.fait', {
      href: cliquable ? '#' : null,
      title: k.aide || null,
      onclick: cliquable ? (e) => { e.preventDefault(); surClic(k); } : null,
    });
    el.append(h('span.fait__label', { texte: k.libelle }));
    el.append(h('span.fait__valeur', { texte: k.affichage }));
    const bas = h('span.fait__bas');
    if (k.delta_affichage) bas.append(delta(k));
    if (k.detail) bas.append(h('span.fait__detail', { texte: k.detail }));
    if (k.serie && k.serie.length >= 3) {
      bas.insertAdjacentHTML('beforeend', sparkline(k.serie, { largeur: 74, hauteur: 18 }));
    }
    el.append(bas);
    liste.append(el);
  }
  return liste;
}

const FLECHES = { hausse: '▲', baisse: '▼', plat: '' };
const MOTS = { bon: 'favorable', mauvais: 'défavorable', neutre: '' };

/** La variation d'un indicateur : flèche, valeur, et le mot du moteur. */
export function delta(k) {
  const fleche = FLECHES[k.delta_direction] || '';
  const mot = MOTS[k.delta_sens] || '';
  return h('span.fait__delta', {},
    fleche ? fleche + NBSP : '', k.delta_affichage,
    h('span', { texte: mot ? ` · ${mot} sur la période précédente` : ' sur la période précédente' }));
}

/* ------------------------------------------------------------ carnet ----- */
/**
 * Le carnet : deux rubans (un trait par dossier, puis les encours) et cinq
 * colonnes nommées. Le ton aide, le libellé et la valeur disent.
 */
// Ce qui est encore chez nous est hachuré ; ce qui n’a pas abouti est un
// contour. Deux états de plus, distingués sans une seconde couleur.
const TEXTURES = { en_cours: 'texture-redaction', sans_suite: 'texture-sanssuite' };

export function carnet(donnees, compartiments, tons, { surClic } = {}) {
  const bloc = h('div.carnet');
  const total = compartiments.reduce((s, c) => s + (donnees.compartiments[c.cle]?.n || 0), 0);
  const totalEncours = compartiments.reduce((s, c) => s + (donnees.compartiments[c.cle]?.encours || 0), 0);

  const rubans = h('div.carnet__rubans');
  for (const [cle, titre, champ, totalChamp] of [['dossiers', 'Dossiers', 'n', total],
    ['encours', 'Encours', 'encours', totalEncours]]) {
    const ligne = h('div.carnet__ligne', {}, h('span.cle', { texte: titre }));
    const ruban = h('div.carnet__ruban');
    for (const c of compartiments) {
      const v = donnees.compartiments[c.cle]?.[champ] || 0;
      if (v <= 0) continue;
      ruban.append(h('i.carnet__seg', {
        classe: TEXTURES[c.cle] || '',
        style: { flex: String(v), background: tons[c.cle], minWidth: '3px' },
        title: `${c.libelle} : ${champ === 'n' ? entier(v) + ' dossiers' : euros(v)}`,
      }));
    }
    ligne.append(ruban);
    rubans.append(ligne);
  }
  bloc.append(rubans);

  const colonnes = h('div.carnet__colonnes');
  for (const c of compartiments) {
    const d = donnees.compartiments[c.cle] || { n: 0, encours: 0 };
    const col = h(surClic ? 'a.carnet__col' : 'div.carnet__col', {
      href: surClic ? '#' : null,
      onclick: surClic ? (e) => { e.preventDefault(); surClic(c.cle, c); } : null,
    });
    col.append(h('span.carnet__col-tete', {},
      h('i.carnet__pastille', { classe: TEXTURES[c.cle] || '',
        style: { background: tons[c.cle] } }),
      h('span.carnet__nom', { texte: c.libelle })));
    col.append(h('span.carnet__n', { texte: entier(d.n) }));
    col.append(h('span.carnet__encours', { texte: euros(d.encours) }));
    col.append(h('span.carnet__sens', { texte: c.sens }));
    colonnes.append(col);
  }
  bloc.append(colonnes);
  return bloc;
}

/** Les identités : ce que vaut exactement un chiffre, calculé par le moteur. */
export function identites(liste) {
  if (!liste || !liste.length) return null;
  const bloc = h('div.identites');
  for (const i of liste) {
    // La réserve de lecture s'écrit sous l'égalité, comme dans le rapport.
    bloc.append(h('div.identite', {},
      h('span.identite__g', { texte: i.grandeur }),
      h('span.identite__v', {}, h('b', { texte: i.valeur }), ' = ', i.egalite, '.',
        i.note ? h('span.identite__n', { texte: i.note }) : null)));
  }
  return bloc;
}

/* ------------------------------------------------------------ tableau ---- */
/**
 * Tableau de dossiers. `colonnes` : [{cle, titre, num, rendu(ligne)}].
 * Une ligne entière est cliquable quand `surLigne` est fourni.
 */
export function tableDossiers(lignes, colonnes, { surLigne, legende } = {}) {
  const table = h('table.donnees');
  if (legende) table.append(h('caption', { texte: legende }));
  const thead = h('thead');
  const tr = h('tr');
  for (const c of colonnes) tr.append(h('th', { scope: 'col', classe: c.num ? 'num' : '', texte: c.titre }));
  thead.append(tr); table.append(thead);
  const tbody = h('tbody');
  for (const l of lignes) {
    const ligne = h('tr', surLigne ? { 'data-clic': '1', tabindex: '0', role: 'button' } : {});
    for (const c of colonnes) {
      const contenu = c.rendu ? c.rendu(l) : (l[c.cle] ?? '—');
      ligne.append(h('td', { classe: (c.num ? 'num' : '') + (c.attenue ? ' attenue' : '') },
        contenu instanceof Node ? contenu : String(contenu)));
    }
    if (surLigne) {
      ligne.addEventListener('click', () => surLigne(l));
      ligne.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); surLigne(l); }
      });
    }
    tbody.append(ligne);
  }
  table.append(tbody);
  return h('div.tableau', {}, table);
}

/** Nom d'un dossier sur deux lignes : le client, puis son contexte. */
export function cellulesNom(d, champs = ['pays', 'classe_actifs']) {
  const sous = champs.map(c => d[c]).filter(v => v && v !== 'Non renseigné').join(' · ');
  return h('span', {},
    h('span.cellule-nom', { texte: d.client || 'Client non renseigné' }),
    sous ? h('span.cellule-sous', { texte: sous }) : null);
}

/** Jauge d'attente : un trait plein sur un filet. Au-delà du seuil, encrée. */
export function jauge(valeur, maxi, { seuil } = {}) {
  const part = maxi > 0 ? Math.min(1, (valeur || 0) / maxi) : 0;
  const alerte = seuil !== undefined && valeur > seuil;
  return h('span.jauge' + (alerte ? '.jauge--alerte' : ''), {
    role: 'img', 'aria-label': `${entier(valeur)} jours`,
  }, h('i', { style: { width: `${(part * 100).toFixed(1)}%` } }));
}

/* ----------------------------------------------------------- messages ---- */
export function message(texte, { sobre = false, actions } = {}) {
  const el = h('div.message' + (sobre ? '.message--sobre' : ''), {}, texte);
  if (actions) el.append(' ', ...actions);
  return el;
}

export function chargement(texte = 'Calcul en cours…') {
  return h('p.chargement', { texte, role: 'status', 'aria-live': 'polite' });
}

/** Lien sobre : un mot souligné d'un filet, pas un bouton. */
export function lien(texte, action, options = {}) {
  return h('button.lien-sobre', { type: 'button', texte, onclick: action, ...options });
}

/* -------------------------------------------------------------- divers --- */
export function svgFleche() {
  return 'data:image/svg+xml,';
}

/** Annonce polie pour les lecteurs d'écran (recalcul, filtre posé…). */
let zoneAnnonce = null;
export function annoncer(texte) {
  if (!zoneAnnonce) {
    zoneAnnonce = h('div', {
      'aria-live': 'polite', 'aria-atomic': 'true',
      style: { position: 'absolute', width: '1px', height: '1px', overflow: 'hidden', clip: 'rect(0 0 0 0)' },
    });
    document.body.append(zoneAnnonce);
  }
  zoneAnnonce.textContent = texte;
}

export { entier, decimal, pourcent, euros, fmtDate, dateCourte, pluriel };
