// donnees.js — brancher le produit sur le classeur du pôle.
//
// Déposer un fichier, vérifier ce que l'application a reconnu, corriger ce
// qu'elle n'a pas reconnu, activer. Rien n'est activé sans avoir été lu.

import { h, vider, lien, entier, message, chargement, annoncer } from '../ui.js';
import * as api from '../api.js';

export function rendreDonnees(ctx) {
  const ecran = h('div.ecran');
  ecran.append(h('h1.titre-ecran', { texte: 'Données' }));
  ecran.append(h('p.sous-ecran', { texte:
    'Le produit lit un classeur Excel ou un fichier CSV. Seules trois colonnes sont indispensables : '
    + 'la date de réception, le type de demande et le statut. Les autres sont facultatives : '
    + 'les analyses qui en dépendent disparaissent, le reste tient.' }));
  const zone = h('div');
  ecran.append(zone);
  peindre(zone, ctx);
  return ecran;
}

async function peindre(zone, ctx) {
  vider(zone).append(chargement('Lecture de l’état…'));
  let etat;
  try {
    etat = await api.get('/api/donnees');
  } catch (e) {
    vider(zone).append(message(`État illisible : ${e.message}`));
    return;
  }
  vider(zone);
  const grille = h('div.lecture');
  const colonne = h('div');
  colonne.append(blocSource(etat, ctx, zone));
  colonne.append(blocDepot(etat, ctx, zone));
  if (etat.fichiers.length) colonne.append(blocFichiers(etat, ctx, zone));
  colonne.append(blocQualite(etat));
  colonne.append(blocTarif(ctx));
  grille.append(colonne);

  const marge = h('div.marge-col');
  marge.append(h('div.marge-titre', { texte: 'Ce qui est attendu' }));
  marge.append(h('p.marge-texte', { html:
    'La correspondance des colonnes est tolérante : la casse, les accents, les espaces, '
    + 'les tirets et les unités entre parenthèses sont ignorés. « Date de réception », '
    + '« DATE_RECEPTION » et « date réception » désignent la même colonne.' }));
  marge.append(h('p.marge-texte', { html:
    'Les colonnes indispensables sont marquées en gras dans le tableau de correspondance. '
    + 'Sans elles, le fichier n’est pas exploitable.' }));
  marge.append(h('p.marge-texte', { html:
    'Les fichiers déposés restent dans le dossier <b>data/</b> de l’installation. '
    + 'Ils ne rejoignent jamais le dépôt de code.' }));
  grille.append(marge);
  zone.append(grille);
}

/* -------------------------------------------------------------- source --- */
function blocSource(etat, ctx, zone) {
  const s = etat.source;
  const b = h('section', { style: { marginBottom: '36px' } });
  b.append(h('div.cle.cle--ink', { texte: 'La source branchée', style: { marginBottom: '12px' } }));
  const p = h('p.prose');
  if (s.mode === 'demo') {
    p.append('L’application tourne sur ses ');
    p.append(h('b', { texte: 'données de démonstration' }));
    p.append(` : ${entier(s.n_lignes_retenues)} questionnaires synthétiques qui reproduisent la forme `
      + 'd’une activité réelle. Aucun client nommé n’existe.');
  } else {
    p.append('L’application lit ');
    p.append(h('b', { texte: s.fichier }));
    if (s.onglet) p.append(`, onglet « ${s.onglet} »`);
    p.append(`. ${entier(s.n_lignes_source)} lignes lues, `);
    p.append(h('b', { texte: `${entier(s.n_lignes_retenues)} questionnaires retenus` }));
    p.append(' après normalisation.');
  }
  b.append(p);

  const actions = h('p', { style: { marginTop: '14px', display: 'flex', gap: '18px', flexWrap: 'wrap' } });
  if (s.mode === 'fichier') {
    actions.append(lien('Revenir aux données de démonstration', async () => {
      await api.post('/api/donnees/demo'); ctx.rechargerTout(); peindre(zone, ctx);
    }));
  } else if (etat.branchement && etat.branchement.fichier) {
    actions.append(lien(`Reprendre le classeur « ${etat.branchement.fichier} »`, async () => {
      await api.post('/api/donnees/reprendre'); ctx.rechargerTout(); peindre(zone, ctx);
    }));
  }
  b.append(actions);
  return b;
}

/* --------------------------------------------------------------- dépôt --- */
function blocDepot(etat, ctx, zone) {
  const b = h('section', { style: { marginBottom: '36px' } });
  b.append(h('div.cle.cle--ink', { texte: 'Déposer un classeur', style: { marginBottom: '12px' } }));

  const entree = h('input', { type: 'file', accept: '.xlsx,.xlsm,.xls,.csv,.tsv,.txt',
    style: { display: 'none' } });
  const depot = h('div.depot', { role: 'button', tabindex: '0',
    onclick: () => entree.click(),
    onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); entree.click(); } },
    ondragover: (e) => { e.preventDefault(); depot.classList.add('depot--survol'); },
    ondragleave: () => depot.classList.remove('depot--survol'),
    ondrop: (e) => {
      e.preventDefault(); depot.classList.remove('depot--survol');
      if (e.dataTransfer.files[0]) envoyer(e.dataTransfer.files[0]);
    },
  });
  depot.append(h('div.depot__t', { texte: 'Glisser un fichier ici, ou cliquer pour le choisir' }));
  depot.append(h('p.note', { style: { marginTop: '6px' },
    texte: 'Excel (.xlsx, .xlsm, .xls) ou texte (.csv, .tsv). 200 Mo au plus.' }));
  depot.append(entree);
  b.append(depot);
  const retour = h('div', { style: { marginTop: '16px' } });
  b.append(retour);

  entree.addEventListener('change', () => { if (entree.files[0]) envoyer(entree.files[0]); });

  async function envoyer(fichier) {
    vider(retour).append(chargement(`Lecture de ${fichier.name}…`));
    try {
      const r = await api.deposer('/api/donnees/fichier', fichier);
      vider(retour).append(correspondance(r.fichier, r.apercu, etat, ctx, zone));
      annoncer(`${fichier.name} déposé, ${r.apercu.n_lignes} lignes lues.`);
    } catch (e) {
      vider(retour).append(message(`Le fichier n’a pas pu être lu : ${e.message}`));
    }
  }
  return b;
}

function blocFichiers(etat, ctx, zone) {
  const b = h('section', { style: { marginBottom: '36px' } });
  b.append(h('div.cle.cle--ink', { texte: 'Les fichiers présents', style: { marginBottom: '10px' } }));
  const liste = h('div');
  for (const f of etat.fichiers) {
    const ligne = h('div', { style: { display: 'flex', gap: '16px', alignItems: 'baseline',
      padding: '9px 0', borderBottom: '1px solid var(--b-12)' } });
    ligne.append(h('span', { texte: f.nom, style: { flex: 1, fontSize: '14px' } }));
    ligne.append(h('span.note', { texte: `${(f.taille / 1024).toFixed(0)} ko · ${f.modifie.replace('T', ' à ')}` }));
    ligne.append(lien('Examiner', async () => {
      const zoneRetour = h('div', { style: { marginTop: '16px' } });
      ligne.after(zoneRetour);
      vider(zoneRetour).append(chargement('Lecture…'));
      try {
        const vue = await api.get('/api/donnees/apercu', { fichier: f.nom });
        vider(zoneRetour).append(correspondance(f.nom, vue, etat, ctx, zone));
      } catch (e) {
        vider(zoneRetour).append(message(`Lecture impossible : ${e.message}`));
      }
    }));
    liste.append(ligne);
  }
  b.append(liste);
  return b;
}

/* ------------------------------------------------------ correspondance --- */
function correspondance(fichier, vue, etat, ctx, zone) {
  const b = h('section', { style: { borderTop: '1px solid var(--b-22)', paddingTop: '20px' } });
  const choix = { ...vue.correspondance };
  let onglet = vue.onglet || (vue.onglets[0] || null);

  const entete = h('p.prose', { style: { fontSize: '18px', marginBottom: '14px' } });
  const majEntete = () => {
    vider(entete);
    entete.append(`${entier(vue.n_lignes)} lignes lues dans ${fichier}`);
    entete.append(onglet ? `, onglet « ${onglet} ». ` : '. ');
    const reconnues = Object.keys(choix).length;
    entete.append(`${reconnues} colonnes sur ${Object.keys(etat.champs).length || etat.champs.length} reconnues.`);
  };
  majEntete();
  b.append(entete);

  if (vue.onglets.length > 1) {
    const sel = h('select.champ-texte', { 'aria-label': 'Onglet',
      onchange: async (e) => {
        onglet = e.target.value;
        const v2 = await api.get('/api/donnees/apercu', { fichier, onglet });
        Object.assign(choix, v2.correspondance);
        vue.colonnes = v2.colonnes; vue.lignes = v2.lignes; vue.n_lignes = v2.n_lignes;
        vue.absentes = v2.absentes; vue.obligatoires_manquants = v2.obligatoires_manquants;
        majEntete(); peindreTable();
      } });
    for (const o of vue.onglets) sel.append(h('option', { value: o, selected: o === onglet ? '' : null, texte: o }));
    b.append(h('p', { style: { marginBottom: '16px' } },
      h('span.cle', { texte: 'Onglet ', style: { marginRight: '10px' } }), sel));
  }

  const zoneTable = h('div');
  b.append(zoneTable);

  const peindreTable = () => {
    vider(zoneTable);
    const table = h('table.correspondance');
    table.append(h('thead', {}, h('tr', {},
      h('th', { texte: 'Champ attendu' }), h('th', { texte: 'Colonne du fichier' }),
      h('th', { texte: 'Exemple' }))));
    const tbody = h('tbody');
    for (const champ of etat.champs) {
      const tr = h('tr');
      tr.append(h('td', {}, h('span', { classe: champ.obligatoire ? 'obligatoire' : '',
        texte: champ.libelle + (champ.obligatoire ? ' *' : '') })));
      const sel = h('select', { 'aria-label': `Colonne pour ${champ.libelle}`,
        onchange: (e) => {
          if (e.target.value) choix[champ.cle] = e.target.value;
          else delete choix[champ.cle];
          majEntete(); majExemple();
        } });
      sel.append(h('option', { value: '', texte: '— aucune —' }));
      for (const col of vue.colonnes) {
        sel.append(h('option', { value: col, selected: choix[champ.cle] === col ? '' : null, texte: col }));
      }
      tr.append(h('td', {}, sel));
      const exemple = h('td.note');
      tr.append(exemple);
      const majExemple = () => {
        const i = vue.colonnes.indexOf(choix[champ.cle]);
        const valeurs = i < 0 ? [] : vue.lignes.map(l => l[i]).filter(v => v !== null && v !== '').slice(0, 2);
        exemple.textContent = valeurs.length ? valeurs.join(' · ') : '—';
      };
      majExemple();
      tbody.append(tr);
    }
    table.append(tbody);
    zoneTable.append(h('div.tableau', {}, table));

    const manquants = etat.champs.filter(c => c.obligatoire && !choix[c.cle]);
    const pied = h('p', { style: { marginTop: '18px', display: 'flex', gap: '16px',
      alignItems: 'center', flexWrap: 'wrap' } });
    const bouton = h('button.bouton', { type: 'button', disabled: manquants.length ? '' : null,
      texte: 'Activer ce fichier' });
    pied.append(bouton);
    if (manquants.length) {
      pied.append(h('span.note', { texte:
        `Colonne${manquants.length > 1 ? 's' : ''} indispensable${manquants.length > 1 ? 's' : ''} à indiquer : `
        + manquants.map(c => c.libelle).join(', ') + '.' }));
    } else {
      pied.append(h('span.note', { texte: 'Les colonnes indispensables sont reconnues.' }));
    }
    const retour = h('div', { style: { marginTop: '14px' } });
    zoneTable.append(pied, retour);

    bouton.addEventListener('click', async () => {
      bouton.disabled = true;
      vider(retour).append(chargement('Lecture du fichier et contrôle des colonnes…'));
      try {
        const r = await api.post('/api/donnees/activer', { fichier, onglet, colonnes: choix });
        vider(retour);
        retour.append(message(`${entier(r.n_lignes)} questionnaires lus. L’application affiche désormais ces données.`));
        if (r.alertes && r.alertes.length) {
          const ul = h('ul.note', { style: { marginTop: '10px', paddingLeft: '18px' } });
          for (const a of r.alertes) ul.append(h('li', { texte: a }));
          retour.append(ul);
        }
        annoncer('Fichier activé.');
        await ctx.rechargerTout();
        setTimeout(() => peindre(zone, ctx), 900);
      } catch (e) {
        vider(retour).append(message(`Activation refusée : ${e.message}`));
        bouton.disabled = false;
      }
    });
  };
  peindreTable();
  return b;
}

/* ------------------------------------------------------------ qualité --- */
function blocQualite(etat) {
  const s = etat.source;
  const b = h('section', { style: { marginBottom: '36px' } });
  b.append(h('div.cle.cle--ink', { texte: 'Qualité de la lecture', style: { marginBottom: '12px' } }));
  if (!s.alertes || !s.alertes.length) {
    b.append(h('p.prose', { texte: 'Aucune anomalie relevée à l’import.' }));
  } else {
    b.append(h('p.prose', { style: { marginBottom: '12px' },
      texte: 'Aucune ligne n’est écartée sans être comptée.' }));
    const ul = h('ul', { style: { margin: 0, paddingLeft: '18px', fontSize: '13.5px',
      color: 'var(--ink)', lineHeight: '1.7' } });
    for (const a of s.alertes) ul.append(h('li', { texte: a }));
    b.append(ul);
  }
  if (s.colonnes_absentes && s.colonnes_absentes.length) {
    b.append(h('p.note', { style: { marginTop: '12px' },
      texte: 'Dimensions absentes du fichier, analyses correspondantes masquées : '
        + s.colonnes_absentes.join(', ') + '.' }));
  }
  if (s.colonnes_ignorees && s.colonnes_ignorees.length) {
    b.append(h('p.note', { style: { marginTop: '8px' },
      texte: `Colonnes du fichier non utilisées : ${s.colonnes_ignorees.slice(0, 12).join(', ')}`
        + (s.colonnes_ignorees.length > 12 ? '…' : '') + '.' }));
  }
  return b;
}

/* ------------------------------------------------ grilles tarifaires --- */
// Le second classeur : celui des grilles de frais (une ligne par tranche),
// qui nourrit l'écran Tarification. Même geste que pour l'activité :
// déposer, lire ce qui a été compris, activer. Rien n'est activé sans avoir été lu.
function blocTarif(ctx) {
  const b = h('section', { id: 'grilles-tarifaires', style: { marginBottom: '36px', paddingTop: '28px',
    borderTop: '1px solid var(--b-12)' } });
  peindreTarif(b, ctx);
  return b;
}

async function peindreTarif(b, ctx) {
  vider(b).append(h('div.cle.cle--ink', { texte: 'Les grilles tarifaires', style: { marginBottom: '12px' } }),
    chargement('Lecture des grilles…'));
  let etat;
  try {
    etat = await api.get('/api/tarif/donnees');
  } catch (e) {
    b.append(message(`État des grilles illisible : ${e.message}`));
    return;
  }
  const titre = b.firstChild;
  vider(b).append(titre);
  const s = etat.source;
  const p = h('p.prose');
  if (s.mode === 'demo') {
    p.append('Le simulateur de l’écran Tarification tourne sur l’');
    p.append(h('b', { texte: 'échantillon de la présentation' }));
    p.append(` : ${entier(s.n_lignes)} lignes, ${entier(etat.n_offres)} offres. Déposez le classeur des grilles pour le remplacer.`);
  } else {
    p.append('Le simulateur lit ');
    p.append(h('b', { texte: s.fichier }));
    if (s.onglet) p.append(`, onglet « ${s.onglet} »`);
    p.append(` : ${entier(s.n_lignes)} lignes, `);
    p.append(h('b', { texte: `${entier(etat.n_offres)} offres` }));
    p.append(etat.n_anomalies ? `, ${entier(etat.n_anomalies)} points signalés dans l’écran.` : ', sans anomalie.');
  }
  b.append(p);
  if (s.alertes && s.alertes.length) {
    const ul = h('ul.note', { style: { margin: '10px 0 0', paddingLeft: '18px' } });
    for (const a of s.alertes) ul.append(h('li', { texte: a }));
    b.append(ul);
  }

  const actions = h('p', { style: { marginTop: '14px', display: 'flex', gap: '18px', flexWrap: 'wrap' } });
  actions.append(lien('Ouvrir le simulateur', () => ctx.aller ? ctx.aller('tarification') : (window.location.href = '/?ecran=tarification')));
  if (s.mode !== 'demo') {
    actions.append(lien('Revenir à l’échantillon', async () => {
      await api.post('/api/tarif/donnees/demo');
      annoncer('Le simulateur est revenu à l’échantillon.');
      peindreTarif(b, ctx);
    }));
  }
  b.append(actions);

  // Ce qui est attendu : une ligne par tranche, quatre colonnes indispensables.
  const attendu = h('p.note', { style: { marginTop: '16px' } });
  attendu.append('Une ligne par tranche. Colonnes reconnues : ');
  etat.colonnes.forEach((c, i) => {
    if (i) attendu.append(', ');
    attendu.append(c.obligatoire ? h('b', { texte: c.attendu }) : c.attendu);
  });
  attendu.append(' — en gras, les indispensables. Les en-têtes renommés ou tronqués sont reconnus ; '
    + 'les taux se lisent en % (0,12) comme en fraction (0,0012).');
  b.append(attendu);

  // Dépôt.
  const entree = h('input', { type: 'file', accept: '.xlsx,.xlsm,.xls,.csv,.tsv,.txt', style: { display: 'none' } });
  const depot = h('div.depot', { role: 'button', tabindex: '0', style: { marginTop: '16px' },
    onclick: () => entree.click(),
    onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); entree.click(); } },
    ondragover: (e) => { e.preventDefault(); depot.classList.add('depot--survol'); },
    ondragleave: () => depot.classList.remove('depot--survol'),
    ondrop: (e) => {
      e.preventDefault(); depot.classList.remove('depot--survol');
      if (e.dataTransfer.files[0]) envoyer(e.dataTransfer.files[0]);
    } });
  depot.append(h('div.depot__t', { texte: 'Déposer le classeur des grilles' }),
    h('p.note', { style: { marginTop: '6px' }, texte: 'Excel ou CSV, 50 Mo au plus. Il est lu, pas encore activé.' }), entree);
  entree.addEventListener('change', () => { if (entree.files[0]) envoyer(entree.files[0]); });
  const retour = h('div', { style: { marginTop: '16px' } });
  b.append(depot, retour);

  async function envoyer(fichier) {
    vider(retour).append(chargement(`Lecture de ${fichier.name}…`));
    try {
      const r = await api.deposer('/api/tarif/donnees/fichier', fichier);
      vider(retour).append(apercuTarif(r, () => activer(r.fichier, r.journal.onglet)));
      annoncer(`${fichier.name} lu : ${r.journal.n_grilles} offres.`);
    } catch (e) {
      vider(retour).append(message(`Le classeur n’a pas pu être lu : ${e.message}`));
    }
  }

  async function activer(fichier, onglet) {
    vider(retour).append(chargement('Contrôle et activation…'));
    try {
      const r = await api.post('/api/tarif/donnees/activer', { fichier, onglet: onglet || null });
      annoncer(`${r.n_offres} offres activées.`);
      await peindreTarif(b, ctx);
      b.append(message(`${entier(r.n_offres)} offres lues. L’écran Tarification affiche désormais ces grilles.`));
    } catch (e) {
      vider(retour).append(message(`Activation refusée : ${e.message}`));
    }
  }

  // Les classeurs déjà déposés.
  if (etat.fichiers.length) {
    b.append(h('div.cle', { texte: 'Classeurs présents', style: { margin: '24px 0 6px' } }));
    for (const f of etat.fichiers) {
      const actif = s.mode !== 'demo' && s.fichier === f.nom;
      const ligne = h('div', { style: { display: 'flex', gap: '16px', alignItems: 'baseline',
        padding: '9px 0', borderBottom: '1px solid var(--b-12)' } });
      ligne.append(h('span', { texte: f.nom, style: { flex: 1, fontSize: '14px' } }),
        h('span.note', { texte: `${(f.taille / 1024).toFixed(0)} ko · ${f.modifie.replace('T', ' à ')}` }),
        actif ? h('span.note', {}, h('b', { texte: 'branché' })) : lien('Activer', () => activer(f.nom, null)));
      b.append(ligne);
    }
  }

  // Les libellés clients, pour remplacer « Client 7 » sans toucher au code.
  const entreeLib = h('input', { type: 'file', accept: '.csv,.txt,.xlsx,.xlsm,.xls', style: { display: 'none' },
    onchange: async () => {
      if (!entreeLib.files[0]) return;
      try {
        const r = await api.deposer('/api/tarif/correspondance', entreeLib.files[0]);
        annoncer(`${r.n_libelles} libellés appliqués.`);
        peindreTarif(b, ctx);
      } catch (e) { annoncer(`Correspondance refusée : ${e.message}`); }
    } });
  b.append(h('div.cle', { texte: 'Libellés clients', style: { margin: '24px 0 8px' } }),
    h('p.note', { html: 'Le classeur nomme ses clients « Client 1 », « Client 2 »… La correspondance '
      + '(<b>client ; libelle</b>) leur rend leur vrai nom partout dans l’écran. Elle se remplit dans Excel '
      + 'ou au crayon, ligne par ligne, dans la liste des offres.' }),
    h('p', { style: { marginTop: '10px', display: 'flex', gap: '18px', flexWrap: 'wrap' } },
      lien('Télécharger la correspondance', () => { window.location.href = '/api/tarif/correspondance.csv'; }),
      lien('Déposer une correspondance', () => entreeLib.click()), entreeLib));
}

function apercuTarif(r, activer) {
  const j = r.journal;
  const b = h('section', { style: { borderTop: '1px solid var(--b-22)', paddingTop: '20px' } });
  const entete = h('p.prose', { style: { fontSize: '18px', marginBottom: '14px' } });
  entete.append(`${entier(j.n_lignes)} lignes lues dans ${r.fichier}`, j.onglet ? `, onglet « ${j.onglet} »` : '',
    ` : ${entier(j.n_grilles)} offres`);
  entete.append(r.n_exclues ? `, dont ${entier(r.n_exclues)} écartée${r.n_exclues > 1 ? 's' : ''} des comparaisons.` : '.');
  b.append(entete);
  const reconnues = Object.entries(j.colonnes || {});
  if (reconnues.length) {
    b.append(h('p.note', { texte: `Colonnes reconnues : ${reconnues.map(([, en]) => en).join(', ')}.`
      + (j.unite_taux ? ` Taux lus en ${j.unite_taux}.` : '') }));
  }
  if (j.ignorees && j.ignorees.length) b.append(h('p.note', { texte: `Non utilisées : ${j.ignorees.join(', ')}.` }));
  if (j.alertes && j.alertes.length) {
    const ul = h('ul.note', { style: { margin: '8px 0 0', paddingLeft: '18px' } });
    for (const a of j.alertes) ul.append(h('li', { texte: a }));
    b.append(ul);
  }
  const table = h('table.correspondance.apercu-tarif');
  table.append(h('thead', {}, h('tr', {}, ...['Client', 'Année', 'Expertise', 'Issue', 'Tranches', 'Taux moyen', 'Signalé']
    .map(t => h('th', { texte: t })))));
  const corps = h('tbody');
  for (const o of r.apercu) {
    corps.append(h('tr', {},
      h('td', { texte: o.client }), h('td', { texte: o.annee ?? '—' }), h('td', { texte: o.expertise || '—' }),
      h('td', { texte: o.issue }), h('td', { texte: entier(o.n_tranches) }),
      h('td', { texte: o.taux_volume === null || o.taux_volume === undefined ? '—'
        : `${o.taux_volume.toLocaleString('fr-FR', { maximumFractionDigits: 3 })} %` }),
      h('td.note', { texte: o.anomalies.length ? o.anomalies[0] + (o.anomalies.length > 1 ? ` (+${o.anomalies.length - 1})` : '') : '—' })));
  }
  table.append(corps);
  b.append(h('div.tableau', { style: { marginTop: '14px' } }, table));
  if (j.n_grilles > r.apercu.length) b.append(h('p.note', { texte: `Les ${entier(r.apercu.length)} premières offres sur ${entier(j.n_grilles)}.` }));
  const bouton = h('button.bouton', { type: 'button', texte: 'Activer ces grilles', onclick: activer });
  b.append(h('p', { style: { marginTop: '18px', display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' } },
    bouton, h('span.note', { texte: 'Les colonnes indispensables sont reconnues.' })));
  return b;
}
