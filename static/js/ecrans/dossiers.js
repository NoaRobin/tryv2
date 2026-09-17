// dossiers.js — du chiffre agrégé au dossier individuel.
//
// La liste obéit au périmètre courant ; la recherche plein texte s'ajoute.
// Une ligne ouvre la fiche, sans quitter la liste ni perdre la position.

import { h, vider, lien, tableDossiers, cellulesNom, entier, euros, pluriel, fmtDate,
  chargement, message, annoncer } from '../ui.js';
import * as api from '../api.js';
import { paramsAPI } from '../etat.js';
import { NBSP } from '../format.js';

const COLONNES_DEFAUT = ['date_reception', 'famille', 'client', 'classe_actifs', 'etat',
  'montant_potentiel', 'delai_calendaire'];
const TAILLE = 100;

export function rendreDossiers(ctx) {
  const { etat, meta } = ctx;
  const ecran = h('div.ecran');
  ecran.append(h('h1.titre-ecran', { texte: 'Dossiers' }));
  ecran.append(h('p.sous-ecran', { texte:
    'La liste suit le périmètre choisi. La recherche porte sur le client, le fonds, le consultant, le pays, l’expertise et l’analyste.' }));

  const barre = h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center',
    flexWrap: 'wrap', marginBottom: '18px' } });
  const champ = h('input.champ-texte', {
    type: 'search', value: etat.q || '', placeholder: 'Chercher un dossier…',
    'aria-label': 'Chercher un dossier', style: { flex: '1 1 260px', fontSize: '14px', padding: '7px 10px' },
  });
  barre.append(champ);
  const bascule = h('label', { style: { display: 'flex', gap: '8px', alignItems: 'center',
    fontSize: '13.5px', color: 'var(--b-72)', cursor: 'pointer' } },
    h('input', { type: 'checkbox', checked: etat.attention || null,
      onchange: (e) => ctx.majEtat({ attention: e.target.checked }) }),
    'À relancer seulement');
  barre.append(bascule);
  ecran.append(barre);

  const zone = h('div');
  ecran.append(zone);

  let saisie = null;
  champ.addEventListener('input', () => {
    clearTimeout(saisie);
    saisie = setTimeout(() => ctx.majEtat({ q: champ.value.trim() }, { remplacer: true }), 260);
  });

  charger(zone, ctx, 1);
  return ecran;
}

async function charger(zone, ctx, page) {
  vider(zone).append(chargement('Recherche…'));
  const p = paramsAPI(ctx.etat);
  if (ctx.etat.q) p.set('q', ctx.etat.q);
  if (ctx.etat.attention) p.set('attention', '1');
  p.set('page', String(page));
  p.set('taille', String(TAILLE));
  let d;
  try {
    d = await api.get('/api/dossiers', p);
  } catch (e) {
    vider(zone).append(message(`La liste n’a pas pu être chargée : ${e.message}`));
    return;
  }
  vider(zone);
  if (!d.n) {
    zone.append(message('Aucun dossier ne correspond à cette recherche.', { sobre: true,
      actions: [lien('Retirer les filtres', () => ctx.retirerTout())] }));
    return;
  }
  annoncer(`${entier(d.n)} dossiers`);

  // L’encours n’est cité que si la liste ne contient que des appels d’offres :
  // additionner les montants d’une liste mêlée ne veut rien dire.
  const queDesRfp = d.lignes.length > 0 && d.lignes.every(l => l.famille === 'RFP');
  const entete = h('p.note', { style: { marginBottom: '10px' } },
    h('b', { texte: pluriel(d.n, 'dossier') }),
    queDesRfp && d.encours ? ` · ${euros(d.encours)} d’encours` : '',
    ' · cliquez une ligne pour ouvrir sa fiche');
  zone.append(entete);

  const colonnes = COLONNES_DEFAUT.filter(c => c === 'etat' || d.colonnes.includes(c)).map(c => ({
    cle: c, titre: c === 'etat' ? 'État' : (d.libelles[c] || c),
    num: ['delai_calendaire', 'montant_potentiel', 'nb_questions'].includes(c),
    attenue: ['famille', 'expertise', 'classe_actifs'].includes(c),
    rendu: rendu(c, d.libelles),
  }));
  zone.append(tableDossiers(d.lignes, colonnes, { surLigne: (l) => ctx.ouvrirDossier(l.id) }));

  const pages = Math.ceil(d.n / TAILLE);
  if (pages > 1) {
    const nav = h('p', { style: { marginTop: '16px', display: 'flex', gap: '16px',
      alignItems: 'baseline' } });
    if (page > 1) nav.append(lien('← Précédents', () => charger(zone, ctx, page - 1)));
    nav.append(h('span.note', { texte: `Page ${page} sur ${pages}` }));
    if (page < pages) nav.append(lien('Suivants →', () => charger(zone, ctx, page + 1)));
    zone.append(nav);
  }
}

function etatDe(d) {
  if (d.famille !== 'RFP') return d.statut === 'En cours' ? 'En cours' : (d.statut || '—');
  if (d.statut === 'En cours') return 'En rédaction';
  if (d.resultat === 'En attente') return 'En attente de décision';
  return d.resultat || d.statut || '—';
}

function rendu(cle, libelles) {
  if (cle === 'client') return (d) => cellulesNom(d, ['segment', 'pays']);
  if (cle === 'etat') return (d) => etatDe(d);
  if (cle === 'date_reception' || cle === 'date_envoi') return (d) => fmtDate(d[cle]);
  if (cle === 'delai_calendaire') return (d) => (d[cle] === null || d[cle] === undefined ? '—' : `${entier(d[cle])}${NBSP}j`);
  if (cle === 'montant_potentiel') return (d) => euros(d[cle]);
  return (d) => (d[cle] === null || d[cle] === undefined || d[cle] === 'Non renseigné' ? '—' : d[cle]);
}

/* -------------------------------------------------------------- fiche --- */
export async function ouvrirFiche(identifiant, ctx) {
  const fond = h('div.fiche-fond', { onclick: (e) => { if (e.target === fond) fermer(); } });
  const panneau = h('div.fiche', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Fiche du dossier' });
  fond.append(panneau);
  document.body.append(fond);
  document.body.style.overflow = 'hidden';

  const fermer = () => {
    fond.remove();
    document.body.style.overflow = '';
    document.removeEventListener('keydown', surTouche);
    ctx.majEtat({ dossier: null }, { remplacer: true, sansRecharger: true });
  };
  const surTouche = (e) => { if (e.key === 'Escape') { e.preventDefault(); fermer(); } };
  document.addEventListener('keydown', surTouche);

  panneau.append(chargement('Ouverture du dossier…'));
  let d;
  try {
    d = await api.get(`/api/dossiers/${identifiant}`);
  } catch (e) {
    vider(panneau).append(h('div.fiche__corps', {}, message(`Dossier introuvable : ${e.message}`)));
    return fermer;
  }
  vider(panneau);

  const tete = h('div.fiche__tete');
  tete.append(h('div', {},
    h('div.cle', { texte: [d.famille, d.type_demande !== d.famille ? d.type_demande : null]
      .filter(Boolean).join(' · ') }),
    h('h2.fiche__nom', { texte: d.client || 'Client non renseigné' })));
  tete.append(h('button.fiche__x', { type: 'button', 'aria-label': 'Fermer', onclick: fermer, texte: '×' }));
  panneau.append(tete);

  const corps = h('div.fiche__corps');
  const etat = d.resultat && d.resultat !== 'Sans objet' ? d.resultat : d.statut;
  const phrase = h('p.prose', { style: { fontSize: '18px', marginBottom: '20px' } });
  phrase.append(`${etat}. Reçu le ${fmtDate(d.date_reception)}`);
  phrase.append(d.date_envoi ? `, réponse envoyée le ${fmtDate(d.date_envoi)}` : ', réponse non partie');
  if (d.delai_calendaire !== null && d.delai_calendaire !== undefined) {
    phrase.append(`, soit ${entier(d.delai_calendaire)} jours`);
  }
  phrase.append('.');
  if (d.montant_potentiel) phrase.append(` Encours en jeu : ${euros(d.montant_potentiel)}.`);
  corps.append(phrase);

  const ouiNon = (v) => (v === true ? 'Oui' : (v === false ? 'Non' : null));
  const champs = [
    ['Numéro', d.numero], ['Segment', d.segment], ['Type de client', d.type_client], ['Pays', d.pays],
    ['Consultant', d.consultant], ['Commercial', d.commercial],
    ['Classe d’actifs', d.classe_actifs], ['Sous-classe', d.sous_classe_actifs],
    ['Expertise', d.expertise], ['Fonds de référence', d.fonds],
    ['Forme juridique', d.forme_juridique], ['Rédacteur', d.analyste], ['Relecteur', d.relecteur],
    ['Langue', d.langue],
    ['Dossier remis', d.famille === 'RFP' ? ouiNon(d.a_remis) : null],
    ['Présélection', d.famille === 'RFP' ? ouiNon(d.a_preselection) : null],
    ['Soutenance orale', d.famille === 'RFP' ? ouiNon(d.a_oral) : null],
    ['ISR', d.sri], ['Tranche ESG', d.bande_esg], ['Mise à jour Qvidian', d.qvidian],
    ['Questions', d.nb_questions === null || d.nb_questions === undefined ? null : entier(d.nb_questions)],
    ['Délai cible', d.sla_cible ? `${entier(d.sla_cible)} jours ouvrés` : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== 'Non renseigné' && v !== 'Sans objet');
  const grille = h('div.champs');
  for (const [c, v] of champs) {
    grille.append(h('div.champ', {}, h('div.champ__c', { texte: c }), h('div.champ__v', { texte: String(v) })));
  }
  corps.append(grille);

  if (d.autres_dossiers_client && d.autres_dossiers_client.length) {
    corps.append(h('div.cle', { style: { marginTop: '32px', marginBottom: '10px' },
      texte: `Les autres dossiers de ce client — ${entier(d.n_dossiers_client - 1)}` }));
    corps.append(tableDossiers(d.autres_dossiers_client, [
      { titre: 'Reçu', rendu: (l) => fmtDate(l.date_reception) },
      { titre: 'Type', attenue: true, cle: 'type_demande' },
      { titre: 'Classe d’actifs', attenue: true, rendu: (l) => l.classe_actifs || '—' },
      { titre: 'Résultat', num: true,
        rendu: (l) => (l.resultat === 'Sans objet'
          ? (l.montant_potentiel ? euros(l.montant_potentiel) : '—')
          : `${l.resultat}${l.montant_potentiel ? ' · ' + euros(l.montant_potentiel) : ''}`) },
    ], { surLigne: (l) => { fermer(); ctx.ouvrirDossier(l.id); } }));
    corps.append(h('p', { style: { marginTop: '14px' } },
      lien(`Voir tous les dossiers de ${d.client}`, () => { fermer(); ctx.chercherClient(d.client); })));
  }
  panneau.append(corps);
  panneau.querySelector('.fiche__x').focus();
  return fermer;
}
