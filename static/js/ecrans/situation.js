// situation.js — l'écran d'ouverture : où en sont les appels d'offres.
//
// Une note qui se réécrit à chaque changement de périmètre. Le texte EST le
// résultat du calcul : chaque nombre vient du moteur, et mène à son détail.

import { h, vider, nombre, faits, carnet, identites, tableDossiers, cellulesNom, jauge,
  lien, entier, euros, pluriel, fmtDate, dateCourte } from '../ui.js';
import { rendreQuandVisible, tableau as tableauHTML } from '../figures.js';
import { NBSP } from '../format.js';

const SEUIL_RELANCE = 120;   // jours : au-delà, une décision qui tarde devient une relance

/**
 * @param {object} ctx — { analyse, meta, etat, tonsEtat, aller(ecran, modif), filtrer(dim, valeur),
 *                         ouvrirDossier(id), listeCompartiment(cle) }
 */
export function rendreSituation(ctx) {
  const { analyse, meta } = ctx;
  const r = analyse.resume;
  const ecran = h('div.ecran');
  if (!r) {
    ecran.append(h('p.prose', { texte: 'Aucun questionnaire sur ce périmètre.' }));
    return ecran;
  }

  // La phrase d’ouverture tient dans la colonne de lecture ; la marge porte la
  // forme des douze derniers mois et le repère historique.
  const ouverture = h('div.lecture.ouverture');
  const gauche = h('div');
  gauche.append(lede(ctx));
  gauche.append(ligneDuMatin(ctx));
  ouverture.append(gauche);
  ouverture.append(margeOuverture(ctx));
  ecran.append(ouverture);
  ecran.append(blocCarnet(ctx));
  ecran.append(blocIndicateurs(ctx));
  if (analyse.carnet.a_relancer.n) ecran.append(blocRelances(ctx));
  ecran.append(blocConstats(ctx));
  ecran.append(blocFigure(ctx, 'decomposition', 'La décomposition de l’activité', margeDecomposition(ctx)));
  ecran.append(blocFigure(ctx, 'trimestre', 'Les huit derniers trimestres', margeTrimestres(ctx)));
  ecran.append(blocListes(ctx));
  return ecran;
}

/** La marge de l’ouverture : la forme des douze derniers mois, puis le repère
 *  historique — les mêmes grandeurs sur tout l’historique. */
function margeOuverture(ctx) {
  const { analyse, meta, majEtat } = ctx;
  const r = analyse.resume;
  const marge = h('div.marge-col');
  const serie = r.series && r.series.questionnaires;
  if (serie && serie.length >= 3) {
    marge.append(h('div.marge-titre', { texte: 'Questionnaires reçus par mois' }));
    marge.append(barresMensuelles(serie));
    const dernier = serie[serie.length - 1];
    marge.append(h('p.marge-texte', { html:
      `De <b>${serie[0].libelle}</b> à <b>${dernier.libelle}</b>.`
      + (dernier.en_cours ? ' Le dernier mois est en cours : sa barre est hachurée, il ne se compare pas.' : '') }));
  }
  const rep = r.repere;
  if (rep && rep.annee_min) {
    marge.append(h('div.marge-titre', { style: { marginTop: '22px' }, texte: 'Repère' }));
    const p = h('p.marge-texte');
    p.append(`Depuis ${rep.annee_min}, l’historique compte `);
    p.append(h('b', { texte: entier(rep.questionnaires) }));
    p.append(' questionnaires et ');
    p.append(h('b', { texte: entier(rep.rfp) }));
    p.append(' appels d’offres, pour un taux de succès de ');
    p.append(h('b', { texte: (rep.taux_succes * 100).toFixed(1).replace('.', ',') + ' %' }));
    p.append('.');
    marge.append(p);
    if (ctx.etat.periode !== 'tout') {
      marge.append(h('p.marge-texte', {},
        lien('Élargir le périmètre à tout l’historique', () => majEtat({ periode: 'tout' }))));
    }
  }
  return marge;
}

/** Douze barres, une par mois. Le mois en cours est hachuré. */
function barresMensuelles(serie) {
  const maxi = Math.max(...serie.map(s => s.valeur), 1);
  const bloc = h('div');
  const barres = h('div.barres', { role: 'img',
    'aria-label': serie.map(s => `${s.libelle} : ${s.valeur}`).join(', ') });
  for (const s of serie) {
    barres.append(h('i', {
      classe: s.en_cours ? 'encours' : '',
      style: { height: `${Math.max(2, (s.valeur / maxi) * 100)}%` },
      title: `${s.libelle} : ${entier(s.valeur)}`,
    }));
  }
  bloc.append(barres);
  bloc.append(h('div.barres-pied', {},
    h('span', { texte: serie[0].libelle }),
    h('span', { texte: serie[serie.length - 1].libelle })));
  return bloc;
}

/* --------------------------------------------------------------- lede ---- */
function lede(ctx) {
  const { analyse, meta, aller } = ctx;
  const r = analyse.resume;
  const kpi = (cle) => analyse.kpis.find(k => k.cle === cle);
  const volume = kpi('questionnaires');

  const p = h('p.lede');
  p.append(`Du ${dateCourte(analyse.filtres.date_min)} au ${dateCourte(analyse.filtres.date_max)}, le pôle a reçu `);
  p.append(nombre(entier(r.questionnaires), () => aller('activite'), 'Ouvrir l’activité'));
  p.append(` questionnaire${r.questionnaires > 1 ? 's' : ''}`);
  if (volume && volume.delta_affichage && volume.delta_affichage !== 'stable') {
    const sens = volume.delta_direction === 'hausse' ? 'de plus' : 'de moins';
    p.append(`, ${volume.delta_affichage.replace('+', '').replace('−', '')} ${sens} que sur la période précédente`);
  }
  p.append('. ');
  const suite = h('span.attenue');
  suite.append(nombre(entier(r.dd), () => aller('dd'), 'Ouvrir la due diligence'));
  suite.append(` relèvent de la due diligence, `);
  suite.append(nombre(entier(r.rfp), () => aller('rfp'), 'Ouvrir les appels d’offres'));
  suite.append(` sont des appels d’offres`);
  if (r.tranches) {
    suite.append(`, dont `);
    suite.append(nombre(entier(r.gagnes), () => ctx.listeCompartiment('gagnes'), 'Voir les mandats remportés'));
    suite.append(` remportés sur ${entier(r.tranches)} tranchés.`);
  } else {
    suite.append(', aucun encore tranché.');
  }
  p.append(suite);
  return p;
}

/** Les trois chiffres du matin, sous la phrase : ce qui appelle une action. */
function ligneDuMatin(ctx) {
  const { analyse, aller } = ctx;
  const r = analyse.resume;
  const c = analyse.carnet;
  const kpiQuestions = analyse.kpis.find(k => k.cle === 'questions');
  const ligne = h('p.matin');

  const fait = (valeur, libelle, action, appui) => {
    const el = h('span', {},
      h('b', {}, nombre(valeur, action)), ' ', libelle,
      appui ? h('span', { texte: ` · ${appui}` }) : null);
    return el;
  };
  ligne.append(fait(entier(c.total ? c.vivants : 0), 'dossiers non tranchés',
    () => ctx.listeCompartiment('en_attente'), `${euros(r.encours_en_jeu)} en jeu`));
  if (c.a_relancer.n) {
    ligne.append(fait(entier(c.a_relancer.n), pluriel(c.a_relancer.n, 'dossier').split(NBSP)[1] + ' à relancer',
      () => ctx.listeCompartiment('a_relancer'),
      c.a_relancer.encours ? `${euros(c.a_relancer.encours)} concernés` : ''));
  }
  if (kpiQuestions) {
    ligne.append(fait(kpiQuestions.affichage, 'questions traitées', () => aller('activite'),
      kpiQuestions.detail));
  }
  return ligne;
}

/* ------------------------------------------------------------- blocs ----- */
let numero = 0;

function bloc(cle, titre, corps, marge) {
  const b = h('section.bloc', { id: `bloc-${cle}` });
  const g = h('div.bloc__corps');
  g.append(h('div.bloc__tete', {},
    h('span.bloc__num', { texte: String(++numero).padStart(2, '0') }),
    h('span.cle.cle--ink', { texte: titre })));
  for (const x of [corps].flat()) if (x) g.append(x);
  b.append(g);
  b.append(h('div.bloc__marge', {}, ...[marge].flat().filter(Boolean)));
  return b;
}

export function reinitialiserNumerotation() { numero = 0; }

function margeTexte(titre, ...paragraphes) {
  return [titre ? h('div.marge-titre', { texte: titre }) : null,
    ...paragraphes.filter(Boolean).map(p => (p instanceof Node ? p : h('p.marge-texte', { html: p })))];
}

/* ------------------------------------------------------------ carnet ----- */
function blocCarnet(ctx) {
  const { analyse, meta, tonsEtat } = ctx;
  const c = analyse.carnet;
  const r = analyse.resume;

  const intro = h('p.prose', {});
  intro.append(`Des ${entier(c.total)} appels d’offres du périmètre, `);
  intro.append(nombre(entier(c.vivants), () => ctx.listeCompartiment('en_attente')));
  intro.append(` ne sont pas tranchés, pour ${euros(r.encours_en_jeu)} d’encours en jeu. `);
  const g = c.compartiments.gagnes.n;
  if (g) {
    intro.append(nombre(entier(g), () => ctx.listeCompartiment('gagnes')));
    intro.append(` mandat${g > 1 ? 's' : ''} remporté${g > 1 ? 's' : ''}, ${euros(r.encours_remporte)} d’encours.`);
  }

  const corps = [intro, carnet(c, meta.compartiments, tonsEtat, {
    surClic: (cle) => ctx.listeCompartiment(cle),
  })];
  const ids = identites(r.identites);
  if (ids) corps.push(ids);

  return bloc('carnet', 'Le carnet d’appels d’offres', corps, margeTexte('Lecture',
    'Le ruban du haut compte les dossiers, un trait par dossier. Celui du bas porte les mêmes états en encours : il montre qu’un dossier sans suite peut peser plus que plusieurs dossiers perdus.',
    '<b>En rédaction</b> et <b>en attente de décision</b> partagent le même résultat, mais appellent deux actions différentes : produire d’un côté, relancer de l’autre.',
    meta.note_censure));
}

/* ------------------------------------------------------- indicateurs ----- */
function blocIndicateurs(ctx) {
  const { analyse, aller } = ctx;
  const ordre = ['succes', 'aum', 'pipeline', 'rfp_gagnes', 'delai_rfp', 'delai_dd', 'sla', 'esg'];
  const choisis = ordre.map(c => analyse.kpis.find(k => k.cle === c)).filter(Boolean);
  if (!choisis.length) return null;
  return bloc('indicateurs', 'Les indicateurs', [
    faits(choisis, { surClic: (k) => aller(k.cible === 'explorateur' ? 'dossiers' : k.cible) }),
  ], margeTexte('Définitions',
    ...choisis.slice(0, 4).map(k => `<b>${k.libelle}</b> — ${k.aide}`)));
}

/* --------------------------------------------------------- relances ----- */
function blocRelances(ctx) {
  const { analyse } = ctx;
  const liste = analyse.carnet.a_relancer;
  const maxi = Math.max(...liste.dossiers.map(d => Math.max(d.jours_attente || 0, d.anciennete_ouvree || 0)), 1);

  const intro = h('p.prose', { texte:
    `${pluriel(liste.n, 'dossier')} ${liste.n > 1 ? 'demandent' : 'demande'} une relance : délai cible dépassé, `
    + `ou décision attendue depuis plus de quatre mois.`
    + (liste.encours ? ` ${euros(liste.encours)} d’encours concernés.` : '') });

  const table = tableDossiers(liste.dossiers, [
    { titre: 'Dossier', rendu: (d) => cellulesNom(d) },
    { titre: 'Motif', attenue: true, rendu: (d) => d.en_retard ? 'délai cible dépassé' : 'sans réponse du client' },
    { titre: 'Attente', rendu: (d) => {
      const v = d.en_retard ? d.anciennete_ouvree : d.jours_attente;
      return h('span', { style: { display: 'flex', gap: '10px', alignItems: 'center' } },
        jauge(v, maxi, { seuil: SEUIL_RELANCE }), h('span.num', { texte: `${entier(v)}${NBSP}j` }));
    } },
    { titre: 'Encours', num: true, rendu: (d) => euros(d.montant_potentiel) },
  ], { surLigne: (d) => ctx.ouvrirDossier(d.id) });

  const pied = h('p', { style: { marginTop: '14px' } },
    lien(`Ouvrir les ${entier(liste.n)} dossiers`, () => ctx.listeCompartiment('a_relancer')));

  return bloc('relances', 'Ce qu’il faut relancer', [intro, table, pied], margeTexte('Repères',
    `<b>Attente</b> compte les jours depuis la remise de la réponse au client ; <b>délai cible dépassé</b> compte les jours ouvrés depuis la réception, de notre côté.`,
    `Le seuil de relance est de quatre mois d’attente d’une décision. Le délai cible est paramétré par type de demande : ${ctx.meta.sla}.`));
}

/* --------------------------------------------------------- constats ----- */
function blocConstats(ctx) {
  const { analyse, aller } = ctx;
  const liste = h('div');
  // Le constat « à relancer » a son propre bloc, avec ses dossiers : le
  // répéter ici ferait lire deux fois la même phrase.
  const constats = analyse.carnet.a_relancer.n
    ? analyse.insights.filter(i => i.cle !== 'attention')
    : analyse.insights;
  if (!constats.length) return null;
  for (const i of constats) {
    const ligne = h('div', { style: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto',
      gap: '24px', alignItems: 'baseline', padding: '14px 0', borderBottom: '1px solid var(--b-12)' } });
    ligne.append(h('p.prose', { texte: i.texte, style: { fontSize: '18px' } }));
    const droite = h('div', { style: { textAlign: 'right' } });
    if (i.appui) droite.append(h('div.note', { texte: i.appui }));
    if (i.cible) {
      const dest = i.cible === 'explorateur' ? 'dossiers' : i.cible;
      const nom = (ctx.meta.sections || {})[dest] || (dest === 'dossiers' ? 'Dossiers' : dest);
      droite.append(h('div', { style: { marginTop: '4px' } }, lien(`${nom} →`, () => aller(dest))));
    }
    ligne.append(droite);
    liste.append(ligne);
  }
  return bloc('constats', 'Ce qui a changé', [liste], margeTexte('Méthode',
    'Chaque constat est produit par une fonction d’analyse sur le périmètre courant. Aucune phrase n’est écrite d’avance : si la donnée ne permet pas de l’établir, le constat n’apparaît pas.',
    'Les variations sont mesurées face à la période précédente de même durée.'));
}

/* ---------------------------------------------------------- figures ----- */
function blocFigure(ctx, cleBloc, titre, marge) {
  const b = ctx.analyse.blocs.find(x => x.cle === cleBloc);
  if (!b) return null;
  const corps = [];
  if (b.accroche) corps.push(h('p.prose', { texte: b.accroche, style: { marginBottom: '16px' } }));
  const hote = h('div.figure');
  corps.push(hote);
  if (b.note) corps.push(h('p.analyse__note', { texte: b.note }));
  const el = bloc(cleBloc, titre, corps, marge);
  if (b.figure) {
    requestAnimationFrame(() => rendreQuandVisible(hote, b.figure, {
      dimension: b.dimension,
      surClic: b.dimension ? (dim, valeur) => ctx.filtrer(dim, valeur) : null,
    }));
  } else if (b.tableau) {
    hote.innerHTML = tableauHTML(b.tableau);
  }
  return el;
}

function margeDecomposition(ctx) {
  const e = ctx.analyse.resume.echelle;
  return margeTexte('Lecture',
    'La branche « due diligence » n’a pas de suite : une due diligence se traite, elle ne se gagne pas.',
    e ? `Les cinq états d’un appel d’offres sont exclusifs et couvrent son total. Facteur d’échelle <b>${e.affichage}</b> : ${e.phrase}.` : null,
    'La barre sous chaque nombre est sa part du total reçu.');
}

function margeTrimestres(ctx) {
  return margeTexte('Lecture',
    'Quatre mouvements, et seulement ceux qu’on sait dater : ce qui arrive, ce qui part, ce que cela rapporte. Une décision client n’a pas de date dans la base : elle ne figure pas ici.',
    'Le trimestre en cours est atténué : il est incomplet, il ne se compare pas.');
}

/* ----------------------------------------------------------- listes ----- */
function blocListes(ctx) {
  const { analyse, meta, tonsEtat } = ctx;
  const c = analyse.carnet;
  const onglets = [
    ...meta.compartiments.filter(x => ['en_attente', 'gagnes', 'perdus'].includes(x.cle))
      .map(x => ({ cle: x.cle, libelle: x.libelle, n: c.compartiments[x.cle].n,
        encours: c.compartiments[x.cle].encours, dossiers: c.compartiments[x.cle].dossiers, sens: x.sens })),
    { cle: 'a_relancer', libelle: 'À relancer', n: c.a_relancer.n, encours: c.a_relancer.encours,
      dossiers: c.a_relancer.dossiers, sens: 'délai dépassé ou décision qui tarde' },
  ].filter(o => o.n > 0);
  if (!onglets.length) return null;

  const barre = h('div.onglets', { role: 'tablist' });
  const zone = h('div');
  let actif = onglets[0].cle;

  const peindre = () => {
    vider(barre); vider(zone);
    for (const o of onglets) {
      barre.append(h('button', {
        role: 'tab', 'aria-selected': String(o.cle === actif), type: 'button',
        onclick: () => { actif = o.cle; peindre(); },
      }, o.libelle, h('span.compte', { texte: `${entier(o.n)} · ${euros(o.encours)}` })));
    }
    const o = onglets.find(x => x.cle === actif);
    const attente = o.cle === 'en_attente' || o.cle === 'a_relancer';
    const maxi = Math.max(...o.dossiers.map(d => d.jours_attente || d.anciennete_ouvree || 0), 1);
    const colonnes = [
      { titre: 'Client', rendu: (d) => cellulesNom(d, ['pays', 'classe_actifs']) },
      attente
        ? { titre: 'Attente', rendu: (d) => {
          const v = d.jours_attente ?? d.anciennete_ouvree;
          return v === null || v === undefined ? '—' : h('span', { style: { display: 'flex', gap: '10px', alignItems: 'center' } },
            jauge(v, maxi, { seuil: SEUIL_RELANCE }), h('span.num', { texte: `${entier(v)}${NBSP}j` }));
        } }
        : { titre: 'Décision', attenue: true, rendu: (d) => fmtDate(d.date_envoi) },
      { titre: 'Encours', num: true, rendu: (d) => euros(d.montant_potentiel) },
    ];
    zone.append(tableDossiers(o.dossiers, colonnes, { surLigne: (d) => ctx.ouvrirDossier(d.id) }));
    zone.append(h('p', { style: { marginTop: '14px' } },
      lien(`Ouvrir ${o.n > 1 ? `les ${entier(o.n)} dossiers` : 'le dossier'} dans la liste`,
        () => ctx.listeCompartiment(o.cle)),
      h('span', { texte: `  ${o.sens}`, style: { marginLeft: '16px', fontSize: '13px', color: 'var(--b-72)' } })));
  };
  peindre();

  return bloc('listes', 'Les dossiers nommés', [barre, zone], margeTexte('Repères',
    'Chaque ligne ouvre la fiche du dossier : ses dates, son analyste, son encours, et les autres dossiers du même client.',
    'Les listes montrent les premiers dossiers du compartiment ; « Ouvrir » les affiche tous, avec le filtre déjà posé.'));
}
