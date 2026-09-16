// app.js — l'orchestration : la marque, le périmètre, le champ de commande,
// le routage des écrans. Tout le reste est dans les modules d'écran.

import * as api from './api.js';
import * as Etat from './etat.js';
import { Commande } from './commande.js';
import { h, vider, lien, entier, euros, pluriel, message, chargement, annoncer,
  dateCourte } from './ui.js';
import { rendreSituation, reinitialiserNumerotation } from './ecrans/situation.js';
import { rendreAnalyses, nettoyerFigures } from './ecrans/analyses.js';
import { rendreDossiers, ouvrirFiche } from './ecrans/dossiers.js';
import { rendreDonnees } from './ecrans/donnees.js';

const QUESTIONS = ['activite', 'rfp', 'dd', 'aum', 'esg', 'diagnostic'];

const App = {
  meta: null,
  analyse: null,
  etat: Etat.etatVide(),
  commande: null,
  tonsEtat: {},
  signature: null,
  fermerFiche: null,
};

/* ------------------------------------------------------------ démarrage -- */
async function demarrer() {
  const racine = document.getElementById('app');
  try {
    // La marque est un SVG inline : elle hérite de la couleur du texte et ne
    // demande aucune requête supplémentaire une fois en cache.
    const [meta, logo] = await Promise.all([
      api.get('/api/meta'),
      fetch('/assets/logo.svg').then(r => (r.ok ? r.text() : '')).catch(() => ''),
    ]);
    App.meta = meta;
    window.__LOGO__ = logo;
  } catch (e) {
    racine.append(h('div.enveloppe', {}, message(`L’application n’a pas pu démarrer : ${e.message}`)));
    return;
  }
  App.commande = new Commande(App.meta);
  App.etat = Etat.lireURL(App.meta.dimensions);
  lireTons();
  document.title = `${App.meta.produit} — ${App.meta.marque.nom}`;

  peindreCadre();
  window.addEventListener('popstate', () => {
    App.etat = Etat.lireURL(App.meta.dimensions);
    rafraichir({ sansURL: true });
  });
  document.addEventListener('keydown', (e) => {
    const cible = e.target;
    const dansChamp = cible && (cible.tagName === 'INPUT' || cible.tagName === 'TEXTAREA' || cible.isContentEditable);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); ouvrirPalette(); }
    else if (e.key === '/' && !dansChamp) { e.preventDefault(); ouvrirPalette(); }
  });
  await rafraichir({ sansURL: true });
}

/** Les tons des cinq états, tels que core.py les a émis en CSS. */
function lireTons() {
  const s = getComputedStyle(document.documentElement);
  App.tonsEtat = {
    en_cours: s.getPropertyValue('--redaction').trim(),
    en_attente: s.getPropertyValue('--attente').trim(),
    gagnes: s.getPropertyValue('--gagne').trim(),
    perdus: s.getPropertyValue('--perdu').trim(),
    sans_suite: s.getPropertyValue('--sans-suite').trim(),
  };
}

/* ---------------------------------------------------------------- cadre -- */
function peindreCadre() {
  const racine = document.getElementById('app');
  vider(racine);
  racine.append(barreMarque());
  racine.append(navMobile());
  racine.append(barrePerimetre());
  const main = h('main', { id: 'contenu', tabindex: '-1' },
    h('div.enveloppe', { id: 'ecran' }, chargement()));
  racine.append(main);
  racine.append(pied());
}

function barreMarque() {
  const m = App.meta.marque;
  const barre = h('header.barre');
  const int = h('div.barre__int');

  const marque = h('a.marque', { href: '?', 'aria-label': `${m.nom} ${m.activite}`,
    onclick: (e) => { e.preventDefault(); aller('lecture'); } });
  const logo = h('span.marque__logo');
  logo.innerHTML = window.__LOGO__ || '';
  marque.append(logo);
  marque.append(h('span.marque__produit', { texte: App.meta.produit }));
  int.append(marque);

  int.append(navPrincipale('nav'));

  const droite = h('div.barre__droite');
  const touche = /Mac|iPhone|iPad/.test(navigator.platform || '') ? '⌘ K' : 'Ctrl K';
  droite.append(h('button.chercher', { type: 'button', onclick: ouvrirPalette,
    'aria-label': 'Chercher ou changer le périmètre' },
    h('span.chercher__texte', { texte: 'Chercher, filtrer, ouvrir' }),
    h('span.chercher__court', { texte: 'Chercher' }),
    h('span.chercher__touche', { texte: touche })));
  droite.append(h('button.bouton', { type: 'button', id: 'bouton-rapport',
    onclick: telechargerRapport }, 'Rapport'));
  int.append(droite);
  barre.append(int);
  return barre;
}

function navPrincipale(classe) {
  const nav = h(`nav.${classe}`, { 'aria-label': 'Sections' });
  const entrees = [['lecture', 'Situation'], ['analyses', 'Analyses'],
    ['dossiers', 'Dossiers'], ['donnees', 'Données']];
  const courant = QUESTIONS.includes(App.etat.ecran) ? 'analyses' : App.etat.ecran;
  for (const [cle, libelle] of entrees) {
    nav.append(h('a', {
      href: `?ecran=${cle === 'analyses' ? QUESTIONS[0] : cle}`,
      'aria-current': cle === courant ? 'page' : null,
      onclick: (e) => { e.preventDefault(); aller(cle === 'analyses' ? premiereQuestion() : cle); },
    }, libelle));
  }
  return nav;
}

function navMobile() {
  const nav = navPrincipale('nav.nav--mobile');
  nav.id = 'nav-mobile';
  return nav;
}

function premiereQuestion() {
  const dispo = (App.analyse?.sections || []).map(s => s.cle).filter(c => QUESTIONS.includes(c));
  return dispo[0] || 'activite';
}

/* ------------------------------------------------------------ périmètre -- */
function barrePerimetre() {
  const barre = h('div.perimetre', { id: 'perimetre' });
  barre.append(h('div.perimetre__int', { id: 'perimetre-int' }));
  return barre;
}

function peindrePerimetre() {
  const int = document.getElementById('perimetre-int');
  if (!int) return;
  vider(int);
  int.append(h('span.perimetre__cle', { texte: 'Périmètre' }));

  const periodes = h('div.periodes', { role: 'group', 'aria-label': 'Période' });
  for (const p of App.meta.periodes) {
    periodes.append(h('button', {
      type: 'button', 'aria-pressed': String(p.cle === App.etat.periode),
      onclick: () => majEtat({ periode: p.cle, date_min: null, date_max: null }),
    }, p.libelle));
  }
  if (App.etat.periode === 'perso') {
    periodes.append(h('button', { type: 'button', 'aria-pressed': 'true' }, 'Période choisie'));
  }
  int.append(periodes);

  if (App.analyse && App.analyse.filtres) {
    int.append(h('span.perimetre__dates', { texte:
      `${dateCourte(App.analyse.filtres.date_min)} → ${dateCourte(App.analyse.filtres.date_max)}` }));
  }

  const puces = h('div.puces');
  for (const [dim, valeurs] of Object.entries(App.etat.dims)) {
    for (const v of valeurs) {
      puces.append(h('span.puce', {},
        h('b', { texte: App.meta.dimensions[dim] || dim }), v,
        h('button.puce__x', { type: 'button', 'aria-label': `Retirer le filtre ${v}`, texte: '×',
          onclick: () => { App.etat = Etat.retirerFiltre(App.etat, dim, v); rafraichir(); } })));
    }
  }
  if (App.etat.q) {
    puces.append(h('span.puce', {}, h('b', { texte: 'Recherche' }), App.etat.q,
      h('button.puce__x', { type: 'button', 'aria-label': 'Retirer la recherche', texte: '×',
        onclick: () => majEtat({ q: '' }) })));
  }
  if (App.etat.attention) {
    puces.append(h('span.puce', {}, h('b', { texte: 'Liste' }), 'À relancer',
      h('button.puce__x', { type: 'button', 'aria-label': 'Retirer', texte: '×',
        onclick: () => majEtat({ attention: false }) })));
  }
  if (Etat.nbFiltres(App.etat) || App.etat.q || App.etat.attention) {
    puces.append(lien('Tout retirer', () => retirerTout()));
  }
  if (puces.childNodes.length) int.append(puces);

  if (App.analyse) {
    int.append(h('span.perimetre__compte', {},
      h('b', { texte: entier(App.analyse.n), style: { color: 'var(--ink)' } }),
      ` questionnaire${App.analyse.n > 1 ? 's' : ''}`,
      App.analyse.n_precedent ? ` · ${entier(App.analyse.n_precedent)} sur la période précédente` : ''));
  }
}

/* ------------------------------------------------------------- routage --- */
function aller(ecran, modif = {}) {
  App.etat = { ...Etat.cloner(App.etat), ecran, ...modif };
  rafraichir();
}

function majEtat(modif, options = {}) {
  App.etat = { ...Etat.cloner(App.etat), ...modif };
  if (options.sansRecharger) { Etat.ecrireURL(App.etat, { remplacer: true }); return; }
  rafraichir(options);
}

function filtrer(dim, valeur) {
  App.etat = Etat.ajouterFiltre(App.etat, dim, valeur);
  annoncer(`Filtre ajouté : ${App.meta.dimensions[dim] || dim} ${valeur}.`);
  rafraichir();
}

function retirerTout() {
  App.etat = Etat.sansFiltres(App.etat);
  rafraichir();
}

async function rafraichir(options = {}) {
  if (!options.sansURL) Etat.ecrireURL(App.etat, { remplacer: Boolean(options.remplacer) });
  const zone = document.getElementById('ecran');
  const ancienne = document.getElementById('nav-mobile');
  const entetes = document.querySelector('header.barre .nav');
  if (entetes) entetes.replaceWith(navPrincipale('nav'));
  if (ancienne) ancienne.replaceWith(navMobile());

  const besoinAnalyse = App.etat.ecran !== 'donnees';
  const signature = Etat.signaturePerimetre(App.etat);
  if (besoinAnalyse && (signature !== App.signature || !App.analyse)) {
    nettoyerFigures(zone);
    vider(zone).append(chargement());
    peindrePerimetre();
    try {
      const p = Etat.paramsAPI(App.etat);
      p.set('lignes', '7');
      App.analyse = await api.get('/api/analyse', p);
      App.signature = signature;
    } catch (e) {
      App.analyse = null;
      vider(zone).append(messageErreur(e));
      peindrePerimetre();
      return;
    }
  }
  peindrePerimetre();
  const barrePerimetreEl = document.getElementById('perimetre');
  if (barrePerimetreEl) barrePerimetreEl.hidden = App.etat.ecran === 'donnees';
  peindreEcran();
  majPied();

  if (App.etat.dossier && !App.fermerFiche) {
    App.fermerFiche = await ouvrirFiche(App.etat.dossier, contexte());
    App.fermerFiche = null;
  }
}

function messageErreur(e) {
  if (e.statut === 409) {
    return message(e.message, { actions: [lien('Ouvrir l’écran Données', () => aller('donnees'))] });
  }
  return message(`Le calcul n’a pas abouti : ${e.message}`);
}

function peindreEcran() {
  const zone = document.getElementById('ecran');
  nettoyerFigures(zone);
  vider(zone);
  const ctx = contexte();
  reinitialiserNumerotation();

  if (App.etat.ecran === 'donnees') { zone.append(rendreDonnees(ctx)); return; }
  if (!App.analyse) { zone.append(chargement()); return; }
  if (App.analyse.vide) {
    zone.append(h('div.ecran', {}, message(
      'Aucun questionnaire ne correspond à ce périmètre. Élargissez la période ou retirez un filtre.',
      { actions: [lien('Tout retirer', retirerTout)] })));
    return;
  }
  if (App.etat.ecran === 'dossiers') { zone.append(rendreDossiers(ctx)); return; }
  if (QUESTIONS.includes(App.etat.ecran)) { zone.append(rendreAnalyses(ctx)); return; }
  zone.append(rendreSituation(ctx));
}

function contexte() {
  return {
    analyse: App.analyse, meta: App.meta, etat: App.etat, tonsEtat: App.tonsEtat,
    aller, majEtat, filtrer, retirerTout,
    ouvrirDossier: async (id) => {
      App.etat = { ...Etat.cloner(App.etat), dossier: id };
      Etat.ecrireURL(App.etat);
      App.fermerFiche = await ouvrirFiche(id, contexte());
      App.fermerFiche = null;
    },
    listeCompartiment: (cle) => {
      const modif = { ecran: 'dossiers', q: '', attention: false };
      let etat = { ...Etat.cloner(App.etat), ...modif };
      etat = Etat.retirerFiltre(etat, 'statut');
      etat = Etat.retirerFiltre(etat, 'resultat');
      const statuts = { en_cours: 'En cours', en_attente: 'Envoyé', gagnes: 'Gagné',
        perdus: 'Perdu', sans_suite: 'Abandonné' };
      if (cle === 'a_relancer') etat.attention = true;
      else if (statuts[cle]) etat = Etat.ajouterFiltre(etat, 'statut', statuts[cle]);
      App.etat = etat;
      rafraichir();
    },
    chercherClient: (client) => { App.etat = { ...Etat.cloner(App.etat), ecran: 'dossiers', q: client }; rafraichir(); },
    rechargerTout: async () => {
      App.meta = await api.get('/api/meta');
      App.commande = new Commande(App.meta);
      App.signature = null; App.analyse = null;
      lireTons();
    },
  };
}

/* ----------------------------------------------------- champ de commande -- */
function ouvrirPalette() {
  if (document.querySelector('.palette-fond')) return;
  const fond = h('div.palette-fond', { onclick: (e) => { if (e.target === fond) fermer(); } });
  const boite = h('div.palette', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Commande' });
  const champ = h('input', { type: 'text', autocomplete: 'off', spellcheck: 'false',
    placeholder: 'Un pays, un client, un exercice, un état…', 'aria-label': 'Commande' });
  const zoneLu = h('div.palette__lu', { hidden: true });
  const liste = h('div.palette__liste', { role: 'listbox' });
  const pied = h('div.palette__pied', {},
    h('span', { texte: '↑ ↓ pour choisir' }), h('span', { texte: '↵ pour appliquer' }),
    h('span', { texte: 'Échap pour fermer' }));
  boite.append(h('div.palette__champ', {}, champ), zoneLu, liste, pied);
  fond.append(boite);
  document.body.append(fond);
  champ.focus();

  let propositions = [];
  let choisi = 0;

  const fermer = () => { fond.remove(); document.removeEventListener('keydown', surTouche, true); };
  const surTouche = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); fermer(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); choisi = Math.min(choisi + 1, propositions.length - 1); peindre(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); choisi = Math.max(choisi - 1, 0); peindre(); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (propositions[choisi]) propositions[choisi].action();
      fermer();
    }
  };
  document.addEventListener('keydown', surTouche, true);

  const peindre = () => {
    vider(liste);
    if (!propositions.length) {
      liste.append(h('div.palette__vide', { texte:
        champ.value.trim() ? 'Rien ne correspond. La saisie deviendra une recherche plein texte.'
          : 'Exemples : « Suisse 2025 », « gagnés obligataire », « Bellecour », « à relancer », « esg ».' }));
      return;
    }
    propositions.forEach((p, i) => {
      liste.append(h('button.palette__item', {
        type: 'button', role: 'option', 'aria-selected': String(i === choisi),
        onclick: () => { p.action(); fermer(); },
        onmouseenter: () => { choisi = i; peindre(); },
      }, h('span.libelle', { texte: p.libelle }), h('span.detail', { texte: p.detail || '' })));
    });
  };

  const analyser = () => {
    const texte = champ.value;
    const lu = App.commande.interpreter(texte);
    choisi = 0;
    propositions = [];

    vider(zoneLu);
    zoneLu.hidden = !lu.interpretation.length;
    if (lu.interpretation.length) {
      zoneLu.append(h('span.palette__lu-cle', { texte: 'Lu comme' }));
      for (const i of lu.interpretation) {
        zoneLu.append(h('span.puce.puce--lecture', {},
          h('b', { texte: i.libelle }), String(i.valeur)));
      }
    }

    if (texte.trim() && (lu.interpretation.length || lu.q.length)) {
      propositions.push({
        libelle: 'Appliquer cette lecture',
        detail: resumeLecture(lu),
        action: () => appliquer(lu),
      });
    }
    for (const s of App.commande.suggerer(texte)) {
      propositions.push({
        libelle: `${s.valeur}`, detail: s.libelle,
        action: () => { filtrer(s.dim, s.valeur); },
      });
    }
    if (texte.trim()) {
      propositions.push({
        libelle: `Chercher « ${texte.trim()} » dans les dossiers`, detail: 'Dossiers',
        action: () => { App.etat = { ...Etat.cloner(App.etat), ecran: 'dossiers', q: texte.trim() }; rafraichir(); },
      });
    }
    if (!texte.trim()) {
      for (const [cle, libelle] of [['lecture', 'Situation'], ...(App.analyse?.sections || [])
        .filter(s => QUESTIONS.includes(s.cle)).map(s => [s.cle, s.libelle]),
      ['dossiers', 'Dossiers'], ['donnees', 'Données']]) {
        propositions.push({ libelle, detail: 'Écran', action: () => aller(cle) });
      }
      propositions.push({ libelle: 'Générer le rapport du périmètre', detail: 'Rapport',
        action: telechargerRapport });
    }
    peindre();
  };
  champ.addEventListener('input', analyser);
  analyser();
}

function resumeLecture(lu) {
  const bouts = [];
  if (lu.periode) bouts.push('période');
  const n = Object.values(lu.filtres).reduce((s, v) => s + v.length, 0);
  if (n) bouts.push(`${n} filtre${n > 1 ? 's' : ''}`);
  if (lu.q.length) bouts.push('recherche');
  if (lu.ecran) bouts.push('écran');
  return bouts.join(' · ');
}

function appliquer(lu) {
  let etat = Etat.cloner(App.etat);
  if (lu.periode) {
    if (typeof lu.periode === 'string') { etat.periode = lu.periode; etat.date_min = null; etat.date_max = null; }
    else { etat.periode = 'perso'; etat.date_min = lu.periode.date_min; etat.date_max = lu.periode.date_max; }
  }
  for (const [dim, valeurs] of Object.entries(lu.filtres)) {
    for (const v of valeurs) etat = Etat.ajouterFiltre(etat, dim, v);
  }
  if (lu.attention) etat.attention = true;
  if (lu.q.length) { etat.q = lu.q.join(' '); etat.ecran = 'dossiers'; }
  if (lu.ecran === 'rapport') { App.etat = etat; rafraichir().then(telechargerRapport); return; }
  if (lu.ecran) etat.ecran = lu.ecran === 'lecture' ? 'lecture' : lu.ecran;
  App.etat = etat;
  annoncer('Périmètre appliqué.');
  rafraichir();
}

/* ------------------------------------------------------------- rapport --- */
async function telechargerRapport() {
  const bouton = document.getElementById('bouton-rapport');
  const texteInitial = bouton ? bouton.textContent : '';
  if (bouton) { bouton.disabled = true; bouton.textContent = 'Génération…'; }
  annoncer('Génération du rapport.');
  try {
    const reponse = await fetch(api.urlRapport(Etat.paramsAPI(App.etat)));
    if (!reponse.ok) throw new Error((await reponse.json()).detail || reponse.statusText);
    const blob = await reponse.blob();
    const nom = (reponse.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/);
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: nom ? nom[1] : 'rapport.html' });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    annoncer('Rapport téléchargé.');
  } catch (e) {
    const zone = document.getElementById('ecran');
    zone.prepend(message(`Le rapport n’a pas pu être produit : ${e.message}`));
  } finally {
    if (bouton) { bouton.disabled = false; bouton.textContent = texteInitial; }
  }
}

/* ---------------------------------------------------------------- pied --- */
function pied() {
  return h('div.enveloppe', {}, h('footer.pied', { id: 'pied' }));
}

function majPied() {
  const p = document.getElementById('pied');
  if (!p) return;
  vider(p);
  const s = App.meta.source;
  p.append(h('span', { texte: s.mode === 'demo'
    ? `Données de démonstration · ${entier(s.n_lignes_retenues)} questionnaires`
    : `${s.fichier}${s.onglet ? ` · onglet ${s.onglet}` : ''} · ${entier(s.n_lignes_retenues)} questionnaires retenus sur ${entier(s.n_lignes_source)} lignes` }));
  if (App.analyse) {
    p.append(h('span', { texte: `Périmètre : ${entier(App.analyse.n)} dans la sélection` }));
  }
  p.append(h('span.pied__droite', {}, lien('Générer le rapport de ce périmètre', telechargerRapport)));
}

/* -------------------------------------------------------------- départ --- */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', demarrer);
} else {
  demarrer();
}
