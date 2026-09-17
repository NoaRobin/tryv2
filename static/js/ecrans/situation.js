// situation.js — l'écran d'ouverture : où en sont les appels d'offres.
//
// La lecture du lundi matin. Elle répond d'abord à une question : quels appels
// d'offres sont ouverts, pour quel encours. Le reste descend en dessous.
// Chaque nombre vient du moteur et mène à son détail.

import { h, vider, nombre, faits, carnet, identites, tableDossiers, cellulesNom, jauge,
  lien, entier, euros, pluriel, fmtDate, dateCourte } from '../ui.js';
import { rendreQuandVisible, tableau as tableauHTML } from '../figures.js';
import { NBSP } from '../format.js';

const SEUIL_RELANCE = 120;   // jours : au-delà, une décision qui tarde devient une relance

/**
 * @param {object} ctx — { analyse, meta, etat, tonsEtat, aller(ecran), filtrer(dim, valeur),
 *                         ouvrirDossier(id), listeCompartiment(cle), listeOuverts() }
 */
export function rendreSituation(ctx) {
  const { analyse } = ctx;
  const r = analyse.resume;
  const ecran = h('div.ecran');
  if (!r) {
    ecran.append(h('p.prose', { texte: 'Aucun questionnaire sur ce périmètre.' }));
    return ecran;
  }

  // L'ouverture tient dans la colonne de lecture ; la marge porte la forme des
  // douze derniers mois et le repère historique.
  const ouverture = h('div.lecture.ouverture');
  const gauche = h('div');
  gauche.append(lede(ctx));
  gauche.append(ligneDuMatin(ctx));
  ouverture.append(gauche);
  ouverture.append(margeOuverture(ctx));
  ecran.append(ouverture);

  ecran.append(blocOuverts(ctx));
  ecran.append(blocCarnet(ctx));
  ecran.append(blocIndicateurs(ctx));
  if (analyse.carnet.a_relancer.n) ecran.append(blocRelances(ctx));
  ecran.append(blocFigure(ctx, 'entonnoir', 'Le chemin des appels d’offres', margeEntonnoir(ctx)));
  ecran.append(blocConstats(ctx));
  ecran.append(blocListes(ctx));
  ecran.append(blocFigure(ctx, 'decomposition', 'La décomposition de l’activité', margeDecomposition(ctx)));
  ecran.append(blocFigure(ctx, 'trimestre', 'Les huit derniers trimestres', margeTrimestres(ctx)));
  return ecran;
}

/* ------------------------------------------------------------ ouverture -- */
function lede(ctx) {
  const { analyse, aller } = ctx;
  const r = analyse.resume;
  const c = analyse.carnet;
  const redaction = c.compartiments.en_cours || { n: 0, encours: 0 };
  const attente = c.compartiments.en_attente || { n: 0, encours: 0 };
  const perdus = c.compartiments.perdus || { n: 0, encours: 0 };

  const p = h('p.lede');
  p.append(`Au ${dateCourte(ctx.meta.aujourdhui)}, `);
  if (c.vivants) {
    p.append(nombre(entier(c.vivants), () => ctx.listeOuverts(), 'Voir les appels d’offres ouverts'));
    p.append(` appel${c.vivants > 1 ? 's' : ''} d’offres ${c.vivants > 1 ? 'sont ouverts' : 'est ouvert'} pour `);
    p.append(h('b', { texte: euros(r.encours_en_jeu), style: { fontWeight: 500 } }));
    p.append(' d’encours');
    const detail = [];
    if (redaction.n) detail.push(`${entier(redaction.n)} en rédaction (${euros(redaction.encours)})`);
    if (attente.n) detail.push(`${entier(attente.n)} en attente de décision (${euros(attente.encours)})`);
    if (detail.length) p.append(` : ${detail.join(', ')}`);
    p.append('. ');
  } else {
    p.append('aucun appel d’offres n’est ouvert. ');
  }

  const suite = h('span.attenue');
  suite.append(`Du ${dateCourte(analyse.filtres.date_min)} au ${dateCourte(analyse.filtres.date_max)}, `);
  if (r.tranches) {
    suite.append(nombre(entier(r.gagnes), () => ctx.listeCompartiment('gagnes'), 'Voir les mandats remportés'));
    suite.append(` mandat${r.gagnes > 1 ? 's' : ''} remporté${r.gagnes > 1 ? 's' : ''} (${euros(r.encours_remporte)}) et `);
    suite.append(nombre(entier(perdus.n), () => ctx.listeCompartiment('perdus'), 'Voir les dossiers perdus'));
    suite.append(` perdu${perdus.n > 1 ? 's' : ''} (${euros(r.encours_perdu)}) sur ${entier(r.tranches)} tranchés. `);
  } else {
    suite.append('aucun appel d’offres n’a encore été tranché. ');
  }
  suite.append('Le pôle a aussi traité ');
  suite.append(nombre(entier(r.dd), () => aller('dd'), 'Ouvrir la due diligence'));
  suite.append(` questionnaire${r.dd > 1 ? 's' : ''} de due diligence.`);
  p.append(suite);
  return p;
}

/** Les trois chiffres du matin : ce qui appelle une action, et ce qui est acquis. */
function ligneDuMatin(ctx) {
  const { analyse } = ctx;
  const r = analyse.resume;
  const c = analyse.carnet;
  const attente = c.compartiments.en_attente || { n: 0, encours: 0 };
  const ligne = h('p.matin');
  const fait = (valeur, libelle, action, appui) => h('span', {},
    h('b', {}, nombre(valeur, action)), ' ', libelle,
    appui ? h('span', { texte: ` · ${appui}` }) : null);

  ligne.append(fait(entier(attente.n), `en attente de décision`,
    () => ctx.listeCompartiment('en_attente'), attente.encours ? euros(attente.encours) : ''));
  if (c.a_relancer.n) {
    ligne.append(fait(entier(c.a_relancer.n), 'à relancer', () => ctx.listeCompartiment('a_relancer'),
      c.a_relancer.encours ? euros(c.a_relancer.encours) : ''));
  }
  const succes = analyse.kpis.find(k => k.cle === 'succes');
  if (succes && r.tranches) {
    ligne.append(fait(succes.affichage, 'de succès', () => ctx.aller('rfp'),
      `${entier(r.gagnes)} sur ${entier(r.tranches)} tranchés`));
  }
  return ligne;
}

/** La marge de l'ouverture : la forme des douze derniers mois, le repère historique. */
function margeOuverture(ctx) {
  const { analyse, majEtat } = ctx;
  const r = analyse.resume;
  const marge = h('div.marge-col');
  const serie = r.series && r.series.rfp;
  if (serie && serie.length >= 3) {
    marge.append(h('div.marge-titre', { texte: 'Appels d’offres reçus par mois' }));
    marge.append(barresMensuelles(serie));
    const dernier = serie[serie.length - 1];
    marge.append(h('p.marge-texte', { html:
      `De <b>${serie[0].libelle}</b> à <b>${dernier.libelle}</b>, ${entier(r.rfp)} appels d’offres reçus.`
      + (dernier.en_cours ? ' Le dernier mois est en cours : sa barre est hachurée.' : '') }));
  }
  const rep = r.repere;
  if (rep && rep.annee_min) {
    marge.append(h('div.marge-titre', { style: { marginTop: '22px' }, texte: 'Repère' }));
    const p = h('p.marge-texte');
    p.append(`Depuis ${rep.annee_min}, `);
    p.append(h('b', { texte: entier(rep.rfp) }));
    p.append(' appels d’offres et ');
    p.append(h('b', { texte: entier(rep.dd) }));
    p.append(' due diligences, pour un taux de succès de ');
    p.append(h('b', { texte: (rep.taux_succes * 100).toFixed(1).replace('.', ',') + NBSP + '%' }));
    p.append(' et ');
    p.append(h('b', { texte: euros(rep.encours_remporte) }));
    p.append(' remportés.');
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

function etapeDe(d) {
  if (d.a_oral) return 'Oral';
  if (d.a_preselection) return 'Présélection';
  if (d.a_remis) return 'Remis';
  return '—';
}

/* ---------------------------------------------------- appels d'offres ouverts */
function blocOuverts(ctx) {
  const { analyse } = ctx;
  const o = analyse.carnet.ouverts;
  if (!o || !o.n) {
    return bloc('ouverts', 'Les appels d’offres ouverts', [
      h('p.prose', { texte: 'Aucun appel d’offres n’est ouvert sur ce périmètre.' }),
    ], margeTexte('Lecture', 'Un appel d’offres est ouvert tant qu’il est en rédaction chez nous ou remis au client sans décision.'));
  }
  const maxi = Math.max(...o.dossiers.map(d => (d.statut === 'En cours' ? d.jours_chez_nous : d.jours_attente) || 0), 1);
  const table = tableDossiers(o.dossiers, [
    { titre: 'Client', rendu: (d) => cellulesNom(d, ['segment', 'pays']) },
    { titre: 'Classe d’actifs', attenue: true, rendu: (d) => h('span', {},
      d.classe_actifs && d.classe_actifs !== 'Non renseigné' ? d.classe_actifs : '—',
      d.fonds && d.fonds !== 'Non renseigné' ? h('span.cellule-sous', { texte: d.fonds }) : null) },
    { titre: 'État', rendu: (d) => h('span', {},
      d.statut === 'En cours' ? 'En rédaction' : 'En attente de décision',
      h('span.cellule-sous', { texte: `Étape : ${etapeDe(d)}` })) },
    { titre: 'Depuis', rendu: (d) => {
      const enRedaction = d.statut === 'En cours';
      const v = enRedaction ? d.jours_chez_nous : d.jours_attente;
      if (v === null || v === undefined) return '—';
      return h('span', { style: { display: 'flex', gap: '10px', alignItems: 'center' } },
        jauge(v, maxi, { seuil: enRedaction ? undefined : SEUIL_RELANCE }),
        h('span.num', { texte: `${entier(v)}${NBSP}j` }));
    } },
    { titre: 'Suivi', attenue: true, rendu: (d) => h('span', {},
      d.commercial && d.commercial !== 'Non renseigné' ? d.commercial : '—',
      d.consultant && d.consultant !== 'Non renseigné' ? h('span.cellule-sous', { texte: `via ${d.consultant}` }) : null) },
    { titre: 'Encours', num: true, rendu: (d) => h('b', { texte: euros(d.montant_potentiel), style: { fontWeight: 600 } }) },
  ], { surLigne: (d) => ctx.ouvrirDossier(d.id) });

  const intro = h('p.prose');
  intro.append(`${pluriel(o.n, 'appel d’offres', 'appels d’offres')} ouvert${o.n > 1 ? 's' : ''}, `);
  intro.append(h('b', { texte: euros(o.encours), style: { fontWeight: 500 } }));
  intro.append(' d’encours en jeu. L’encours le plus important d’abord.');

  const total = h('p.note', { style: { marginTop: '12px', display: 'flex', justifyContent: 'space-between' } },
    h('span', {}, lien('Ouvrir la liste complète', () => ctx.listeOuverts())),
    h('span', {}, h('b', { texte: `${entier(o.n)} dossiers · ${euros(o.encours)}` })));

  return bloc('ouverts', 'Les appels d’offres ouverts', [intro, table, total], margeTexte('Lecture',
    '<b>En rédaction</b> : la réponse est chez nous, non partie. <b>En attente de décision</b> : remise au client, non tranchée.',
    '<b>Étape</b> reprend les colonnes Step_1, Step_2 et ORAL_RFP du classeur : dossier remis, présélection, soutenance orale.',
    '<b>Depuis</b> compte les jours depuis la réception pour un dossier en rédaction, depuis la remise pour un dossier en attente. Le trait s’encre au-delà de quatre mois d’attente.'));
}

/* ------------------------------------------------------------ carnet ----- */
function blocCarnet(ctx) {
  const { analyse, meta, tonsEtat } = ctx;
  const c = analyse.carnet;
  const r = analyse.resume;

  const intro = h('p.prose', {});
  intro.append(`Des ${entier(c.total)} appels d’offres du périmètre, `);
  intro.append(nombre(entier(c.vivants), () => ctx.listeOuverts()));
  intro.append(` ne sont pas tranchés (${euros(r.encours_en_jeu)}), `);
  intro.append(nombre(entier(c.compartiments.gagnes.n), () => ctx.listeCompartiment('gagnes')));
  intro.append(` remporté${c.compartiments.gagnes.n > 1 ? 's' : ''} (${euros(r.encours_remporte)}), `);
  intro.append(nombre(entier(c.compartiments.perdus.n), () => ctx.listeCompartiment('perdus')));
  intro.append(` perdu${c.compartiments.perdus.n > 1 ? 's' : ''} (${euros(r.encours_perdu)}).`);

  const corps = [intro, carnet(c, meta.compartiments, tonsEtat, {
    surClic: (cle) => ctx.listeCompartiment(cle),
  })];
  const ids = identites(r.identites);
  if (ids) corps.push(ids);

  return bloc('carnet', 'Le carnet d’appels d’offres', corps, margeTexte('Lecture',
    'Le ruban du haut compte les dossiers, un trait par dossier. Celui du bas porte les mêmes états en encours : c’est lui qui dit où se joue l’argent.',
    '<b>En rédaction</b> et <b>en attente de décision</b> partagent le même résultat, mais appellent deux actions différentes : produire d’un côté, relancer de l’autre.',
    meta.note_censure));
}

/* ------------------------------------------------------- indicateurs ----- */
function blocIndicateurs(ctx) {
  const { analyse, aller } = ctx;
  const ordre = ['succes', 'aum', 'aum_perdu', 'pipeline', 'oral', 'preselection',
    'delai_rfp', 'sla', 'delai_dd', 'esg'];
  const choisis = ordre.map(c => analyse.kpis.find(k => k.cle === c)).filter(Boolean);
  if (!choisis.length) return null;
  return bloc('indicateurs', 'Les indicateurs', [
    faits(choisis, { surClic: (k) => aller(k.cible === 'explorateur' ? 'dossiers' : k.cible) }),
  ], margeTexte('Définitions',
    ...choisis.slice(0, 5).map(k => `<b>${k.libelle}</b> — ${k.aide}`)));
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
    { titre: 'Dossier', rendu: (d) => cellulesNom(d, ['segment', 'pays']) },
    { titre: 'Motif', attenue: true, rendu: (d) => d.en_retard ? 'délai cible dépassé' : 'sans réponse du client' },
    { titre: 'Attente', rendu: (d) => {
      const v = d.en_retard ? d.anciennete_ouvree : d.jours_attente;
      return h('span', { style: { display: 'flex', gap: '10px', alignItems: 'center' } },
        jauge(v, maxi, { seuil: SEUIL_RELANCE }), h('span.num', { texte: `${entier(v)}${NBSP}j` }));
    } },
    { titre: 'Encours', num: true, rendu: (d) => euros(d.montant_potentiel) },
  ], { surLigne: (d) => ctx.ouvrirDossier(d.id) });

  const pied = h('p', { style: { marginTop: '14px' } },
    lien(`Ouvrir ${liste.n > 1 ? `les ${entier(liste.n)} dossiers` : 'le dossier'}`, () => ctx.listeCompartiment('a_relancer')));

  return bloc('relances', 'Ce qu’il faut relancer', [intro, table, pied], margeTexte('Repères',
    `<b>Attente</b> compte les jours depuis la remise de la réponse au client ; <b>délai cible dépassé</b> compte les jours ouvrés depuis la réception, de notre côté.`,
    `Le seuil de relance est de quatre mois d’attente d’une décision. Le délai cible est paramétré par type de demande : ${ctx.meta.sla}.`));
}

/* --------------------------------------------------------- constats ----- */
function blocConstats(ctx) {
  const { analyse, aller } = ctx;
  const liste = h('div');
  // Le constat « à relancer » a son propre bloc : le répéter ici ferait lire
  // deux fois la même phrase.
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

function margeEntonnoir(ctx) {
  const e = (ctx.analyse.resume.entonnoir || []);
  const remis = e.find(x => x.cle === 'remis');
  const gagnes = e.find(x => x.cle === 'gagnes');
  return margeTexte('Lecture',
    'Chaque barre est une étape franchie ; le pourcentage à gauche est la part de l’étape précédente qui passe. L’encours suit les dossiers.',
    remis && gagnes && remis.n
      ? `Sur ${entier(remis.n)} dossiers remis, ${entier(gagnes.n)} ont abouti à un mandat : ${((gagnes.n / remis.n) * 100).toFixed(0).replace('.', ',')}${NBSP}% des remis.`
      : null,
    'Les dossiers encore ouverts comptent dans les étapes qu’ils ont franchies, pas dans les remportés.');
}

function margeDecomposition(ctx) {
  const e = ctx.analyse.resume.echelle;
  return margeTexte('Lecture',
    'La branche « due diligence » n’a pas de suite : une due diligence se traite, elle ne se gagne pas.',
    e ? `Les cinq états d’un appel d’offres sont exclusifs et couvrent son total. Facteur d’échelle <b>${e.affichage}</b> : ${e.phrase}.` : null,
    'La barre sous chaque nombre est sa part du total reçu.');
}

function margeTrimestres() {
  return margeTexte('Lecture',
    'Quatre mouvements, et seulement ceux qu’on sait dater : ce qui arrive, ce qui part, ce que cela rapporte. Une décision client n’a pas de date dans la base : elle ne figure pas ici.',
    'Le trimestre en cours est atténué : il est incomplet, il ne se compare pas.');
}

/* ----------------------------------------------------------- listes ----- */
function blocListes(ctx) {
  const { analyse, meta } = ctx;
  const c = analyse.carnet;
  const onglets = [
    ...meta.compartiments.filter(x => ['gagnes', 'perdus', 'sans_suite'].includes(x.cle))
      .map(x => ({ cle: x.cle, libelle: x.libelle, n: c.compartiments[x.cle].n,
        encours: c.compartiments[x.cle].encours, dossiers: c.compartiments[x.cle].dossiers, sens: x.sens })),
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
    const colonnes = [
      { titre: 'Client', rendu: (d) => cellulesNom(d, ['segment', 'pays']) },
      { titre: 'Classe d’actifs', attenue: true, rendu: (d) => d.classe_actifs || '—' },
      { titre: 'Étape atteinte', attenue: true, rendu: (d) => etapeDe(d) },
      { titre: 'Décision', attenue: true, rendu: (d) => fmtDate(d.date_envoi) },
      { titre: 'Encours', num: true, rendu: (d) => euros(d.montant_potentiel) },
    ];
    zone.append(tableDossiers(o.dossiers, colonnes, { surLigne: (d) => ctx.ouvrirDossier(d.id) }));
    zone.append(h('p', { style: { marginTop: '14px' } },
      lien(`Ouvrir ${o.n > 1 ? `les ${entier(o.n)} dossiers` : 'le dossier'} dans la liste`,
        () => ctx.listeCompartiment(o.cle)),
      h('span', { texte: `  ${o.sens}`, style: { marginLeft: '16px', fontSize: '13px', color: 'var(--b-72)' } })));
  };
  peindre();

  return bloc('listes', 'Les dossiers tranchés', [barre, zone], margeTexte('Repères',
    'Les mandats remportés, les dossiers perdus et ceux restés sans suite, l’encours le plus important d’abord. Chaque ligne ouvre la fiche du dossier.',
    'Les listes montrent les premiers dossiers du compartiment ; « Ouvrir » les affiche tous, avec le filtre déjà posé.'));
}
