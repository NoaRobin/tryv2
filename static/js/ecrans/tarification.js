// tarification.js — le simulateur de prix des appels d'offres.
//
// Une question : pour ce mandat, quel prix proposer, et comment se situe-t-il
// par rapport à ce que le pôle a déjà fait ? La grille se modifie en place ;
// tout le reste — phrase d'ouverture, fourchettes, courbe, relief — suit la
// frappe. Le calcul est celui de tarification.py (static/js/tarif.js).

import { h, vider, lien, entier, message, chargement, annoncer } from '../ui.js';
import * as api from '../api.js';
import * as T from '../tarif.js';
import { courbeTarif, jaugeMarche, bandeTranche, legendeIssues, fmtTaux, fmtPb, fmtFrais, fmtEcartFrais, fmtM,
  fmtCentile, plafondJoli } from '../graphes-tarif.js';
import { NBSP, decimal, dateCourte } from '../format.js';

const MEMOIRE = 'tarif.simulateur.v1';
const TAILLES_REFERENCE = [25, 50, 100, 150, 250, 500];
const ISSUES = [['Gagné', 'Gagnées'], ['Perdu', 'Perdues'], ['En cours', 'En cours']];

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
    }
  } catch (e) { /* stockage indisponible : on repart de la grille type */ }
  s.lignes = T.normaliser(s.lignes);
  return s;
}

function memoriser() {
  try {
    localStorage.setItem(MEMOIRE, JSON.stringify({ lignes: S.lignes, encours: S.encours,
      expertise: S.expertise, origine: S.origine }));
  } catch (e) { /* stockage indisponible : sans conséquence */ }
}

/* ------------------------------------------------------------- calculs --- */
const libelleExpertise = (cle) => (S.donnees.expertises.find(e => e.cle === cle) || {}).libelle || cle;

function passe(o) {
  const f = S.filtres;
  if (o.annee !== null && o.annee !== undefined && f.de !== null && (o.annee < f.de || o.annee > f.a)) return false;
  if (!f.issues.has(o.issue)) return false;
  if (S.donnees.natures.length > 1 && o.nature && !f.natures.has(o.nature)) return false;
  return true;
}

function eligibles(cle = S.expertise) {
  return S.donnees.offres.filter(o => !o.exclue && o.expertise_cle === cle && passe(o));
}

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
  return { grille, elig, A, tm, fr, marche, centile, comparaisons };
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

function construire(ecran, ctx) {
  R.ctx = ctx;
  // L'ouverture : la phrase calculée, et les chiffres qui comptent.
  const ouverture = h('div.lecture.ouverture');
  R.lede = h('p.lede');
  R.matin = h('p.matin');
  ouverture.append(h('div', {}, R.lede, R.matin));
  R.margeOuverture = h('div.marge-col');
  ouverture.append(R.margeOuverture);
  ecran.append(ouverture);

  ecran.append(barreReglages());
  ecran.append(blocGrille());
  ecran.append(blocMarche());
  ecran.append(blocCourbe());
  ecran.append(blocRelief());
  ecran.append(blocExpertises());
  ecran.append(blocOffres());
  ecran.append(blocClasseur());
}

/* ----------------------------------------------------- barre de réglages --- */
function barreReglages() {
  const barre = h('div.reglages', { role: 'region', 'aria-label': 'Réglages du simulateur' });
  R.tuiles = h('div.tuiles', { role: 'group', 'aria-label': 'Expertise' });
  barre.append(R.tuiles);

  const ligne = h('div.reglages__ligne');
  // La taille du mandat : saisie libre, et un curseur logarithmique de 5 à 1 000 M€.
  const champ = h('input.saisie.saisie--encours', { type: 'number', min: 1, max: 100000, step: 5,
    value: S.encours, 'aria-label': 'Taille du mandat en millions d’euros' });
  const curseur = h('input.curseur', { type: 'range', min: 0, max: 1000, step: 1,
    'aria-label': 'Taille du mandat', value: versCurseur(S.encours) });
  const poser = (v, source) => {
    if (!(v > 0)) return;
    S.encours = Math.round(v);
    if (source !== champ) champ.value = S.encours;
    if (source !== curseur) curseur.value = versCurseur(S.encours);
    maj();
  };
  champ.addEventListener('input', () => poser(Number(champ.value), champ));
  curseur.addEventListener('input', () => poser(deCurseur(Number(curseur.value)), curseur));
  R.champEncours = champ; R.curseurEncours = curseur;
  ligne.append(h('label.reglage', {}, h('span.reglage__c', { texte: 'Taille du mandat' }),
    h('span.reglage__v', {}, champ, h('span.unite', { texte: 'M€' }), curseur)));

  // Les offres comparées : années, issue, nature du client.
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
      const b = h('button.puce-filtre', { type: 'button', 'aria-pressed': 'true', texte: nat,
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
  barre.append(ligne);
  return barre;
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
  R.tableGrille.append(h('thead', {}, h('tr', {},
    h('th', { texte: 'Tranche' }), h('th.num', { texte: 'De (M€)' }), h('th.num', { texte: 'À (M€)' }),
    h('th.num', { texte: 'Taux (%)' }), h('th', { texte: 'Déjà pratiqué sur la tranche' }),
    R.enteteFrais = h('th.num', { texte: 'Frais' }), h('th', { 'aria-label': 'Actions' }))));
  R.corpsGrille = h('tbody');
  R.tableGrille.append(R.corpsGrille);
  R.piedGrille = h('tfoot');
  R.tableGrille.append(R.piedGrille);
  R.origine = h('p.note.grille-origine');

  return bloc('grille', 'La grille', [outils, h('div.tableau', {}, R.tableGrille), R.origine], margeTexte('Lecture',
    'Chaque taux ne s’applique qu’à la <b>part de l’encours</b> qui tombe dans sa tranche, comme un barème progressif : c’est ainsi que la présentation obtient 0,093 % à 150 M€.',
    'La <b>dernière tranche</b> s’applique au-delà de son seuil.',
    '<b>Déjà pratiqué</b> : ce que les offres passées de l’expertise facturaient sur la même part d’encours — trait de la médiane, bande du plus bas au plus haut, point pour votre taux. Changer les bornes d’une tranche recalcule ce marché.',
    'Flèches haut et bas dans une case : ±0,005 point de taux, ±5 M€ de borne.'));
}

function charger(tranches, origine) {
  S.lignes = T.normaliser(tranches.map(t => ({ ...t })));
  S.origine = origine;
  peindreGrille();
  maj();
  annoncer(`Grille chargée : ${origine}.`);
}

function partirDe(o) {
  S.expertise = o.expertise_cle;
  if (o.volume) { S.encours = Math.round(o.volume); R.champEncours.value = S.encours; R.curseurEncours.value = versCurseur(S.encours); }
  charger(o.tranches, `l’offre ${o.libelle} ${o.annee ?? ''} (${o.issue.toLowerCase()}), à son encours de ${fmtM(o.volume)}`.replace(/\s+/g, ' '));
  maj({ offres: true });
}

/** La grille entière se redessine (structure) ; la frappe ne met à jour que les calculs. */
function peindreGrille() {
  vider(R.corpsGrille);
  R.lignesGrille = S.lignes.map((t, i) => {
    const derniere = i === S.lignes.length - 1;
    const tr = h('tr');
    tr.append(h('td.grille-tarif__nom', { texte: `T${i + 1}` }));
    tr.append(h('td.num.attenue', { texte: entier(t.minimum) }));
    let champMax = null;
    if (derniere) {
      tr.append(h('td.num.attenue', { texte: 'et au-delà' }));
    } else {
      champMax = h('input.saisie.saisie--borne', { type: 'number', step: 5, min: 0, value: t.maximum,
        'aria-label': `Plafond de la tranche ${i + 1} en M€` });
      champMax.addEventListener('input', () => {
        const v = Number(champMax.value);
        const bas = S.lignes[i].minimum;
        const haut = i + 2 < S.lignes.length ? S.lignes[i + 1].maximum : Infinity;
        const ok = Number.isFinite(v) && v > bas && v < haut;
        champMax.setAttribute('aria-invalid', String(!ok));
        if (!ok) return;
        S.lignes[i].maximum = v; S.lignes[i + 1].minimum = v;
        R.lignesGrille[i + 1].de.textContent = entier(v);
        maj({ source: 'grille' });
      });
      champMax.addEventListener('change', () => { champMax.value = S.lignes[i].maximum; champMax.setAttribute('aria-invalid', 'false'); });
      tr.append(h('td.num', {}, champMax));
    }
    const champTaux = h('input.saisie.saisie--taux', { type: 'number', step: 0.005, min: 0, max: 5,
      value: t.taux, 'aria-label': `Taux de la tranche ${i + 1} en pour cent` });
    champTaux.addEventListener('input', () => {
      const v = Number(champTaux.value);
      const ok = champTaux.value !== '' && Number.isFinite(v) && v >= 0 && v <= 5;
      champTaux.setAttribute('aria-invalid', String(!ok));
      if (!ok) return;
      S.lignes[i].taux = v;
      maj({ source: 'grille' });
    });
    champTaux.addEventListener('change', () => { champTaux.value = S.lignes[i].taux; champTaux.setAttribute('aria-invalid', 'false'); });
    tr.append(h('td.num', {}, champTaux));
    const marche = h('td.grille-tarif__marche');
    tr.append(marche);
    const frais = h('td.num');
    tr.append(frais);
    const actions = h('td.grille-tarif__actions');
    if (S.lignes.length > 1) {
      actions.append(h('button.croix', { type: 'button', 'aria-label': `Retirer la tranche ${i + 1}`, texte: '×',
        onclick: () => {
          S.lignes.splice(i, 1);
          S.lignes = T.normaliser(S.lignes);
          S.origine = `${S.origine.replace(/, modifiée$/, '')}, modifiée`;
          peindreGrille(); maj();
        } }));
    }
    tr.append(actions);
    R.corpsGrille.append(tr);
    return { tr, de: tr.children[1], champMax, champTaux, marche, frais };
  });
}

function ajouterTranche() {
  const der = S.lignes[S.lignes.length - 1];
  const seuil = Math.round(Math.max(der.minimum * 2, der.minimum + 50) / 5) * 5;
  const marche = T.fourchetteTranche(eligibles(), seuil, T.hautDeTrancheOuverte(seuil, S.encours));
  der.maximum = seuil;
  S.lignes.push({ minimum: seuil, maximum: null, taux: marche.n ? T.arrondiBp(marche.mediane) : der.taux });
  S.lignes = T.normaliser(S.lignes);
  peindreGrille(); maj();
  annoncer(`Tranche ajoutée au-delà de ${seuil} M€.`);
}

function majGrille(D) {
  const domaine = plafondJoli(Math.max(...D.comparaisons.map(c => (c.resume.n ? c.resume.max : 0)),
    ...D.grille.map(t => t.taux), 0.05) * 1.08, 4);
  R.enteteFrais.textContent = `Frais à ${entier(D.A)} M€`;
  D.comparaisons.forEach((c, i) => {
    const l = R.lignesGrille[i];
    if (!l) return;
    const t = D.grille[i];
    vider(l.marche);
    if (c.resume.n) {
      l.marche.append(bandeTranche(c.resume, t.taux, domaine));
      const txt = h('span.grille-tarif__fourchette.cellule-sous', {},
        `${fmtTaux(c.resume.min, { unite: false })}–${fmtTaux(c.resume.max, { unite: false })}`,
        h('span.attenue', { texte: ` · méd. ${fmtTaux(c.resume.mediane, { unite: false })}` }));
      l.marche.append(txt);
      const ecartMediane = t.taux - c.resume.mediane;
      if (Math.abs(ecartMediane) >= 0.0005) {
        l.marche.append(h('button.lien-sobre.lien-sobre--mini', { type: 'button',
          title: `Appliquer la médiane pratiquée sur cette tranche (${fmtTaux(c.resume.mediane)})`,
          texte: '→ médiane',
          onclick: () => {
            S.lignes[i].taux = T.arrondiBp(c.resume.mediane);
            l.champTaux.value = S.lignes[i].taux;
            S.origine = `${S.origine.replace(/, modifiée$/, '')}, modifiée`;
            maj();
          } }));
      }
    } else {
      l.marche.append(h('span.attenue', { texte: 'aucune offre comparable' }));
    }
    const part = Math.max(0, Math.min(D.A, c.ouverte ? Infinity : t.maximum) - t.minimum);
    l.frais.textContent = part > 0 ? fmtFrais(part * t.taux / 100) : 'non atteinte';
    l.frais.classList.toggle('attenue', !(part > 0));
  });
  // Le total sous ses colonnes : le taux moyen sous les taux, les frais sous les frais.
  vider(R.piedGrille);
  R.piedGrille.append(h('tr', {},
    h('td', { colspan: 3 }, h('button.lien-sobre', { type: 'button', texte: '+ Ajouter une tranche', onclick: ajouterTranche })),
    h('td.num.grille-tarif__total', {}, h('b', { texte: fmtTaux(D.tm) })),
    h('td.grille-tarif__total.attenue', { texte: `taux moyen et frais à ${entier(D.A)} M€` }),
    h('td.num.grille-tarif__total', {}, h('b', { texte: fmtFrais(D.fr) })),
    h('td')));
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

/* ============================================================ 02 marché === */
function blocMarche() {
  R.phraseMarche = h('p.prose.prose--bloc');
  R.zoneJauge = h('div');
  R.pointsMarche = h('p.note.repere-marche');
  return bloc('marche', 'Le prix dans le marché', [R.phraseMarche, R.zoneJauge, legendeIssues(), R.pointsMarche],
    margeTexte('Lecture',
      'Chaque carré est une offre déjà faite, <b>appliquée à la taille de votre mandat</b> : le prix qu’elle aurait donné à ce client. Plein : gagnée. Creux : perdue. À moitié : en cours.',
      'Bande claire : du plus bas au plus haut. Bande foncée : la moitié centrale des offres. Trait : la médiane.',
      'Un clic sur un carré ouvre la fiche de l’offre.'));
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
}

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
const pluriel2 = (n, mot, pluriel = null) => `${entier(n)}${NBSP}${n > 1 ? (pluriel || `${mot}s`) : mot}`;
const capitale = (t) => t.charAt(0).toUpperCase() + t.slice(1);

/* ============================================================ 03 courbe === */
function blocCourbe() {
  R.zoneCourbe = h('div');
  R.legendeCourbe = h('div.legende-tarif');
  return bloc('courbe', 'La dégressivité', [R.legendeCourbe, R.zoneCourbe, legendeIssues()], margeTexte('Lecture',
    'Le taux moyen payé selon la taille du mandat. <b>Trait épais</b> : votre grille. <b>Trait fin</b> : la médiane des offres de l’expertise ; en pointillé, leur moyenne, la mesure de la présentation d’origine.',
    'Les bandes disent ce que la moyenne cache : du plus bas au plus haut, et la moitié centrale.',
    'Chaque carré est une offre à son propre encours. Survolez la figure pour lire les valeurs à une taille donnée.',
    'La dernière tranche s’appliquant au-delà de son seuil, la moyenne ne s’effondre plus vers zéro aux grandes tailles comme dans la version d’origine.'));
}

function majCourbe(D) {
  const pts = D.elig.filter(o => o.volume).map(o => ({ x: o.volume, y: o.taux_volume, issue: o.issue,
    titre: `${o.libelle} · ${o.annee ?? '—'}`, id: o.id }));
  const xMax = plafondJoli(Math.max(D.A * 1.8, ...pts.map(p => p.x * 1.1), 200), 5);
  const params = { grille: D.grille, eligibles: D.elig, encours: D.A, xMax, points: pts,
    libelleExpertise: libelleExpertise(S.expertise), surPoint: (p) => ouvrirOffre(p.id) };
  if (!R.courbe) { R.courbe = courbeTarif(params); R.zoneCourbe.append(R.courbe.el); } else R.courbe.maj(params);
  vider(R.legendeCourbe);
  const item = (classe, texte) => h('span.legende-tarif__item', {}, h('span', { classe }), texte);
  R.legendeCourbe.append(item('trait trait--fort', 'Votre grille'), item('trait trait--moyen', 'Médiane'),
    item('trait trait--pointille', 'Moyenne'), item('aplat aplat--clair', 'Plus bas – plus haut'),
    item('aplat aplat--fonce', 'Moitié centrale'));
}

/* ============================================================ 04 relief === */
function blocRelief() {
  R.phraseRelief = h('p.prose.prose--bloc');
  R.hoteRelief = h('div.relief-hote');
  const vues = h('div.relief-vues', { role: 'group', 'aria-label': 'Point de vue' });
  for (const [cle, texte] of [['perspective', 'Perspective'], ['face', 'De face'], ['dessus', 'Vue de dessus']]) {
    vues.append(h('button.puce-filtre', { type: 'button', 'aria-pressed': String(cle === 'perspective'), texte,
      onclick: (e) => {
        for (const b of vues.children) b.setAttribute('aria-pressed', String(b === e.currentTarget));
        if (R.relief) R.relief.vue(cle);
      } }));
  }
  R.boutonBalayage = h('button.bouton.bouton--sobre.bouton--petit', { type: 'button', texte: '▶ Si le mandat grossit',
    onclick: balayer });
  R.etatBalayage = h('span.note');
  R.variante = h('div.relief-variante', { hidden: true });
  R.sensibilite = h('p.note.relief-lecture');
  const commandes = h('div.relief-commandes', {}, vues, h('span.relief-commandes__droite', {}, R.etatBalayage, R.boutonBalayage));
  // Le module 3D et Three.js ne se chargent qu'ici, à la demande.
  import('../relief.js').then((m) => {
    R.moduleRelief = m;
    R.relief = m.creerRelief(R.hoteRelief, {
      surApercu: majVariante,
      surAppliquer: (remise, facteur) => {
        charger(grilleAjustee(remise, facteur), `${S.origine.replace(/, ajustée.*$/, '')}, ajustée depuis le relief`);
      },
    });
    majRelief(calculer());
  }).catch((e) => { R.hoteRelief.append(message(`Le relief n’a pas pu se charger : ${e.message}`, { sobre: true })); });
  return bloc('relief', 'Le relief du prix', [R.phraseRelief, commandes, R.hoteRelief, R.variante, R.sensibilite],
    margeTexte('Lire le relief',
      'Chaque point de la nappe est une <b>variante de votre grille</b> pour ce client. De gauche à droite : une remise ou une majoration de tous les taux. D’avant en arrière : les seuils des tranches divisés par deux ou doublés.',
      '<b>Hauteur</b> : le taux moyen payé. <b>Couleur</b> : claire sous la plus basse des offres déjà faites à cette taille, foncée au-dessus de la plus haute ; c’est dans la fourchette qu’elle change.',
      'Les lignes grises relient les variantes de <b>même prix</b> ; les lignes blanches cernées d’encre marquent le plus bas, la médiane et le plus haut déjà proposés.',
      'Faites glisser pour tourner, molette pour s’approcher. Un clic sur la nappe choisit une variante ; « Appliquer » l’écrit dans la grille.'), { large: true });
}

function majRelief(D) {
  vider(R.phraseRelief);
  R.phraseRelief.append(`Pour un mandat de ${entier(D.A)} M€, quelle concession pèse le plus ? `);
  R.phraseRelief.append(h('span.attenue', { texte: 'Plus la nappe monte, plus le client paie ; la pente dit quel levier compte.' }));
  if (R.relief) R.relief.maj({ grille: D.grille, encours: D.A, eligibles: D.elig, libelle: libelleExpertise(S.expertise) });
  if (R.moduleRelief) {
    const s = R.moduleRelief.sensibilite(D.grille, D.A);
    const eq = Number.isFinite(s.equivalente) ? `, soit l’équivalent d’une remise de ${decimal(Math.abs(s.equivalente) * 100, 0)}${NBSP}%` : '';
    R.sensibilite.textContent = `Pour ce client, 10 % de remise sur tous les taux changent le prix de ${fmtPb(s.remise10)} ; `
      + `abaisser tous les seuils d’un tiers le change de ${fmtPb(s.seuilsBas)}${eq} ; les relever de moitié, de ${fmtPb(s.seuilsHaut)}.`;
  }
}

/** La variante telle qu'elle s'écrira dans la grille : seuils au multiple de
 * 5 M€, taux au millième de point. Le bandeau annonce CE prix-là, pas celui du
 * point exact de la nappe, pour que « Appliquer » ne réserve aucune surprise. */
function grilleAjustee(remise, facteur) {
  return T.ajuster(T.normaliser(S.lignes), remise, facteur)
    .map(t => ({ minimum: Math.round(t.minimum / 5) * 5, maximum: t.maximum === null ? null : Math.round(t.maximum / 5) * 5,
      taux: T.arrondiBp(t.taux) }));
}

function majVariante(v) {
  vider(R.variante);
  R.variante.hidden = !v;
  if (!v) return;
  const D = calculer();
  v = { ...v, taux: T.tauxMoyen(T.normaliser(grilleAjustee(v.remise, v.facteur)), D.A) };
  const f = D.A * v.taux / 100;
  R.variante.append(h('span', {},
    h('b', { texte: `${v.remise ? `${v.remise < 0 ? 'Remise' : 'Majoration'} de ${Math.abs(Math.round(v.remise * 100))}${NBSP}%` : 'Taux inchangés'}` }),
    `, ${Math.abs(v.facteur - 1) < 0.005 ? 'seuils inchangés' : `seuils ×${decimal(v.facteur, 2)}`} : `,
    h('b', { texte: fmtTaux(v.taux) }), ` · ${fmtFrais(f)} HT par an (${fmtPb(v.taux - D.tm)}, ${fmtEcartFrais(f - D.fr)}).`));
  R.variante.append(h('span.relief-variante__actions', {},
    h('button.bouton.bouton--petit', { type: 'button', texte: 'Appliquer à la grille', onclick: () => R.relief.appliquer() }),
    lien('Annuler', () => R.relief.oublier())));
}

function balayer() {
  if (!R.relief) return;
  const jusqua = Math.max(S.encours * 4, 400);
  R.boutonBalayage.disabled = true;
  R.relief.balayer({ jusqua,
    surPas: (a) => { R.etatBalayage.textContent = `mandat à ${entier(a)} M€`; },
    fin: () => { R.boutonBalayage.disabled = false; R.etatBalayage.textContent = ''; } });
}

/* ========================================================= 05 expertises === */
function blocExpertises() {
  R.corpsExpertises = h('tbody');
  R.teteExpertises = h('thead');
  R.mesures = h('div.relief-vues', { role: 'group', 'aria-label': 'Mesure' });
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

/* ============================================================ 06 offres === */
function blocOffres() {
  R.zoneOffres = h('div');
  R.bascule = h('div.relief-vues', { role: 'group', 'aria-label': 'Périmètre de la liste' });
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

/* =========================================================== 07 classeur === */
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
  // Deux phrases, pas trois : le prix, puis sa place parmi ce qui a été fait.
  const suite = h('span.attenue');
  const f = D.marche;
  if (f.n) {
    suite.append(`${capitale(cherete(D.centile))} ${exp} déjà faites à cette taille, qui allaient de ${fmtTaux(f.min)} à ${fmtTaux(f.max)}.`);
  } else {
    suite.append(`Aucune offre ${exp} ne répond aux réglages : élargissez les années ou l’issue pour situer ce prix.`);
  }
  R.lede.append(suite);

  vider(R.matin);
  const fait = (valeur, libelle) => h('span', {}, h('b', { texte: valeur }), ` ${libelle}`);
  R.matin.append(fait(fmtTaux(D.tm), 'de taux moyen'), fait(fmtFrais(D.fr), 'HT par an'));
  if (f.n) R.matin.append(fait(positionCourte(D.centile), `parmi ${pluriel2(f.n, 'offre')} ${exp}`));
  if (f.gagnes.n) {
    const e = ecart(D.tm - f.gagnes.mediane);
    R.matin.append(e.valeur ? fait(e.valeur, `${e.sens} la médiane des gagnées`)
      : h('span', { texte: 'Au niveau de la médiane des gagnées' }));
  }

  vider(R.margeOuverture).append(...margeTexte('La simulation',
    `Expertise <b>${exp}</b>, mandat de <b>${entier(D.A)} M€</b>, grille à ${pluriel2(D.grille.length, 'tranche')}.`,
    `Comparée aux offres ${S.filtres.de !== null ? `de ${S.filtres.de} à ${S.filtres.a}` : ''}, ${[...S.filtres.issues].map(i => i.toLowerCase()).join(', ')}.`),
  h('p.marge-texte', {}, lien('Recommencer depuis la grille type', () => {
    try { localStorage.removeItem(MEMOIRE); } catch (e) { /* rien */ }
    S.encours = 150; R.champEncours.value = 150; R.curseurEncours.value = versCurseur(150);
    charger(S.donnees.grille_type, 'la grille type de la présentation (page 2)');
  })));
}

/* ================================================================ maj === */
let attente = null;
function maj({ offres = false, source = null } = {}) {
  const D = calculer();
  majOuverture(D);
  peindreTuiles();
  if (!R.lignesGrille || R.lignesGrille.length !== S.lignes.length) peindreGrille();
  majGrille(D);
  majMarche(D);
  majCourbe(D);
  majExpertises(D);
  if (offres || !R.offresPeintes) { majOffres(); majClasseur(); R.offresPeintes = true; }
  // Le relief suit la frappe sans la freiner : une image après la dernière touche.
  clearTimeout(attente);
  attente = setTimeout(() => majRelief(calculer()), source === 'grille' ? 90 : 0);
  memoriser();
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
