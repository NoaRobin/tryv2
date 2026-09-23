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
| A8 | Relief 3D : taux moyen selon la remise et les seuils, à la taille du mandat | Voir § 4. |
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

**Stack.** Aucune dépendance ajoutée côté Python. Côté navigateur, Three.js
0.169 (licence MIT) est embarqué dans `static/vendor/` et servi hors ligne,
comme Plotly. Le calcul du prix existe deux fois, en Python pour l'historique
et les fiches, en JavaScript pour l'édition en direct et la 3D ; l'auto-test du
moteur exécute la version JavaScript et exige des résultats identiques.

**Relief 3D.** La nappe représente le taux moyen payé par le client, à la taille
de son mandat, selon deux leviers de négociation : une remise uniforme sur les
taux et un déplacement des seuils des tranches. Un graphique plat écrase cette
dimension : il montre la courbe d'une grille, jamais l'ensemble des grilles
voisines. La nappe dit d'un coup d'œil quel levier pèse le plus pour ce
client : près d'un seuil, déplacer les tranches change beaucoup le prix ; loin
dans la dernière tranche, seule la remise compte. La fourchette déjà pratiquée
teinte la bande de nappe qui s'y trouve ; les lignes d'iso-prix relient les
grilles équivalentes. Le point d'offre se déplace à la souris, et « Appliquer »
écrit la grille ajustée dans le tableau. Un balayage de la taille du mandat
anime la nappe : c'est la trajectoire du prix si le mandat grossit.

Détails qui portent le sens, fixés après essais à l'écran :

- *Couleur = rang.* La teinte n'encode pas la hauteur (la hauteur le fait
  déjà) mais le rang parmi les offres passées à cette taille : claire sous la
  plus basse, foncée au-dessus de la plus haute, graduée entre les deux par
  interpolation entre offres voisines — continue, donc sans marches d'escalier.
- *Parois.* Les quatre bords descendent au sol : la nappe se lit comme un
  volume, pas comme un plan qui flotte.
- *Axes auto-décrits.* Les graduations disent ce qu'elles sont (« remise
  −40 % », « taux actuels », « seuils ×2 ») au lieu d'un titre d'axe qui se
  chevauche avec elles ; l'axe des taux est au coin arrière gauche et disparaît
  en vue de dessus, où il n'a plus de sens. Quand la base de l'axe n'est pas
  zéro, elle est écrite dans son titre.
- *Échelle figée pendant le balayage.* Sinon la nappe serait recadrée à chaque
  image et ne descendrait pas à l'œil — l'information même du balayage.
- *Ce qu'on annonce est ce qu'on applique.* « Appliquer » arrondit les seuils au
  multiple de 5 M€ et les taux au millième de point ; le bandeau de la variante
  affiche le prix de cette grille arrondie, pas celui du point exact de la nappe.
- *Sobriété du mouvement.* Balancement lent au repos (amorti, suspendu dès
  qu'on reprend la main), rendu suspendu hors écran, `prefers-reduced-motion`
  respecté, repli textuel si WebGL manque — la phrase de sensibilité sous la
  nappe donne les mêmes chiffres.

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
