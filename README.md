# RFP Intelligence

Produit de pilotage de l'activité **RFP / Due Diligence** d'une société de
gestion d'actifs. Il répond en un écran à la question du dirigeant — *où en
sont les appels d'offres ?* — puis laisse descendre, page après page, jusqu'au
dossier individuel.

Trois fichiers Python, dix pages, un rapport HTML autonome.

<!-- ÉTAT : début — généré par `python export.py --readme`, ne pas éditer -->

## État du carnet au 16 septembre 2026

> **Jeu de démonstration.** Les chiffres de cette page sont produits par le générateur livré avec le dépôt. Ils reproduisent la FORME d'une activité réelle — saisonnalité, délais, concentration de la collecte — mais aucun ne décrit une activité réelle, et aucun client nommé n'existe. Voir « Brancher vos données ».

| Appels d'offres vivants | Encours en jeu | Taux de succès | Encours remporté |
|---:|---:|---:|---:|
| **13** | **569 M€** | **33,1 %** | **5 625 M€** |

<sub>86 mandats remportés sur 260 dossiers tranchés. Les dossiers en attente de décision sont exclus du dénominateur.</sub>

| Compartiment | Dossiers | Encours |
|---|---:|---:|
| En rédaction <sub>chez nous, réponse non partie</sub> | 6 | 265 M€ |
| En attente de décision <sub>remis au client, non tranché</sub> | 7 | 304 M€ |
| Gagnés <sub>mandat remporté</sub> | 86 | 5 625 M€ |
| Perdus <sub>mandat non retenu</sub> | 174 | 7 537 M€ |
| Sans suite <sub>abandonné avant décision</sub> | 15 | 853 M€ |

### En attente de décision — 7

| Dossier | | Attente |
|---|---|---:|
| Sovereign Reserve Authority | Singapour · Obligataire | 183 j |
| Caja de Pensiones Ibérica | Espagne · Actions | 156 j |
| Albion Wealth Partners | Royaume-Uni · Obligataire | 134 j |
| Groupe Financier Bellecour | France · Obligataire | 125 j |
| Banque Privée du Léman | Suisse · Obligataire | 55 j |
| _… et 2 autres_ | | |

### Gagnés — 86

| Dossier | | Encours |
|---|---|---:|
| Stiftung Rheinland Vorsorge | Allemagne · Alternatif | 4 M€ |
| Université de Genève — Dotation | Suisse · Monétaire | 88 M€ |
| Conseil Actuariel Lutèce | France · Actifs réels | 73 M€ |
| Pensioenfonds Rijnmond | Pays-Bas · Obligataire | 23 M€ |
| Albion Wealth Partners | Royaume-Uni · Actifs réels | 184 M€ |
| _… et 81 autres_ | | |

### Perdus — 174

| Dossier | | Encours |
|---|---|---:|
| Assurance Vie Méditerranée | France · Actifs réels | 7 M€ |
| Assurance Vie Méditerranée | France · Obligataire | 31 M€ |
| Albion Wealth Partners | Royaume-Uni · Monétaire | 19 M€ |
| Banque Privée du Léman | Suisse · Actions | 25 M€ |
| Plateforme Épargne Digitale | France · Obligataire | 70 M€ |
| _… et 169 autres_ | | |

Mix des demandes : **288** RFP · **387** RFI · **996** DDQ. Le rapport diffusé, lui, s'en tient aux deux familles de pilotage — RFP et due diligence.

> Source : Données synthétiques (1 691 lignes, graine 20260914). 1 671 lignes exploitables sur 1 691. Bloc régénéré par `python export.py --readme`.

<!-- ÉTAT : fin -->

---

## Démarrer en 2 minutes

```bash
pip install -r requirements.txt
streamlit run app.py
```

L'application s'ouvre sur **http://localhost:8501**. Port occupé ?
`streamlit run app.py --server.port 8502`. `Ctrl + C` arrête le serveur.

Elle démarre sur un jeu de **données de démonstration** couvrant 2014 →
aujourd'hui (~1 700 questionnaires). Rien à configurer pour la découvrir.

```bash
python core.py                # contrôle la chaîne de bout en bout
python export.py              # écrit rapport.html
python export.py --clair      # variante claire, pour l'impression
python export.py --readme     # régénère l'état du carnet en tête de ce fichier
```

---

## Architecture

| Fichier | Rôle | Dépendance à Streamlit |
|---|---|---|
| `core.py` | Configuration, lecture Excel, normalisation, **couche métrique**, statistiques, thèmes, figures Plotly, moteur d'insights | **aucune** |
| `app.py` | Interface : accueil, navigation, filtres globaux, drill-down, explorateur, export | oui |
| `export.py` | Rapport HTML autonome, et l'état du carnet écrit dans ce README | non |
| `assets/` | Marque (`logo.svg`), police Inter (OFL), lecteur Lottie (MIT), 4 animations | — |

`core.py` produit un objet `Analysis` — indicateurs, blocs d'analyse, constats —
que `app.py` et `export.py` consomment **à l'identique**. Un chiffre affiché à
l'écran est le même que dans le rapport, par construction.

**Couche métrique.** Chaque indicateur est défini une fois, dans une fonction
documentée (`carnet`, `taux_succes_rfp`, `aum_gagne`, `cadence_mensuelle`,
`croissance`…). Deux graphiques ne peuvent pas compter la même chose
différemment, et le README ne peut pas dire autre chose que l'écran.

**Ajouter une analyse** : écrire `_bloc_xxx(df, mensuel, stats)` qui renvoie un
`Block`, puis l'inscrire dans `_CONSTRUCTEURS`. Un `Block` dont la figure est
`None` **est** un tableau : il s'affiche déplié, à l'écran comme dans le rapport
— certaines réponses se lisent ligne à ligne. Elle apparaît automatiquement
dans la page de sa section **et** dans le rapport. Un bloc qui échoue est
signalé dans la page qualité ; il n'interrompt jamais l'écran.

---

## Deux parties

L'écran et le rapport ont la **même** architecture de l'information. Deux
niveaux de navigation, pas cinq.

### Partie I · Direction — se lit debout, en trois minutes

| Page | Question à laquelle elle répond |
|---|---|
| **Vue d'ensemble** | Où en sommes-nous, et qu'est-ce qui a bougé ce trimestre ? |
| **Aujourd'hui** | Quels appels d'offres attendent une décision, lesquels viennent d'être gagnés, lesquels sont à relancer ? |

**La vue d'ensemble ouvre sur l'arbre.** La décomposition de l'activité est la
première chose que l'on voit : questionnaires reçus → due diligence / appels
d'offres → les cinq états d'un appel d'offres. La branche « due diligence » n'a
volontairement pas de suite — une due diligence se traite, elle ne se gagne pas.
Les effectifs vont de 6 à 1 400 : la forme est donc un arbre de nombres reliés et
non un pavage proportionnel, qui rendrait illisibles les petites branches, celles
mêmes qui appellent une décision. La proportion reste encodée, par la barre sous
chaque nombre.

Viennent ensuite **les huit derniers trimestres** — quatre mouvements en petits
multiples : reçus, appels d'offres reçus, réponses envoyées, encours remporté.
Le trimestre en cours est atténué : il est incomplet, il ne se compare pas. Puis
quatre indicateurs, les constats calculés, la tendance longue, et **les mandats
remportés** ligne à ligne (client, consultant, pays, classe et sous-classe
d'actifs, forme juridique, fonds de référence, encours).

Le **sélecteur d'exercice** est dans l'en-tête, à droite du titre : un réglage a
sa place dans la barre de commande, pas au-dessus du contenu qu'il pilote.

**Aujourd'hui** porte le carnet vivant : le ruban des cinq compartiments, les
trois registres nommés — qui attend, qui est gagné, qui est perdu — la liste à
relancer avec son motif, et le mix réel des demandes. Chaque ligne est cliquable :
elle ouvre l'explorateur sur ce client, où un second clic ouvre la fiche.

### Partie II · Analyse — le détail, dimension par dimension

| Page | Question à laquelle elle répond |
|---|---|
| **Activité** | La charge augmente-t-elle ? À quelle vitesse la traite-t-on ? |
| **Pipeline RFP** | Que deviennent les appels d'offres, et où gagne-t-on ? |
| **Due diligence** | Quelles expertises et quels pays absorbent la charge ? |
| **Encours & gains** | Combien l'effort commercial rapporte-t-il réellement ? |
| **ESG** | Quel poids prend la composante ESG, et chez qui ? |
| **Diagnostic** | Qu'est-ce qui explique les délais, et que laisse attendre la tendance ? |
| **Explorateur** | Du chiffre agrégé au dossier individuel. |
| **Qualité & export** | D'où viennent les données, que valent-elles, comment les diffuser ? |

### RFI et DDQ : à l'écran, pas dans le rapport

Le pilotage raisonne en **deux familles** — RFP d'un côté, toute la due diligence
de l'autre — et c'est la seule lecture que porte le rapport diffusé. Le détail du
type fin (RFP / RFI / DDQ) reste visible **à l'écran** : dans le mix de la page
d'accueil, dans deux indicateurs de la page due diligence, et dans le bloc « RFI
et DDQ : le détail de la charge ».

Techniquement, un `Block` ou un `Kpi` porte un drapeau `hors_rapport` ;
`export.py` les écarte. L'auto-test vérifie qu'il reste au moins un bloc d'écran
et qu'aucun indicateur marqué ne part dans le rapport.

### Drill-down

Le produit ne laisse jamais dans une impasse analytique :

- **une carte d'indicateur est un lien** — « Appels d'offres » ouvre le pipeline
  RFP, « Encours remporté » ouvre la page des gains ;
- **un clic sur une barre filtre tout le tableau de bord** — cliquer
  « Investment Solutions » sur la charge par expertise recalcule l'ensemble des
  pages sur cette expertise ;
- **un clic sur une ligne de l'explorateur ouvre la fiche du dossier**, sans
  perdre les filtres ni la position dans la liste ;
- **l'URL porte l'état** — `?page=rfp`, et un lien peut même transporter un
  filtre (`?page=explorateur&statut=Gagné`) ou une recherche (`&q=Bellecour`).
  Les liens sont partageables, et le bouton « précédent » fonctionne.

### Filtres

Une seule barre, sous le titre et au-dessus de tout ce qu'elle porte : période,
puis les quatre dimensions de premier niveau, les autres derrière « Plus de
filtres ». Les filtres actifs sont affichés en permanence — on ne lit jamais un
chiffre sans savoir sur quoi il porte.

La **période** accepte les fenêtres glissantes (12 / 24 / 36 derniers mois),
l'historique complet, et les **exercices civils** — le pilotage se fait aussi en
années pleines. La bande d'exercices de la vue d'ensemble n'est qu'une autre
façon d'actionner ce même sélecteur.

---

## Brancher vos données (5 minutes)

Tout se passe dans le bloc **`[BRANCHEMENT PRINCIPAL]`**, en tête de `core.py`.

1. `USE_FAKE_DATA = False`
2. `DATA_PATH` — chemin du classeur ; `SHEET_NAME` — onglet
3. `COLUMN_MAP` — nom réel de chaque colonne

**La correspondance est tolérante** : casse, accents, espaces, tirets et
underscores sont ignorés, et `COLUMN_ALIASES` reconnaît les intitulés courants
(`"Date de réception"`, `"Sub asset class"`, `"ESG %"`…).

**Colonnes indispensables** : date de réception, type de demande, statut. Toutes
les autres sont facultatives — si `Expertise` manque, la page due diligence perd
son classement par expertise et conserve le reste. Rien ne casse, et la page
« Qualité » dit précisément ce qui manque.

**Vocabulaire métier** — paramétrable dans le même bloc :

- `FAMILLE_PAR_TYPE` regroupe les types fins (RFP / RFI / DDQ) dans les deux
  familles du pilotage : **RFP** et **Due Diligence** ;
- `STATUS_NORMALIZATION` ramène les variantes d'écriture (`gagne`, `GAGNÉ`,
  `won`) à une valeur unique ; une modalité inconnue reste visible et remonte
  dans la page qualité ;
- la **part ESG** est acceptée sous trois formes : fraction (`0,45`),
  pourcentage (`45 %`) ou tranche écrite (`> 75 % ESG`). Une tranche écrite
  donne une tranche, jamais un pourcentage inventé ;
- `SLA_JOURS_OUVRES`, `HORIZONS_CROISSANCE`, `ESG_SEUIL_FORT`, `THEME_DEFAUT`.

> Les données réelles ne doivent pas rejoindre le dépôt : `.gitignore` exclut
> `*.xlsx`, `*.csv` et le rapport généré. Régénérer l'état de ce README sur des
> données réelles y publierait des noms de clients : c'est une décision à
> prendre, pas un automatisme.

---

## Identité de la maison

Le bloc **`[BRANCHEMENT MARQUE]`**, juste en dessous, tient toute l'identité :
nom, activité, fichier de logo, et trois couleurs — bleu de nuit, bleu profond,
or.

> **Ces trois couleurs sont une reconstruction, pas la charte.** Les sites de la
> maison ne sont pas accessibles depuis l'environnement de développement : les
> valeurs livrées reproduisent le couple bleu de nuit / or, elles ne sont pas
> extraites du référentiel officiel. Les remplacer par celles de la charte prend
> trente secondes, et n'a d'effet qu'à cet endroit.

> **`assets/logo.svg` n'est pas le logo officiel.** C'est un repère géométrique
> dessiné pour ce produit — les cinq flèches, tracées au compas. Déposer le SVG
> de la charte sous ce nom exact suffit à le remplacer partout : barre latérale,
> page d'accueil, couverture du rapport. Voir `assets/LOGO.txt`.

---

## Définitions qui engagent

- **Famille** — RFP d'un côté, toute la due diligence de l'autre. C'est la
  lecture du pôle ; le type fin reste disponible en filtre et à l'écran.
- **Résultat** — n'existe **que** pour un appel d'offres. Une due diligence ne
  se gagne pas : son résultat est « sans objet », pas « perdu ».
- **Carnet** — les cinq états d'un appel d'offres. « En rédaction » et « en
  attente de décision » partagent le résultat « en attente » mais appellent deux
  actions différentes : produire d'un côté, relancer de l'autre. Le carnet
  distingue les deux ; c'est tout l'intérêt de la page d'accueil.
- **Taux de succès** — gagnés / (gagnés + perdus). Les dossiers en attente de
  décision sont exclus du dénominateur ; les compter comme des échecs
  fabriquerait un effondrement sur les périodes récentes.
- **Encours remporté** — encours des RFP gagnés, rattaché à l'année de
  réception du dossier. **Encours en jeu** — celui des dossiers encore ouverts :
  un pipeline, pas une collecte acquise.
- **Délai de traitement** — jours **calendaires** entre réception et envoi,
  comme au comité. Le respect du délai cible se mesure, lui, en jours ouvrés.
- **Cadence** — dossiers **terminés** par mois : la capacité de production de
  l'équipe, à distinguer de la charge qui lui arrive.
- **Croissance sur N ans** — dernière année civile **complète** contre celle
  d'il y a N ans. L'année en cours est exclue : la comparer à une année pleine
  afficherait un effondrement qui n'existe pas.
- **Limite de lecture** — les clients tranchent plusieurs mois après l'envoi.
  Sur une période récente, le taux de succès et l'encours remporté sont
  mécaniquement sous-évalués, l'encours en jeu surévalué. L'avertissement est
  affiché sous les indicateurs.

Les **insights** sont calculés, jamais rédigés d'avance : chaque phrase provient
d'une fonction analytique, et disparaît si la donnée ne permet pas de
l'établir. Aucun chiffre n'est produit par un modèle de langage.

---

## Design

**Un système, deux surfaces.** Espacement (multiples de 4 et 8), échelle
typographique, rayons, profondeur et courbes de mouvement sont définis une seule
fois dans `core.py` — `ESPACEMENT`, `TYPO`, `MOTION` — et émis en variables CSS
par `core.jetons_css()`. `app.py` et `export.py` consomment les mêmes jetons :
aucune valeur en dur nulle part ailleurs. Changer une échelle la change partout.

**Quatre thèmes** définis au même endroit : *maison* (sombre, par défaut),
*Sombre neutre*, *Institutionnel*, *Clair* pour l'impression. Le sélecteur est en
bas de la barre latérale, et `?theme=clair` le transporte dans l'URL.

**Direction artistique du thème maison** : bleu de nuit, surfaces plates, filets
d'un pixel qui dessinent la grille, angles courts (4 px), micro-libellés en
capitales espacées, chiffres tabulaires larges. Aucune ombre, aucun dégradé,
aucun halo — la hiérarchie tient au contraste typographique et au vide. L'or ne
porte jamais une donnée : il marque la navigation active, la marque, et le seul
chiffre qui compte vraiment, l'encours remporté.

**Palette validée** sur sa propre surface : bande de clarté, plancher de chroma,
séparation sous daltonisme et contraste — les huit teintes passent les contrôles
sur le bleu de nuit comme sur l'ivoire. L'ordre des teintes est le mécanisme de
sécurité, pas une préférence : ne pas permuter sans revalider. L'identité d'une
série n'est jamais portée par la seule couleur (légende, libellés directs,
tableau équivalent), et les couleurs d'état s'accompagnent toujours du libellé et
de la valeur — y compris sur le ruban du carnet.

**Choix de formes assumés** : pas de camembert à vingt parts pour la répartition
par expertise — un classement en barres, queue regroupée dans « Autres ». Au-delà
de sept catégories, aucune part d'un disque n'est comparable à l'œil.

**Typographie** : Inter variable (SIL OFL) embarquée en base64 — même rendu hors
ligne et dans un rapport transmis par courriel. Chiffres tabulaires partout où
des valeurs s'alignent. Et pas un seul « dossier(s) » : les accords sont
calculés (`core.pluriel`, `core.accord`).

**Mouvement** : le logo est un SVG inline, net à toutes les tailles et immobile —
une marque qui se redessine à chaque rerun de Streamlit fatigue. Les animations
Lottie (lecteur `lottie_light`, MIT, servi depuis `assets/`, jamais un CDN)
restent là où un mouvement signifie quelque chose : l'attente pendant la
génération du rapport, la confirmation ensuite, le tracé de couverture du
rapport — où les cinq flèches se dessinent une fois, au chargement.
`prefers-reduced-motion` coupe tout.

Si `assets/` est absent, l'interface perd sa marque, ses animations et sa
police — jamais son contenu.

---

## Rapport HTML

Le bouton « Générer le rapport » (page *Qualité & export*) produit un fichier
unique d'environ 5 Mo reprenant le périmètre filtré : couverture avec la marque
et les chiffres clés, constats calculés, sept pages navigables (clic, flèches
← →, touches 0-7), les analyses interactives, leurs tableaux et une annexe
méthodologique. Plotly, Lottie, les animations et la police y sont embarqués :
il s'ouvre d'un double-clic, sans Python, sans serveur, sans réseau.

C'est le document **diffusé** : il parle le vocabulaire du comité — deux
familles, pas de types fins. Il reprend les deux parties de l'application, et sa
vue d'ensemble ouvre elle aussi sur l'arbre.

**Il bascule clair / sombre tout seul**, sans être régénéré : les deux palettes y
sont embarquées. Une figure Plotly fige pourtant ses couleurs — l'encre d'une
annotation, le fond d'une piste, l'anneau de surface d'une marque ; un simple
changement de gabarit ne les atteint pas. `core.substitutions()` produit la table
des seuls jetons de **chrome**, que le rapport applique à tout ce qui est chaîne
dans la figure. Les marques ne bougent pas : leur palette passe les contrôles
daltonisme et contraste sur le bleu de nuit **comme** sur l'ivoire — vérifié, pas
supposé. Raccourci clavier : `t`.

---

## Données de démonstration

Le jeu par défaut est **explicitement synthétique** — la source est libellée
comme telle dans la barre latérale, sur la page qualité, dans l'annexe du
rapport et en tête de ce fichier. Sa forme reproduit celle d'un pôle réel : due
diligence multipliée par quatre en dix ans à effectif RFP constant, creux d'août,
délais corrélés au volume de questions, collecte très concentrée sur quelques
mandats. Aucun client nommé n'existe.

Les volumes annuels sont paramétrés (`VOLUMES_ANNUELS`) de sorte que les trois
indicateurs de croissance du produit tombent sur ceux que publie le pôle :
**+49 % sur 3 ans, +149 % sur 5 ans, +158 % sur 10 ans**. `python core.py`
vérifie cette concordance à chaque exécution — c'est ainsi que les définitions
de métriques sont validées, et non par leur seul intitulé.
