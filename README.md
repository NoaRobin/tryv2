# RFP & Due Diligence

Application interne de pilotage des appels d’offres et de la due diligence, pour

Elle répond en un écran à la question du matin — *où en sont les appels
d’offres ?* — puis laisse descendre, page après page, jusqu’au dossier
individuel. Un bouton produit le rapport HTML du périmètre affiché : un fichier
unique, ouvrable d’un double-clic, sans Python ni connexion.

---

## Démarrer

```bash
pip install -r requirements.txt
python server.py
```

L’application s’ouvre sur **http://localhost:8000**. Port occupé ?
`uvicorn server:app --port 8080`.

Elle démarre sur un jeu de **données de démonstration** (environ 1 700
questionnaires, 2014 → aujourd’hui). Rien à configurer pour la découvrir.

```bash
python core.py                # contrôle la chaîne de bout en bout
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

**La correspondance est tolérante** : casse, accents, espaces, tirets,
underscores et unités entre parenthèses sont ignorés. « Date de réception »,
`DATE_RECEPTION` et « date réception » désignent la même colonne. Les intitulés
courants sont reconnus (« Sub asset class », « Ticket (M€) », « ESG % »…) ; pour
en ajouter, compléter `COLUMN_ALIASES` en tête de `core.py`.

**Trois colonnes sont indispensables** : date de réception, type de demande,
statut. Toutes les autres sont facultatives — si `Expertise` manque, la page due
diligence perd son classement par expertise et conserve le reste. L’écran
« Données » dit précisément ce qui manque et ce qui a été écarté.

> Les données réelles ne rejoignent jamais le dépôt : `data/` est ignoré par
> git, à l’exception de son `.gitignore`.

**Vocabulaire métier**, paramétrable dans le bloc `[BRANCHEMENT PRINCIPAL]` de
`core.py` : familles (RFP / due diligence), normalisation des statuts, délais
cibles par type, seuil ESG, horizons de croissance.

---

## Architecture

| Fichier | Rôle | Dépendances |
|---|---|---|
| `core.py` | Configuration, lecture, normalisation, **couche métrique**, statistiques, thème, figures Plotly, moteur de constats | pandas, numpy, plotly |
| `server.py` | API et service de l’interface : périmètre, analyse, dossiers, rapport, branchement | FastAPI, uvicorn |
| `static/` | L’interface : HTML, CSS, modules JavaScript — aucune étape de construction | — |
| `export.py` | Le rapport HTML autonome | plotly |
| `assets/` | La marque (SVG vectoriels), Inter et EB Garamond (SIL OFL) | — |

`core.py` n’importe ni Streamlit, ni FastAPI : il se teste et se réutilise seul
(notebook, script, tâche planifiée). Il produit un objet `Analysis` — indicateurs,
blocs d’analyse, constats — que le serveur et le rapport consomment **à
l’identique**. Un chiffre affiché à l’écran est le même que dans le rapport, par
construction.

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

**Situation** — la lecture du matin. Une phrase calculée sur le périmètre, les
trois chiffres qui appellent une action, le carnet des cinq états (en rédaction,
en attente de décision, gagnés, perdus, sans suite) avec ses encours et ses
identités arithmétiques, les indicateurs, les dossiers à relancer, ce qui a
changé, la décomposition de l’activité, les huit derniers trimestres, et les
listes nommées.

**Analyses** — six questions, une à la fois : Activité, Appels d’offres, Due
diligence, Encours & gains, ESG, Diagnostic. Chaque analyse porte sa phrase, sa
figure, sa note de méthode et son tableau jumeau. Un clic sur une catégorie
recalcule tout le périmètre.

**Dossiers** — la recherche plein texte, la liste, et la fiche d’un dossier avec
les autres dossiers du même client.

**Données** — la source branchée, le dépôt d’un classeur, la correspondance des
colonnes, la qualité de la lecture.

**Le champ de commande** (`Ctrl K`, `⌘ K` sur Mac, ou `/`) comprend le
vocabulaire des données : « Suisse 2025 », « gagnés obligataire », « Bellecour »,
« à relancer », « janvier 2026 ». Ce qu’il a compris est **écrit en toutes
lettres avant d’agir** — aucune phrase n’est produite par un modèle de langage,
c’est un rapprochement de vocabulaire, et il se lit.

---

## Définitions qui engagent

- **Famille** — RFP d’un côté, toute la due diligence de l’autre. Le type fin
  (RFP / RFI / DDQ) reste disponible en filtre et à l’écran.
- **Résultat** — n’existe **que** pour un appel d’offres. Une due diligence ne se
  gagne pas : son résultat est « sans objet », pas « perdu ».
- **Carnet** — les cinq états d’un appel d’offres. « En rédaction » et « en
  attente de décision » partagent le résultat « en attente » mais appellent deux
  actions : produire d’un côté, relancer de l’autre.
- **Taux de succès** — gagnés / (gagnés + perdus). Les dossiers non tranchés sont
  exclus du dénominateur ; les compter comme des échecs fabriquerait un
  effondrement sur les périodes récentes.
- **Encours remporté** — encours des appels d’offres gagnés, rattaché à l’année
  de réception du dossier. **Encours en jeu** — celui des dossiers encore
  ouverts : un pipeline, pas une collecte acquise.
- **Délai de traitement** — jours **calendaires** entre réception et envoi, comme
  au comité. Le respect du délai cible se mesure, lui, en jours ouvrés.
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

**La marque.** `assets/logo.svg` (emblème et logotype), `assets/embleme.svg`
(les cinq flèches seules) et `assets/logo-empile.svg` (pour une couverture), en
`fill="currentColor"`. Ce sont des tracés vectoriels reconstruits : les sites de
la maison ne sont pas accessibles depuis l’environnement de développement.
Déposer les fichiers officiels de la charte sous ces trois noms suffit à les
remplacer partout.

---

## Rapport HTML

Le bouton « Rapport » produit un fichier unique reprenant le périmètre affiché :
couverture, indicateurs, constats calculés, les sections navigables, leurs
analyses interactives, leurs tableaux et une annexe méthodologique. Plotly et
les polices y sont embarqués : il s’ouvre d’un double-clic, sans Python, sans
serveur, sans réseau.

C’est le document **diffusé** : il parle le vocabulaire du comité — deux
familles, pas de types fins. Le détail RFI / DDQ reste à l’écran ; techniquement,
un `Block` ou un `Kpi` porte un drapeau `hors_rapport` et `export.py` l’écarte.

---

## Données de démonstration

Le jeu par défaut est **explicitement synthétique** — la source est libellée
comme telle dans le pied de page, sur l’écran « Données » et dans l’annexe du
rapport. Sa forme reproduit celle d’un pôle réel : due diligence multipliée par
quatre en dix ans à effectif RFP constant, creux d’août, délais corrélés au
volume de questions, collecte très concentrée sur quelques mandats. Aucun client
nommé n’existe.

Les volumes annuels sont paramétrés de sorte que les trois indicateurs de
croissance tombent sur ceux que publie le pôle : **+49 % sur 3 ans, +149 % sur
5 ans, +158 % sur 10 ans**. `python core.py` vérifie cette concordance à chaque
exécution — c’est ainsi que les définitions de métriques sont validées, et non
par leur seul intitulé.
