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
