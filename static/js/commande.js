// commande.js — comprendre une requête écrite avec le vocabulaire des données.
//
// « Suisse 2025 », « gagnés obligataire », « Bellecour », « France attente
// 24 mois », « esg », « rapport »… Le texte est découpé, chaque morceau est
// rapproché des valeurs connues (dimensions, exercices, mois, états,
// familles, écrans). Ce qui n'est reconnu par rien devient une recherche
// plein texte dans les dossiers. Rien n'est deviné par un modèle : c'est un
// rapprochement de vocabulaire, et l'interprétation est rendue en clair.

import { cle, MOIS_LONG } from './format.js';

const ECRANS = [
  ['lecture', ['lecture', 'accueil', 'situation', 'vue d ensemble', 'synthese', 'ou en sommes nous']],
  ['activite', ['activite', 'charge', 'volume', 'volumes', 'delai', 'delais', 'cadence']],
  ['rfp', ['pipeline', 'appels d offres', 'appel d offres', 'resultats']],
  ['dd', ['due diligence', 'dd', 'questionnaires', 'expertise', 'expertises']],
  ['aum', ['encours', 'gains', 'mandats', 'collecte', 'aum']],
  ['esg', ['esg']],
  ['diagnostic', ['diagnostic', 'constats', 'causes', 'tendance', 'projection']],
  ['dossiers', ['dossiers', 'explorateur', 'explorer', 'liste', 'recherche', 'fiche']],
  ['donnees', ['donnees', 'data', 'source', 'brancher', 'branchement', 'import', 'importer', 'qualite', 'fichier', 'excel', 'classeur']],
  ['rapport', ['rapport', 'export', 'exporter', 'html', 'pdf', 'imprimer']],
];

// Mots qui désignent un état ou un résultat d'appel d'offres → filtre.
const ETATS = [
  ['statut', 'Gagné', ['gagne', 'gagnes', 'remporte', 'remportes', 'won', 'gagnee', 'gagnees']],
  ['statut', 'Perdu', ['perdu', 'perdus', 'lost', 'perdue', 'perdues']],
  ['statut', 'Envoyé', ['attente', 'en attente', 'envoye', 'envoyes', 'remis', 'decision']],
  ['statut', 'En cours', ['redaction', 'en redaction', 'en cours', 'ouverts', 'ouvert']],
  ['statut', 'Abandonné', ['sans suite', 'abandonne', 'abandonnes', 'no bid']],
  ['famille', 'RFP', ['rfp', 'appel d offres', 'appels d offres', 'ao']],
  ['famille', 'Due Diligence', ['due diligence', 'due diligences', 'dd']],
  ['bande_esg', '> 75 % ESG', ['tres esg', 'forte esg', 'esg fort', 'esg forte']],
  ['soutenance', 'Oui', ['avec oral', 'a l oral', 'soutenance', 'soutenu', 'soutenus', 'oral']],
  ['sri', 'Oui', ['isr', 'sri', 'socialement responsable']],
];

const PERIODES = [
  ['12m', ['12 mois', '12 derniers mois', 'douze mois', 'un an', '1 an', 'annee glissante']],
  ['24m', ['24 mois', '24 derniers mois', 'deux ans', '2 ans']],
  ['36m', ['36 mois', '36 derniers mois', 'trois ans', '3 ans']],
  ['tout', ['tout', 'tout l historique', 'historique', 'historique complet', 'depuis le debut', 'toutes les annees']],
];

// Préfixes explicites : « pays: suisse », « client = bellecour ».
const PREFIXES = {
  pays: 'pays', client: 'client', classe: 'classe_actifs', 'classe d actifs': 'classe_actifs',
  expertise: 'expertise', consultant: 'consultant', fonds: 'fonds', analyste: 'analyste',
  langue: 'langue', statut: 'statut', resultat: 'resultat', type: 'famille', famille: 'famille',
  'type de client': 'type_client', 'sous classe': 'sous_classe_actifs', forme: 'forme_juridique',
  segment: 'segment', commercial: 'commercial', sales: 'commercial', redacteur: 'analyste',
  writer: 'analyste', relecteur: 'relecteur', reviewer: 'relecteur', isr: 'sri', sri: 'sri',
  oral: 'soutenance', soutenance: 'soutenance',
};

export class Commande {
  /**
   * @param {object} meta — /api/meta : options (dimension → valeurs), dimensions
   *   (dimension → libellé), periodes, dates.
   */
  constructor(meta) {
    this.meta = meta;
    this.libelles = meta.dimensions || {};
    // Index valeur normalisée → [dimension, valeur] ; les valeurs longues d'abord.
    this.index = [];
    for (const [dim, valeurs] of Object.entries(meta.options || {})) {
      for (const v of valeurs) {
        const k = cle(v);
        if (k) this.index.push({ k, dim, v, mots: k.split(' ').length });
      }
    }
    this.index.sort((a, b) => b.mots - a.mots || b.k.length - a.k.length);
    const [amin, amax] = [meta.dates?.min, meta.dates?.max].map(d => (d ? Number(String(d).slice(0, 4)) : null));
    this.annees = amin && amax ? { min: amin, max: amax } : null;
  }

  /** Découpe la requête en morceaux puis rapproche. */
  interpreter(texte) {
    const resultat = { filtres: {}, periode: null, ecran: null, q: [], interpretation: [], action: null };
    const brut = String(texte || '').trim();
    if (!brut) return resultat;

    // Préfixes « dimension: valeur » (jusqu'au prochain préfixe ou à la fin)
    let reste = brut;
    const motifPrefixe = new RegExp(`(?:^|\\s)(${Object.keys(PREFIXES).map(p => p.replace(/ /g, '\\s')).join('|')})\\s*[:=]\\s*([^:=]+?)(?=\\s+[a-zé ]+\\s*[:=]|$)`, 'gi');
    reste = reste.replace(motifPrefixe, (m, pref, val) => {
      const dim = PREFIXES[cle(pref)];
      const valeur = this._valeurDe(dim, val);
      if (valeur) {
        this._ajouter(resultat, dim, valeur, `${this.libelles[dim] || dim} : ${valeur}`);
      } else {
        resultat.q.push(val.trim());
        resultat.interpretation.push({ type: 'recherche', libelle: 'Recherche', valeur: val.trim() });
      }
      return ' ';
    });

    let k = cle(reste);
    if (!k) return resultat;

    // 1. Périodes écrites
    for (const [code, formes] of PERIODES) {
      for (const f of formes) {
        if (this._contient(k, f)) { k = this._retirer(k, f); resultat.periode = code; }
      }
    }
    // 2. Exercices : « 2025 », « 2024 2025 » → le second devient la borne ; « en 2025 »
    const annees = [];
    k = k.replace(/\b(19|20)\d{2}\b/g, (a) => {
      const n = Number(a);
      if (this.annees && n >= this.annees.min && n <= this.annees.max) { annees.push(n); return ' '; }
      return a;
    });
    if (annees.length) {
      annees.sort();
      if (annees.length === 1) resultat.periode = String(annees[0]);
      else resultat.periode = { date_min: `${annees[0]}-01-01`, date_max: `${annees[annees.length - 1]}-12-31` };
    }
    // 3. Mois écrits : « janvier », « janvier 2026 »
    for (let i = 0; i < MOIS_LONG.length; i++) {
      const m = cle(MOIS_LONG[i]);
      if (this._contient(k, m)) {
        k = this._retirer(k, m);
        const an = annees.length ? annees[annees.length - 1] : (this.annees?.max ?? new Date().getFullYear());
        const fin = new Date(an, i + 1, 0).getDate();
        resultat.periode = { date_min: `${an}-${String(i + 1).padStart(2, '0')}-01`, date_max: `${an}-${String(i + 1).padStart(2, '0')}-${fin}` };
      }
    }
    // 4. Écrans et actions ; « à relancer » restreint la liste aux dossiers qui attendent
    for (const f of ['a relancer', 'relancer', 'relances', 'relance', 'en retard', 'urgents', 'urgent']) {
      if (this._contient(k, f)) {
        k = this._retirer(k, f);
        resultat.attention = true;
        resultat.ecran = resultat.ecran || 'dossiers';
        resultat.interpretation.push({ type: 'attention', libelle: 'Liste', valeur: 'À relancer' });
      }
    }
    for (const [ecran, formes] of ECRANS) {
      for (const f of formes) {
        if (this._contient(k, f)) { k = this._retirer(k, f); resultat.ecran = ecran; }
      }
    }
    // 5. États, familles, types
    for (const [dim, valeur, formes] of ETATS) {
      for (const f of formes) {
        if (this._contient(k, f)) {
          k = this._retirer(k, f);
          if ((this.meta.options || {})[dim]?.includes(valeur) || dim === 'famille' || dim === 'statut') {
            this._ajouter(resultat, dim, valeur, `${this.libelles[dim] || dim} : ${valeur}`);
          }
        }
      }
    }
    // 6. Valeurs des dimensions, les plus longues d'abord ; puis correspondance partielle
    for (const e of this.index) {
      if (!k) break;
      if (this._contient(k, e.k)) {
        k = this._retirer(k, e.k);
        this._ajouter(resultat, e.dim, e.v, `${this.libelles[e.dim] || e.dim} : ${e.v}`);
      }
    }
    // Correspondance partielle : un mot d'au moins 4 lettres contenu dans UNE seule
    // valeur d'une dimension à faible cardinalité (pays, classe, expertise…).
    const restants = k.split(' ').filter(Boolean);
    const nonReconnus = [];
    for (const mot of restants) {
      if (mot.length < 4) { nonReconnus.push(mot); continue; }
      const candidats = this.index.filter(e => e.dim !== 'client' && e.dim !== 'fonds' && e.dim !== 'consultant'
        && e.dim !== 'analyste' && e.k.split(' ').some(w => w.startsWith(mot)));
      const dims = new Set(candidats.map(c => c.dim + '|' + c.v));
      if (dims.size === 1) {
        const c = candidats[0];
        this._ajouter(resultat, c.dim, c.v, `${this.libelles[c.dim] || c.dim} : ${c.v}`);
      } else {
        nonReconnus.push(mot);
      }
    }
    // 7. Le reste : une recherche plein texte (client, fonds, consultant…)
    const libre = nonReconnus.join(' ').trim();
    if (libre) {
      resultat.q.push(libre);
      resultat.interpretation.push({ type: 'recherche', libelle: 'Recherche', valeur: libre });
      if (!resultat.ecran && !Object.keys(resultat.filtres).length) resultat.ecran = 'dossiers';
    }
    if (resultat.periode) {
      const lib = typeof resultat.periode === 'string'
        ? (this.meta.periodes || []).find(p => p.cle === resultat.periode)?.libelle || `Exercice ${resultat.periode}`
        : `Du ${resultat.periode.date_min} au ${resultat.periode.date_max}`;
      resultat.interpretation.unshift({ type: 'periode', libelle: 'Période', valeur: lib });
    }
    if (resultat.ecran) {
      resultat.interpretation.push({ type: 'ecran', libelle: 'Écran', valeur: resultat.ecran });
    }
    return resultat;
  }

  /** Suggestions pour l'autocomplétion : valeurs commençant par le dernier mot. */
  suggerer(texte, max = 8) {
    const morceaux = cle(texte).split(' ');
    const dernier = morceaux[morceaux.length - 1];
    if (!dernier || dernier.length < 2) return [];
    const vus = new Set();
    const sortie = [];
    for (const e of this.index) {
      if (e.k.split(' ').some(w => w.startsWith(dernier)) && !vus.has(e.dim + e.v)) {
        vus.add(e.dim + e.v);
        sortie.push({ dim: e.dim, libelle: this.libelles[e.dim] || e.dim, valeur: e.v });
        if (sortie.length >= max) break;
      }
    }
    return sortie;
  }

  _valeurDe(dim, texte) {
    const k = cle(texte);
    if (!k) return null;
    const exact = this.index.find(e => e.dim === dim && e.k === k);
    if (exact) return exact.v;
    const partiels = this.index.filter(e => e.dim === dim && e.k.includes(k));
    return partiels.length === 1 ? partiels[0].v : (partiels[0]?.v ?? null);
  }

  _ajouter(resultat, dim, valeur, libelle) {
    const liste = resultat.filtres[dim] || (resultat.filtres[dim] = []);
    if (!liste.includes(valeur)) {
      liste.push(valeur);
      resultat.interpretation.push({ type: 'filtre', dim, libelle: this.libelles[dim] || dim, valeur });
    }
  }

  _contient(k, forme) {
    return (` ${k} `).includes(` ${forme} `);
  }

  _retirer(k, forme) {
    return (` ${k} `).split(` ${forme} `).join(' ').replace(/\s+/g, ' ').trim();
  }
}
