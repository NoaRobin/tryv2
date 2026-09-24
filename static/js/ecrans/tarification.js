// tarification.js — le simulateur de prix des appels d'offres.
//
// Les questions d'un gérant avant de chiffrer un mandat, dans l'ordre où il
// se les pose : quelle grille (le tableau), comment le client la paie
// (l'escalier), où elle se situe (le marché), quelle chance de gagner à ce
// prix, ce que le mandat rapporte sur sa durée, et comment céder un effort au
// moindre coût. Tout suit la frappe. Calcul : static/js/tarif.js (miroir de
// tarification.py) et static/js/simulateurs.js.

import { h, vider, lien, entier, message, chargement, annoncer } from '../ui.js';
import * as api from '../api.js';
import * as T from '../tarif.js';
import * as SIM from '../simulateurs.js';
import { creerEscalier } from '../escalier.js';
import { courbeTarif, jaugeMarche, bandeTranche, legendeIssues, courbeGain, courbeValeur, fmtEcartPct,
  fmtTaux, fmtPb, fmtFrais, fmtEcartFrais, fmtM, fmtCentile, plafondJoli } from '../graphes-tarif.js';
import { NBSP, decimal, dateCourte } from '../format.js';

const MEMOIRE = 'tarif.simulateur.v2';
const TAILLES_REFERENCE = [25, 50, 100, 150, 250, 500];
const ISSUES = [['Gagné', 'Gagnées'], ['Perdu', 'Perdues'], ['En cours', 'En cours']];
const MOINS = '−';

let S = null;            // l'état du simulateur
let R = {};              // les zones qui se mettent à jour
let numero = 0;

/* ======================================================================= */
export function rendreTarification(ctx) {
  const ecran = h('div.ecran.tarif');
  ecran.append(chargement('Lecture des grilles…'));
  demarrer(ecran, ctx);
  return ecran;
}

async function demarrer(ecran, ctx) {
  let donnees;
  try {
    donnees = await api.get('/api/tarif');
  } catch (e) {
    vider(ecran).append(message(`Les grilles n’ont pas pu être lues : ${e.message}`));
    return;
  }
  S = etatInitial(donnees);
  R = {};
  numero = 0;
  vider(ecran);
  construire(ecran, ctx);
  maj();
}

function etatInitial(donnees) {
  const exps = donnees.expertises.filter(e => e.n > 0);
  const annees = donnees.annees;
  const s = {
    donnees,
    expertise: exps.length ? exps[0].cle : (donnees.expertises[0] || {}).cle,
    encours: 150,
    lignes: donnees.grille_type.map(t => ({ ...t })),
    origine: 'la grille type de la présentation (page 2)',
    filtres: { de: annees[0] ?? null, a: annees[annees.length - 1] ?? null,
      issues: new Set(donnees.issues), natures: new Set(donnees.natures) },
    // Les hypothèses du mandat : durée et croissance de l'encours (marchés + flux).
    horizon: 5, croissance: 0.03,
    concession: 0.01,          // l'effort demandé par le client, en points de taux (0,01 = 1 pb)
    sensibilite: 'auto',
    comparerOuvert: false,
    toutes: false,
    tri: { cle: 'annee', sens: -1 },
    mesure: 'mediane',
  };
  // Le travail en cours se retrouve au retour : une commodité du navigateur,
  // jamais une donnée du produit.
  try {
    const m = JSON.parse(localStorage.getItem(MEMOIRE) || 'null');
    if (m && Array.isArray(m.lignes) && m.lignes.length && donnees.expertises.some(e => e.cle === m.expertise)) {
      s.lignes = T.normaliser(m.lignes);
      s.encours = Number(m.encours) > 0 ? Number(m.encours) : s.encours;
      s.expertise = m.expertise;
      s.origine = m.origine || 'votre dernière simulation';
      if (Number(m.horizon) >= 1 && Number(m.horizon) <= 10) s.horizon = Number(m.horizon);
      if (Number.isFinite(Number(m.croissance))) s.croissance = Number(m.croissance);
      if (Number(m.concession) > 0) s.concession = Number(m.concession);
      if (m.sensibilite && (m.sensibilite === 'auto' || SIM.SENSIBILITES[m.sensibilite])) s.sensibilite = m.sensibilite;
    }
  } catch (e) { /* stockage indisponible : on repart de la grille type */ }
  s.lignes = T.normaliser(s.lignes);
  return s;
}

function memoriser() {
  try {
    localStorage.setItem(MEMOIRE, JSON.stringify({ lignes: S.lignes, encours: S.encours, expertise: S.expertise,
      origine: S.origine, horizon: S.horizon, croissance: S.croissance, concession: S.concession, sensibilite: S.sensibilite }));
  } catch (e) { /* stockage indisponible : sans conséquence */ }
}

/* ------------------------------------------------------------- calculs --- */
const libelleExpertise = (cle) => (S.donnees.expertises.find(e => e.cle === cle) || {}).libelle || cle;

function passeHorsIssue(o) {
  const f = S.filtres;
  if (o.annee !== null && o.annee !== undefined && f.de !== null && (o.annee < f.de || o.annee > f.a)) return false;
  if (S.donnees.natures.length > 1 && o.nature && !f.natures.has(o.nature)) return false;
  return true;
}
const passe = (o) => passeHorsIssue(o) && S.filtres.issues.has(o.issue);

function eligibles(cle = S.expertise) {
  return S.donnees.offres.filter(o => !o.exclue && o.expertise_cle === cle && passe(o));
}

// Les décisions passées ne dépendent que des filtres : calculées une fois par réglage.
let cacheDecisions = { cle: null, obs: [] };
function decisionsPassees() {
  const cle = JSON.stringify([S.filtres.de, S.filtres.a, [...S.filtres.natures].sort(), S.donnees.offres.length]);
  if (cacheDecisions.cle !== cle) {
    const obs = SIM.decisions(S.donnees.offres.filter(passeHorsIssue));
    for (const d of obs) d.titre = `${d.offre.libelle} · ${d.offre.expertise} · ${d.offre.annee ?? '—'}`;
    cacheDecisions = { cle, obs };
  }
  return cacheDecisions.obs;
}

const hypotheses = () => ({ horizon: S.horizon, croissance: S.croissance });

function calculer() {
  const grille = T.normaliser(S.lignes);
  const elig = eligibles();
  const A = S.encours;
  const tm = T.tauxMoyen(grille, A);
  const fr = T.frais(grille, A);
  const marche = T.fourchetteTaille(elig, A);
  const centile = T.centile(marche.valeurs.map(x => x.v), tm);
  const comparaisons = T.tranchesDeComparaison(grille, A)
    .map(c => ({ ...c, resume: T.fourchetteTranche(elig, c.bas, c.haut) }));
  const projection = SIM.projeter(grille, A, hypotheses());
  const im = SIM.trancheMarginale(grille, A);

  // La chance de gagner : en automatique, les données si elles parlent, sinon une hypothèse moyenne, dite.
  const obs = decisionsPassees();
  let gain = null;
  if (obs.length >= 5 && marche.n && marche.mediane > 0 && tm > 0) {
    let modele = SIM.modeleGain(obs, S.sensibilite === 'auto' ? 'donnees' : S.sensibilite);
    let repli = false;
    if (S.sensibilite === 'auto' && !modele.demontre) { modele = SIM.modeleGain(obs, 'moyenne'); repli = true; }
    const xActuel = Math.log(tm / marche.mediane);
    const courbe = SIM.revenuEspere(modele, { xActuel, valeurActuelle: projection.total,
      domaine: [Math.log(0.5), Math.log(2)] });
    const plat = modele.b === 0;
    gain = { obs, modele, repli, xActuel, courbe, plat, mediane: marche.mediane,
      tauxDe: (x) => marche.mediane * Math.exp(x) };
  }
  const negociation = SIM.leviers(grille, A, S.concession, hypotheses());
  return { grille, elig, A, tm, fr, marche, centile, comparaisons, projection, im, gain, obs, negociation };
}

/** Le centile d'une offre parmi ses pairs de l'expertise, à son propre encours. */
function positionOffre(o) {
  if (!o.volume || o.exclue) return NaN;
  const pairs = S.donnees.offres.filter(p => !p.exclue && p.expertise_cle === o.expertise_cle && p.id !== o.id);
  if (pairs.length < 2) return NaN;
  return T.centile(pairs.map(p => T.tauxMoyen(p.tranches, o.volume)), o.taux_volume);
}

/* ============================================================ gabarit === */
function bloc(cle, titre, corps, marge, { large = false } = {}) {
  const b = h(`section.bloc${large ? '.bloc--large' : ''}`, { id: `bloc-${cle}` });
  const g = h('div.bloc__corps');
  g.append(h('div.bloc__tete', {},
    h('span.bloc__num', { texte: String(++numero).padStart(2, '0') }),
    h('span.cle.cle--ink', { texte: titre })));
  for (const x of [corps].flat()) if (x) g.append(x);
  b.append(g);
  b.append(h('div.bloc__marge', {}, ...[marge].flat().filter(Boolean)));
  return b;
}

function margeTexte(titre, ...paragraphes) {
  return [titre ? h('div.marge-titre', { texte: titre }) : null,
    ...paragraphes.filter(Boolean).map(p => (p instanceof Node ? p : h('p.marge-texte', { html: p })))]
    .filter(Boolean);
}

/** Un écart de taux, sa valeur et son sens : { valeur: '4,0 pb', sens: 'sous' }. */
function ecart(e) {
  if (!Number.isFinite(e) || Math.abs(e) < 0.0005) return { valeur: null, sens: 'au niveau de' };
  return { valeur: fmtPb(Math.abs(e)).replace('+', ''), sens: e < 0 ? 'sous' : 'au-dessus de' };
}

const pluriel2 = (n, mot, pluriel = null) => `${entier(n)}${NBSP}${n > 1 ? (pluriel || `${mot}s`) : mot}`;
const capitale = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const pct = (p) => `${Math.round(p * 100)}${NBSP}%`;
const pctSigne = (f) => { const v = Math.round(f * 1000) / 10; return `${v > 0 ? '+' : (v < 0 ? MOINS : '')}${decimal(Math.abs(v), Math.abs(v) < 10 && v % 1 ? 1 : 0)}${NBSP}%`; };

/** « moins chère que 71 % des offres » — la phrase complète se lit seule. */
function cherete(c) {
  if (!Number.isFinite(c)) return 'sans comparaison possible avec les offres';
  if (c >= 99.5) return 'plus chère que toutes les offres';
  if (c <= 0.5) return 'moins chère que toutes les offres';
  return c >= 50 ? `plus chère que ${Math.round(c)}${NBSP}% des offres` : `moins chère que ${Math.round(100 - c)}${NBSP}% des offres`;
}

/** Le rang court d'un tableau : « 29e centile », ou les deux extrêmes en mots. */
function positionCourte(c) {
  if (!Number.isFinite(c)) return '—';
  if (c >= 99.5) return 'la plus chère';
  if (c <= 0.5) return 'la moins chère';
  return fmtCentile(c);
}

/* -------------------------------------------------------- saisie des nombres --- */
// Les cases acceptent « 0,12 » comme « 0.12 » : on écrit en français, on lit les deux.
const lireNombre = (texte) => {
  const t = String(texte).trim().replace(/\s|%|M€/g, '').replace(',', '.').replace(MOINS, '-');
  return t === '' ? NaN : Number(t);
};
const ecrireNombre = (v, decimales = 3) => {
  if (!Number.isFinite(v)) return '';
  const r = Math.round(v * 10 ** decimales) / 10 ** decimales;
  return String(r).replace('.', ',').replace('-', MOINS);
};

/** Une case numérique : saisie libre, flèches pour le pas, validation visible, jamais bloquante. */
function caseNombre({ valeur, pas, decimales, min = -Infinity, max = Infinity, largeur, etiquette, surValeur }) {
  const champ = h('input.saisie', { type: 'text', inputmode: 'decimal', autocomplete: 'off', spellcheck: 'false',
    value: ecrireNombre(valeur, decimales), 'aria-label': etiquette, style: largeur ? { width: largeur } : null });
  const accepter = (v) => {
    const ok = Number.isFinite(v) && v >= min && v <= max;
    champ.setAttribute('aria-invalid', String(!ok));
    if (ok) surValeur(v);
    return ok;
  };
  champ.addEventListener('input', () => accepter(lireNombre(champ.value)));
  champ.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const courant = Number.isFinite(lireNombre(champ.value)) ? lireNombre(champ.value) : valeur;
      const v = Math.min(max, Math.max(min, Math.round((courant + (e.key === 'ArrowUp' ? 1 : -1) * pas * (e.shiftKey ? 10 : 1)) / pas) * pas));
      champ.value = ecrireNombre(v, decimales);
      accepter(v);
    } else if (e.key === 'Enter') { e.preventDefault(); champ.blur(); }
  });
  champ.addEventListener('change', () => champ.dispatchEvent(new CustomEvent('reformer')));
  champ.poser = (v) => { valeur = v; if (document.activeElement !== champ) { champ.value = ecrireNombre(v, decimales); champ.setAttribute('aria-invalid', 'false'); } };
  champ.addEventListener('blur', () => { champ.value = ecrireNombre(valeur, decimales); champ.setAttribute('aria-invalid', 'false'); });
  return champ;
}

/* ============================================================ construction === */
function construire(ecran, ctx) {
  R.ctx = ctx;
  const ouverture = h('div.lecture.ouverture');
  R.lede = h('p.lede');
  R.matin = h('p.matin');
  ouverture.append(h('div', {}, R.lede, R.matin));
  R.margeOuverture = h('div.marge-col');
  ouverture.append(R.margeOuverture);
  ecran.append(ouverture);

  ecran.append(barreReglages());
  ecran.append(blocGrille());
  ecran.append(blocEscalier());
  ecran.append(blocMarche());
  ecran.append(blocGain());
  ecran.append(blocValeur());
  ecran.append(blocNegocier());
  ecran.append(blocExpertises());
  ecran.append(blocOffres());
  ecran.append(blocClasseur());
}

/* ----------------------------------------------------- barre de réglages --- */
function poserEncours(v, source = null) {
  if (!(v > 0)) return;
  S.encours = Math.round(v);
  if (source !== R.champEncours) R.champEncours.poser(S.encours);
  if (source !== R.curseurEncours) R.curseurEncours.value = versCurseur(S.encours);
  majPlanifiee();
}

function barreReglages() {
  const barre = h('div.reglages', { role: 'region', 'aria-label': 'Réglages du simulateur' });
  R.tuiles = h('div.tuiles', { role: 'group', 'aria-label': 'Expertise' });
  barre.append(R.tuiles);

  const ligne = h('div.reglages__ligne');
  // Le mandat : sa taille (saisie ou curseur logarithmique), sa durée, sa croissance.
  R.champEncours = caseNombre({ valeur: S.encours, pas: 5, decimales: 0, min: 1, max: 100000, largeur: '76px',
    etiquette: 'Taille du mandat en millions d’euros', surValeur: (v) => poserEncours(v, R.champEncours) });
  R.curseurEncours = h('input.curseur', { type: 'range', min: 0, max: 1000, step: 1, 'aria-label': 'Taille du mandat',
    value: versCurseur(S.encours) });
  R.curseurEncours.addEventListener('input', () => poserEncours(deCurseur(Number(R.curseurEncours.value)), R.curseurEncours));
  ligne.append(h('label.reglage', {}, h('span.reglage__c', { texte: 'Mandat' }),
    h('span.reglage__v', {}, R.champEncours, h('span.unite', { texte: 'M€' }), R.curseurEncours)));

  const duree = h('select.saisie', { 'aria-label': 'Durée du mandat en années',
    onchange: (e) => { S.horizon = Number(e.target.value); maj(); } });
  for (let n = 1; n <= 10; n++) duree.append(h('option', { value: n, texte: `${n} an${n > 1 ? 's' : ''}`, selected: n === S.horizon ? '' : null }));
  ligne.append(h('label.reglage', {}, h('span.reglage__c', { texte: 'Durée' }), h('span.reglage__v', {}, duree)));

  R.champCroissance = caseNombre({ valeur: S.croissance * 100, pas: 0.5, decimales: 1, min: -30, max: 50, largeur: '58px',
    etiquette: 'Croissance annuelle de l’encours en pour cent', surValeur: (v) => { S.croissance = v / 100; majPlanifiee(); } });
  ligne.append(h('label.reglage', { title: 'Marchés et flux nets confondus : une hypothèse, pas une prévision' },
    h('span.reglage__c', { texte: 'Croissance' }),
    h('span.reglage__v', {}, R.champCroissance, h('span.unite', { texte: '% par an' }))));
  barre.append(ligne);

  // Les offres comparées : un résumé qui s'ouvre sur ses filtres.
  R.resumeComparer = h('button.lien-sobre.comparer__resume', { type: 'button', 'aria-expanded': String(S.comparerOuvert),
    onclick: () => { S.comparerOuvert = !S.comparerOuvert; majComparer(); } });
  R.filtres = h('div.reglages__ligne.comparer__filtres');
  barre.append(h('div.comparer', {}, R.resumeComparer, R.filtres));
  peindreFiltres();
  return barre;
}

function peindreFiltres() {
  const ligne = R.filtres;
  vider(ligne);
  const annees = S.donnees.annees;
  if (annees.length) {
    const sel = (valeur, surChange) => {
      const s = h('select.saisie', { onchange: (e) => surChange(Number(e.target.value)) });
      for (const a of annees) s.append(h('option', { value: a, texte: String(a), selected: a === valeur ? '' : null }));
      return s;
    };
    const de = sel(S.filtres.de, (v) => { S.filtres.de = Math.min(v, S.filtres.a); maj({ offres: true }); });
    const a = sel(S.filtres.a, (v) => { S.filtres.a = Math.max(v, S.filtres.de); maj({ offres: true }); });
    ligne.append(h('span.reglage', {}, h('span.reglage__c', { texte: 'Offres de' }),
      h('span.reglage__v', {}, de, h('span.unite', { texte: 'à' }), a)));
  }
  const puces = h('span.reglage__v');
  for (const [issue, texte] of ISSUES) {
    if (!S.donnees.issues.includes(issue)) continue;
    const b = h('button.puce-filtre', { type: 'button', 'aria-pressed': String(S.filtres.issues.has(issue)),
      onclick: () => {
        if (S.filtres.issues.has(issue) && S.filtres.issues.size === 1) return;   // jamais zéro offre par clic
        if (S.filtres.issues.has(issue)) S.filtres.issues.delete(issue); else S.filtres.issues.add(issue);
        b.setAttribute('aria-pressed', String(S.filtres.issues.has(issue)));
        maj({ offres: true });
      } }, h('span', { classe: `forme forme--${issue === 'Gagné' ? 'gagne' : (issue === 'Perdu' ? 'perdu' : 'cours')}` }), texte);
    puces.append(b);
  }
  ligne.append(h('span.reglage', {}, h('span.reglage__c', { texte: 'Issue' }), puces));
  if (S.donnees.natures.length > 1) {
    const n = h('span.reglage__v');
    for (const nat of S.donnees.natures) {
      const b = h('button.puce-filtre', { type: 'button', 'aria-pressed': String(S.filtres.natures.has(nat)), texte: nat,
        onclick: () => {
          if (S.filtres.natures.has(nat) && S.filtres.natures.size === 1) return;
          if (S.filtres.natures.has(nat)) S.filtres.natures.delete(nat); else S.filtres.natures.add(nat);
          b.setAttribute('aria-pressed', String(S.filtres.natures.has(nat)));
          maj({ offres: true });
        } });
      n.append(b);
    }
    ligne.append(h('span.reglage', {}, h('span.reglage__c', { texte: 'Client' }), n));
  }
}

function majComparer() {
  const n = eligibles().length;
  const issues = S.filtres.issues.size === S.donnees.issues.length ? 'toutes issues'
    : [...S.filtres.issues].map(i => i.toLowerCase()).join(', ');
  const annees = S.filtres.de !== null ? (S.filtres.de === S.filtres.a ? `${S.filtres.de}` : `${S.filtres.de} → ${S.filtres.a}`) : '';
  R.resumeComparer.textContent = `Comparé à ${pluriel2(n, 'offre')} ${libelleExpertise(S.expertise)} · ${[annees, issues].filter(Boolean).join(' · ')} ${S.comparerOuvert ? '▴' : '▾'}`;
  R.resumeComparer.setAttribute('aria-expanded', String(S.comparerOuvert));
  R.filtres.hidden = !S.comparerOuvert;
}

const versCurseur = (v) => Math.round((Math.log(Math.max(5, Math.min(1000, v)) / 5) / Math.log(200)) * 1000);
const deCurseur = (u) => {
  const v = 5 * 200 ** (u / 1000);
  return v < 100 ? Math.round(v) : Math.round(v / 5) * 5;
};

function peindreTuiles() {
  vider(R.tuiles);
  for (const e of S.donnees.expertises) {
    const n = eligibles(e.cle).length;
    R.tuiles.append(h('button.tuile', { type: 'button', 'aria-pressed': String(e.cle === S.expertise),
      disabled: e.n === 0 ? '' : null, title: e.n === 0 ? 'Aucune offre exploitable' : null,
      onclick: () => { S.expertise = e.cle; maj({ offres: true }); } },
      h('span.tuile__nom', { texte: e.libelle }), h('span.tuile__n', { texte: entier(n) })));
  }
}

/* ============================================================ 01 grille === */
function blocGrille() {
  const outils = h('div.outils-grille');
  const depart = h('div.outils-grille__depart');
  depart.append(h('span.cle', { texte: 'Partir de' }));
  depart.append(h('button.bouton.bouton--sobre.bouton--petit', { type: 'button', texte: 'La grille type',
    title: 'La grille de simulation de la présentation : 0,12 / 0,09 / 0,07 / 0,05 %',
    onclick: () => charger(S.donnees.grille_type, 'la grille type de la présentation (page 2)') }));
  R.boutonReference = h('button.bouton.bouton--sobre.bouton--petit', { type: 'button',
    onclick: () => {
      const ref = T.grilleReference(eligibles(), S.donnees.seuils_reference, S.encours);
      charger(ref, `la référence ${libelleExpertise(S.expertise)} (médiane des offres, tranche par tranche)`);
    } });
  depart.append(R.boutonReference);
  R.choixOffre = h('select.saisie.saisie--offre', { 'aria-label': 'Partir d’une offre passée',
    onchange: (e) => {
      const o = S.donnees.offres.find(x => x.id === e.target.value);
      e.target.value = '';
      if (o) partirDe(o);
    } });
  depart.append(R.choixOffre);
  outils.append(depart);
  outils.append(h('div.outils-grille__export', {},
    lien('Copier', copierGrille, { title: 'Copier la grille pour la coller dans Word ou Excel' }),
    lien('Exporter (CSV)', exporterGrille)));

  R.tableGrille = h('table.grille-tarif');
  R.enteteClient = h('th', { texte: 'Chez ce client' });
  R.enteteFrais = h('th.num', { texte: 'Frais par an' });
  R.tableGrille.append(h('thead', {}, h('tr', {},
    h('th', { texte: 'Tranche' }), h('th', { texte: 'Part d’encours (M€)' }), h('th.num', { texte: 'Taux (%)' }),
    R.enteteClient, R.enteteFrais, h('th', { texte: 'Face au marché, sur la même part' }), h('th', { 'aria-label': 'Actions' }))));
  R.corpsGrille = h('tbody');
  R.tableGrille.append(R.corpsGrille);
  R.piedGrille = h('tfoot');
  R.tableGrille.append(R.piedGrille);
  R.lectureGrille = h('p.lecture-grille');
  R.origine = h('p.note.grille-origine');

  return bloc('grille', 'La grille', [outils, h('div.tableau', {}, R.tableGrille), R.lectureGrille, R.origine], margeTexte('Lecture',
    'Chaque taux ne s’applique qu’à la <b>part de l’encours</b> qui tombe dans sa tranche, comme un barème progressif ; la dernière tranche vaut au-delà de son seuil.',
    '<b>Chez ce client</b> : ce que son encours met dans chaque tranche. <b>Face au marché</b> : ce que les offres passées de l’expertise facturaient sur la même part — la bande va du plus bas au plus haut, le trait est la médiane, le point est votre taux.',
    'Les cases acceptent 0,12 comme 0.12. Flèches haut et bas : ±0,005 point de taux ou ±5 M€ (Maj : ×10). ✂ coupe une tranche en deux.'), { large: true });
}

function modifiee() { S.origine = `${S.origine.replace(/, modifiée$/, '')}, modifiée`; }

function charger(tranches, origine) {
  S.lignes = T.normaliser(tranches.map(t => ({ ...t })));
  S.origine = origine;
  peindreGrille();
  maj();
  annoncer(`Grille chargée : ${origine}.`);
}

function partirDe(o) {
  S.expertise = o.expertise_cle;
  if (o.volume) { S.encours = Math.round(o.volume); R.champEncours.poser(S.encours); R.curseurEncours.value = versCurseur(S.encours); }
  charger(o.tranches, `l’offre ${o.libelle} ${o.annee ?? ''} (${o.issue.toLowerCase()}), à son encours de ${fmtM(o.volume)}`.replace(/\s+/g, ' '));
  maj({ offres: true });
}

/** Déplace le seuil entre les tranches i et i+1, sans jamais croiser ses voisins. */
function poserSeuil(i, v) {
  const bas = S.lignes[i].minimum + 1;
  const haut = i + 2 < S.lignes.length ? S.lignes[i + 1].maximum - 1 : Infinity;
  if (!Number.isFinite(v) || v < bas || v > haut) return false;
  S.lignes[i].maximum = v; S.lignes[i + 1].minimum = v;
  modifiee();
  return true;
}

/** La grille entière se redessine (structure) ; la frappe ne met à jour que les calculs. */
function peindreGrille() {
  vider(R.corpsGrille);
  R.lignesGrille = S.lignes.map((t, i) => {
    const derniere = i === S.lignes.length - 1;
    const tr = h('tr');
    tr.append(h('td.grille-tarif__nom', { texte: `T${i + 1}` }));
    const part = h('td.grille-tarif__part');
    const de = h('span.num', { texte: entier(t.minimum) });
    let champMax = null;
    if (derniere) {
      part.append(de, h('span.attenue', { texte: `${NBSP}et au-delà` }));
    } else {
      champMax = caseNombre({ valeur: t.maximum, pas: 5, decimales: 0, min: 0, largeur: '64px',
        etiquette: `Seuil haut de la tranche ${i + 1} en M€`,
        surValeur: (v) => { if (poserSeuil(i, v)) { R.lignesGrille[i + 1].de.textContent = entier(v); maj({ source: 'grille' }); } else champMax.setAttribute('aria-invalid', 'true'); } });
      part.append(de, h('span.fleche-part', { texte: ' → ' }), champMax);
    }
    tr.append(part);
    const champTaux = caseNombre({ valeur: t.taux, pas: 0.005, decimales: 3, min: 0, max: 5, largeur: '64px',
      etiquette: `Taux de la tranche ${i + 1} en pour cent`,
      surValeur: (v) => { S.lignes[i].taux = v; modifiee(); maj({ source: 'grille' }); } });
    tr.append(h('td.num', {}, champTaux));
    const client = h('td.grille-tarif__client');
    const frais = h('td.num.grille-tarif__frais');
    const marche = h('td.grille-tarif__marche');
    tr.append(client, frais, marche);
    const actions = h('td.grille-tarif__actions');
    actions.append(h('button.croix', { type: 'button', 'aria-label': `Couper la tranche ${i + 1} en deux`, title: 'Couper en deux', texte: '✂',
      onclick: () => couperTranche(i) }));
    if (S.lignes.length > 1) {
      actions.append(h('button.croix', { type: 'button', 'aria-label': `Retirer la tranche ${i + 1}`, title: 'Retirer (la tranche voisine l’absorbe)', texte: '×',
        onclick: () => {
          S.lignes.splice(i, 1);
          S.lignes = T.normaliser(S.lignes);
          modifiee();
          peindreGrille(); maj();
        } }));
    }
    tr.append(actions);
    R.corpsGrille.append(tr);
    return { tr, de, champMax, champTaux, client, marche, frais };
  });
}

/** Coupe une tranche en deux au milieu (la dernière, au double de son seuil) ; même taux des deux côtés. */
function couperTranche(i) {
  const t = S.lignes[i];
  const derniere = i === S.lignes.length - 1;
  const milieu = derniere ? Math.max(t.minimum * 2, t.minimum + 50) : (t.minimum + t.maximum) / 2;
  const seuil = Math.round(milieu / 5) * 5;
  if (seuil <= t.minimum || (!derniere && seuil >= t.maximum)) { annoncer('Tranche trop étroite pour être coupée.'); return; }
  S.lignes.splice(i + 1, 0, { minimum: seuil, maximum: derniere ? null : t.maximum, taux: t.taux });
  S.lignes[i].maximum = seuil;
  S.lignes = T.normaliser(S.lignes);
  modifiee();
  peindreGrille(); maj();
  annoncer(`Tranche ${i + 1} coupée à ${seuil} M€.`);
}

function ajouterTranche() {
  const der = S.lignes[S.lignes.length - 1];
  const seuil = Math.round(Math.max(der.minimum * 2, der.minimum + 50) / 5) * 5;
  const marche = T.fourchetteTranche(eligibles(), seuil, T.hautDeTrancheOuverte(seuil, S.encours));
  der.maximum = seuil;
  S.lignes.push({ minimum: seuil, maximum: null, taux: marche.n ? T.arrondiBp(marche.mediane) : der.taux });
  S.lignes = T.normaliser(S.lignes);
  modifiee();
  peindreGrille(); maj();
  annoncer(`Tranche ajoutée au-delà de ${seuil} M€.`);
}

/** Où tombe un taux dans la fourchette d'une tranche, en mots : jamais par la couleur seule. */
function verdict(r, taux) {
  if (!r.n) return null;
  const e = 0.0005;
  if (taux < r.min - e) return 'sous le plus bas';
  if (taux > r.max + e) return 'au-dessus du plus haut';
  if (Math.abs(taux - r.mediane) <= e) return 'à la médiane';
  return taux < r.mediane ? 'sous la médiane' : 'au-dessus de la médiane';
}

function majGrille(D) {
  const domaine = plafondJoli(Math.max(...D.comparaisons.map(c => (c.resume.n ? c.resume.max : 0)),
    ...D.grille.map(t => t.taux), 0.05) * 1.08, 4);
  R.enteteClient.textContent = `Chez ce client (${entier(D.A)} M€)`;
  D.comparaisons.forEach((c, i) => {
    const l = R.lignesGrille[i];
    if (!l) return;
    const t = D.grille[i];
    l.de.textContent = entier(t.minimum);
    if (l.champMax) l.champMax.poser(t.maximum);
    l.champTaux.poser(t.taux);
    // Ce que l'encours du client met dans la tranche : une barre remplie à proportion de la tranche.
    const derniere = i === D.grille.length - 1;
    const part = Math.max(0, Math.min(D.A, derniere ? Infinity : t.maximum) - t.minimum);
    const largeur = derniere ? null : t.maximum - t.minimum;
    const remplissage = derniere ? (part > 0 ? 1 : 0) : Math.min(1, part / largeur);
    vider(l.client).append(
      h('span.part-client', { 'aria-hidden': 'true' }, h('i', { style: { width: `${Math.round(remplissage * 100)}%` } })),
      h('span.part-client__v', { texte: part > 0 ? `${entier(part)} M€${!derniere && remplissage >= 1 ? ' · pleine' : ''}` : 'non atteinte' }));
    l.client.classList.toggle('attenue', !(part > 0));
    const f = part * t.taux / 100;
    vider(l.frais).append(h('b', { texte: part > 0 ? fmtFrais(f) : '—' }),
      ...(part > 0 && D.fr > 0 ? [h('span.cellule-sous', { texte: `${Math.round((f / D.fr) * 100)}${NBSP}% du total` })] : []));
    vider(l.marche);
    if (c.resume.n) {
      l.marche.append(bandeTranche(c.resume, t.taux, domaine));
      l.marche.append(h('span.cellule-sous', {}, h('b', { texte: verdict(c.resume, t.taux) }),
        ` · ${fmtTaux(c.resume.min, { unite: false })}–${fmtTaux(c.resume.max, { unite: false })}, méd. ${fmtTaux(c.resume.mediane, { unite: false })}`));
      if (Math.abs(t.taux - c.resume.mediane) >= 0.0005) {
        l.marche.append(h('button.lien-sobre.lien-sobre--mini', { type: 'button',
          title: `Appliquer la médiane pratiquée sur cette tranche (${fmtTaux(c.resume.mediane)})`, texte: '→ médiane',
          onclick: () => { S.lignes[i].taux = T.arrondiBp(c.resume.mediane); modifiee(); maj(); } }));
      }
    } else {
      l.marche.append(h('span.attenue', { texte: 'aucune offre comparable' }));
    }
  });
  vider(R.piedGrille);
  R.piedGrille.append(h('tr', {},
    h('td', { colspan: 2 }, h('button.lien-sobre', { type: 'button', texte: '+ Ajouter une tranche au-delà', onclick: ajouterTranche })),
    h('td.num.grille-tarif__total', {}, h('b', { texte: fmtTaux(D.tm) })),
    h('td.grille-tarif__total.attenue', { texte: 'taux moyen payé' }),
    h('td.num.grille-tarif__total', {}, h('b', { texte: fmtFrais(D.fr) })),
    h('td.grille-tarif__total.attenue', { texte: `HT par an, pour ${entier(D.A)} M€` }),
    h('td')));
  const is = SIM.trancheSuivante(D.grille, D.A);
  R.lectureGrille.replaceChildren(`Le million suivant paie `, h('b', { texte: fmtTaux(D.grille[is].taux) }),
    ` (T${is + 1}) : c’est le taux qui compte si le mandat grossit. Un encours doublé rapporterait ${pctSigne(SIM.elasticite(D.grille, D.A))} de frais.`);
  R.origine.textContent = `Grille partie de ${S.origine}. Les montants sont hors taxes.`;
  R.boutonReference.textContent = `La référence ${libelleExpertise(S.expertise)}`;
  vider(R.choixOffre);
  R.choixOffre.append(h('option', { value: '', texte: 'Une offre passée…' }));
  for (const o of D.elig) {
    R.choixOffre.append(h('option', { value: o.id,
      texte: `${o.libelle} · ${o.annee ?? '—'} · ${o.issue} · ${fmtM(o.volume)} · ${fmtTaux(o.taux_volume)}` }));
  }
}

function lignesExport() {
  const D = calculer();
  const n = (v) => String(v).replace('.', ',');
  const lignes = [[`Grille simulée — ${libelleExpertise(S.expertise)}, mandat de ${D.A} M€ (frais HT)`],
    ['Tranche', 'De (M€)', 'À (M€)', 'Taux (%)', `Frais à ${D.A} M€ (k€ HT par an)`]];
  D.grille.forEach((t, i) => {
    const part = Math.max(0, Math.min(D.A, t.maximum ?? Infinity) - t.minimum);
    lignes.push([`T${i + 1}`, n(t.minimum), t.maximum === null ? 'et au-delà' : n(t.maximum), n(t.taux),
      n(Math.round(part * t.taux * 10))]);                       // M€ × % / 100 × 1 000 = k€
  });
  lignes.push(['Taux moyen', '', '', n(Math.round(D.tm * 10000) / 10000), n(Math.round(D.fr * 1000))]);
  return lignes;
}

function exporterGrille() {
  const csv = '﻿' + lignesExport().map(l => l.join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = h('a', { href: url, download: `grille_${S.expertise.replace(/\s+/g, '-')}_${S.encours}M.csv` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function copierGrille() {
  try {
    await navigator.clipboard.writeText(lignesExport().map(l => l.join('\t')).join('\n'));
    annoncer('Grille copiée : elle se colle dans Word ou Excel.');
  } catch (e) {
    annoncer('La copie a été refusée par le navigateur : utilisez l’export CSV.');
  }
}

/* ========================================================== 02 escalier === */
function blocEscalier() {
  R.phraseEscalier = h('p.prose.prose--bloc');
  R.boutonGrandir = h('button.bouton.bouton--sobre.bouton--petit', { type: 'button', texte: '▶ Faire grandir le mandat',
    onclick: () => {
      if (R.escalier.enCourse()) { R.escalier.arreter(); return; }
      R.boutonGrandir.textContent = '■ Arrêter';
      R.escalier.grandir({ fin: () => { R.boutonGrandir.textContent = '▶ Faire grandir le mandat'; } });
    } });
  R.escalier = creerEscalier({
    surEncours: (v) => poserEncours(v),
    surTaux: (i, v) => { if (Math.abs(S.lignes[i].taux - v) < 1e-9) return; S.lignes[i].taux = v; modifiee(); majPlanifiee(); },
    surSeuil: (i, v) => { if (S.lignes[i].maximum === v) return; if (poserSeuil(i, v)) majPlanifiee(); },
  });
  const legende = h('div.legende-tarif', {},
    h('span.legende-tarif__item', {}, h('span.aplat.aplat--paye'), 'ce que paie le client'),
    h('span.legende-tarif__item', {}, h('span.trait.trait--fort'), 'votre grille'),
    h('span.legende-tarif__item', {}, h('span.trait.trait--tirets'), 'médiane du marché'),
    h('span.legende-tarif__item', {}, h('span.aplat.aplat--clair'), 'marché, du plus bas au plus haut'),
    h('span.legende-tarif__item', {}, h('span.trait.trait--pointille'), 'taux moyen'));
  const commandes = h('div.figure-commandes', {}, legende, R.boutonGrandir);
  return bloc('escalier', 'L’escalier des frais', [R.phraseEscalier, commandes, R.escalier.el], margeTexte('Lire l’escalier',
    'Chaque <b>marche</b> est une tranche : sa largeur est la part d’encours qu’elle couvre, sa hauteur son taux. La <b>surface foncée</b>, à gauche du curseur, est ce que paie le client : largeur × hauteur, marche par marche.',
    'Derrière chaque marche, la <b>bande grise</b> : ce que le marché facturait sur la même part d’encours. Le pointillé est le taux moyen — il descend à chaque marche franchie.',
    '<b>Tout se tire</b> : le haut d’une marche change son taux, son bord déplace le seuil, le curseur change la taille du mandat. Au clavier : Tab puis les flèches.',
    '« Faire grandir le mandat » fait courir l’encours de zéro à la droite de la figure : on voit la surface se remplir et le taux moyen baisser.'), { large: true });
}

function majEscalier(D) {
  vider(R.phraseEscalier);
  const morceaux = [];
  D.grille.forEach((t, i) => {
    const derniere = i === D.grille.length - 1;
    const part = Math.max(0, Math.min(D.A, derniere ? Infinity : t.maximum) - t.minimum);
    if (part > 0) morceaux.push(`${fmtFrais(part * t.taux / 100)} sur ${i === 0 ? 'ses' : 'les'} ${entier(part)} ${i === 0 ? 'premiers' : 'suivants'} M€`);
  });
  R.phraseEscalier.append(`À ${entier(D.A)} M€, le client paie `, h('b', { texte: `${fmtFrais(D.fr)} par an` }), ' ');
  R.phraseEscalier.append(h('span.attenue', { texte: morceaux.length > 1 ? `: ${morceaux.join(', ')}.` : '.' }));
  R.escalier.maj({ grille: D.grille, encours: D.A, marche: D.comparaisons.map(c => c.resume) });
}

/* ============================================================ 03 marché === */
function blocMarche() {
  R.phraseMarche = h('p.prose.prose--bloc');
  R.zoneJauge = h('div');
  R.pointsMarche = h('p.note.repere-marche');
  R.zoneCourbe = h('div');
  R.legendeCourbe = h('div.legende-tarif');
  return bloc('marche', 'Face au marché', [R.phraseMarche, R.zoneJauge, legendeIssues(), R.pointsMarche,
    h('div.sous-titre', { texte: 'À toutes les tailles de mandat' }), R.legendeCourbe, R.zoneCourbe],
  margeTexte('Lecture',
    'Chaque carré est une offre déjà faite, <b>appliquée à la taille de votre mandat</b> : le prix qu’elle aurait donné à ce client. Plein : gagnée. Creux : perdue. À moitié : en cours. Un clic ouvre sa fiche.',
    'Bande claire : du plus bas au plus haut. Bande foncée : la moitié centrale. Trait : la médiane.',
    'Dessous, la <b>dégressivité</b> : le taux moyen selon la taille, votre grille en trait épais contre la bande du marché. C’est la lecture des consultants, qui comparent les grilles à 50, 100, 250 ou 500 M€.'));
}

function majMarche(D) {
  const f = D.marche;
  const exp = libelleExpertise(S.expertise);
  vider(R.phraseMarche);
  if (!f.n) {
    R.phraseMarche.append(`Aucune offre ${exp} ne correspond aux réglages : élargissez les années ou l’issue.`);
  } else {
    R.phraseMarche.append(`À ${entier(D.A)} M€, les ${pluriel2(f.n, 'offre')} ${exp} donneraient de `);
    R.phraseMarche.append(h('b', { texte: fmtTaux(f.min) }), ' à ', h('b', { texte: fmtTaux(f.max) }), '. ');
    R.phraseMarche.append(`Votre grille, à ${fmtTaux(D.tm)}, est ${cherete(D.centile)}.`);
    if (f.gagnes.n && f.perdus.n) {
      const e = ecart(f.gagnes.mediane - f.perdus.mediane);
      R.phraseMarche.append(h('span.attenue', { texte: !e.valeur
        ? ' Gagnées et perdues se tiennent au même prix : ici, le prix n’a pas départagé.'
        : ` Les offres gagnées étaient ${e.sens === 'sous' ? 'moins' : 'plus'} chères que les perdues, de ${e.valeur} en médiane.` }));
    }
  }
  const titre = (g) => `${g.libelle} · ${g.annee ?? '—'}`;
  const params = { marche: { ...f, valeurs: f.valeurs.map(x => ({ ...x, titre: titre(x.g) })) }, moi: D.tm,
    encours: D.A, surOffre: (g) => ouvrirOffre(g.id) };
  if (!R.jauge) { R.jauge = jaugeMarche(params); R.zoneJauge.append(R.jauge.el); } else R.jauge.maj(params);
  const morceaux = [];
  if (f.gagnes.n) {
    const e = ecart(D.tm - f.gagnes.mediane);
    morceaux.push(`médiane des gagnées ${fmtTaux(f.gagnes.mediane)}, votre grille ${e.valeur ? `${e.valeur} ${e.sens === 'sous' ? 'en dessous' : 'au-dessus'}` : 'au même niveau'}`);
  }
  if (f.perdus.n) morceaux.push(`médiane des perdues ${fmtTaux(f.perdus.mediane)}`);
  R.pointsMarche.textContent = morceaux.length ? `${capitale(morceaux.join(' · '))}.` : '';

  const pts = D.elig.filter(o => o.volume).map(o => ({ x: o.volume, y: o.taux_volume, issue: o.issue,
    titre: `${o.libelle} · ${o.annee ?? '—'}`, id: o.id }));
  const xMax = plafondJoli(Math.max(D.A * 1.8, ...pts.map(p => p.x * 1.1), 200), 5);
  const pc = { grille: D.grille, eligibles: D.elig, encours: D.A, xMax, points: pts,
    libelleExpertise: exp, surPoint: (p) => ouvrirOffre(p.id) };
  if (!R.courbe) { R.courbe = courbeTarif(pc); R.zoneCourbe.append(R.courbe.el); } else R.courbe.maj(pc);
  vider(R.legendeCourbe);
  const item = (classe, texte) => h('span.legende-tarif__item', {}, h('span', { classe }), texte);
  R.legendeCourbe.append(item('trait trait--fort', 'Votre grille'), item('trait trait--moyen', 'Médiane'),
    item('trait trait--pointille', 'Moyenne'), item('aplat aplat--clair', 'Plus bas – plus haut'),
    item('aplat aplat--fonce', 'Moitié centrale'));
}

/* ======================================================= 04 chance de gain === */
function blocGain() {
  R.phraseGain = h('p.prose.prose--bloc');
  R.noteGain = h('p.note.note-gain');
  R.sensibilites = h('div.groupe-puces', { role: 'group', 'aria-label': 'Sensibilité au prix' });
  R.actionGain = h('span.figure-commandes__droite');
  R.zoneGain = h('div');
  return bloc('gain', 'Le prix et la chance de gagner', [R.phraseGain, R.noteGain,
    h('div.figure-commandes', {}, h('span.figure-commandes__gauche', {}, h('span.cle', { texte: 'Sensibilité au prix' }), R.sensibilites), R.actionGain),
    R.zoneGain], R.margeGain = h('div.marge-gain'), { large: true });
}

function majGain(D) {
  const g = D.gain;
  vider(R.phraseGain); vider(R.noteGain); vider(R.actionGain); vider(R.sensibilites);
  const marge = R.margeGain;
  const choix = [['auto', 'Automatique'], ...Object.entries(SIM.SENSIBILITES).map(([k, v]) => [k, v.libelle])];
  for (const [cle, texte] of choix) {
    R.sensibilites.append(h('button.puce-filtre', { type: 'button', 'aria-pressed': String(S.sensibilite === cle), texte,
      title: cle === 'auto' ? 'Vos décisions si elles montrent un effet du prix, sinon une sensibilité moyenne'
        : (SIM.SENSIBILITES[cle].texte ? `Hypothèse : ${SIM.SENSIBILITES[cle].texte}` : 'Estimée sur vos décisions passées, sans hypothèse'),
      onclick: () => { S.sensibilite = cle; maj(); } }));
  }
  if (!g) {
    R.phraseGain.append(D.obs.length < 5
      ? `Il faut au moins cinq décisions passées — gagnées ou perdues, avec des offres comparables — pour estimer une chance de gain ; les réglages en retiennent ${entier(D.obs.length)}.`
      : 'Aucune offre de l’expertise sous ces réglages : sans prix de marché, la chance de gain ne se situe pas.');
    vider(R.zoneGain); R.courbeGain = null;
    if (marge) vider(marge).append(...margeGain(null));
    return;
  }
  const m = g.modele; const c = g.courbe; const a = c.actuel;
  const e = Math.round((Math.exp(g.xActuel) - 1) * 100);
  const position = Math.abs(e) < 1 ? 'au prix médian du marché' : `${Math.abs(e)}${NBSP}% ${e < 0 ? 'sous le' : 'au-dessus du'} prix médian du marché`;
  R.phraseGain.append(`Votre grille est ${position} à ${entier(D.A)} M€ : la chance de l’emporter est estimée à `,
    h('b', { texte: pct(a.p) }), h('span.attenue', { texte: ` (entre ${Math.round(a.bas * 100)} et ${pct(a.haut)}). ` }));
  const montrerOptimum = !g.plat;
  if (montrerOptimum) {
    const b = c.meilleur;
    if (Math.abs(b.x - a.x) < 0.02) {
      R.phraseGain.append(h('span.attenue', { texte: `C’est, à peu de chose près, le prix qui rapporte le plus en espérance : ${fmtFrais(a.espere)} sur ${pluriel2(S.horizon, 'an')}.` }));
    } else {
      R.phraseGain.append(`Le prix qui rapporte le plus en espérance est `, h('b', { texte: fmtTaux(g.tauxDe(b.x)) }),
        h('span.attenue', { texte: ` (${fmtEcartPct(b.x)} vs médiane) : ${pct(b.p)} de chance, ${fmtFrais(b.espere)} espérés sur ${pluriel2(S.horizon, 'an')}, contre ${fmtFrais(a.espere)} aujourd’hui.` }));
      const k = Math.exp(b.x - g.xActuel);
      R.actionGain.append(h('button.bouton.bouton--petit', { type: 'button', texte: `Appliquer ce prix (${pctSigne(k - 1)} sur tous les taux)`,
        onclick: () => charger(SIM.arrondirGrille(D.grille.map(t => ({ ...t, taux: t.taux * k }))),
          `${S.origine.replace(/, (modifiée|ajustée.*)$/, '')}, ajustée au meilleur espoir de gain`) }));
    }
  }
  // Ce sur quoi repose l'estimation : dit en une phrase, jamais caché.
  const base = `${pluriel2(m.n, 'décision passée', 'décisions passées')} (${entier(m.gagnes)} gagnées), toutes expertises, chacune ramenée à son écart au marché.`;
  if (g.repli) {
    R.noteGain.append(h('b', { texte: 'Hypothèse moyenne. ' }),
      `Vos ${base} Elles ne montrent pas que les offres moins chères gagnent plus souvent : le simulateur retient une sensibilité moyenne (${SIM.SENSIBILITES.moyenne.texte}). Changez-la ci-dessous.`);
  } else if (S.sensibilite === 'donnees' || S.sensibilite === 'auto') {
    R.noteGain.append(`Estimé sur vos ${base} `, g.plat
      ? 'Les offres gagnées n’y étaient pas moins chères que les perdues : le prix ne les a pas départagées, la chance ne dépend donc pas du prix et aucun prix « optimal » ne s’en déduit. Choisissez une hypothèse pour raisonner.'
      : (m.demontre ? 'L’effet du prix y est net.' : 'L’effet du prix y reste incertain : lisez la bande.'));
  } else {
    R.noteGain.append(h('b', { texte: `Hypothèse ${SIM.SENSIBILITES[S.sensibilite].libelle.toLowerCase()}. ` }),
      `${capitale(SIM.SENSIBILITES[S.sensibilite].texte)} ; le niveau est calé sur vos ${base}`);
  }
  const p = { modele: m, courbe: c, decisions: g.obs, horizon: S.horizon, tauxDe: g.tauxDe, montrerOptimum,
    surDecision: (o) => ouvrirOffre(o.id) };
  if (!R.courbeGain) { R.courbeGain = courbeGain(p); vider(R.zoneGain).append(R.courbeGain.el); } else R.courbeGain.maj(p);
  if (marge) vider(marge).append(...margeGain(g));
}

function margeGain(g) {
  return margeTexte('Comment c’est estimé',
    'Chaque offre gagnée ou perdue est ramenée à son <b>écart de prix</b> avec les autres offres de son expertise, à la taille de son mandat : c’est ce qui permet de mettre en commun toutes les décisions. Les carrés pleins, en haut, sont les gagnées ; les creux, en bas, les perdues.',
    'La courbe est une régression logistique prudente : un a priori faible, et la contrainte qu’être plus cher ne fait pas gagner. La <b>bande</b> dit l’incertitude à 90 % ; les zones <b>hachurées</b> sont hors des décisions passées.',
    '<b>Revenu espéré</b> : la chance de gagner × les frais sur la durée du mandat (réglages Durée et Croissance). Le « meilleur espoir » est le prix qui maximise ce produit, en gardant la forme de votre grille.',
    g ? `Le prix, seul, n’explique pas une issue : la qualité de la gestion, la relation et le consultant pèsent autant. Ce bloc dit ce que le prix change, toutes choses égales par ailleurs.` : null);
}

/* ================================================= 05 la valeur du mandat === */
function blocValeur() {
  R.phraseValeur = h('p.prose.prose--bloc');
  R.zoneValeur = h('div');
  R.tableValeur = h('div.tableau');
  const legende = h('div.legende-tarif', {},
    h('span.legende-tarif__item', {}, h('span.aplat.aplat--barre'), 'frais de votre grille'),
    h('span.legende-tarif__item', {}, h('span.aplat.aplat--hachure'), 'ce qu’il paierait en plus au taux moyen d’aujourd’hui'));
  return bloc('valeur', 'Ce que rapporte le mandat', [R.phraseValeur, legende, R.zoneValeur, R.tableValeur], margeTexte('Lecture',
    'Les frais de chaque année, si l’encours croît au rythme choisi dans les réglages (marchés et flux nets confondus). L’année 1 est le mandat tel qu’il se chiffre aujourd’hui.',
    'Le <b>hachuré</b> : ce que paierait en plus le même encours à un taux unique, celui d’aujourd’hui. L’écart est ce que la dégressivité rend au client quand il grossit — l’argument, et le coût, d’une grille à paliers.',
    'Survolez une année pour son détail.'));
}

function majValeur(D) {
  const pr = D.projection;
  const der = pr.annees[pr.annees.length - 1];
  vider(R.phraseValeur);
  R.phraseValeur.append(`Sur ${pluriel2(S.horizon, 'an')}, à ${pctSigne(S.croissance)} par an, ce mandat rapporte `,
    h('b', { texte: `${fmtFrais(pr.total)} HT` }), '. ');
  if (S.horizon > 1 && Math.abs(S.croissance) > 1e-9) {
    const hausseA = der.encours / D.A - 1; const hausseF = der.frais / pr.annees[0].frais - 1;
    const rendu = pr.totalFixe - pr.total;
    R.phraseValeur.append(h('span.attenue', { texte: `L’encours ${hausseA >= 0 ? 'aura grossi' : 'aura baissé'} de ${pctSigne(hausseA).replace('+', '')}, les frais de ${pctSigne(hausseF).replace('+', '')} seulement`
      + (Math.abs(rendu) >= 0.0005 ? ` : la dégressivité ${rendu > 0 ? 'rend' : 'coûte'} ${fmtFrais(Math.abs(rendu))} au client par rapport au taux d’aujourd’hui.` : '.') }));
  } else {
    R.phraseValeur.append(h('span.attenue', { texte: `Sans croissance de l’encours, les frais restent de ${fmtFrais(D.fr)} chaque année.` }));
  }
  const p = { projection: pr };
  if (!R.courbeValeur) { R.courbeValeur = courbeValeur(p); R.zoneValeur.append(R.courbeValeur.el); } else R.courbeValeur.maj(p);
  // Le tableau jumeau : les mêmes nombres, à lire ou copier.
  const t = h('table.donnees.table-valeur');
  t.append(h('thead', {}, h('tr', {}, h('th', { texte: 'Année' }), h('th.num', { texte: 'Encours' }), h('th.num', { texte: 'Taux moyen' }),
    h('th.num', { texte: 'Frais' }), h('th.num', { texte: 'Cumul' }))));
  const tb = h('tbody');
  for (const a of pr.annees) {
    tb.append(h('tr', {}, h('td', { texte: `an ${a.annee}` }), h('td.num', { texte: fmtM(a.encours) }), h('td.num', { texte: fmtTaux(a.taux) }),
      h('td.num', { texte: fmtFrais(a.frais) }), h('td.num', {}, h('b', { texte: fmtFrais(a.cumul) }))));
  }
  t.append(tb);
  vider(R.tableValeur).append(t);
}

/* ======================================================== 06 négocier === */
function blocNegocier() {
  R.phraseNego = h('p.prose.prose--bloc');
  R.champConcession = caseNombre({ valeur: S.concession * 100, pas: 0.5, decimales: 1, min: 0, max: 100, largeur: '58px',
    etiquette: 'Effort demandé par le client, en points de base de taux moyen', surValeur: (v) => { S.concession = v / 100; majPlanifiee(); } });
  R.raccourcisNego = h('span.raccourcis');
  R.zoneNego = h('div');
  const commandes = h('div.figure-commandes', {},
    h('label.reglage', {}, h('span.reglage__c', { texte: 'Le client demande' }),
      h('span.reglage__v', {}, R.champConcession, h('span.unite', { texte: 'pb de taux moyen' }))), R.raccourcisNego);
  return bloc('negocier', 'Négocier sans se tromper de levier', [R.phraseNego, commandes, R.zoneNego], margeTexte('Lecture',
    'Un même effort aujourd’hui — tant de points de base sur le taux moyen, à la taille actuelle — ne coûte pas la même chose sur la durée du mandat : tout dépend de <b>où</b> on le concède.',
    'Baisser une tranche que l’encours <b>remplit déjà</b> coûte un montant fixe chaque année. Une <b>remise sur tous les taux</b> se paie aussi sur la croissance : chaque nouveau million est facturé moins cher.',
    'Le coût est calculé sur la grille arrondie qui s’appliquerait (seuils au M€, taux au millième de point), avec la durée et la croissance des réglages.'), { large: true });
}

function majNegocier(D) {
  const N = D.negociation;
  vider(R.phraseNego); vider(R.zoneNego); vider(R.raccourcisNego);
  R.champConcession.poser(S.concession * 100);
  // Des raccourcis qui parlent : l'effort pour rejoindre le marché.
  const raccourcis = [[0.01, '1 pb'], [0.02, '2 pb'], [0.05, '5 pb']];
  if (D.marche.n && D.tm - D.marche.mediane > 0.0005) raccourcis.push([D.tm - D.marche.mediane, `jusqu’à la médiane (${fmtPb(D.tm - D.marche.mediane).replace('+', '')})`]);
  if (D.marche.n && D.tm - D.marche.min > 0.0005) raccourcis.push([D.tm - D.marche.min, `jusqu’au plus bas (${fmtPb(D.tm - D.marche.min).replace('+', '')})`]);
  for (const [v, t] of raccourcis) {
    R.raccourcisNego.append(h('button.puce-filtre', { type: 'button', 'aria-pressed': String(Math.abs(v - S.concession) < 1e-6), texte: t,
      onclick: () => { S.concession = Math.round(v * 1000) / 1000; maj(); } }));
  }
  if (!(S.concession > 0) || !N.options.length) {
    R.phraseNego.append(!(S.concession > 0) ? 'Indiquez l’effort demandé pour comparer les leviers.'
      : `Un effort de ${fmtPb(S.concession).replace('+', '')} dépasse le taux moyen de la grille (${fmtTaux(D.tm)}).`);
    return;
  }
  const b = N.meilleur;
  const annuel = S.concession * D.A / 100;
  const uni = N.options.find(o => o.cle === 'uniforme');
  const horizon = pluriel2(S.horizon, 'an');
  if (!b) {
    R.phraseNego.append(`Aucun levier ne permet d’accorder ${fmtPb(S.concession).replace('+', '')} sans passer un taux sous zéro.`);
  } else {
    R.phraseNego.append(`Pour accorder ${fmtPb(S.concession).replace('+', '')} — ${fmtFrais(annuel)} par an aujourd’hui —, le levier le moins coûteux est `,
      h('b', { texte: b.libelle.charAt(0).toLowerCase() + b.libelle.slice(1) }), ` : ${fmtFrais(b.cout)} sur ${horizon}`);
    if (uni && uni !== b && uni.faisable && uni.cout - b.cout >= 0.0005) {
      R.phraseNego.append(h('span.attenue', { texte: `, contre ${fmtFrais(uni.cout)} pour une remise sur tous les taux.` }));
    } else if (Math.abs(S.croissance) < 1e-9 || S.horizon === 1) {
      R.phraseNego.append(h('span.attenue', { texte: '. Sans croissance de l’encours, tous les leviers se valent : la différence naît quand le mandat grossit.' }));
    } else R.phraseNego.append('.');
  }
  const coutMax = Math.max(...N.options.filter(o => o.faisable).map(o => o.cout), 1e-9);
  const t = h('table.donnees.table-leviers');
  t.append(h('thead', {}, h('tr', {}, h('th', { texte: 'Levier' }), h('th', { texte: 'Ce qui change dans la grille' }),
    h('th.num', { texte: `Frais à ${entier(D.A)} M€` }), h('th.th-cout', { texte: `Coût sur ${horizon}` }), h('th', { 'aria-label': 'Action' }))));
  const tb = h('tbody');
  for (const o of N.options) {
    const tr = h('tr', { classe: o === b ? 'ligne-meilleure' : '' });
    tr.append(h('td', {}, h('span.cellule-nom', { texte: o.libelle }), o === b ? h('span.cellule-sous', {}, h('b', { texte: 'le moins coûteux' })) : null));
    tr.append(h('td', { texte: changement(o, D) }));
    if (!o.faisable) {
      tr.append(h('td.num.attenue', { texte: '—' }), h('td.attenue', { texte: 'impossible sans taux négatif' }), h('td'));
    } else {
      tr.append(h('td.num', {}, fmtFrais(o.fraisAujourdhui), h('span.cellule-sous', { texte: `${fmtEcartFrais(o.fraisAujourdhui - N.F0)} par an` })));
      tr.append(h('td.cout-levier', {}, h('span.barre-cout', { 'aria-hidden': 'true' }, h('i', { style: { width: `${Math.max(2, (o.cout / coutMax) * 100)}%` } })),
        h('b', { texte: fmtFrais(o.cout) }),
        b && o !== b && o.cout - b.cout >= 0.0005 ? h('span.attenue', { texte: ` ${fmtEcartFrais(o.cout - b.cout)}` }) : null));
      tr.append(h('td', {}, h('button.bouton.bouton--sobre.bouton--petit', { type: 'button', texte: 'Appliquer',
        onclick: () => charger(o.grille, `${S.origine.replace(/, (modifiée|ajustée.*)$/, '')}, ajustée : ${o.libelle.toLowerCase()}`) })));
    }
    tb.append(tr);
  }
  t.append(tb);
  R.zoneNego.append(h('div.tableau', {}, t));
}

/** Ce qu'un levier change, en une ligne lisible. */
function changement(o, D) {
  const d = o.detail;
  if (o.cle === 'uniforme') return `tous les taux ${pctSigne(-d.remise)}`;
  if (o.cle === 'seuils') {
    if (!Number.isFinite(d.facteur)) return 'les seuils ne suffisent pas';
    const avant = D.grille.slice(1).map(t => entier(t.minimum)).join(' / ');
    const apres = o.grille.slice(1).map(t => entier(t.minimum)).join(' / ');
    return `seuils ${avant} → ${apres} M€`;
  }
  if (!o.faisable) return `T${d.tranche + 1} ne porte pas assez d’encours`;
  return `T${d.tranche + 1} : ${fmtTaux(d.avant)} → ${fmtTaux(o.grille[d.tranche].taux)}`;
}

/* ========================================================= 07 expertises === */
function blocExpertises() {
  R.corpsExpertises = h('tbody');
  R.teteExpertises = h('thead');
  R.mesures = h('div.groupe-puces', { role: 'group', 'aria-label': 'Mesure' });
  for (const [cle, texte] of [['mediane', 'Médiane'], ['moyenne', 'Moyenne']]) {
    R.mesures.append(h('button.puce-filtre', { type: 'button', 'aria-pressed': String(cle === S.mesure), texte,
      onclick: (e) => {
        S.mesure = cle;
        for (const b of R.mesures.children) b.setAttribute('aria-pressed', String(b === e.currentTarget));
        majExpertises(calculer());
      } }));
  }
  const table = h('table.donnees.table-expertises', {}, R.teteExpertises, R.corpsExpertises);
  return bloc('expertises', 'Les expertises', [R.mesures, h('div.tableau', {}, table)], margeTexte('Lecture',
    'Le taux moyen des offres de chaque expertise aux tailles de référence, sous les réglages en cours. Sous chaque valeur, du plus bas au plus haut.',
    'La première ligne est votre grille : elle se compare d’un coup d’œil à toutes les expertises.',
    'La <b>moyenne</b> est la mesure de la présentation d’origine ; la <b>médiane</b> résiste mieux à une grille atypique.',
    'Un clic sur une ligne choisit l’expertise.'), { large: true });
}

function majExpertises(D) {
  vider(R.teteExpertises).append(h('tr', {}, h('th', { texte: 'Expertise' }), h('th.num', { texte: 'Offres' }),
    ...TAILLES_REFERENCE.map(t => h('th.num', { texte: `${t} M€` }))));
  vider(R.corpsExpertises);
  const moi = h('tr.ligne-moi', {}, h('td', { texte: 'Votre grille' }), h('td.num', { texte: '' }),
    ...TAILLES_REFERENCE.map(t => h('td.num', {}, h('b', { texte: fmtTaux(T.tauxMoyen(D.grille, t)) }))));
  R.corpsExpertises.append(moi);
  // Le rang de votre grille dans l'expertise choisie, à chaque taille : la lecture d'un consultant.
  const elig0 = eligibles();
  if (elig0.length) {
    R.corpsExpertises.append(h('tr.ligne-moi.ligne-rang', {}, h('td', { texte: `Son rang, ${libelleExpertise(S.expertise)}` }), h('td.num', { texte: '' }),
      ...TAILLES_REFERENCE.map(t => h('td.num', { texte: positionCourte(T.centile(elig0.map(g => T.tauxMoyen(g.tranches, t)), T.tauxMoyen(D.grille, t))) }))));
  }
  for (const e of S.donnees.expertises) {
    const elig = eligibles(e.cle);
    const tr = h('tr', { 'data-clic': '', classe: e.cle === S.expertise ? 'ligne-choisie' : '',
      tabindex: 0, onclick: () => { S.expertise = e.cle; maj({ offres: true }); },
      onkeydown: (ev) => { if (ev.key === 'Enter') { S.expertise = e.cle; maj({ offres: true }); } } });
    tr.append(h('td', { texte: e.libelle }), h('td.num', { texte: entier(elig.length) }));
    for (const t of TAILLES_REFERENCE) {
      const r = T.resume(elig.map(g => T.tauxMoyen(g.tranches, t)));
      tr.append(r.n ? h('td.num', {}, h('span', { texte: fmtTaux(r[S.mesure]) }),
        r.n > 1 ? h('span.cellule-sous', { texte: `${fmtTaux(r.min, { unite: false })}–${fmtTaux(r.max, { unite: false })}` }) : null)
        : h('td.num.attenue', { texte: '—' }));
    }
    R.corpsExpertises.append(tr);
  }
}

/* ============================================================ 08 offres === */
function blocOffres() {
  R.zoneOffres = h('div');
  R.bascule = h('div.groupe-puces', { role: 'group', 'aria-label': 'Périmètre de la liste' });
  R.margeOffres = h('div');
  return bloc('offres', 'Les offres passées', [R.bascule, R.zoneOffres], R.margeOffres, { large: true });
}

const COLONNES_OFFRES = [
  ['libelle', 'Client', null], ['expertise', 'Expertise', null], ['annee', 'Année', 'num'],
  ['issue', 'Issue', 'col-issue'], ['volume', 'Encours', 'num'], ['taux_volume', 'Taux moyen', 'num'],
  ['frais_volume', 'Frais', 'num'], ['position', 'Position', 'num'], ['dossier', 'Dossier', 'col-dossier'],
];

function majOffres() {
  const exp = libelleExpertise(S.expertise);
  vider(R.bascule);
  for (const [toutes, texte] of [[false, exp], [true, 'Toutes les expertises']]) {
    R.bascule.append(h('button.puce-filtre', { type: 'button', 'aria-pressed': String(S.toutes === toutes), texte,
      onclick: () => { S.toutes = toutes; majOffres(); } }));
  }
  const liste = S.donnees.offres.filter(o => passe(o) && (S.toutes || o.expertise_cle === S.expertise))
    .map(o => ({ o, position: positionOffre(o) }));
  const { cle, sens } = S.tri;
  const val = (x) => (cle === 'position' ? x.position : (cle === 'dossier' ? (x.o.rattachement ? 1 : 0) : x.o[cle]));
  liste.sort((a, b) => {
    const va = val(a); const vb = val(b);
    if (va === vb) return 0;
    if (va === null || va === undefined || Number.isNaN(va)) return 1;
    if (vb === null || vb === undefined || Number.isNaN(vb)) return -1;
    return (typeof va === 'string' ? va.localeCompare(vb, 'fr', { numeric: true }) : va - vb) * sens;
  });
  const table = h('table.donnees.table-offres');
  const trTete = h('tr');
  for (const [c, titre, classe] of COLONNES_OFFRES) {
    const actif = S.tri.cle === c;
    trTete.append(h(`th${classe ? `.${classe}` : ''}`, { role: 'button', tabindex: 0,
      'aria-sort': actif ? (S.tri.sens > 0 ? 'ascending' : 'descending') : null,
      onclick: () => { S.tri = { cle: c, sens: actif ? -S.tri.sens : (classe === 'num' ? -1 : 1) }; majOffres(); },
      onkeydown: (e) => { if (e.key === 'Enter') { S.tri = { cle: c, sens: actif ? -S.tri.sens : (classe === 'num' ? -1 : 1) }; majOffres(); } } },
    titre, actif ? (S.tri.sens > 0 ? ' ↑' : ' ↓') : ''));
  }
  table.append(h('thead', {}, trTete));
  const tbody = h('tbody');
  for (const { o, position } of liste) {
    const tr = h('tr', { 'data-clic': '', tabindex: 0, onclick: (e) => { if (!e.target.closest('.crayon, .saisie')) ouvrirOffre(o.id); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === tr) ouvrirOffre(o.id); } });
    const nom = h('td.cellule-client');
    nomEditable(nom, o);
    tr.append(nom);
    tr.append(h('td.attenue', { texte: o.expertise }), h('td.num', { texte: o.annee ?? '—' }));
    tr.append(h('td.col-issue', {}, h('span', { classe: `forme forme--${o.issue === 'Gagné' ? 'gagne' : (o.issue === 'Perdu' ? 'perdu' : 'cours')}` }), o.issue));
    tr.append(h('td.num', { texte: fmtM(o.volume) }), h('td.num', {}, h('b', { texte: fmtTaux(o.taux_volume) })),
      h('td.num', { texte: fmtFrais(o.frais_volume) }),
      h('td.num', { texte: positionCourte(position) }));
    tr.append(h('td.col-dossier', {}, o.rattachement ? h('span.lien-dossier', { texte: `n° ${o.rattachement.numero ?? o.rattachement.cle}` })
      : h('span.attenue', { texte: '—' })));
    if (o.anomalies.some(a => a.gravite !== 'info')) tr.classList.add('ligne-signalee');
    tbody.append(tr);
  }
  table.append(tbody);
  vider(R.zoneOffres);
  if (!liste.length) R.zoneOffres.append(h('p.note', { texte: 'Aucune offre sous ces réglages.' }));
  else R.zoneOffres.append(h('div.tableau', {}, table));

  const c = S.donnees.correspondance;
  const n = new Set(S.donnees.offres.map(o => o.client)).size;
  const entree = h('input', { type: 'file', accept: '.csv,.txt,.xlsx,.xlsm,.xls', hidden: true,
    onchange: async () => {
      if (!entree.files[0]) return;
      try {
        const r = await api.deposer('/api/tarif/correspondance', entree.files[0]);
        annoncer(`${r.n_libelles} libellés appliqués.`);
        await recharger();
      } catch (e) { annoncer(`Correspondance refusée : ${e.message}`); }
    } });
  vider(R.margeOffres).append(...margeTexte('Les libellés clients',
    `Le classeur nomme ses clients « Client 1 », « Client 2 »… : ${entier(c.n_libelles)} sur ${entier(n)} ont reçu leur vrai libellé.`,
    'Le crayon d’une ligne donne le sien à un client. Pour tous d’un coup : téléchargez la correspondance, remplissez la colonne <b>libelle</b> dans Excel, redéposez-la.'),
  h('p.marge-texte', {}, lien('Télécharger la correspondance', () => { window.location.href = '/api/tarif/correspondance.csv'; })),
  h('p.marge-texte', {}, lien('Déposer une correspondance', () => entree.click()), entree),
  ...margeTexte(null, 'Un libellé identique à celui d’un client du classeur d’activité rattache l’offre à son dossier d’appel d’offres de la même année.'));
}

/** Le nom d'un client, et le crayon qui permet de le remplacer par son vrai libellé. */
function nomEditable(cellule, o, { apres } = {}) {
  vider(cellule);
  cellule.append(h('span.nom-client', { texte: o.libelle }));
  if (o.libelle_edite) cellule.append(h('span.cellule-sous', { texte: o.client }));
  const crayon = h('button.crayon', { type: 'button', 'aria-label': `Renommer ${o.client}`, title: 'Donner son vrai libellé', texte: '✎',
    onclick: (e) => {
      e.stopPropagation();
      const champ = h('input.saisie.saisie--libelle', { type: 'text', value: o.libelle_edite ? o.libelle : '',
        placeholder: o.client, maxlength: 120, 'aria-label': `Libellé réel de ${o.client}` });
      vider(cellule).append(champ);
      champ.focus();
      let fini = false;
      const valider = async (garder) => {
        if (fini) return; fini = true;
        if (garder) {
          try {
            const r = await api.post('/api/tarif/libelles', { client: o.client, libelle: champ.value });
            for (const x of S.donnees.offres) if (x.client === o.client) { x.libelle = r.libelle; x.libelle_edite = r.libelle_edite; }
            annoncer(r.libelle_edite ? `${o.client} s’appelle désormais ${r.libelle}.` : `${o.client} reprend son libellé d’origine.`);
            await recharger();
            if (apres) apres();
            return;
          } catch (err) { annoncer(`Libellé refusé : ${err.message}`); }
        }
        nomEditable(cellule, o, { apres });
      };
      champ.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') { ev.preventDefault(); valider(true); }
        if (ev.key === 'Escape') { ev.preventDefault(); valider(false); }
      });
      champ.addEventListener('blur', () => valider(true));
    } });
  cellule.append(crayon);
}

/** Relit les offres (libellés et rattachements changent) sans perdre la simulation. */
async function recharger() {
  S.donnees = await api.get('/api/tarif');
  maj({ offres: true });
}

/* =========================================================== 09 classeur === */
/** L'écran Données, directement à la section des grilles. */
function allerAuxGrilles() {
  R.ctx.aller('donnees');
  const fin = performance.now() + 3000;
  const chercher = () => {
    const cible = document.getElementById('grilles-tarifaires');
    if (cible && cible.querySelector('.depot')) cible.scrollIntoView({ block: 'start' });
    else if (performance.now() < fin) requestAnimationFrame(chercher);
  };
  requestAnimationFrame(chercher);
}

function blocClasseur() {
  R.zoneClasseur = h('div');
  return bloc('classeur', 'Le classeur', R.zoneClasseur, margeTexte('Brancher le vrai classeur',
    'Le vrai classeur se dépose depuis l’écran <b>Données</b>, section « Les grilles tarifaires ». Mêmes colonnes que la page 5 de la présentation ; les en-têtes se reconnaissent sans casse ni accent.',
    'Aucune anomalie n’est corrigée en silence : elle est nommée ici, et une grille qui fausserait les comparaisons en sort.'));
}

function majClasseur() {
  const s = S.donnees.source;
  vider(R.zoneClasseur);
  const p = h('p.prose.prose--bloc');
  if (s.mode === 'demo') {
    p.append('Le simulateur tourne sur l’', h('b', { texte: 'échantillon de démonstration' }),
      ` : les ${entier(s.n_lignes)} lignes lisibles de la page 5 de la présentation, ${entier(s.n_grilles)} offres de clients anonymisés.`);
  } else {
    p.append('Le simulateur lit ', h('b', { texte: s.fichier }), s.onglet ? `, onglet « ${s.onglet} »` : '',
      ` : ${entier(s.n_lignes)} tranches, ${entier(s.n_grilles)} offres.`);
  }
  R.zoneClasseur.append(p);
  R.zoneClasseur.append(h('p', { style: { margin: '10px 0 18px' } }, lien('Brancher un classeur', allerAuxGrilles)));
  for (const a of s.alertes || []) R.zoneClasseur.append(h('p.note', { texte: a }));
  const signalees = S.donnees.offres.filter(o => o.anomalies.length);
  if (!signalees.length) { R.zoneClasseur.append(h('p.note', { texte: 'Aucune anomalie dans les grilles.' })); return; }
  const ul = h('ul.liste-anomalies');
  for (const o of signalees) {
    for (const a of o.anomalies) {
      ul.append(h('li', {}, h('button.lien-sobre', { type: 'button', texte: `${o.libelle} · ${o.expertise} · ${o.annee ?? '—'}`,
        onclick: () => ouvrirOffre(o.id) }), h('span', { classe: `gravite gravite--${a.gravite}`, texte: a.gravite === 'bloquante' ? 'écartée' : (a.gravite === 'attention' ? 'à vérifier' : 'note') }),
      h('span', { texte: a.texte })));
    }
  }
  R.zoneClasseur.append(ul);
}


/* ============================================================ ouverture === */
function majOuverture(D) {
  const exp = libelleExpertise(S.expertise);
  vider(R.lede);
  R.lede.append(`À ${entier(D.A)} M€, votre grille facture `);
  R.lede.append(h('b', { texte: fmtTaux(D.tm), style: { fontWeight: 500 } }));
  R.lede.append(` — ${fmtFrais(D.fr)} HT par an. `);
  // Deux phrases : le prix, puis sa place et ce qu'il vaut sur la durée.
  const suite = h('span.attenue');
  const f = D.marche;
  suite.append(f.n ? `${capitale(cherete(D.centile))} ${exp} à cette taille ; sur ${pluriel2(S.horizon, 'an')}, le mandat rapporterait ${fmtFrais(D.projection.total)}.`
    : `Aucune offre ${exp} ne répond aux réglages : élargissez les années ou l’issue pour situer ce prix.`);
  R.lede.append(suite);

  vider(R.matin);
  const fait = (valeur, libelle, cible) => h('span', {}, cible
    ? h('a.nombre', { href: `#bloc-${cible}`, texte: valeur, onclick: (e) => { e.preventDefault(); document.getElementById(`bloc-${cible}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); } })
    : h('b', { texte: valeur }), ` ${libelle}`);
  R.matin.append(fait(fmtTaux(D.tm), 'de taux moyen', 'escalier'));
  if (f.n) R.matin.append(fait(positionCourte(D.centile), `parmi ${pluriel2(f.n, 'offre')} ${exp}`, 'marche'));
  if (D.gain) R.matin.append(fait(pct(D.gain.courbe.actuel.p), `de chance de gagner${D.gain.repli || S.sensibilite !== 'donnees' && S.sensibilite !== 'auto' ? ' (hypothèse)' : ''}`, 'gain'));
  R.matin.append(fait(fmtFrais(D.projection.total), `sur ${pluriel2(S.horizon, 'an')}`, 'valeur'));

  vider(R.margeOuverture).append(...margeTexte('La simulation',
    `Expertise <b>${exp}</b>, mandat de <b>${entier(D.A)} M€</b> sur ${pluriel2(S.horizon, 'an')}, encours ${pctSigne(S.croissance)} par an.`,
    `Grille à ${pluriel2(D.grille.length, 'tranche')}, comparée à ${pluriel2(D.elig.length, 'offre')} passée${D.elig.length > 1 ? 's' : ''}.`),
  h('p.marge-texte', {}, lien('Recommencer depuis la grille type', () => {
    try { localStorage.removeItem(MEMOIRE); } catch (e) { /* rien */ }
    S.encours = 150; R.champEncours.poser(150); R.curseurEncours.value = versCurseur(150);
    charger(S.donnees.grille_type, 'la grille type de la présentation (page 2)');
  })));
}

/* ================================================================ maj === */
function maj({ offres = false } = {}) {
  enAttente = false;
  const D = calculer();
  majOuverture(D);
  peindreTuiles();
  majComparer();
  if (!R.lignesGrille || R.lignesGrille.length !== S.lignes.length) peindreGrille();
  majGrille(D);
  majEscalier(D);
  majMarche(D);
  majGain(D);
  majValeur(D);
  majNegocier(D);
  majExpertises(D);
  if (offres || !R.offresPeintes) { majOffres(); majClasseur(); R.offresPeintes = true; }
  memoriser();
}

// Un geste continu (tirer une marche, glisser le curseur) ne recalcule qu'une fois par image.
let enAttente = false;
function majPlanifiee() {
  if (enAttente) return;
  enAttente = true;
  requestAnimationFrame(() => { if (enAttente) maj(); });
}

/* =========================================================== la fiche === */
export async function ouvrirOffre(id) {
  const ctx = R.ctx;
  const fond = h('div.fiche-fond', { onclick: (e) => { if (e.target === fond) fermer(); } });
  const panneau = h('div.fiche.fiche--offre', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Fiche de l’offre' });
  fond.append(panneau);
  document.body.append(fond);
  document.body.style.overflow = 'hidden';
  const fermer = () => {
    fond.remove(); document.body.style.overflow = '';
    document.removeEventListener('keydown', surTouche);
  };
  const surTouche = (e) => { if (e.key === 'Escape' && !e.target.closest('.saisie')) { e.preventDefault(); fermer(); } };
  document.addEventListener('keydown', surTouche);
  panneau.append(chargement('Ouverture de l’offre…'));

  let o;
  try {
    o = await api.get(`/api/tarif/offres/${encodeURIComponent(id)}`);
  } catch (e) {
    vider(panneau).append(h('div.fiche__corps', {}, message(`Offre introuvable : ${e.message}`)));
    return;
  }
  const peindre = () => {
    vider(panneau);
    const tete = h('div.fiche__tete');
    const nom = h('div.fiche__nom-offre');
    nomEditable(nom, o, { apres: async () => { o = await api.get(`/api/tarif/offres/${encodeURIComponent(id)}`); peindre(); } });
    tete.append(h('div', {}, h('div.cle', { texte: `${o.expertise} · ${o.annee ?? 'année inconnue'} · ${o.issue}` }), nom));
    tete.append(h('button.fiche__x', { type: 'button', 'aria-label': 'Fermer', onclick: fermer, texte: '×' }));
    panneau.append(tete);
    const corps = h('div.fiche__corps');
    panneau.append(corps);

    const pairs = S.donnees.offres.filter(p => !p.exclue && p.expertise_cle === o.expertise_cle && p.id !== o.id);
    const pos = o.volume && pairs.length >= 2 ? T.centile(pairs.map(p => T.tauxMoyen(p.tranches, o.volume)), o.taux_volume) : NaN;
    const phrase = h('p.prose', { style: { fontSize: '18px', marginBottom: '18px' } });
    phrase.append(o.volume ? `Mandat de ${fmtM(o.volume)}, grille à ${pluriel2(o.tranches.length, 'tranche')} : `
      : `Grille à ${pluriel2(o.tranches.length, 'tranche')}, encours du mandat non renseigné. `);
    if (o.volume) phrase.append(h('b', { texte: fmtTaux(o.taux_volume) }), ` en moyenne, ${fmtFrais(o.frais_volume)} HT par an. `);
    if (Number.isFinite(pos)) phrase.append(`Au ${fmtCentile(pos)} des ${pluriel2(pairs.length, 'autre offre', 'autres offres')} ${o.expertise} appliquées à cette taille.`);
    corps.append(phrase);

    if (pairs.length || o.volume) {
      const xMax = plafondJoli(Math.max((o.volume || 100) * 2, 200), 5);
      corps.append(courbeTarif({ compact: true, largeur: 556, hauteur: 190, grille: o.tranches, eligibles: pairs,
        encours: o.volume, xMax, points: [], libelleExpertise: o.expertise, libelleGrille: 'Cette grille' }).el);
      corps.append(h('p.note', { style: { margin: '2px 0 18px' }, texte: `Trait épais : cette grille. Bandes et trait fin : les autres offres ${o.expertise}.` }));
    }

    const t = h('table.donnees.table-fiche');
    t.append(h('thead', {}, h('tr', {}, h('th', { texte: 'De' }), h('th', { texte: 'À' }), h('th.num', { texte: 'Taux' }),
      h('th.num', { texte: o.volume ? `Frais à ${fmtM(o.volume)}` : 'Frais' }))));
    const tb = h('tbody');
    o.tranches.forEach((tr, i) => {
      const der = i === o.tranches.length - 1;
      const part = o.volume ? Math.max(0, Math.min(o.volume, der ? Infinity : tr.maximum) - tr.minimum) : 0;
      tb.append(h('tr', {}, h('td', { texte: fmtM(tr.minimum) }),
        h('td', { texte: der ? (o.plafond_saisi ? `au-delà (saisi : ${fmtM(o.plafond_saisi)})` : 'et au-delà') : fmtM(tr.maximum) }),
        h('td.num', {}, h('b', { texte: fmtTaux(tr.taux) })),
        h('td.num', { texte: part > 0 ? fmtFrais(part * tr.taux / 100) : '—' })));
    });
    t.append(tb);
    corps.append(h('div.tableau', {}, t));
    const faits = [['Nature du client', o.nature || '—'], ['Régime', o.tva || 'HT'],
      ['Surperformance', o.surperformance ? decimal(o.surperformance, 2) : 'aucune'],
      ['Lignes du classeur', o.lignes.join(', ')]];
    const champs = h('div.champs.champs--fiche');
    for (const [c, v] of faits) champs.append(h('div.champ', {}, h('div.champ__c', { texte: c }), h('div.champ__v', { texte: v })));
    corps.append(champs);
    if (o.anomalies.length) {
      const ul = h('ul.liste-anomalies');
      for (const a of o.anomalies) ul.append(h('li', {}, h('span', { classe: `gravite gravite--${a.gravite}`,
        texte: a.gravite === 'bloquante' ? 'écartée' : (a.gravite === 'attention' ? 'à vérifier' : 'note') }), h('span', { texte: a.texte })));
      corps.append(h('h3.fiche__section', { texte: 'Ce que le classeur signale' }), ul);
    }

    // Les offres comparables : même expertise, encours voisin.
    if (o.volume && pairs.length) {
      const proches = [...pairs].filter(p => p.volume).sort((a, b) => Math.abs(Math.log(a.volume / o.volume)) - Math.abs(Math.log(b.volume / o.volume))).slice(0, 4);
      corps.append(h('h3.fiche__section', { texte: 'Offres comparables' }));
      const liste = h('div.comparables');
      for (const p of proches) {
        liste.append(h('button.comparable', { type: 'button', onclick: () => { fermer(); ouvrirOffre(p.id); } },
          h('span', { classe: `forme forme--${p.issue === 'Gagné' ? 'gagne' : (p.issue === 'Perdu' ? 'perdu' : 'cours')}` }),
          h('span.comparable__nom', { texte: `${p.libelle} · ${p.annee ?? '—'}` }),
          h('span.comparable__v', { texte: `${fmtM(p.volume)} · ${fmtTaux(p.taux_volume)}` }),
          h('span.attenue', { texte: `à ${fmtM(o.volume)} : ${fmtTaux(T.tauxMoyen(p.tranches, o.volume))}` })));
      }
      corps.append(liste);
    }

    corps.append(h('h3.fiche__section', { texte: 'Le dossier d’appel d’offres' }));
    corps.append(sectionDossier(o, ctx, fermer, async () => { o = await api.get(`/api/tarif/offres/${encodeURIComponent(id)}`); peindre(); await recharger(); }));

    if (o.contexte) {
      const c = o.contexte;
      const p = h('p.note', { style: { marginTop: '14px' } });
      if (c.n) {
        p.append(`Dans le classeur d’activité, ${c.criteres.join(' ou ')}${c.annee ? ` en ${c.annee}` : ''} : `,
          h('b', { texte: pluriel2(c.n, 'appel d’offres', 'appels d’offres') }),
          c.tranches ? `, ${entier(c.gagnes)} gagnés sur ${entier(c.tranches)} tranchés (${decimal(c.taux_succes * 100, 0)}${NBSP}%)` : '',
          c.montant_median ? `, encours médian ${fmtM(c.montant_median)}` : '',
          c.delai_median ? `, délai médian ${entier(c.delai_median)}${NBSP}jours` : '', '.');
      } else {
        p.append(`Aucun appel d’offres ${c.criteres.join(' ou ')}${c.annee ? ` en ${c.annee}` : ''} dans le classeur d’activité.`);
      }
      corps.append(p);
    }

    if (o.autres_offres_client.length) {
      corps.append(h('h3.fiche__section', { texte: 'Les autres offres de ce client' }));
      const liste = h('div.comparables');
      for (const p of o.autres_offres_client) {
        liste.append(h('button.comparable', { type: 'button', onclick: () => { fermer(); ouvrirOffre(p.id); } },
          h('span', { classe: `forme forme--${p.issue === 'Gagné' ? 'gagne' : (p.issue === 'Perdu' ? 'perdu' : 'cours')}` }),
          h('span.comparable__nom', { texte: `${p.expertise} · ${p.annee ?? '—'}` }),
          h('span.comparable__v', { texte: `${fmtM(p.volume)} · ${fmtTaux(p.taux_volume)}` })));
      }
      corps.append(liste);
    }

    const pied = h('p', { style: { marginTop: '28px', display: 'flex', gap: '14px', flexWrap: 'wrap' } });
    pied.append(h('button.bouton', { type: 'button', texte: 'Partir de cette grille', onclick: () => {
      fermer();
      const offre = S.donnees.offres.find(x => x.id === o.id) || o;
      partirDe(offre);
      document.getElementById('bloc-grille')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } }));
    corps.append(pied);
  };
  peindre();
}

function sectionDossier(o, ctx, fermer, rafraichir) {
  const zone = h('div.section-dossier');
  if (o.dossier) {
    const d = o.dossier;
    const mode = o.rattachement.mode === 'manuel' ? 'rattaché à la main' : 'rattaché par le libellé client et l’année';
    const p = h('p.prose', { style: { fontSize: '17px' } });
    p.append(h('b', { texte: d.client }), ` — dossier n° ${d.numero ?? '—'}, ${mode}. `,
      `Reçu le ${dateCourte(d.date_reception)}${d.date_envoi ? `, réponse envoyée le ${dateCourte(d.date_envoi)}` : ', réponse non partie'}. `,
      `${d.resultat && d.resultat !== 'Sans objet' ? d.resultat : d.statut}.`);
    zone.append(p);
    const etapes = [d.a_remis ? 'Step 1' : null, d.a_preselection ? 'Step 2' : null, d.a_oral ? 'Oral' : null].filter(Boolean).join(' · ') || 'aucune';
    const champs = [['Encours du dossier', d.montant_potentiel ? fmtM(d.montant_potentiel) : '—'],
      ['Encours de la grille', o.volume ? fmtM(o.volume) : '—'],
      ['Étapes franchies', etapes], ['Délai de réponse', d.delai_calendaire !== null && d.delai_calendaire !== undefined ? `${entier(d.delai_calendaire)} jours` : '—'],
      ['Classe d’actifs', [d.classe_actifs, d.sous_classe_actifs].filter(Boolean).join(' · ') || '—'],
      ['Segment', d.segment || '—'], ['Pays', d.pays || '—'], ['Consultant', d.consultant || '—'],
      ['Commercial', d.commercial || '—'], ['Fonds', d.fonds || '—']];
    const grille = h('div.champs.champs--fiche');
    for (const [c, v] of champs) grille.append(h('div.champ', {}, h('div.champ__c', { texte: c }), h('div.champ__v', { texte: v })));
    zone.append(grille);
    const actions = h('p', { style: { marginTop: '12px', display: 'flex', gap: '16px', flexWrap: 'wrap' } });
    actions.append(lien('Ouvrir le dossier complet', () => { fermer(); ctx.ouvrirDossier(d.id); }));
    if (o.rattachement.mode === 'manuel') {
      actions.append(lien('Détacher ce dossier', async () => {
        await api.post(`/api/tarif/offres/${encodeURIComponent(o.id)}/rattachement`, { dossier: null });
        await rafraichir();
      }));
    }
    zone.append(actions);
    return zone;
  }
  zone.append(h('p.note', { texte: o.libelle_edite
    ? `Aucun dossier de « ${o.libelle} » en ${o.annee ?? 'cette année'} dans le classeur d’activité. Choisissez-le parmi les candidats.`
    : `Le libellé « ${o.client} » est anonymisé : l’offre ne se relie à aucun dossier par son nom. Donnez-lui son vrai libellé, ou choisissez le dossier.` }));
  const liste = h('div');
  const chercher = async (niveau) => {
    vider(liste).append(chargement('Recherche des dossiers candidats…'));
    let r;
    try {
      r = await api.get(`/api/tarif/offres/${encodeURIComponent(o.id)}/candidats`, niveau === undefined ? undefined : { niveau });
    } catch (e) { vider(liste).append(message(`Recherche impossible : ${e.message}`, { sobre: true })); return; }
    vider(liste);
    liste.append(h('p.note', { style: { margin: '8px 0' } }, `Critère : ${r.libelle}. `,
      r.niveau < r.niveaux.length - 1 ? lien('Élargir la recherche', () => chercher(r.niveau + 1)) : null));
    if (!r.candidats.length) { liste.append(h('p.note', { texte: 'Aucun dossier candidat.' })); return; }
    for (const c of r.candidats) {
      const carte = h('div.candidat');
      carte.append(h('div.candidat__tete', {}, h('b', { texte: c.client }),
        h('span.attenue', { texte: ` · ${c.annee} · ${c.resultat} · ${c.montant_potentiel ? fmtM(c.montant_potentiel) : '—'}` })));
      carte.append(h('div.note', { texte: [c.sous_classe_actifs || c.classe_actifs, ...c.raisons].filter(Boolean).join(' · ') }));
      carte.append(h('button.bouton.bouton--sobre.bouton--petit', { type: 'button', texte: 'Rattacher',
        onclick: async () => {
          await api.post(`/api/tarif/offres/${encodeURIComponent(o.id)}/rattachement`, { dossier: c.cle });
          annoncer(`Offre rattachée au dossier de ${c.client}.`);
          await rafraichir();
        } }));
      liste.append(carte);
    }
  };
  zone.append(h('p', { style: { margin: '10px 0' } }, h('button.bouton.bouton--sobre.bouton--petit', { type: 'button',
    texte: 'Chercher le dossier', onclick: () => chercher() })));
  zone.append(liste);
  return zone;
}
