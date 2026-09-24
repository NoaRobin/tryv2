# RFP & Due Diligence

Application interne de pilotage des appels d’offres et de la due diligence.

Elle répond en un écran à la question de la semaine — *quels appels d’offres
sont ouverts, pour quel encours, et qu’avons-nous gagné ou perdu ?* — puis
laisse descendre, page après page, jusqu’au dossier individuel. Un bouton
produit le rapport HTML du périmètre affiché : un fichier unique, ouvrable
d’un double-clic, sans Python ni connexion.

---

## Démarrer

```bash
pip install -r requirements.txt
python server.py
```

L’application s’ouvre sur **http://localhost:8000**. Port occupé ?
`uvicorn server:app --port 8080`.

Sous Windows, **`demarrer.bat`** fait les deux d’un double-clic : il installe
les dépendances au premier lancement, démarre le serveur et ouvre le navigateur.

Elle démarre sur un jeu de **données de démonstration** au format du classeur
du pôle (environ 1 700 questionnaires, 2014 → aujourd’hui). Rien à configurer
pour la découvrir.

```bash
python core.py                # contrôle la chaîne de bout en bout
python tarification.py        # contrôle le moteur tarifaire et sa parité JavaScript
python export.py              # écrit le rapport HTML sur tout l’historique
```

---

## Brancher vos données

Trois façons, de la plus simple à la plus précise.

1. **Déposer un fichier dans `data/`.** S’il est seul, il est lu au démarrage :
   premier onglet, colonnes reconnues automatiquement.
2. **Depuis l’application, écran « Données ».** Glisser le classeur, choisir
   l’onglet, vérifier la correspondance des colonnes, corriger celles qui n’ont
   pas été reconnues, activer. Le fichier n’est activé qu’après avoir été lu
   sans erreur.
3. **Écrire `data/branchement.json`** à la main :

```json
{
  "fichier": "Extraction RFP 2026.xlsx",
  "onglet": "Suivi",
  "colonnes": { "montant_potentiel": "Ticket (M€)" },
  "actif": true
}
```

**Formats acceptés** : `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.tsv`, `.txt`.

**Le classeur du pôle est lu tel quel.** Les en-têtes attendus sont ceux du
fichier de suivi, et voici comment chacun est lu :

| Colonne | Lecture |
|---|---|
| `Numero` | identifiant du dossier |
| `Année`, `Month` | servent à reconstruire une date de réception si elle manque |
| `Date de réception`, `Date de fin` | bornes du dossier ; le délai de traitement est leur écart en jours calendaires |
| `Client`, `Segment`, `Type de client`, `Country` | qui demande — Instit. / Distr. / Intern. deviennent Institutionnel / Distributeur / International |
| `Consultant` | cabinet intermédiaire ; « None » = en direct |
| `Writer`, `Reviewer` | rédacteur et relecteur |
| `Type` | RFP ou Due Diligence : la famille du dossier. Il n’existe pas de type plus fin ; un intitulé ancien (« questionnaire », « DDQ », « RFI ») est compris à la lecture et rattaché à la due diligence |
| `Volume` | **l’encours en jeu, en M€**. C’est la grandeur centrale : elle est sommée par état (ouvert, gagné, perdu), par segment, par étape |
| `Number` | vaut 1 ; ignoré, on compte les lignes |
| `Step_1`, `Step_2`, `ORAL_RFP` | trois étapes binaires : dossier remis, présélection, soutenance orale. Elles forment le chemin des appels d’offres |
| `Status` | Done / In progress / Cancelled → envoyé / en cours / abandonné |
| `Result` | Won / Lost / NA → gagné / perdu / en attente. Prime sur `Status` pour un appel d’offres |
| `Qvidian Update` | la base de réponses a-t-elle été mise à jour |
| `Expertise` | High Conviction / Open Architecture / Corporate |
| `Legal form`, `Asset class`, `Sub-asset class`, `Reference fund` | ce qui est proposé |
| `SRI` | fonds ISR, Yes / No |
| `% ESG` | tranche : « < 25 % ESG », « 25-50 % », « 50-75 % », « 75 % » |
| `Sales` | commercial en charge |
| `Language` | FR / EN |
| `4Change` | conservée, jamais interprétée |

**La correspondance est tolérante** : casse, accents, espaces, tirets,
underscores et unités entre parenthèses sont ignorés. « Date de réception »,
`DATE_RECEPTION` et « date réception » désignent la même colonne, et les
intitulés d’anciennes extractions (« Sub asset class », « Ticket (M€) »,
« Analyste », « Montant »…) restent reconnus ; pour en ajouter, compléter
`COLUMN_ALIASES` en tête de `core.py`.

**Trois colonnes sont indispensables** : `Date de réception`, `Type`, `Status`.
Toutes les autres sont facultatives — si `Step_1` manque, le chemin des appels
d’offres disparaît et le reste demeure. L’écran « Données » dit précisément ce
qui manque et ce qui a été écarté.

> Les données réelles ne rejoignent jamais le dépôt : `data/` est ignoré par
> git, à l’exception de son `.gitignore`.

**Vocabulaire métier**, paramétrable dans le bloc `[BRANCHEMENT PRINCIPAL]` de
`core.py` : familles (RFP / due diligence), normalisation des statuts, délais
cibles par type, seuil ESG, horizons de croissance.

### Le classeur des grilles tarifaires

Le simulateur de l’écran **Tarification** lit un second classeur, indépendant du
premier : **une ligne par tranche** d’une offre de frais passée. Il se dépose
depuis l’écran « Données », section « Les grilles tarifaires » (lu, contrôlé,
puis activé : jamais activé sans avoir été lu), et vit dans `data/tarification/`
— à l’écart de `data/`, pour que la détection automatique du classeur d’activité
ne le prenne jamais pour lui.

| Colonne | Lecture |
|---|---|
| **`Client`** | clé catégorielle (« Client 7 ») : rien n’en est déduit |
| **`Quantite_Minimum`**, **`Quantite_Maximum`** | bornes de la tranche, en M€ ; la dernière tranche est ouverte |
| **`Frais_par_seuil`** | taux de la tranche, en % (0,12) ou en fraction (0,0012, format pourcentage d’Excel) — l’unité est décidée par colonne |
| `Volume1` | l’encours de l’offre, en M€ |
| `Annee`, `Sub_asset_class`, `Client_Prospect`, `Public_Privé`, `TVA`, `Commissions de surperformance` | millésime, expertise, issue (gagné / perdu / en cours), nature, fiscalité |

Les en-têtes renommés ou tronqués sont reconnus (`tarification.COLONNES`), une
ligne de titre au-dessus du tableau est sautée, le meilleur onglet est choisi.
Sans classeur, le simulateur tourne sur les 48 lignes de la page 5 de la
présentation d’origine, et le dit.

**Les vrais libellés clients** remplacent « Client 7 » sans toucher au code :
`data/tarification/correspondance_clients.csv` (`client;libelle`, UTF-8 ou
cp1252, `;` ou `,`), à télécharger pré-rempli depuis l’écran, à compléter dans
Excel et à redéposer — ou au crayon, ligne par ligne, dans la liste des offres.
Un libellé identique à un client du classeur d’activité rattache l’offre à son
dossier d’appel d’offres ; un rattachement manuel (`rattachements.json`) prime
et se défait d’un clic. `correspondance_expertises.csv` (`expertise;dimension;valeur`, par
exemple `Credit IG;sous_classe_actifs;Crédit investment grade`) redéfinit,
expertise par expertise, le rapprochement avec les classes d’actifs de
l’activité.

---

## Architecture

| Fichier | Rôle | Dépendances |
|---|---|---|
| `core.py` | Configuration, lecture, normalisation, **couche métrique**, statistiques, thème, figures Plotly, moteur de constats | pandas, numpy, plotly |
| `server.py` | API et service de l’interface : périmètre, analyse, dossiers, rapport, branchement | FastAPI, uvicorn |
| `static/` | L’interface : HTML, CSS, modules JavaScript — aucune étape de construction | — |
| `export.py` | Le rapport HTML autonome | plotly |
| `tarification.py` | Le moteur tarifaire : lecture du classeur des grilles, contrôle des anomalies, calcul progressif, corridors par tranche, croisement avec l’activité | pandas |
| `static/js/tarif.js` | Le même calcul en JavaScript, pour simuler sans aller-retour serveur ; sa parité avec Python est testée | — |
| `static/js/simulateurs.js` | Les simulateurs du gérant : valeur du mandat sur sa durée, leviers de négociation, chance de gain selon le prix ; testés sous node par `python tarification.py` | — |
| `static/js/escalier.js` | L’escalier des frais : la grille dessinée telle que le client la paie, manipulable et animée (SVG) | — |
| `assets/` | Inter et EB Garamond (SIL OFL) ; emplacement du logo officiel | — |

`core.py` n’importe pas FastAPI : il se teste et se réutilise seul (notebook,
script, tâche planifiée). Il produit un objet `Analysis` — indicateurs, blocs
d’analyse, constats — que le serveur et le rapport consomment **à l’identique**,
et il calcule lui-même la charge utile de la vue d’ensemble (`carnet_detaille`,
`resume_situation`) que l’un sert par HTTP et que l’autre imprime. Un chiffre
affiché à l’écran est le même que dans le rapport, par construction ; les
constantes que l’écran doit connaître (ordre des indicateurs, seuil d’attente
longue, longueur des listes) lui sont transmises par `/api/meta`, jamais recopiées.

**Couche métrique.** Chaque indicateur est défini une fois, dans une fonction
documentée (`carnet`, `taux_succes_rfp`, `aum_gagne`, `cadence_mensuelle`,
`croissance`, `identites_carnet`…). Deux graphiques ne peuvent pas compter la
même chose différemment.

**Ajouter une analyse** : écrire `_bloc_xxx(df, mensuel, stats)` qui renvoie un
`Block`, puis l’inscrire dans `_CONSTRUCTEURS`. Elle apparaît automatiquement
dans l’écran de sa section **et** dans le rapport. Un `Block` dont la figure est
`None` **est** un tableau : il s’affiche déplié. Un bloc qui échoue est signalé
sans interrompre l’écran.

**L’état vit dans l’URL** : `?ecran=rfp&periode=2025&pays=Suisse&q=leman`. Un
lien copié rouvre le même écran, le même périmètre, la même fiche ; le bouton
« précédent » fonctionne.

---

## Les écrans

**Situation** — la lecture hebdomadaire de la direction, sans rien ouvrir
d’autre. Une phrase calculée : combien d’appels d’offres sont ouverts, pour quel
encours, combien en rédaction et combien en attente de décision ; puis, sur la
période, les mandats remportés et perdus avec leurs encours. Dessous, dans
l’ordre : **la liste des appels d’offres ouverts** (client, classe d’actifs,
état, étape atteinte, jours d’attente, suivi commercial, encours — le plus gros
encours d’abord), le carnet des cinq états avec ses identités arithmétiques,
les indicateurs (succès, encours remporté, perdu, en jeu, présélection, oral,
délais), le chemin des appels d’offres (reçus → Step 1 → Step 2 → Oral →
remportés, effectifs et encours à chaque marche),
ce qui a changé, les listes nommées des gagnés et perdus, **l’année par année**
(une ligne par exercice du périmètre : reçus, tranchés, taux de succès, encours,
délai — triable d’un clic sur l’en-tête), **les classes d’actifs** (ce que
chacune reçoit, remporte et porte d’encours, triable de même), la décomposition
de l’activité et les huit derniers trimestres.

La barre de périmètre propose les douze, vingt-quatre et trente-six derniers
mois, **chaque exercice présent dans les données**, et tout l’historique. Le
rapport est produit sur le périmètre affiché.

**Analyses** — six questions, une à la fois : Activité, Appels d’offres, Due
diligence, Encours & gains, ESG, Diagnostic. La page Appels d’offres ouvre sur
la liste des dossiers ouverts et le chemin des étapes, puis le taux de succès
par classe d’actifs, par segment de client, par consultant et par commercial.
Chaque analyse porte sa phrase, sa figure, sa note de méthode et son tableau
jumeau. Un clic sur une catégorie recalcule tout le périmètre.

**Tarification** — le simulateur de prix d’appels d’offres, reconstruit depuis
le rapport Power BI d’origine puis repensé du point de vue du gérant
(inventaire, arbitrages et décisions :
[`docs/simulateur-tarification.md`](docs/simulateur-tarification.md)). Les
réglages : l’expertise, la taille du mandat, sa durée et la croissance supposée
de l’encours ; les offres comparées se résument en une ligne qui s’ouvre sur ses
filtres. Puis, dans l’ordre où l’on se pose les questions :

1. **La grille**, en haut, éditable dans le tableau : pour chaque tranche, la
   part d’encours, le taux, ce que l’encours du client y met, les frais qu’elle
   produit, et sa place face au marché sur la même part (sous le plus bas, sous
   ou au-dessus de la médiane…). Couper une tranche en deux, en retirer une,
   partir de la grille type, de la référence de l’expertise ou d’une offre passée.
2. **L’escalier des frais** : chaque marche est une tranche (largeur = part
   d’encours, hauteur = taux), la surface pleine est ce que paie le client, la
   bande grise ce que le marché facturait. Tout se tire à la souris ou au
   clavier ; « Faire grandir le mandat » fait courir l’encours et remplit
   l’escalier.
3. **Face au marché** : le rang parmi les offres passées à la taille du client,
   et la dégressivité à toutes les tailles.
4. **Le prix et la chance de gagner** : toutes les décisions passées, ramenées à
   leur écart au prix du marché, donnent une chance de gain selon le prix ; le
   revenu espéré (chance × frais sur la durée) désigne le prix qui rapporte le
   plus. Quand les décisions ne suffisent pas à mesurer l’effet du prix,
   l’écran le dit et retient une hypothèse, modifiable.
5. **Ce que rapporte le mandat** : les frais année après année, et ce que la
   dégressivité rend au client quand l’encours grossit.
6. **Négocier sans se tromper de levier** : pour un effort demandé (en pb de
   taux moyen), le coût sur la durée d’une remise uniforme, d’une baisse de la
   tranche où tombe l’encours, de la première tranche ou des seuils ; chacun
   s’applique d’un clic.
7. Les expertises aux tailles de référence (avec le rang de votre grille), les
   offres passées — chacune ouvre **sa fiche** : grille, courbe, rang,
   anomalies, comparables, autres offres du client et, croisé avec le classeur
   d’activité, son dossier d’appel d’offres — et la qualité du classeur.

**Dossiers** — la recherche plein texte, la liste, et la fiche d’un dossier avec
les autres dossiers du même client.

**Données** — la source branchée, le dépôt d’un classeur, la correspondance des
colonnes, la qualité de la lecture ; et, à part, le classeur des grilles
tarifaires et la correspondance des libellés clients.

**Le champ de commande** (`Ctrl K`, `⌘ K` sur Mac, ou `/`) comprend le
vocabulaire des données : « Suisse 2025 », « gagnés obligataire », « Bellecour »,
« janvier 2026 », « 2019 ». Ce qu’il a compris est **écrit en toutes
lettres avant d’agir** — aucune phrase n’est produite par un modèle de langage,
c’est un rapprochement de vocabulaire, et il se lit.

---

## Définitions qui engagent

- **Famille** — RFP d’un côté, toute la due diligence de l’autre : les deux
  valeurs de la colonne `Type` du classeur. Il n’existe pas de type plus fin,
  ni à l’écran, ni dans le rapport.
- **Résultat** — n’existe **que** pour un appel d’offres. Une due diligence ne se
  gagne pas : son résultat est « sans objet », pas « perdu ».
- **Carnet** — les cinq états d’un appel d’offres. « En rédaction » et « en
  attente de décision » partagent le résultat « en attente » mais ne disent pas la
  même chose : la réponse se produit d’un côté, se décide de l’autre.
- **Taux de succès** — gagnés / (gagnés + perdus). Les dossiers non tranchés sont
  exclus du dénominateur ; les compter comme des échecs fabriquerait un
  effondrement sur les périodes récentes.
- **Encours** — la colonne `Volume` du classeur, en M€. **Encours remporté** :
  celui des appels d’offres gagnés, rattaché à l’année de réception du dossier.
  **Encours perdu** : celui des appels d’offres perdus. **Encours en jeu** :
  celui des dossiers encore ouverts — un pipeline, pas une collecte acquise.
- **Chemin des appels d’offres** — `Step_1` (dossier remis), `Step_2`
  (présélection), `ORAL_RFP` (soutenance orale), puis le résultat. Un dossier
  en attente compte dans les étapes qu’il a franchies, jamais dans les
  remportés. Le taux de passage se lit d’une marche à la suivante.
- **Délai de traitement** — jours **calendaires** entre réception et envoi, comme
  au comité, dans les indicateurs comme dans les tableaux par dimension. Le
  respect du délai cible se mesure, lui, en jours ouvrés, et les modèles du
  diagnostic le disent quand ils raisonnent en jours ouvrés.
- **Relance** — un appel d’offres remis sans décision depuis plus de quatre mois
  (`JOURS_RELANCE`), ou un dossier en cours au-delà de son délai cible.
- **Cadence** — dossiers **terminés** par mois : la capacité de production de
  l’équipe, à distinguer de la charge qui lui arrive.
- **Croissance sur N ans** — dernière année civile **complète** contre celle d’il
  y a N ans. L’année en cours est exclue.
- **Limite de lecture** — les clients tranchent plusieurs mois après l’envoi. Sur
  une période récente, le taux de succès et l’encours remporté sont mécaniquement
  sous-évalués, l’encours en jeu surévalué. L’avertissement est affiché sous les
  indicateurs.

Les **constats** sont calculés, jamais rédigés d’avance : chaque phrase provient
d’une fonction analytique et disparaît si la donnée ne permet pas de l’établir.
Aucun chiffre n’est produit par un modèle de langage.

---

## Design

**Une couleur.** Le bleu de la maison, `#0B2545`, et ses tons — chaque autre
valeur est un mélange de ce bleu et du blanc, produit par `core.teinte()`. Ni or,
ni vert / rouge, ni palette catégorielle. Les séries se distinguent par le ton,
la texture et le libellé direct ; un état s’écrit, il ne se colore pas. Une
variation se lit à son signe, à sa flèche et au mot qui l’accompagne.
`python core.py` vérifie qu’aucune couleur du produit ne sort de cette droite.

**Un système, deux surfaces.** Espacement, échelle typographique, rayons et
courbes de mouvement sont définis une seule fois dans `core.py` et émis en
variables CSS par `core.jetons_css()`. L’interface les lit par `/jetons.css`, le
rapport les embarque : l’écran et le rapport ne peuvent pas diverger.

**Typographie.** EB Garamond porte la voix — les phrases calculées et les grands
chiffres ; Inter porte l’instrument — libellés, tableaux, marges. Chiffres
tabulaires partout où des valeurs s’alignent. Les deux polices sont sous licence
SIL OFL et embarquées : même rendu hors ligne et dans un rapport transmis par
courriel.

**Contraste.** Sous 18 px, l’encre est à 72 % au minimum (6,3:1 sur blanc) ; les
tons plus clairs ne portent que des traits, des filets et des aplats de figure.

**Mise en page.** Une colonne de lecture et une marge qui parle : la définition
est à côté du chiffre, pas derrière un survol. Aucune carte, aucune ombre,
aucun dégradé : des filets d’un pixel et du vide. `prefers-reduced-motion`
coupe tout mouvement.

**La marque.** Le logo officiel, ou rien. Le dépôt ne contient aucun tracé
reconstruit : sans fichier de la charte, l’application et le rapport écrivent
le nom de la maison en toutes lettres. Pour afficher le logo, déposer les
fichiers officiels dans `assets/` : `logo.svg` (emblème et logotype, barre de
l’application), `embleme.svg` (favicon) et `logo-empile.svg` (couverture du
rapport), de préférence en `fill="currentColor"` pour qu’ils prennent le bleu
de la maison. Ils sont pris en compte au démarrage suivant, partout.

---

## Rapport HTML

Le bouton « Rapport » produit un fichier unique reprenant le périmètre affiché :
couverture, indicateurs, constats calculés, les sections navigables, leurs
analyses interactives, leurs tableaux et une annexe méthodologique. Plotly et
les polices y sont embarqués : il s’ouvre d’un double-clic, sans Python, sans
serveur, sans réseau.

C’est le document **diffusé**, et il dit exactement ce que dit l’application :
sa page « Vue d’ensemble » est l’écran Situation, bloc pour bloc — même phrase
d’ouverture, même tableau des appels d’offres ouverts, même carnet, mêmes
indicateurs dans le même ordre, même chemin, mêmes listes,
même année par année, mêmes classes d’actifs. Les pages suivantes sont les
écrans d’analyse. Rien n’est réservé à l’écran, rien n’est réservé au document :
`python core.py` le vérifie. Le rapport suit le périmètre choisi dans
l’application — chaque exercice s’y ouvre un par un — et ses tableaux « Année
par année » et « Classes d’actifs » se trient d’un clic sur l’en-tête, comme à
l’écran. Il se lit sur ordinateur : aucune mise en page mobile.

---

## Données de démonstration

Le jeu par défaut est **explicitement synthétique** — la source est libellée
comme telle dans le pied de page, sur l’écran « Données » et dans l’annexe du
rapport. Il est produit **exactement au format du classeur du pôle** (mêmes
en-têtes, mêmes vocabulaires Done / Won / Instit. / Yes), de sorte que la chaîne
de lecture exercée par la démonstration est celle qui lira le vrai fichier. Sa
forme reproduit celle d’un pôle réel : due diligence multipliée par quatre en
dix ans à effectif RFP constant, creux d’août, encours très concentré sur
quelques mandats. Aucun client nommé n’existe.

Les volumes annuels sont paramétrés de sorte que les trois indicateurs de
croissance tombent sur ceux que publie le pôle : **+49 % sur 3 ans, +149 % sur
5 ans, +158 % sur 10 ans**. `python core.py` vérifie cette concordance à chaque
exécution — c’est ainsi que les définitions de métriques sont validées, et non
par leur seul intitulé.
