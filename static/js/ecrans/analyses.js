// analyses.js — une question à la fois, et ses analyses.
//
// Chaque analyse porte la phrase du moteur, sa figure, sa note de méthode et
// son tableau jumeau. Un clic sur une catégorie filtre tout le périmètre.

import { h, vider, lien, entier, pluriel } from '../ui.js';
import { rendreQuandVisible, detruireFigure, tableau as tableauHTML } from '../figures.js';

const MARGES = {
  activite: ['Lecture',
    'Le volume reçu n’est pas le volume traité : la charge qui arrive et la capacité de production sont deux questions distinctes.',
    'La cadence compte les dossiers <b>terminés</b> par mois ; le délai se mesure de la réception à l’envoi.'],
  rfp: ['Lecture',
    'Le taux de succès rapporte les mandats gagnés aux dossiers tranchés. Les dossiers en attente de décision sont exclus du dénominateur.',
    'Les clients tranchent plusieurs mois après l’envoi : sur une période récente, le taux de succès est mécaniquement sous-évalué.'],
  dd: ['Lecture',
    'Une due diligence se traite, elle ne se gagne pas : elle n’a pas de résultat commercial.',
    'Le détail RFI / DDQ est une lecture d’écran. Le rapport diffusé s’en tient aux deux familles.'],
  aum: ['Lecture',
    'L’encours remporté est rattaché à l’année de <b>réception</b> du dossier, pas à celle de la décision.',
    'La collecte issue des appels d’offres est très irrégulière : un mandat peut peser plus qu’une année ordinaire.'],
  esg: ['Lecture',
    'La part ESG est calculée sur les seuls dossiers dont elle est renseignée : compter les non-renseignés comme peu ESG ferait mentir la série.',
    'Une part écrite en tranche (« plus de 75 % ») donne une tranche, jamais un pourcentage inventé.'],
  diagnostic: ['Méthode',
    'Ces modèles cherchent ce qui explique les délais et ce que la tendance laisse attendre. Ils répondent au « pourquoi », pas au « combien ».',
    'Deux intervalles de confiance qui se recouvrent ne permettent pas de conclure à une différence.'],
};

export function rendreAnalyses(ctx) {
  const { analyse, meta, etat } = ctx;
  const ecran = h('div.ecran');
  const sections = analyse.sections.filter(s => s.cle !== 'synthese');
  const courante = sections.find(s => s.cle === etat.ecran) || sections[0];
  if (!courante) {
    ecran.append(h('p.prose', { texte: 'Aucune analyse sur ce périmètre.' }));
    return ecran;
  }

  const nav = h('nav.questions', { 'aria-label': 'Questions' });
  for (const s of sections) {
    nav.append(h('a', {
      href: `?ecran=${s.cle}`, 'aria-current': s.cle === courante.cle ? 'page' : null,
      onclick: (e) => { e.preventDefault(); ctx.aller(s.cle); },
    }, s.libelle));
  }
  ecran.append(nav);

  const blocs = analyse.blocs.filter(b => b.section === courante.cle);
  ecran.append(h('div', { style: { marginTop: '28px' } },
    h('h1.titre-ecran', { texte: courante.libelle }),
    h('p.sous-ecran', { texte: `${pluriel(blocs.length, 'analyse')} sur ${pluriel(analyse.n, 'questionnaire')}.` })));

  const grille = h('div.lecture');
  const colonne = h('div');
  for (const b of blocs) colonne.append(uneAnalyse(b, ctx));
  grille.append(colonne);

  const marge = h('div.marge-col');
  const texte = MARGES[courante.cle];
  if (texte) {
    marge.append(h('div.marge-titre', { texte: texte[0] }));
    for (const p of texte.slice(1)) marge.append(h('p.marge-texte', { html: p }));
  }
  const suivante = sections[(sections.indexOf(courante) + 1) % sections.length];
  if (suivante && suivante !== courante) {
    marge.append(h('p.marge-texte', { style: { marginTop: '20px' } },
      lien(`${suivante.libelle} →`, () => ctx.aller(suivante.cle))));
  }
  grille.append(marge);
  ecran.append(grille);
  return ecran;
}

/** Une analyse : titre, phrase, figure ou tableau, note. */
function uneAnalyse(b, ctx) {
  const el = h('section.analyse', { id: `analyse-${b.cle}` });
  const tete = h('div.analyse__tete');
  tete.append(h('h2.analyse__titre', { texte: b.titre }));

  const corps = h('div.analyse__corps');
  const hote = h('div.figure');
  const zoneTableau = h('div', { hidden: true });
  let vue = 'figure';

  if (b.figure) {
    const outils = h('div.analyse__outils', { role: 'group', 'aria-label': 'Affichage' });
    const boutons = [['figure', 'Figure'], ['tableau', 'Tableau']].map(([cle, libelle]) =>
      h('button.periodes-bouton', {
        type: 'button', 'aria-pressed': String(cle === vue),
        style: { font: 'inherit', fontSize: '12.5px', color: 'var(--b-72)', background: 'none',
          border: 0, padding: '4px 9px', cursor: 'pointer' },
        onclick: () => {
          vue = cle;
          hote.hidden = cle !== 'figure';
          zoneTableau.hidden = cle !== 'tableau';
          for (const bt of boutons) bt.setAttribute('aria-pressed', String(bt.dataset.cle === cle));
          for (const bt of boutons) {
            const actif = bt.dataset.cle === cle;
            bt.style.color = actif ? 'var(--ink)' : 'var(--b-72)';
            bt.style.fontWeight = actif ? '600' : '400';
            bt.style.background = actif ? 'var(--b-12)' : 'none';
          }
        },
        dataset: { cle },
      }, libelle));
    boutons[0].style.color = 'var(--ink)'; boutons[0].style.fontWeight = '600';
    boutons[0].style.background = 'var(--b-12)';
    outils.append(...boutons);
    tete.append(outils);
  }
  el.append(tete);
  if (b.accroche) el.append(h('p.analyse__accroche', { texte: b.accroche }));

  if (b.figure) {
    corps.append(hote);
    zoneTableau.innerHTML = tableauHTML(b.tableau, { max: 120 });
    corps.append(zoneTableau);
    requestAnimationFrame(() => rendreQuandVisible(hote, b.figure, {
      dimension: b.dimension,
      surClic: b.dimension ? (dim, valeur) => ctx.filtrer(dim, valeur) : null,
    }));
    if (b.dimension) {
      corps.append(h('p.figure__aide', { texte:
        `Un clic sur une barre recalcule tout le périmètre sur cette modalité de « ${(ctx.meta.dimensions[b.dimension] || b.dimension).toLowerCase()} ».` }));
    }
  } else {
    // Le bloc EST un tableau : certaines réponses se lisent ligne à ligne.
    corps.innerHTML = tableauHTML(b.tableau, { max: 200 });
  }
  el.append(corps);
  if (b.note) el.append(h('p.analyse__note', { texte: b.note }));
  return el;
}

export function nettoyerFigures(racine) {
  for (const f of racine.querySelectorAll('.figure')) detruireFigure(f);
}
