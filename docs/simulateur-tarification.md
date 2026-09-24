# Simulateur de tarification — inventaire, arbitrages, décisions

Ce document a été écrit **avant** la première ligne de code du simulateur. Il
dépouille le rapport Power BI d'origine, valide la structure du classeur source,
tranche angle par angle, puis consigne les décisions de construction.

---

## 0. Les sources, et ce qui manque

| Source | Contenu | Usage |
|---|---|---|
| `Presentation 1 (1).pdf` | 5 pages : 4 écrans Power BI + la structure du classeur | Base de l'inventaire |
| `Presentation 1.pptx` (supprimé du dépôt, récupéré dans l'historique git, commit `69a0aaf`) | Les mêmes 5 captures, en meilleure résolution | Lecture fine des valeurs, transcription de la page 5 |
| `Années d'expérience - FR_EN pour Qvidian.xlsx` | Suivi des merge codes Qvidian et des années d'expérience du personnel | **Hors sujet.** Ce n'est pas le classeur tarifaire. Non utilisé. |

**Le classeur tarifaire décrit en page 5 n'est pas dans le dépôt.** Le seul
classeur déposé est un suivi Qvidian sans rapport avec les grilles. Ce n'est pas
bloquant : la page 5 donne les 11 colonnes, leurs types et 48 lignes lisibles en
haute résolution. Ces 48 lignes (23 clients anonymisés) sont transcrites telles
quelles et servent de jeu de démonstration. Le vrai classeur se dépose ensuite
depuis l'écran « Données », sans toucher au code.

---

## 1. Inventaire de l'existant, page par page

### Page 1 — « Frais HT »

| Élément | Type Power BI | Contenu observé |
|---|---|---|
| Titre « Frais HT » | Texte | Tous les montants sont hors taxes |
| Bandeau gris « OA - DIVERSIFIED » | Carte / segment | Expertise (`Sub_asset_class`) du client sélectionné |
| « Annee » | Segment | Une seule valeur visible (2022) : filtrée par le client choisi |
| « Client_Prospect » | Segment | Une seule valeur visible (GAGNÉ) : filtrée par le client choisi |
| « Prospect/Client » | Segment liste, sélection simple | Noms de clients (libellés réels dans Power BI) |
| « Grille proposée » | Table | `Quantite_Minimum`, `Quantite_Maximum`, `Frais_par_seuil` : 0 → 100 à 0,12 % |
| « Montant investi par le client sélectionné (M€) » | Carte | 75 |
| « Taux moyen du client sélectionné » | Carte | 0,12 % |
| « Sélectionner un montant (M€) » | Segment, 0 à 55 par pas de 5 | 25 sélectionné |
| « Taux moyen en fonction du montant sélectionné » | Carte | 0,12000 % (5 décimales, contre 2 sur la carte voisine) |

Angle d'analyse : **la grille d'un client, et le taux qu'elle produit à son
encours et à un encours choisi.**

### Page 2 — « Simulation de frais »

| Élément | Type | Contenu observé |
|---|---|---|
| Table de simulation | Table figée | Tranche 1 : 0 → 50 à 0,12 % · Tranche 2 : 50 → 100 à 0,09 % · Tranche 3 : 100 → 150 à 0,07 % · Tranche 4 : 150 → 200 à 0,05 % |
| « Sélectionner un montant (M€) » | Segment par pas de 5 | Valeur sélectionnée hors de la zone visible |
| « Taux moyen obtenu en fonction de l'encours sélectionné » | Carte | 0,093 % |
| « Tranche » | Petit segment | Tranche 1 à 4 : active ou masque des paliers |

Angle d'analyse : **simuler une grille type et lire le taux moyen qu'elle
produit.** La grille n'est pas modifiable dans le rapport : Power BI ne permet
pas d'éditer une table en place, il faut changer la source.

### Page 3 — « Moyenne de frais par expertise »

| Élément | Type | Contenu observé |
|---|---|---|
| Tuiles d'expertise | Segment tuiles | 12 expertises : Assurantiel, Climate, Convertibles, Credit IG, Diversifié, Equity, Global Credit, OA - Diversified, OA - ETF, OA - Gestion conseillée, OA - GSM, OA - GSM ETF |
| Matrice | Matrice | Lignes : expertise ; colonnes : montants 5, 10, … 95 par pas de 5 ; cellules : taux moyen (Assurantiel : 0,22 % à 5 M€ → 0,15 % à 90 M€) |
| « Evolution du taux proposé par expertise en fonction des montants » | Courbe | Abscisse 0 → 500 M€, ordonnée « Taux moyen par expertise » : plateau à ~0,215 % jusqu'à 25 M€, puis chute continue jusqu'à **0,045 % à 500 M€** |

Angle d'analyse : **la dégressivité moyenne d'une expertise selon la taille du
mandat.**

### Page 4 — « Visualisation des frais proposés »

| Élément | Type | Contenu observé |
|---|---|---|
| Tuiles d'expertise | Segment tuiles | Credit IG sélectionné |
| « Annee » | Segment | 2025, 2024, 2023, … |
| « Client_Prospect » | Segment | EN COURS, GAGNÉ, PERDU |
| « Client » | Segment liste | Noms de clients |
| Nuage de points | Nuage | Abscisse : montant (M€, curseur de plage) ; ordonnée : taux moyen (0 → 0,50 %, curseur de plage) ; un point par client ; **une couleur par client** (15 couleurs en légende) |

Observations : deux points superposés à 100 M€ ; un point à **0,00 %** à 70 M€,
anomalie affichée sans signalement.

Angle d'analyse : **comparer les offres entre elles, taille contre prix.**

### Page 5 — Structure du classeur source

| Colonne | Type observé | Rôle |
|---|---|---|
| `Client` | Texte, anonymisé « Client 1 » … « Client 23 » | Dimension catégorielle pure |
| `Quantite_Minimum` | Nombre (M€) | Borne basse de la tranche |
| `Quantite_Maximum` | Nombre (M€) ; certaines cellules surlignées en jaune | Borne haute de la tranche |
| `Frais_par_seuil` | Pourcentage (0,19 %) | Taux appliqué **dans** la tranche |
| `Commissions de surperformance` | Nombre, toujours 0 | Commission de performance |
| `Volume1` | Nombre (M€), répété sur chaque ligne du client | Encours du mandat |
| `Annee` | **Tantôt texte (triangle vert), tantôt nombre** | Année de l'offre |
| `Sub_asset_class` | Texte, casse variable (« Global credit » / « GLOBAL CREDIT ») | Expertise |
| `Client_Prospect` | Gagné / Perdu / En cours | Issue de l'appel d'offres |
| `Public_Privé` | Privé / Public | Nature du client |
| `TVA` | Toujours « HT » | Régime des montants |

**Granularité : une ligne par tranche.** Une grille = les lignes d'un même
client pour une même année et une même expertise. Les 48 lignes lisibles
couvrent 23 clients, de 1 à 7 tranches chacun.

---

## 2. La logique du prix, déduite et prouvée

### Le calcul par tranches

Les frais se calculent comme un barème progressif : chaque taux ne s'applique
qu'à la part de l'encours qui tombe dans sa tranche.

```
Frais(A)      = Σ  taux_k × max(0, min(A, max_k) − min_k)
Taux_moyen(A) = Frais(A) / A
```

**Preuve par la page 2.** Avec la grille 0,12 / 0,09 / 0,07 / 0,05 %, le taux
moyen vaut 0,093 % pour un encours de **150 M€** exactement :
(50 × 0,12 + 50 × 0,09 + 50 × 0,07) / 150 = 14 / 150 = 0,0933 %. À 140, 145, 155
ou 160 M€ on obtient 0,095, 0,094, 0,092, 0,091 % : la valeur est unique.
Un barème « à la marche » (tout l'encours au taux de sa tranche) donnerait 0,07
ou 0,05 %. L'hypothèse progressive est la seule qui tienne.

**Preuve par la page 1.** Grille à tranche unique 0 → 100 à 0,12 % : 0,12 % à
75 M€ comme à 25 M€.

### Les mesures implicites

| Mesure | Définition déduite |
|---|---|
| Montant investi | `Volume1` du client |
| Taux moyen du client | `Taux_moyen(Volume1)` de sa grille |
| Taux moyen à un montant | `Taux_moyen(A)` pour le montant du segment |
| Taux moyen par expertise | Moyenne simple, client par client, des `Taux_moyen(A)` des grilles de l'expertise — non pondérée par l'encours |
| Paramètre « Montant » | Série 0 → 500 M€ par pas de 5 |

### Un défaut du modèle d'origine : la dernière tranche bornée

Power BI traite `Quantite_Maximum` de la dernière tranche comme un plafond : la
part d'encours au-delà ne paie rien. Trois indices concordants :

1. **La courbe de la page 3 s'effondre à 0,045 % à 500 M€**, alors qu'aucune
   grille Assurantiel ne descend sous 0,11 % sur sa dernière tranche. Sur les
   quatre grilles Assurantiel lisibles, la moyenne à 500 M€ vaut 0,059 % avec un
   plafond, 0,155 % sans plafond.
2. **Client 23** : encours 300 M€, grille unique 0 → 200 à 0,14 %. Avec plafond,
   il paierait 0,093 % ; le contrat dit 0,14 %.
3. **Les cellules jaunes** marquent toutes des plafonds de dernière tranche, et
   six grilles ont un dernier plafond égal à leur encours (clients 7, 8, 10, 11,
   21, 22) : le plafond est l'endroit où la saisie s'arrête, pas une limite
   contractuelle.

**Décision : la dernière tranche d'une grille s'applique au-delà de son
plafond.** C'est la seule lecture commerciale possible, et elle corrige la
courbe de la page 3.

### Anomalies observées dans l'échantillon

| Anomalie | Où | Traitement |
|---|---|---|
| `Annee` tantôt texte, tantôt nombre | Clients 1 à 6 et 14 | Lue dans les deux cas |
| Plafond de dernière tranche inférieur à l'encours | Client 23 | Tranche ouverte, signalée |
| Tranches consécutives au même taux | Client 7 (7 tranches, 3 taux distincts) | Calcul inchangé, signalé « paliers sans effet » |
| Taux moyen à 0,00 % | Page 4, un point à 70 M€ | Signalé, exclu des fourchettes |
| Casse variable de l'expertise | « Global credit » / « GLOBAL CREDIT » | Libellés rapprochés sans casse ni accent |

---

## 3. Arbitrages, angle par angle

| # | Élément d'origine | Arbitrage | Justification |
|---|---|---|---|
| 1 | Grille d'un client (p1) | **Gardé, enrichi** — dans la fiche de l'offre | La grille reste la pièce maîtresse ; la fiche y ajoute frais en euros et position dans le marché. |
| 2 | Montant investi (p1) | **Gardé** — dans la fiche | Donnée d'entrée du prix, indispensable. |
| 3 | Taux moyen du client (p1) | **Gardé, corrigé** | Une seule précision partout : 0,12 % et 0,12000 % côte à côte faisaient douter. |
| 4 | Taux moyen à un montant choisi (p1, p2) | **Reformulé** — saisie libre de la taille du mandat | Un segment à pas de 5 limité à 55 M€ ne répond pas pour 73 ou 395 M€. |
| 5 | Segments Année et Statut (p1, p4) | **Gardés** — filtres du simulateur | Comparer à ce qui a été gagné, ou à ce qui est récent, reste la question centrale. |
| 6 | Liste Prospect/Client (p1, p4) | **Reformulée** — liste des offres, libellés par correspondance | Les libellés sont anonymisés ; la liste devient un index de fiches cherchable. |
| 7 | Table de simulation figée (p2) | **Reformulée** — grille éditable en place, recalcul immédiat | C'est ce que Power BI ne sait pas faire, et la demande non négociable. |
| 8 | Carte « taux moyen obtenu » (p2) | **Gardée** — résultat en direct, avec frais en euros | Le taux seul cache l'enjeu : 0,093 % de 150 M€, ce sont 140 k€ par an. |
| 9 | Segment Tranche (p2) | **Remplacé** — ajouter ou retirer une ligne de la grille | Son seul rôle était d'activer des paliers ; l'édition directe le rend inutile. |
| 10 | Tuiles d'expertise (p3, p4) | **Gardées** — avec le nombre d'offres de chaque expertise | Premier filtre du métier ; le compte dit si la comparaison est solide. |
| 11 | Matrice expertise × montant (p3) | **Reformulée** — tableau aux tailles de référence, médiane, moyenne et fourchette | Dix-neuf colonnes de 0,22 % à 0,15 % ne se lisent pas ; la courbe porte la forme, le tableau les repères. |
| 12 | Courbe par expertise (p3) | **Gardée, corrigée, enrichie** — dernière tranche ouverte, fourchette haute et basse autour | La courbe d'origine s'effondrait vers zéro ; la fourchette dit ce que la moyenne masque. |
| 13 | Moyenne simple entre clients (p3) | **Gardée** — en ligne pointillée et dans le tableau, la médiane devient la référence | Un mandat de 395 M€ et un de 37 M€ pèsent pareil dans une moyenne ; la médiane résiste mieux aux grilles atypiques. |
| 14 | Nuage montant × taux (p4) | **Gardé, fusionné** — sur la courbe, points cliquables vers la fiche | Quinze couleurs de client ne se distinguent pas ; l'issue gagné, perdu, en cours se lit par la forme. |
| 15 | Curseurs de plage (p4) | **Remplacés** — zoom de la figure | Même usage, sans deux commandes de plus. |
| 16 | Structure du classeur (p5) | **Gardée à l'identique** — contrat d'import, en-têtes reconnus avec tolérance | Le vrai classeur doit se déposer tel quel. |
| 17 | « Frais HT » et colonne TVA | **Gardés** — montants hors taxes, régime affiché | Le fichier ne donne aucun taux de TVA : on n'en invente pas. |
| 18 | Commissions de surperformance | **Gardées** — lues et affichées dans la fiche si non nulles | De nature différente des frais de gestion : jamais additionnées au taux. |
| 19 | Dernière tranche plafonnée | **Corrigée** — tranche ouverte | Voir § 2 : client 23 et la courbe de la page 3. |

### Ajouts rendus possibles par la donnée

| # | Ajout | Justification |
|---|---|---|
| A1 | Fourchette déjà pratiquée **pour chaque tranche** de la grille simulée : taux minimum, médian et maximum que les offres passées appliquaient sur la même part d'encours | Répond à « le prix de la fourchette s'adapte » : changer les bornes d'une tranche recalcule le marché de cette tranche. |
| A2 | Fourchette haute et basse du taux moyen à la taille du mandat, avec gagnés et perdus distingués | « Ce qui a déjà été fait » à la taille qui compte, en une jauge. |
| A3 | Position de l'offre : centile, écart à la médiane des offres gagnées | Dit en une phrase si l'on est cher. |
| A4 | Frais annuels en euros hors taxes | Le chiffre que lit la direction. |
| A5 | Fiche d'offre cliquable, croisée avec le classeur d'activité | Grille, courbe, position, offres comparables et dossier d'appel d'offres rattaché. |
| A6 | Rattachement manuel d'une offre à un dossier d'activité | Tant que les libellés sont anonymisés, le lien se fait en un clic et se conserve. |
| A7 | Libellés clients par fichier de correspondance ou édités dans l'écran | Les vrais noms remplacent « Client 7 » sans toucher au code. |
| A8 | L'escalier des frais, manipulable et animé (il remplace le relief 3D de la première version) | Voir § 5. |
| A9 | Point de départ au choix : grille passée ou grille de référence de l'expertise | On ne part jamais d'une feuille blanche. |
| A10 | Filtre Public / Privé | Présent dans le classeur, absent des visuels d'origine. |
| A11 | Journal qualité du classeur | Chaque anomalie de § 2 est nommée, jamais corrigée en silence. |
| A12 | Export de la grille simulée | La grille part dans la réponse à l'appel d'offres. |

---

## 4. Décisions de construction

**Emplacement.** Un écran de premier niveau « Tarification », entre « Analyses »
et « Dossiers ». Le simulateur est un outil de préparation de l'appel
d'offres, pas une analyse de plus ; il a ses propres filtres, et le bandeau de
périmètre de l'activité s'efface sur cet écran. Le rapport HTML n'en contient
pas : c'est un outil de travail, et la parité écran/rapport porte sur
l'analyse.

**Stack.** Aucune dépendance ajoutée, ni en Python ni dans le navigateur : les
figures sont en SVG natif. Le calcul du prix existe deux fois, en Python pour
l'historique et les fiches, en JavaScript pour l'édition en direct ; l'auto-test
du moteur exécute la version JavaScript et exige des résultats identiques, puis
contrôle les simulateurs (§ 5).

**Correspondance des clients.** Fichier externe
`data/tarification/correspondance_clients.csv` (colonnes `client`, `libelle` ;
`;` ou `,`, UTF-8 ou cp1252, CSV ou Excel au dépôt), lu à chaque requête, écrit
par l'écran quand on édite un libellé au crayon, téléchargeable pré-rempli et
redéposable. Les rattachements manuels à un dossier vivent à part, dans
`rattachements.json`, indexés par numéro de dossier (stable d'un import à
l'autre, contrairement à un rang de ligne). « Client 7 » n'est jamais
interprété : c'est une clé, rien de plus.

**Croisement avec l'activité.** Une offre se rattache à un dossier d'appel
d'offres par ordre de priorité : numéro de dossier enregistré dans
`rattachements.json`, puis libellé client identique et même année. Sans lien,
la fiche propose des dossiers candidats par cercles qui s'élargissent à la
demande (même année et même famille d'expertise ; à un an près ; toutes
expertises), triés par proximité d'encours et de date, chaque candidat avec ses
raisons ; le choix reste humain, se conserve et se défait. Les expertises des deux classeurs ne partagent pas leur vocabulaire
(« Credit IG » contre « Crédit investment grade », « OA - ETF » contre
l'expertise « Open Architecture ») : une table de rapprochement par défaut est
fournie, et `data/tarification/correspondance_expertises.csv` la remplace.

**Import du vrai classeur.** Depuis l'écran « Données », section « Les grilles
tarifaires » (le bloc 07 de l'écran Tarification y mène directement). Le fichier va dans `data/tarification/`, hors de la détection
automatique du classeur d'activité. En-têtes reconnus sans casse ni accent, avec
synonymes ; types mixtes absorbés ; journal qualité affiché avant activation.
Un classeur qui ne se lit pas n'est jamais activé.

---

## 5. Deuxième version : les simulateurs du gérant

Consigne : des simulateurs plus pertinents, plus poussés et plus simples à lire ;
remplacer l'animation 3D par quelque chose de plus intuitif ; garder le tableau
en haut, en plus clair. Ce qui suit est la version livrée, et pourquoi.

### Le fil de l'écran

Un gérant qui chiffre un mandat se pose six questions, dans cet ordre ; l'écran
les suit, un bloc par question, chacun ouvert par une phrase qui y répond :

| Bloc | La question | Ce qui répond |
|---|---|---|
| 01 La grille | Quelle grille je propose ? | Le tableau, éditable |
| 02 L'escalier des frais | Comment le client la paie-t-il ? | La grille dessinée en marches, surface = frais |
| 03 Face au marché | Suis-je cher ? | Rang à la taille du client, dégressivité à toutes les tailles |
| 04 Le prix et la chance de gagner | À ce prix, est-ce que je gagne ? Quel prix rapporte le plus ? | Chance de gain et revenu espéré selon le prix |
| 05 Ce que rapporte le mandat | Combien sur sa durée ? | Frais année par année, avec croissance de l'encours |
| 06 Négocier | Le client demande un effort : où le céder ? | Coût sur la durée de chaque levier |

Les réglages communs sont réduits à ce qui change la réponse : l'expertise, la
taille du mandat, sa **durée** (5 ans par défaut, un cycle de revue de mandat
courant) et la **croissance** supposée de l'encours (+3 % par an par défaut,
marchés et flux nets confondus — une hypothèse affichée, jamais une prévision).
Les filtres des offres comparées (années, issue, nature du client) se replient
dans une ligne-résumé : « Comparé à 7 offres Credit IG · 2017 → 2025 · toutes
issues ▾ ».

### 01 — Le tableau, plus intuitif

- **Une colonne « Part d'encours »** (0 → [50]) remplace le couple De / À : le
  début se déduit, seule la fin se saisit.
- **« Chez ce client »** : une barre qui se remplit à mesure que l'encours du
  client occupe la tranche (« 50 M€ · pleine », « non atteinte »). C'est ce qui
  manquait pour comprendre un barème progressif sans explication.
- **Frais par tranche et leur part du total** (« 60 k€ · 43 % du total »).
- **Face au marché, en mots** : « sous le plus bas », « sous la médiane »,
  « au-dessus du plus haut »… en plus de la bande. Un état ne se lit jamais à la
  seule forme ou couleur.
- **Saisie à la française** : 0,12 comme 0.12 ; flèches pour le pas, Maj pour ×10.
- **✂ Couper** une tranche en deux au milieu (même taux des deux côtés), × pour
  la retirer, « + Ajouter une tranche au-delà ».
- **Sous le tableau, la phrase du gérant** : « Le million suivant paie 0,05 %
  (T4) : c'est le taux qui compte si le mandat grossit. Un encours doublé
  rapporterait +54 % de frais. »

### 02 — L'escalier des frais, à la place du relief 3D

Le relief 3D montrait une vraie information (le prix selon deux leviers), mais
il demandait un apprentissage : tourner, lire une hauteur en perspective,
décoder une couleur. Il est retiré, avec Three.js.

L'escalier montre **la grille elle-même telle que le client la paie** : chaque
marche est une tranche, sa largeur la part d'encours, sa hauteur le taux ; la
surface pleine à gauche du curseur est exactement la facture (largeur × hauteur
= M€ × % = frais), inscrite dans chaque marche. Derrière chaque marche, la bande
de ce que le marché facturait sur la même part ; en pointillé, le taux moyen, qui
descend à chaque marche franchie. C'est la définition même d'un barème
progressif, rendue visible ; elle se comprend sans légende.

- **Manipulation directe** : le haut d'une marche se tire pour changer son
  taux (pas de 0,005 point), son bord pour déplacer le seuil (pas de 5 M€), le
  curseur pour changer la taille du mandat. Le tableau suit, et inversement.
  Au clavier : Tab jusqu'à la poignée, puis les flèches.
- **L'animation qui porte l'information** : « Faire grandir le mandat » fait
  courir l'encours de zéro au bord de la figure en six secondes. La surface se
  remplit marche après marche, le compteur de frais monte, le taux moyen
  descend, et la lecture dit à chaque instant quel taux paie le million
  suivant. Puis le curseur revient à la taille choisie. Échelle figée pendant
  la course ; `prefers-reduced-motion` respecté.
- Les changements de grille se font en transition courte (260 ms) pour que
  l'œil voie ce qui bouge ; pendant un geste, aucune transition, pour que la
  marche suive la main.

### 04 — Le prix et la chance de gagner

La question que le rapport d'origine ne posait pas : **à ce prix, quelle chance
de gagner ?** Elle est estimée sur les décisions passées.

- Chaque offre gagnée ou perdue est ramenée à son **écart de prix** avec les
  autres offres de son expertise, à la taille de son propre mandat :
  x = ln(taux de l'offre / médiane des autres offres). Cet écart rend les
  expertises comparables, ce qui permet de mettre en commun toutes les
  décisions au lieu de n'en avoir que trois par expertise. Il faut au moins deux
  offres comparables pour situer une décision, et cinq décisions pour estimer.
- **Modèle** : régression logistique P(gagner) = σ(a + b·x), au maximum a
  posteriori, avec des a priori faibles (a autour du taux de succès observé,
  b autour de zéro) et une **contrainte économique** : b ≤ 0, être plus cher ne
  fait pas gagner. La bande à 90 % vient de l'approximation de Laplace.
- **Revenu espéré** = chance de gagner × frais sur la durée du mandat (bloc 05).
  Le « meilleur espoir » est le prix qui le maximise, la forme de la grille
  étant conservée (tous les taux suivent le même facteur) ; « Appliquer ce
  prix » l'écrit dans le tableau.
- **Honnêteté sur l'échantillon.** Dans les 11 décisions de l'échantillon, les
  offres gagnées ne sont pas moins chères que les perdues : le prix n'y
  départage rien, b vaut 0, et aucun prix « optimal » ne peut s'en déduire.
  Le réglage **Automatique** utilise donc vos décisions quand elles montrent un
  effet net du prix, et sinon une **hypothèse moyenne** (environ 12 points de
  chance perdus à +20 % au-dessus du marché), **écrite en tête du bloc**.
  « D'après vos décisions », « Faible », « Moyenne », « Forte » se choisissent
  à la main ; les hypothèses recalent le niveau sur le taux de succès observé.
  Avec le vrai classeur et plus de décisions, l'estimation prendra la main
  d'elle-même.
- Ce que le bloc ne prétend pas : le prix n'explique pas seul une issue (la
  gestion, la relation, le consultant pèsent autant). Il dit ce que le prix
  change, toutes choses égales par ailleurs, et c'est écrit dans ses repères.

### 05 — Ce que rapporte le mandat

Les frais de chaque année : l'année 1 est le mandat chiffré aujourd'hui, puis
l'encours croît au rythme des réglages. En hachuré au-dessus de chaque barre,
ce que le même encours paierait à un taux unique égal au taux moyen
d'aujourd'hui : l'écart est ce que la dégressivité rend au client quand il
grossit — l'argument commercial d'une grille à paliers, et son coût pour la
maison. Tableau jumeau dessous. Pas d'actualisation : sur cinq ans, elle
changerait les montants de quelques pour cent sans changer aucune décision, et
ajouterait un réglage à expliquer.

### 06 — Négocier sans se tromper de levier

Le client demande un effort, exprimé comme il l'est en négociation : tant de
points de base sur le taux moyen, à la taille actuelle (raccourcis : 1, 2, 5 pb,
« jusqu'à la médiane », « jusqu'au plus bas »). Le simulateur résout exactement
quatre façons de l'accorder, qui coûtent toutes la même chose la première
année :

- une remise sur tous les taux ;
- une baisse de la seule tranche où tombe l'encours du client ;
- une baisse de la seule première tranche ;
- des seuils abaissés d'un même facteur, taux inchangés.

Il les classe par **coût sur la durée du mandat**. L'enseignement, que le
tableau rend visible : baisser une tranche déjà pleine coûte un montant fixe
chaque année, alors qu'une remise uniforme se paie aussi sur chaque million de
croissance. Sans croissance, les leviers se valent, et l'écran le dit. Les
coûts sont calculés sur la grille **arrondie** qui s'appliquerait (seuils au
M€, taux au millième de point) : ce qui est annoncé est ce que « Appliquer »
écrit. Un levier impossible (taux négatif) est montré comme tel, jamais caché.

### Ce qui reste de la première version

Le rang face au marché (jauge et dégressivité, regroupées en un bloc), le
tableau des expertises (avec une ligne « Son rang » : le centile de votre grille
à chaque taille de référence, la lecture d'un consultant), les offres passées et
leurs fiches, le croisement avec l'activité, les libellés clients et le
classeur. Aucune fonctionnalité de la première version n'a disparu, sauf le
relief 3D, remplacé par l'escalier.

### Contrôles

`python tarification.py`, section 8, exécute les simulateurs sous node et
vérifie : la projection égale au calcul Python ; chaque levier tient la
concession demandée (au millième près après arrondi) et les leviers sont
classés par coût ; la remise uniforme coûte plus qu'une tranche pleine quand
l'encours croît, et autant sans croissance ; une sensibilité au prix connue est
retrouvée sur des décisions synthétiques ; la contrainte b ≤ 0 joue sur des
décisions « à l'envers » ; les 11 décisions de l'échantillon sont lues.
