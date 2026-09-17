# =============================================================================
#  core.py — Moteur de données et d’analyse « RFP & Due Diligence »
# -----------------------------------------------------------------------------
#  RÈGLE D’ARCHITECTURE : ce fichier n’importe JAMAIS Streamlit.
#  Il ne fait que : charger → normaliser → enrichir → filtrer → calculer →
#  construire les figures Plotly. Il est donc testable et réutilisable seul
#  (notebook, script, API) et partagé à l’identique par server.py et export.py.
# =============================================================================
from __future__ import annotations

import base64
import datetime as dt
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

_PANDAS_2 = int(pd.__version__.split(".")[0]) >= 2

# =============================================================================
#  [BRANCHEMENT PRINCIPAL] — TOUT CE QUI SE PARAMÈTRE TIENT DANS CE BLOC
#  Brancher le produit sur les vraies données ne demande AUCUNE modification de
#  ce fichier : déposer le classeur dans le dossier data/ (ou le déposer depuis
#  l’écran « Données » de l’application), qui écrit data/branchement.json —
#  fichier, onglet, correspondance des colonnes. Voir plus bas la section
#  « BRANCHEMENT DES DONNÉES ».
#
#  Ce qui suit règle la LECTURE : les noms de colonnes attendus et leurs
#  synonymes, le vocabulaire des statuts et des types, les seuils métier.
#  Les colonnes absentes du fichier sont neutralisées : les analyses concernées
#  disparaissent, l’application ne casse pas.
# =============================================================================

# Données de démonstration : None = automatique (le classeur branché s’il
# existe, la démonstration sinon) ; True = toujours la démonstration ;
# False = jamais (erreur explicite si aucun classeur n’est branché).
USE_FAKE_DATA: bool | None = None
DATA_PATH = "données.xlsx"    # chemin par défaut si aucun branchement n’est écrit
SHEET_NAME = None             # onglet par défaut : le premier du classeur

# Les intitulés attendus sont ceux du classeur de suivi du pôle. À gauche le
# champ interne, à droite l’en-tête tel qu’il figure dans le fichier. La
# correspondance est tolérante (casse, accents, espaces, tirets, unités entre
# parenthèses) et COLUMN_ALIASES accepte les intitulés voisins.
COLUMN_MAP = {
    "numero": "Numero",                    # identifiant de la ligne
    "annee_source": "Année",               # année de rattachement (secours si la date manque)
    "mois_source": "Month",                # mois de rattachement, 1 à 12
    "date_reception": "Date de réception",
    "date_envoi": "Date de fin",           # remise, finalisation ou envoi de la réponse
    "client": "Client",
    "segment": "Segment",                  # fonds de pension, assureur, banque privée…
    "type_client": "Type de client",       # institutionnel, distributeur, international
    "pays": "Country",
    "consultant": "Consultant",            # cabinet intermédiaire ; « None » = aucun
    "analyste": "Writer",                  # rédacteur de la réponse
    "relecteur": "Reviewer",               # relecteur ou valideur
    "type_demande": "Type",                # RFP ou Due Diligence
    "montant_potentiel": "Volume",         # ENCOURS en jeu, en millions d’euros
    "etape_1": "Step_1",                   # étape 1 du processus RFP (binaire)
    "etape_2": "Step_2",                   # étape 2 du processus RFP (binaire)
    "oral": "ORAL_RFP",                    # soutenance orale (binaire)
    "statut": "Status",                    # Done, In progress, Cancelled
    "qvidian": "Qvidian Update",           # mise à jour de la base de contenus
    "resultat_brut": "Result",             # Won, Lost, NA
    "expertise": "Expertise",              # High Conviction, Open Architecture, Corporate
    "forme_juridique": "Legal form",       # fonds ouvert, mandat, fonds dédié
    "classe_actifs": "Asset class",
    "sous_classe_actifs": "Sub-asset class",
    "sri": "SRI",                          # dimension ISR : Yes / No
    "part_esg": "% ESG",                   # tranche ou pourcentage
    "fonds": "Reference fund",             # fonds ou solution de référence présentée
    "commercial": "Sales",                 # commercial responsable
    "langue": "Language",                  # FR, EN
    "nb_questions": "Nombre de questions", # facultatif : absent du classeur du pôle
}

# Intitulés voisins reconnus pour chaque champ, en plus de COLUMN_MAP. Sert
# quand un export ne porte pas exactement les mêmes en-têtes : inutile de
# modifier COLUMN_MAP, il suffit d’ajouter l’intitulé ici. La comparaison ignore
# casse, accents, espaces, tirets, underscores et unités entre parenthèses.
COLUMN_ALIASES: dict[str, list[str]] = {
    "numero": ["numero", "numéro", "n°", "no", "id", "identifiant", "ref", "reference"],
    "annee_source": ["annee", "année", "year", "exercice", "annee de rattachement"],
    "mois_source": ["mois", "month", "mois de rattachement"],
    "date_reception": ["date reception", "date de reception", "date réception", "reception",
                       "date demande", "date d’arrivee", "received date", "date in",
                       "date_reception", "date recue"],
    "date_envoi": ["date de fin", "date fin", "fin", "date d’envoi", "date envoi", "date reponse",
                   "date de réponse", "date rendu", "date de remise", "date limite", "deadline",
                   "date de cloture", "end date", "sent date", "date out", "date_envoi"],
    "client": ["nom du client", "client", "prospect", "contrepartie", "client name", "client_nom"],
    "segment": ["segment", "segment client", "categorie client", "catégorie", "secteur"],
    "type_client": ["type de client", "type client", "canal", "client type", "relation"],
    "pays": ["pays", "pays du client", "country", "juridiction", "zone"],
    "consultant": ["consultant", "cabinet", "conseil", "intermediaire", "gatekeeper"],
    "analyste": ["writer", "redacteur", "rédacteur", "analyste", "nom de l’analyste",
                 "rfp manager", "owner", "assigne a", "analyste_nom"],
    "relecteur": ["reviewer", "relecteur", "valideur", "relecture", "validation"],
    "type_demande": ["type", "type de demande", "type demande", "nature de la demande",
                     "nature", "request type", "categorie"],
    "montant_potentiel": ["volume", "encours", "encours en jeu", "encours potentiel",
                          "montant", "montant eur", "montant potentiel", "aum", "ticket",
                          "amount", "montant_eur", "assets"],
    "etape_1": ["step 1", "step1", "etape 1", "étape 1", "soumission"],
    "etape_2": ["step 2", "step2", "etape 2", "étape 2", "shortlist", "preselection"],
    "oral": ["oral rfp", "oral", "soutenance", "soutenance orale", "presentation", "pitch"],
    "statut": ["status", "statut", "statut du dossier", "etat", "état", "etat du dossier",
               "etat d’avancement", "avancement", "stage", "phase"],
    "qvidian": ["qvidian update", "qvidian", "mise a jour qvidian", "maj qvidian"],
    "resultat_brut": ["result", "resultat", "résultat", "outcome", "decision", "décision",
                      "won lost", "issue"],
    "expertise": ["expertise", "equipe de gestion", "pole de gestion", "desk",
                  "investment team", "capability", "type de gestion"],
    "forme_juridique": ["legal form", "legalform", "forme juridique", "vehicule", "véhicule",
                        "structure", "wrapper"],
    "classe_actifs": ["asset class", "assetclass", "classe d’actifs", "classe actifs", "classe"],
    "sous_classe_actifs": ["sub asset class", "subassetclass", "sous classe d’actifs",
                           "sous classe actifs", "sous classe", "sous categorie", "strategie",
                           "stratégie", "strategie detaillee"],
    "sri": ["sri", "isr", "socialement responsable", "label isr"],
    "part_esg": ["% esg", "esg %", "esg", "part esg", "pourcentage esg", "esg share",
                 "poids esg", "composante esg", "niveau esg"],
    "fonds": ["reference fund", "fonds de reference", "fonds de référence", "fonds", "fund",
              "nom du fonds", "produit", "solution"],
    "commercial": ["sales", "commercial", "vendeur", "charge d’affaires", "chargé d’affaires",
                   "responsable commercial", "sales rep", "relationship manager"],
    "langue": ["language", "langue", "langue de reponse", "langue de réponse"],
    "nb_questions": ["nombre de questions", "nb questions", "questions", "number of questions"],
}

# Seules ces trois colonnes sont indispensables ; le reste est optionnel.
REQUIRED_FIELDS: tuple[str, ...] = ("date_reception", "type_demande", "statut")

# Statut opérationnel. « Done » vaut « Envoyé » tant que Result ne dit pas
# gagné ou perdu : c’est la colonne Result qui tranche (voir normalize).
STATUS_NORMALIZATION = {
    "en cours": "En cours", "en-cours": "En cours", "encours": "En cours",
    "en traitement": "En cours", "wip": "En cours", "in progress": "En cours",
    "in-progress": "En cours", "ongoing": "En cours", "open": "En cours", "ouvert": "En cours",
    "envoye": "Envoyé", "envoyé": "Envoyé", "soumis": "Envoyé", "repondu": "Envoyé",
    "submitted": "Envoyé", "done": "Envoyé", "termine": "Envoyé", "terminé": "Envoyé",
    "finished": "Envoyé", "completed": "Envoyé", "closed": "Envoyé", "sent": "Envoyé",
    "remis": "Envoyé",
    "gagne": "Gagné", "gagné": "Gagné", "won": "Gagné", "remporte": "Gagné", "win": "Gagné",
    "perdu": "Perdu", "lost": "Perdu",
    "abandonne": "Abandonné", "abandonné": "Abandonné", "annule": "Abandonné",
    "annulé": "Abandonné", "cancelled": "Abandonné", "canceled": "Abandonné",
    "no bid": "Abandonné", "nobid": "Abandonné", "declined": "Abandonné", "withdrawn": "Abandonné",
}

# Résultat commercial (colonne Result). « NA » n’est pas une inconnue : c’est
# l’absence de résultat, normale pour une due diligence ou un dossier non tranché.
RESULT_NORMALIZATION = {
    "won": "Gagné", "win": "Gagné", "gagne": "Gagné", "gagné": "Gagné", "remporte": "Gagné",
    "lost": "Perdu", "perdu": "Perdu", "loss": "Perdu",
    "na": "Sans objet", "n a": "Sans objet", "n/a": "Sans objet", "none": "Sans objet",
    "sans objet": "Sans objet", "nan": "Sans objet", "": "Sans objet", "-": "Sans objet",
    "pending": "En attente", "en attente": "En attente", "en cours": "En attente",
    "no bid": "Sans suite", "nobid": "Sans suite", "cancelled": "Sans suite",
    "withdrawn": "Sans suite", "abandonne": "Sans suite", "abandonné": "Sans suite",
}

# Le classeur du pôle ne connaît que deux types : RFP et Due Diligence. Les
# intitulés des anciennes extractions (RFI, DDQ, « questionnaire ») restent
# compris à la lecture, mais rejoignent la due diligence : le produit n’affiche
# plus de type fin.
TYPE_NORMALIZATION = {
    "rfp": "RFP", "r.f.p": "RFP", "request for proposal": "RFP", "appel d’offres": "RFP",
    "appel d offres": "RFP", "appel d’offre": "RFP", "ao": "RFP", "tender": "RFP",
    "due diligence": "Due Diligence", "duediligence": "Due Diligence",
    "due diligence questionnaire": "Due Diligence", "questionnaire": "Due Diligence",
    "ddq": "Due Diligence", "d.d.q": "Due Diligence", "dd": "Due Diligence",
    "due dil": "Due Diligence", "rfi": "Due Diligence", "r.f.i": "Due Diligence",
    "request for information": "Due Diligence",
}

CLIENT_TYPE_NORMALIZATION = {
    "institutionnel": "Institutionnel", "institution": "Institutionnel",
    "institutional": "Institutionnel", "asset owner": "Institutionnel", "instit": "Institutionnel",
    "instit.": "Institutionnel", "inst": "Institutionnel",
    "distributeur": "Distributeur", "distribution": "Distributeur", "wholesale": "Distributeur",
    "plateforme": "Distributeur", "distr": "Distributeur", "distr.": "Distributeur",
    "dist": "Distributeur", "distributor": "Distributeur",
    "international": "International", "intern": "International", "intern.": "International",
    "int": "International", "intl": "International", "etranger": "International",
    "étranger": "International",
    "consultant": "Consultant", "conseil": "Consultant", "gatekeeper": "Consultant",
}

# Segment du client : le vocabulaire du classeur est anglais, l’écran est français.
SEGMENT_NORMALIZATION = {
    "pension/retirement": "Fonds de pension", "pension retirement": "Fonds de pension",
    "pension": "Fonds de pension", "retirement": "Fonds de pension", "pension fund": "Fonds de pension",
    "fonds de pension": "Fonds de pension", "caisse de retraite": "Fonds de pension",
    "retraite": "Fonds de pension",
    "insurance company": "Assureur", "insurance": "Assureur", "insurer": "Assureur",
    "assureur": "Assureur", "assurance": "Assureur",
    "mutual": "Mutuelle", "mutuelle": "Mutuelle", "mutual insurance": "Mutuelle",
    "corporate": "Entreprise", "entreprise": "Entreprise", "company": "Entreprise",
    "private bank": "Banque privée", "banque privee": "Banque privée", "banque privée": "Banque privée",
    "private banking": "Banque privée", "wealth": "Banque privée",
    "asset management company": "Société de gestion", "asset manager": "Société de gestion",
    "societe de gestion": "Société de gestion", "société de gestion": "Société de gestion",
    "banking network": "Réseau bancaire", "retail bank": "Réseau bancaire", "bank": "Réseau bancaire",
    "reseau bancaire": "Réseau bancaire", "réseau bancaire": "Réseau bancaire", "banque": "Réseau bancaire",
    "family office": "Family office",
    "foundation": "Fondation", "endowment": "Fondation", "fondation": "Fondation",
    "sovereign": "Fonds souverain", "sovereign wealth fund": "Fonds souverain",
    "consultant": "Consultant", "platform": "Plateforme", "plateforme": "Plateforme",
    "public": "Secteur public", "public sector": "Secteur public",
}

PAYS_NORMALIZATION = {
    "france": "France", "fr": "France",
    "uk": "Royaume-Uni", "united kingdom": "Royaume-Uni", "great britain": "Royaume-Uni",
    "england": "Royaume-Uni", "royaume uni": "Royaume-Uni", "royaume-uni": "Royaume-Uni", "gb": "Royaume-Uni",
    "italy": "Italie", "italie": "Italie", "it": "Italie",
    "spain": "Espagne", "espagne": "Espagne", "es": "Espagne",
    "germany": "Allemagne", "allemagne": "Allemagne", "de": "Allemagne", "deutschland": "Allemagne",
    "switzerland": "Suisse", "suisse": "Suisse", "ch": "Suisse",
    "netherlands": "Pays-Bas", "the netherlands": "Pays-Bas", "pays bas": "Pays-Bas", "nl": "Pays-Bas",
    "belgium": "Belgique", "belgique": "Belgique", "be": "Belgique",
    "luxembourg": "Luxembourg", "lu": "Luxembourg",
    "usa": "États-Unis", "us": "États-Unis", "united states": "États-Unis", "etats unis": "États-Unis",
    "états-unis": "États-Unis",
    "sweden": "Suède", "suede": "Suède", "denmark": "Danemark", "danemark": "Danemark",
    "norway": "Norvège", "norvege": "Norvège", "finland": "Finlande", "finlande": "Finlande",
    "portugal": "Portugal", "austria": "Autriche", "autriche": "Autriche",
    "ireland": "Irlande", "irlande": "Irlande", "singapore": "Singapour", "singapour": "Singapour",
    "japan": "Japon", "japon": "Japon", "china": "Chine", "chine": "Chine",
    "monaco": "Monaco", "hong kong": "Hong Kong", "australia": "Australie", "australie": "Australie",
    "canada": "Canada", "middle east": "Moyen-Orient", "uae": "Émirats arabes unis",
    "europe": "Europe", "international": "International", "other": "Autre", "autre": "Autre",
}

CLASSE_NORMALIZATION = {
    "equity": "Actions", "equities": "Actions", "actions": "Actions",
    "fixed income": "Obligataire", "bonds": "Obligataire", "obligataire": "Obligataire",
    "obligations": "Obligataire", "credit": "Obligataire",
    "diversified": "Diversifié", "diversifie": "Diversifié", "diversifié": "Diversifié",
    "multi asset": "Diversifié", "balanced": "Diversifié", "allocation": "Diversifié",
    "oa diversified": "Diversifié (architecture ouverte)",
    "oa-diversified": "Diversifié (architecture ouverte)",
    "open architecture": "Diversifié (architecture ouverte)",
    "hedge funds": "Alternatif", "hedge fund": "Alternatif", "alternative": "Alternatif",
    "alternatif": "Alternatif", "alternatives": "Alternatif",
    "money market": "Monétaire", "monetaire": "Monétaire", "monétaire": "Monétaire", "cash": "Monétaire",
    "real assets": "Actifs réels", "real estate": "Actifs réels", "private equity": "Actifs réels",
    "infrastructure": "Actifs réels", "actifs reels": "Actifs réels", "actifs réels": "Actifs réels",
    "convertible": "Convertibles", "convertibles": "Convertibles",
    "corporate": "Corporate",
}

FORME_NORMALIZATION = {
    "open-ended fund": "Fonds ouvert", "open ended fund": "Fonds ouvert", "open ended": "Fonds ouvert",
    "fund": "Fonds ouvert", "opcvm": "Fonds ouvert", "ucits": "Fonds ouvert", "sicav": "Fonds ouvert",
    "fcp": "Fonds ouvert", "fonds ouvert": "Fonds ouvert", "sicav luxembourg": "Fonds ouvert",
    "mandate": "Mandat", "mandat": "Mandat", "segregated mandate": "Mandat",
    "dedicated fund": "Fonds dédié", "fonds dedie": "Fonds dédié", "fonds dédié": "Fonds dédié",
    "fia": "Fonds dédié", "aif": "Fonds dédié",
    "corporate": "Corporate",
}

# Réponses binaires : SRI, Qvidian, étapes du processus.
OUI_NON_NORMALIZATION = {
    "yes": "Oui", "y": "Oui", "oui": "Oui", "o": "Oui", "true": "Oui", "1": "Oui", "x": "Oui",
    "done": "Oui", "fait": "Oui", "ok": "Oui",
    "no": "Non", "n": "Non", "non": "Non", "false": "Non", "0": "Non", "none": "Non",
    "to do": "À faire", "todo": "À faire", "a faire": "À faire", "à faire": "À faire",
    "pending": "À faire",
}

LANGUE_NORMALIZATION = {
    "fr": "Français", "francais": "Français", "français": "Français", "french": "Français",
    "en": "Anglais", "anglais": "Anglais", "english": "Anglais", "uk": "Anglais", "gb": "Anglais",
    "de": "Allemand", "allemand": "Allemand", "german": "Allemand", "deutsch": "Allemand",
    "it": "Italien", "italien": "Italien", "italian": "Italien",
    "es": "Espagnol", "espagnol": "Espagnol", "spanish": "Espagnol",
    "nl": "Néerlandais", "neerlandais": "Néerlandais", "dutch": "Néerlandais",
    "fr/en": "Français et anglais", "en/fr": "Français et anglais", "bilingue": "Français et anglais",
}

# Étapes du processus d’un appel d’offres, telles que le classeur les code.
# L’interprétation des deux premières est celle du pôle ; elle se règle ici.
ETAPES_RFP: tuple[tuple[str, str, str], ...] = (
    ("etape_1", "Step 1", "Step_1 : la proposition est déposée"),
    ("etape_2", "Step 2", "Step_2 : retenu après lecture du dossier"),
    ("oral", "Oral", "ORAL_RFP : présentation devant le client"),
)

# Valeur attribuée à une modalité inconnue (elle reste visible, jamais supprimée)
VALEUR_INCONNUE = "Non renseigné"

# [BRANCHEMENT] Le pôle raisonne en DEUX familles, celles de la colonne « Type »
# du classeur : les appels d’offres d’un côté, la due diligence de l’autre. Il
# n’existe pas de type plus fin — ni à l’écran, ni dans le rapport.
FAMILLE_RFP, FAMILLE_DD = "RFP", "Due Diligence"
FAMILLE_PAR_TYPE = {FAMILLE_RFP: FAMILLE_RFP, FAMILLE_DD: FAMILLE_DD}
FAMILLE_ORDER = [FAMILLE_DD, FAMILLE_RFP]

# Résultat commercial d’un RFP, vocabulaire du pilotage (Won / Lost / Pending / N/A).
RESULTAT_GAGNE, RESULTAT_PERDU = "Gagné", "Perdu"
RESULTAT_ATTENTE, RESULTAT_SANS_SUITE = "En attente", "Sans suite"
RESULTAT_HORS_RFP = "Sans objet"      # une due diligence ne se gagne pas
RESULTAT_ORDER = [RESULTAT_GAGNE, RESULTAT_ATTENTE, RESULTAT_PERDU, RESULTAT_SANS_SUITE]

# Tranches ESG : celles que suit la manager dans son rapport actuel.
ESG_INCONNU = "Non renseigné"
ESG_FAIBLE, ESG_MOYEN, ESG_FORT = "< 25 % ESG", "25–75 % ESG", "> 75 % ESG"
ESG_ORDER = [ESG_FORT, ESG_MOYEN, ESG_FAIBLE, ESG_INCONNU]
ESG_SEUIL_FORT = 0.75            # [BRANCHEMENT] seuil « questionnaire à forte composante ESG »

# [BRANCHEMENT] Horizons de croissance suivis au comité (en années).
HORIZONS_CROISSANCE = (3, 5, 10)

# Ordre métier des statuts (pipeline), utilisé partout dans l’interface
STATUT_EN_COURS, STATUT_ENVOYE = "En cours", "Envoyé"
STATUT_GAGNE, STATUT_PERDU, STATUT_ABANDONNE = "Gagné", "Perdu", "Abandonné"
STATUT_ORDER = [STATUT_EN_COURS, STATUT_ENVOYE, STATUT_GAGNE, STATUT_PERDU, STATUT_ABANDONNE]
STATUTS_ENVOYES = (STATUT_ENVOYE, STATUT_GAGNE, STATUT_PERDU)   # la réponse est partie
STATUTS_DECIDES = (STATUT_GAGNE, STATUT_PERDU)                  # le client a tranché
TYPE_ORDER = [FAMILLE_RFP, FAMILLE_DD]

# [BRANCHEMENT] Engagement de service, en jours OUVRÉS, par type de demande
SLA_JOURS_OUVRES = {FAMILLE_RFP: 15, FAMILLE_DD: 12}
SLA_DEFAUT = 12

# [BRANCHEMENT] Nombre de mandats détaillés dans la table « Mandats remportés »
# de la vue d’ensemble ; au-delà, le reste est agrégé (le total reste exact).
TOP_MANDATS = 15

# [BRANCHEMENT] Au-delà de ce nombre de jours, l’attente d’un appel d’offres
# ouvert est signalée comme longue sur la jauge du carnet (quatre mois).
SEUIL_ATTENTE = 120

# [BRANCHEMENT] Horizon de projection de la tendance (mois)
PROJECTION_MOIS = 6
# [BRANCHEMENT] Seuil de significativité statistique
ALPHA = 0.05

# [BRANCHEMENT] Données synthétiques : profondeur d’historique et graine
FAKE_MOIS_HISTORIQUE = 36
FAKE_SEED = 20260914
FAKE_VOLUME_MENSUEL_BASE = 38

# Avertissement affiché sous les indicateurs : les décisions clients arrivent
# plusieurs mois après l’envoi, donc les périodes récentes sont mécaniquement
# riches en dossiers non tranchés (censure à droite). Ne jamais lire un taux de
# succès récent comme un taux définitif.
NOTE_CENSURE = ("Les clients tranchent plusieurs mois après l’envoi de la réponse : sur une "
                "période récente, le taux de succès et l’encours remporté sont mécaniquement "
                "sous-évalués, et l’encours en jeu surévalué.")

# Dimensions filtrables : clé interne -> libellé affiché (pilote la barre latérale)
# Dimensions filtrables : clé interne -> libellé affiché. L’ordre est celui de
# la barre de filtres ; les six premières sont les filtres de premier niveau.
DIMENSIONS: dict[str, str] = {
    "famille": "Famille",
    "resultat": "Résultat",
    "segment": "Segment",
    "pays": "Pays",
    "classe_actifs": "Classe d’actifs",
    "client": "Client",
    "consultant": "Consultant",
    "commercial": "Commercial",
    "expertise": "Expertise",
    "sous_classe_actifs": "Sous-classe d’actifs",
    "forme_juridique": "Forme juridique",
    "fonds": "Fonds de référence",
    "type_client": "Type de client",
    "soutenance": "Oral",
    "sri": "ISR",
    "bande_esg": "Tranche ESG",
    "statut": "Statut",
    "qvidian": "Mise à jour Qvidian",
    "langue": "Langue",
}
# Filtres affichés sans repli ; le reste passe derrière « Plus de filtres ».
DIMENSIONS_PRINCIPALES = ("famille", "resultat", "segment", "pays", "classe_actifs",
                          "client", "consultant", "commercial")

# =============================================================================
#  [MARQUE] — une couleur, ses tons
# -----------------------------------------------------------------------------
#  Une seule teinte : le bleu Rothschild & Co. Toute autre couleur, à l’écran
#  comme dans le rapport, est un mélange de ce bleu et du blanc (`teinte`).
#  Ni or, ni vert / rouge, ni palette catégorielle : un état s’écrit en toutes
#  lettres, il ne se colore pas. Les séries se distinguent par le ton, le
#  contour et le libellé direct.
#
#  Si la charte fournit un code différent, MARQUE_BLEU est le seul endroit à
#  corriger : tous les tons en découlent.
#
#  La marque est en tracés vectoriels dans assets/ (fill="currentColor", elle
#  prend la couleur du texte) : logo.svg (emblème aux cinq flèches et logotype,
#  horizontal), embleme.svg (les flèches seules), logo-empile.svg (vertical,
#  pour une couverture). Pour installer le fichier officiel de la charte,
#  déposer le SVG sous ces noms : rien d’autre à modifier.
# =============================================================================
MARQUE_NOM = "Rothschild & Co"
MARQUE_ACTIVITE = "Asset Management"
MARQUE_PRODUIT = "RFP & Due Diligence"
MARQUE_BLEU = "#0B2545"
MARQUE_BLANC = "#FFFFFF"
MARQUE_LOGO = "logo.svg"
MARQUE_EMBLEME = "embleme.svg"
MARQUE_LOGO_EMPILE = "logo-empile.svg"


def _hex_vers_rgb(couleur: str) -> tuple[int, int, int]:
    h = couleur.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def melanger(a: str, b: str, t: float) -> str:
    """Couleur à la position t entre a (t = 0) et b (t = 1), en sRGB."""
    t = min(1.0, max(0.0, float(t)))
    ra, ga, ba = _hex_vers_rgb(a)
    rb, gb, bb = _hex_vers_rgb(b)
    return "#{:02x}{:02x}{:02x}".format(
        round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def teinte(t: float) -> str:
    """Le bleu de la maison à `t` (1 = plein, 0 = blanc), mélangé au blanc.

    C’est la seule fabrique de couleur du produit : ce qui n’en sort pas n’a pas
    sa place à l’écran.
    """
    return melanger(MARQUE_BLANC, MARQUE_BLEU, t)


# Échelle de tons exposée en CSS (--b-3 … --b-100) : le système visuel entier
# se compose avec ces huit valeurs.
TONS: tuple[int, ...] = (3, 6, 12, 22, 36, 52, 72, 100)

# Tons des cinq états d’un appel d’offres : du plus soutenu (remporté) au plus
# effacé (sans suite). Toujours accompagnés du libellé et de la valeur.
TONS_ETAT: dict[str, float] = {
    "gagnes": 1.00, "en_attente": 0.66, "en_cours": 0.44, "perdus": 0.26, "sans_suite": 0.14,
}


# =============================================================================
#  IDENTITÉ VISUELLE — un thème, dérivé de la teinte
# -----------------------------------------------------------------------------
#  Fond blanc, encre bleue, tout le reste en tons du bleu. Le thème est unique :
#  l’écran et le rapport le partagent, il n’y a rien à basculer.
# =============================================================================
FONT_STACK = ('"InterVariable", "Inter", system-ui, -apple-system, "Segoe UI", '
              'Roboto, "Helvetica Neue", Arial, sans-serif')
FONT_SERIF = '"EB Garamond", Garamond, "Times New Roman", serif'
TEMPLATE_NAME = "rothschild"

THEMES: dict[str, dict[str, Any]] = {
    "rothschild": dict(
        PLANE=teinte(0.03),           # page : blanc très légèrement bleuté
        SURFACE=MARQUE_BLANC,         # surfaces et aires de tracé
        ELEVATION=teinte(0.06),       # survol, ligne sélectionnée
        INK=MARQUE_BLEU,              # encre
        INK_2=teinte(0.72),           # texte secondaire
        INK_MUTED=teinte(0.52),       # libellés discrets, axes (4,5:1 sur blanc)
        GRID=teinte(0.10),
        AXIS=teinte(0.22),
        BORDER=teinte(0.12),
        VOILE="rgba(255,255,255,0.94)",
        ACCENT=MARQUE_BLEU,
        # Séries : tons décroissants. La première est l’encre pleine ; la
        # deuxième et la troisième portent les séries secondaires. Au-delà de
        # quatre séries, un graphique monochrome se lit par ses libellés.
        SERIES=[teinte(1.0), teinte(0.62), teinte(0.34), teinte(0.18),
                teinte(0.80), teinte(0.48), teinte(0.26), teinte(0.12)],
        SEQUENTIEL=[teinte(t) for t in (0.06, 0.16, 0.28, 0.42, 0.58, 0.78, 1.0)],
        ORDINAL=[teinte(t) for t in (1.0, 0.66, 0.40, 0.20)],
        RAYON="2px",
    ),
}

THEME_DEFAUT = "rothschild"

# Jetons exposés au reste du programme — renseignés par appliquer_theme().
THEME = THEME_DEFAUT
PLANE = SURFACE = ELEVATION = INK = INK_2 = INK_MUTED = ""
GRID = AXIS = BORDER = VOILE = ACCENT = ""
RAYON = "2px"
SUR_ACCENT = MARQUE_BLANC   # encre posée SUR un aplat de bleu
# Couleurs « d’état » : des tons du bleu, jamais du vert ou du rouge. Les noms
# historiques sont conservés pour les fonctions de tracé.
STATUS_GOOD = STATUS_WARNING = STATUS_SERIOUS = STATUS_CRITICAL = ""
TEXTE_BON = TEXTE_MAUVAIS = ""
SERIES: list[str] = []
SEQUENTIEL: list[str] = []
ORDINAL: list[str] = []
STATUT_COLORS: dict[str, str] = {}
COMPARTIMENT_COLORS: dict[str, str] = {}


# =============================================================================
#  SYSTÈME DE DESIGN — une seule définition, deux surfaces
# -----------------------------------------------------------------------------
#  Espacement, échelle typographique, rayons, profondeur et mouvement sont
#  définis ICI et émis en variables CSS. server.py et export.py consomment les
#  mêmes jetons : l’écran et le rapport ne peuvent pas diverger d’un pixel.
# =============================================================================
# Échelle d’espacement, multiples de 4 et 8 — aucune valeur en dur ailleurs.
ESPACEMENT = {"1": "4px", "2": "8px", "3": "12px", "4": "16px", "5": "24px",
              "6": "32px", "7": "48px", "8": "64px", "9": "96px"}

# Échelle typographique. Le rapport de 1,25 entre les corps de texte, plus
# marqué au-delà : une hiérarchie se voit, elle ne se devine pas.
TYPO = {"xs": "10px", "s": "11px", "m": "12.5px", "l": "14px", "xl": "18px",
        "2xl": "24px", "3xl": "32px", "4xl": "44px", "5xl": "60px"}

# Mouvement. Une seule courbe pour les entrées (décélération franche, la
# sensation « ressort » sans rebond parasite), une pour les états.
MOTION = {
    "rapide": "150ms", "moyen": "260ms", "lent": "420ms",
    "sortie": "cubic-bezier(.22,1,.36,1)",
    "etat": "cubic-bezier(.4,0,.2,1)",
}


def jetons_css(selecteur: str = ":root") -> str:
    """Tous les jetons du thème, en variables CSS : couleurs (une teinte et ses
    tons), espacement, typographie, mouvement. L’écran et le rapport lisent
    exactement le même bloc."""
    jetons = {
        "bleu": MARQUE_BLEU, "blanc": MARQUE_BLANC,
        "plane": PLANE, "surface": SURFACE, "elevation": ELEVATION,
        "ink": INK, "ink-2": INK_2, "muted": INK_MUTED,
        "grid": GRID, "axis": AXIS, "border": BORDER, "voile": VOILE,
        "accent": ACCENT, "sur-accent": SUR_ACCENT,
        "bon": TEXTE_BON, "mauvais": TEXTE_MAUVAIS, "neutre": INK_MUTED,
        "gagne": COMPARTIMENT_COLORS.get("gagnes", INK),
        "attente": COMPARTIMENT_COLORS.get("en_attente", INK),
        "redaction": COMPARTIMENT_COLORS.get("en_cours", INK),
        "perdu": COMPARTIMENT_COLORS.get("perdus", INK),
        "sans-suite": COMPARTIMENT_COLORS.get("sans_suite", INK),
        "rayon": RAYON,
        "rayon-s": RAYON,
        "rayon-l": f"calc({RAYON} + 2px)",
        "police": FONT_STACK,
        "police-serif": FONT_SERIF,
    }
    for ton in TONS:
        jetons[f"b-{ton}"] = teinte(ton / 100)
    for i, couleur in enumerate(SERIES, start=1):
        jetons[f"serie{i}"] = couleur
    for cle, valeur in ESPACEMENT.items():
        jetons[f"e{cle}"] = valeur
    for cle, valeur in TYPO.items():
        jetons[f"t-{cle}"] = valeur
    for cle, valeur in MOTION.items():
        jetons[cle] = valeur
    corps = "".join(f"--{c}:{v};" for c, v in jetons.items())
    return f"{selecteur}{{{corps}}}"


def chrome_plotly() -> dict[str, Any]:
    """Couleurs de CHROME d’une figure — grille, axes, encre, infobulle.

    Les marques n’y figurent pas : la palette de séries passe les contrôles sur
    les deux surfaces (bleu de nuit et ivoire), elle n’a donc pas à changer. Ce
    dictionnaire est ce que le rapport applique en `Plotly.relayout` quand on
    bascule l’apparence.
    """
    return {
        "font.color": INK_2,
        "xaxis.gridcolor": GRID, "yaxis.gridcolor": GRID,
        "xaxis.linecolor": AXIS, "yaxis.linecolor": AXIS,
        "xaxis.tickcolor": AXIS, "yaxis.tickcolor": AXIS,
        "xaxis.tickfont.color": INK_MUTED, "yaxis.tickfont.color": INK_MUTED,
        "xaxis.title.font.color": INK_2, "yaxis.title.font.color": INK_2,
        "legend.font.color": INK_2,
        "hoverlabel.bgcolor": ELEVATION, "hoverlabel.bordercolor": AXIS,
        "hoverlabel.font.color": INK,
    }


def _luminance(couleur: str) -> float:
    """Luminance relative WCAG d’une couleur hexadécimale."""
    h = couleur.lstrip("#")
    canaux = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        canaux.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canaux[0] + 0.7152 * canaux[1] + 0.0722 * canaux[2]


def encre_lisible(fond: str) -> str:
    """Encre à poser sur un aplat : celle des deux qui contraste le plus.
    Indispensable pour les valeurs écrites dans une cellule de carte de chaleur
    ou dans un segment d’entonnoir, dont la couleur varie avec la donnée."""
    clair, sombre = MARQUE_BLANC, MARQUE_BLEU
    lum = _luminance(fond)
    contraste_clair = 1.05 / (lum + 0.05)
    contraste_sombre = (lum + 0.05) / 0.05
    return clair if contraste_clair >= contraste_sombre else sombre


def couleur_rampe(rampe: Sequence[str], t: float) -> str:
    """Couleur de la rampe séquentielle à la position t ∈ [0, 1]."""
    if not math.isfinite(t):
        return rampe[0]
    return rampe[min(len(rampe) - 1, max(0, int(round(t * (len(rampe) - 1)))))]


def appliquer_theme(nom: str = THEME_DEFAUT) -> None:
    """Renseigne tous les jetons de couleur et enregistre le gabarit Plotly.

    Il n’existe qu’un thème ; la fonction reste le seul point d’entrée, pour
    que rien d’autre ne fabrique une couleur.
    """
    global THEME, PLANE, SURFACE, ELEVATION, INK, INK_2, INK_MUTED, GRID, AXIS
    global BORDER, VOILE, ACCENT, SERIES, SEQUENTIEL, ORDINAL, RAYON, SUR_ACCENT
    global STATUS_GOOD, STATUS_WARNING, STATUS_SERIOUS, STATUS_CRITICAL
    global TEXTE_BON, TEXTE_MAUVAIS, STATUT_COLORS, COMPARTIMENT_COLORS

    if nom not in THEMES:
        raise ValueError(f"Thème inconnu : {nom!r}. Choix : {', '.join(THEMES)}.")
    jetons = THEMES[nom]
    THEME = nom
    PLANE, SURFACE, ELEVATION = jetons["PLANE"], jetons["SURFACE"], jetons["ELEVATION"]
    INK, INK_2, INK_MUTED = jetons["INK"], jetons["INK_2"], jetons["INK_MUTED"]
    GRID, AXIS, BORDER, VOILE = jetons["GRID"], jetons["AXIS"], jetons["BORDER"], jetons["VOILE"]
    ACCENT = jetons["ACCENT"]
    RAYON = jetons.get("RAYON", "2px")
    SUR_ACCENT = encre_lisible(ACCENT)
    SERIES = list(jetons["SERIES"])
    SEQUENTIEL = list(jetons["SEQUENTIEL"])
    ORDINAL = list(jetons["ORDINAL"])

    # Les cinq états d’un appel d’offres, par ton. Le libellé et la valeur
    # accompagnent toujours la marque : le ton aide, il ne porte pas seul.
    COMPARTIMENT_COLORS = {cle: teinte(t) for cle, t in TONS_ETAT.items()}
    STATUT_COLORS = {
        STATUT_EN_COURS: COMPARTIMENT_COLORS["en_cours"],
        STATUT_ENVOYE: COMPARTIMENT_COLORS["en_attente"],
        STATUT_GAGNE: COMPARTIMENT_COLORS["gagnes"],
        STATUT_PERDU: COMPARTIMENT_COLORS["perdus"],
        STATUT_ABANDONNE: COMPARTIMENT_COLORS["sans_suite"],
    }
    STATUS_GOOD = COMPARTIMENT_COLORS["gagnes"]
    STATUS_WARNING = COMPARTIMENT_COLORS["en_attente"]
    STATUS_CRITICAL = COMPARTIMENT_COLORS["perdus"]
    STATUS_SERIOUS = COMPARTIMENT_COLORS["sans_suite"]
    # Une variation se lit à son signe et à sa flèche, pas à sa couleur.
    TEXTE_BON = INK
    TEXTE_MAUVAIS = INK_2
    _register_template()


def _register_template() -> None:
    """Gabarit Plotly de la maison : marques fines, grille en filet très
    léger, encre sobre, angles vifs."""
    axe = dict(
        showgrid=True, gridcolor=GRID, gridwidth=1, griddash="solid",
        zeroline=False, showline=True, linecolor=AXIS, linewidth=1,
        ticks="outside", tickcolor=AXIS, ticklen=4,
        tickfont=dict(color=INK_MUTED, size=11.5),
        title=dict(font=dict(color=INK_2, size=12)),
        automargin=True,
    )
    pio.templates[TEMPLATE_NAME] = go.layout.Template(
        layout=go.Layout(
            font=dict(family=FONT_STACK, size=12.5, color=INK_2),
            paper_bgcolor="rgba(0,0,0,0)",   # la surface hôte porte le fond
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=SERIES,
            xaxis=axe,
            yaxis=axe,
            margin=dict(l=8, r=16, t=28, b=8),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                bgcolor="rgba(0,0,0,0)", borderwidth=0,
                font=dict(size=11.5, color=INK_2),
                itemsizing="constant", tracegroupgap=6, traceorder="normal",
            ),
            hoverlabel=dict(
                bgcolor=SURFACE, bordercolor=AXIS, align="left",
                font=dict(family=FONT_STACK, size=12, color=INK),
            ),
            hovermode="closest",
            bargap=0.32,
            separators=", ",   # virgule décimale, milliers en espace fine
            colorscale=dict(sequential=[[i / (len(SEQUENTIEL) - 1), c]
                                        for i, c in enumerate(SEQUENTIEL)]),
            annotationdefaults=dict(font=dict(family=FONT_STACK, size=11.5, color=INK_2),
                                    showarrow=False),
        )
    )


appliquer_theme(THEME_DEFAUT)


# =============================================================================
#  RESSOURCES EMBARQUÉES — marque et polices
# -----------------------------------------------------------------------------
#  Tout est servi depuis assets/ et jamais depuis un CDN : l’écran comme le
#  rapport fonctionnent sur un poste sans accès réseau. Si un fichier manque,
#  la fonction renvoie une valeur vide : l’interface perd sa marque ou sa
#  police, jamais son contenu.
# =============================================================================
DOSSIER_ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=16)
def _texte_asset(nom: str) -> str:
    try:
        return (DOSSIER_ASSETS / nom).read_text(encoding="utf-8")
    except OSError:
        return ""


@lru_cache(maxsize=16)
def _base64_asset(nom: str) -> str:
    try:
        return base64.b64encode((DOSSIER_ASSETS / nom).read_bytes()).decode("ascii")
    except OSError:
        return ""


def logo_svg(variante: str = "horizontal") -> str:
    """La marque en SVG inline, fill="currentColor".

    `variante` : "horizontal" (emblème + logotype), "embleme" (les cinq flèches
    seules), "empile" (vertical, pour une couverture). Vide si le fichier
    manque : l’interface retombe sur le libellé typographique.
    """
    nom = {"horizontal": MARQUE_LOGO, "embleme": MARQUE_EMBLEME,
           "empile": MARQUE_LOGO_EMPILE}.get(variante, MARQUE_LOGO)
    return _texte_asset(nom).strip()


def police_css() -> str:
    """Règles @font-face des deux polices, en base64.

    Inter (interface) et EB Garamond (la voix de la marque : logotype, grands
    chiffres) sont sous licence SIL OFL — voir assets/*-LICENSE.txt. Les
    embarquer est autorisé, et c’est la seule façon d’obtenir la même
    typographie hors ligne comme dans un rapport transmis par courriel.
    """
    regles = []
    inter = _base64_asset("inter-variable.woff2")
    if inter:
        regles.append("@font-face{font-family:'InterVariable';font-style:normal;"
                      "font-weight:100 900;font-display:swap;"
                      f"src:url(data:font/woff2;base64,{inter}) format('woff2-variations');}}")
    garamond = _base64_asset("eb-garamond-latin.woff2")
    if garamond:
        regles.append("@font-face{font-family:'EB Garamond';font-style:normal;"
                      "font-weight:400 800;font-display:swap;"
                      f"src:url(data:font/woff2;base64,{garamond}) format('woff2-variations');}}")
    return "".join(regles)


PLOT_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
}

# =============================================================================
#  FORMATAGE FRANÇAIS  (espace fine insécable en séparateur de milliers)
# =============================================================================
# Typographie française : espace insécable comme séparateur de milliers et
# devant une unité. L’espace FINE insécable (U+202F) serait la forme la plus
# juste, mais elle mesure moins de deux pixels dans un texte courant : à la
# lecture, « 1 835 » redevient « 1835 ». La lisibilité prime.
NBSP = " "
ESP_UNITE = NBSP


def _arrondi(x: Any, n: int) -> Decimal:
    """Arrondi au demi-SUPÉRIEUR (loin de zéro), la règle de toLocaleString en
    JavaScript : l’écran et le rapport écrivent le même nombre pour 90,5."""
    return Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)


def fmt_int(x: Any, unite: str = "") -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    s = f"{int(_arrondi(x, 0)):,}".replace(",", NBSP)
    return f"{s}{ESP_UNITE}{unite}" if unite else s


def fmt_dec(x: Any, n: int = 1, unite: str = "") -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    s = f"{_arrondi(x, n):,.{n}f}".replace(",", "\x00").replace(".", ",").replace("\x00", NBSP)
    return f"{s}{ESP_UNITE}{unite}" if unite else s


def fmt_pct(x: Any, n: int = 0) -> str:
    """x est une proportion (0-1)."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    return fmt_dec(float(x) * 100, n, "%")


def fmt_eur(x: Any, court: bool = True) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    x = float(x)
    if court and abs(x) >= 1e9:
        return fmt_dec(x / 1e9, 2, "Md€")
    if court and abs(x) >= 1e6:
        return fmt_dec(x / 1e6, 1, "M€")
    if court and abs(x) >= 1e3:
        return fmt_dec(x / 1e3, 0, "k€")
    return fmt_int(x, "€")


def fmt_compact(x: Any) -> str:
    """Format court pour les graduations d’axe : 12 k, 1,3 M, 4,2 Md."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    x = float(x)
    if abs(x) >= 1e9:
        return fmt_dec(x / 1e9, 1, "Md")
    if abs(x) >= 1e6:
        return fmt_dec(x / 1e6, 1, "M")
    if abs(x) >= 1e3:
        return fmt_dec(x / 1e3, 0, "k")
    return fmt_int(x)


def fmt_eur_tick(x: Any) -> str:
    """Graduation monétaire : « 5 Md€ », « 2,5 Md€ », « 500 M€ »."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    x = float(x)
    for seuil, unite in ((1e9, "Md€"), (1e6, "M€"), (1e3, "k€")):
        if abs(x) >= seuil:
            valeur = x / seuil
            return fmt_dec(valeur, 0 if abs(valeur - round(valeur)) < 0.05 else 1, unite)
    return fmt_int(x, "€")


def fmt_jours(x: Any) -> str:
    return "—" if x is None or pd.isna(x) else fmt_dec(x, 1, "j")


def fmt_p(p: float | None) -> str:
    if p is None or pd.isna(p):
        return "—"
    return "p < 0,001" if p < 0.001 else f"p = {fmt_dec(p, 3)}"


MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
           "juil.", "août", "sept.", "oct.", "nov.", "déc."]
MOIS_FR_LONG = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
                "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def fmt_mois(ts: pd.Timestamp) -> str:
    ts = pd.Timestamp(ts)
    return f"{MOIS_FR[ts.month - 1]} {ts.year}"


def accord(n: Any) -> str:
    """Le « s » du pluriel, ou rien. Un produit qui écrit « dossier(s) » se lit
    comme un formulaire administratif, pas comme un outil de direction."""
    try:
        return "" if abs(float(n)) < 2 else "s"
    except (TypeError, ValueError):
        return ""


def pluriel(n: Any, singulier: str, forme_pluriel: str | None = None) -> str:
    """« 1 dossier », « 7 dossiers » — le nombre et son nom, accordés."""
    marque = accord(n)
    mot = (forme_pluriel or singulier + "s") if marque else singulier
    return f"{fmt_int(n)}{NBSP}{mot}"


def fmt_date_longue(d: Any) -> str:
    """« 16 septembre 2026 » — pour un titre, jamais pour un tableau."""
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return "—"
    ts = pd.Timestamp(d)
    if pd.isna(ts):
        return "—"
    return f"{ts.day} {MOIS_FR_LONG[ts.month - 1].lower()} {ts.year}"


def fmt_encours(x: Any, court: bool = True) -> str:
    """Un encours, tel que l’écrit l’application : les montants du moteur sont
    en millions d’euros, et passent au milliard au-delà de mille.

    Jumeau exact de `euros()` dans static/js/format.js — l’écran et le rapport
    impriment la même chaîne pour la même valeur.
    """
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "—"
    v = float(x)
    if court and abs(v) >= 1000:
        return fmt_dec(v / 1000, 0 if v >= 10000 else 1, "Md€")
    return fmt_dec(v, 0, "M€")


def fmt_date_courte(d: Any) -> str:
    """« 1er oct. 2025 » — jumeau de `dateCourte()` dans format.js."""
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return "—"
    ts = pd.Timestamp(d)
    if pd.isna(ts):
        return "—"
    jour = "1er" if ts.day == 1 else str(ts.day)
    return f"{jour} {MOIS_FR[ts.month - 1]} {ts.year}"


def fmt_date(d: Any) -> str:
    if d is None or pd.isna(d):
        return "—"
    d = pd.Timestamp(d)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


# =============================================================================
#  BOÎTE À OUTILS STATISTIQUE
#  Implémentée à la main (bêta incomplète régularisée) pour éviter SciPy :
#  une dépendance de 60 Mo pour trois p-values ne se justifie pas.
#  Validée contre les tables de Student dans le bloc d’auto-test en bas de
#  fichier (`python core.py`).
# =============================================================================
def _betacf(a: float, b: float, x: float) -> float:
    """Fraction continue de Lentz pour la fonction bêta incomplète."""
    MAXIT, EPS, FPMIN = 300, 3.0e-16, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = FPMIN if abs(d) < FPMIN else d
        c = 1.0 + aa / c
        c = FPMIN if abs(c) < FPMIN else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = FPMIN if abs(d) < FPMIN else d
        c = 1.0 + aa / c
        c = FPMIN if abs(c) < FPMIN else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc_reg(a: float, b: float, x: float) -> float:
    """Fonction bêta incomplète régularisée I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    back = math.exp(lbeta + b * math.log1p(-x) + a * math.log(x))
    return 1.0 - back * _betacf(b, a, 1.0 - x) / b


def t_sf_two_sided(t: float, df: float) -> float:
    """P(|T| > |t|) pour une loi de Student à `df` degrés de liberté."""
    if df <= 0 or not math.isfinite(t):
        return float("nan")
    t = abs(float(t))
    return betainc_reg(df / 2.0, 0.5, df / (df + t * t))


def t_ppf(p: float, df: float) -> float:
    """Quantile de Student (bissection sur la fonction de répartition)."""
    if df <= 0:
        return float("nan")
    if p <= 0.5:
        return -t_ppf(1.0 - p, df)
    lo, hi = 0.0, 200.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        cdf = 1.0 - 0.5 * t_sf_two_sided(mid, df)
        if cdf < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def z_ppf(p: float) -> float:
    """Quantile de la loi normale centrée réduite (bissection sur erf)."""
    if not 0.0 < p < 1.0:
        return float("nan")
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def wilson_ci(succes: int, total: int, niveau: float = 0.95) -> tuple[float, float]:
    """Intervalle de confiance de Wilson : robuste aux petits effectifs,
    contrairement à l’intervalle normal qui déborde de [0, 1]."""
    if total <= 0:
        return (float("nan"), float("nan"))
    z = z_ppf(0.5 + niveau / 2.0)
    p = succes / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    marge = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - marge), min(1.0, centre + marge))


@dataclass(frozen=True)
class OLSResult:
    """Régression linéaire simple y = a + b·x, avec inférence complète."""
    n: int
    pente: float
    ordonnee: float
    r2: float
    r2_ajuste: float
    stderr_pente: float
    t_stat: float
    p_value: float
    ic_pente: tuple[float, float]
    sigma: float          # écart-type résiduel
    x_moyen: float
    sxx: float

    @property
    def significatif(self) -> bool:
        return bool(np.isfinite(self.p_value) and self.p_value < ALPHA)

    def predire(self, x: Iterable[float]) -> np.ndarray:
        x = np.asarray(list(x), dtype=float)
        return self.ordonnee + self.pente * x

    def bande(self, x: Iterable[float], niveau: float = 0.95,
              prediction: bool = False) -> tuple[np.ndarray, np.ndarray]:
        """Bande de confiance (moyenne) ou de prédiction (observation)."""
        x = np.asarray(list(x), dtype=float)
        ddl = self.n - 2
        if ddl <= 0 or not math.isfinite(self.sigma) or self.sxx <= 0:
            nan = np.full_like(x, np.nan, dtype=float)
            return nan, nan
        t = t_ppf(0.5 + niveau / 2.0, ddl)
        base = 1.0 / self.n + (x - self.x_moyen) ** 2 / self.sxx
        se = self.sigma * np.sqrt(base + (1.0 if prediction else 0.0))
        centre = self.predire(x)
        return centre - t * se, centre + t * se


def ols(x: Sequence[float], y: Sequence[float]) -> OLSResult | None:
    """Moindres carrés ordinaires sur deux vecteurs (NaN écartés)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = x.size
    if n < 3 or np.allclose(x, x[0]):
        return None
    x_moyen, y_moyen = x.mean(), y.mean()
    sxx = float(((x - x_moyen) ** 2).sum())
    sxy = float(((x - x_moyen) * (y - y_moyen)).sum())
    syy = float(((y - y_moyen) ** 2).sum())
    pente = sxy / sxx
    ordonnee = y_moyen - pente * x_moyen
    residus = y - (ordonnee + pente * x)
    sse = float((residus ** 2).sum())
    ddl = n - 2
    sigma = math.sqrt(sse / ddl) if ddl > 0 else float("nan")
    r2 = 1.0 - sse / syy if syy > 0 else float("nan")
    r2_aj = 1.0 - (1.0 - r2) * (n - 1) / ddl if ddl > 0 and math.isfinite(r2) else float("nan")
    se_pente = sigma / math.sqrt(sxx) if sxx > 0 else float("nan")
    t_stat = pente / se_pente if se_pente else float("nan")
    p = t_sf_two_sided(t_stat, ddl) if math.isfinite(t_stat) else float("nan")
    t_crit = t_ppf(0.975, ddl) if ddl > 0 else float("nan")
    return OLSResult(
        n=int(n), pente=float(pente), ordonnee=float(ordonnee), r2=float(r2),
        r2_ajuste=float(r2_aj), stderr_pente=float(se_pente), t_stat=float(t_stat),
        p_value=float(p), ic_pente=(pente - t_crit * se_pente, pente + t_crit * se_pente),
        sigma=float(sigma), x_moyen=float(x_moyen), sxx=sxx,
    )


@dataclass(frozen=True)
class Coefficient:
    nom: str
    valeur: float
    stderr: float
    t_stat: float
    p_value: float
    ic_bas: float
    ic_haut: float

    @property
    def significatif(self) -> bool:
        return bool(np.isfinite(self.p_value) and self.p_value < ALPHA)


@dataclass(frozen=True)
class MultiOLSResult:
    n: int
    r2: float
    r2_ajuste: float
    coefficients: list[Coefficient]
    cible: str

    @property
    def explicatives(self) -> list[Coefficient]:
        return [c for c in self.coefficients if c.nom != "Constante"]


def ols_multiple(X: pd.DataFrame, y: pd.Series, cible: str = "y") -> MultiOLSResult | None:
    """Régression multiple (matrice de conception + constante) avec t et p par
    coefficient. numpy.linalg.lstsq + variance sigma²·(XᵀX)⁻¹ : c’est tout ce
    qu’exige une analyse de facteurs explicatifs honnête."""
    data = X.copy()
    data["__y__"] = y.to_numpy()
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < len(X.columns) + 3:
        return None
    yv = data.pop("__y__").to_numpy(dtype=float)
    noms = ["Constante"] + list(data.columns)
    Xm = np.column_stack([np.ones(len(data)), data.to_numpy(dtype=float)])
    n, k = Xm.shape
    if n <= k:
        return None
    beta, *_ = np.linalg.lstsq(Xm, yv, rcond=None)
    residus = yv - Xm @ beta
    sse = float(residus @ residus)
    sst = float(((yv - yv.mean()) ** 2).sum())
    ddl = n - k
    sigma2 = sse / ddl
    try:
        xtx_inv = np.linalg.pinv(Xm.T @ Xm)
    except np.linalg.LinAlgError:
        return None
    se = np.sqrt(np.maximum(np.diag(sigma2 * xtx_inv), 0.0))
    t_crit = t_ppf(0.975, ddl)
    coefs: list[Coefficient] = []
    for nom, b, s in zip(noms, beta, se):
        t_stat = b / s if s > 0 else float("nan")
        p = t_sf_two_sided(t_stat, ddl) if math.isfinite(t_stat) else float("nan")
        coefs.append(Coefficient(nom=nom, valeur=float(b), stderr=float(s),
                                 t_stat=float(t_stat), p_value=float(p),
                                 ic_bas=float(b - t_crit * s), ic_haut=float(b + t_crit * s)))
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    r2_aj = 1.0 - (1.0 - r2) * (n - 1) / ddl if math.isfinite(r2) else float("nan")
    return MultiOLSResult(n=int(n), r2=float(r2), r2_ajuste=float(r2_aj),
                          coefficients=coefs, cible=cible)


# =============================================================================
#  GÉNÉRATEUR DE DONNÉES SYNTHÉTIQUES
# -----------------------------------------------------------------------------
#  DONNÉES DE DÉMONSTRATION — jamais présentées comme réelles : la source est
#  libellée « Données synthétiques » partout dans l’interface et dans le rapport.
#
#  Leur forme reproduit celle d’un pôle RFP réel : la due diligence croît
#  fortement sur dix ans pendant que le nombre de RFP reste stable, la charge
#  chute en août, les délais suivent le volume de questions, et les encours
#  gagnés sont très concentrés sur quelques mandats.
#
#  Le fichier produit est volontairement SALE (casse hétérogène, accents
#  manquants, dates et montants en texte, doublons, trous) et porte les noms de
#  colonnes de COLUMN_MAP : la chaîne de normalisation est donc réellement
#  exercée, et non court-circuitée.
# =============================================================================

# [BRANCHEMENT] Volumes annuels de la démonstration : (due diligence, RFP).
# Ces valeurs donnent à la fixture la trajectoire d’un pôle qui absorbe une
# charge de due diligence multipliée par quatre en dix ans, à effectif RFP
# constant. L’année en cours est calculée au prorata des jours écoulés.
VOLUMES_ANNUELS: dict[int, tuple[int, int]] = {
    2014: (52, 26), 2015: (60, 30), 2016: (55, 22), 2017: (48, 23),
    2018: (92, 20), 2019: (88, 19), 2020: (72, 21), 2021: (115, 17),
    2022: (138, 18), 2023: (178, 23), 2024: (163, 18), 2025: (203, 29),
    2026: (175, 32),
}

# [BRANCHEMENT] Encours gagnés par année, en millions d’euros. La collecte issue
# des RFP est par nature très irrégulière : un mandat remporté peut représenter
# plusieurs fois le total d’une année ordinaire.
AUM_GAGNE_ANNUEL: dict[int, float] = {
    2014: 120, 2015: 260, 2016: 180, 2017: 200, 2018: 300, 2019: 100,
    2020: 100, 2021: 700, 2022: 100, 2023: 900, 2024: 400, 2025: 2100,
    2026: 165,
}

_CLIENTS: list[tuple[str, str, str, str]] = [
    # (nom, type de client, pays, langue)
    ("Caisse de Retraite Helvetia", "Institutionnel", "Suisse", "Français"),
    ("Fondation Van der Berg", "Institutionnel", "Pays-Bas", "Anglais"),
    ("Régime de Prévoyance Atlantique", "Institutionnel", "France", "Français"),
    ("Assurances Mutuelles du Nord", "Institutionnel", "France", "Français"),
    ("Pensioenfonds Rijnmond", "Institutionnel", "Pays-Bas", "Anglais"),
    ("Nordic Pension Alliance", "Institutionnel", "Suède", "Anglais"),
    ("Fondo Previdenza Lombarda", "Institutionnel", "Italie", "Italien"),
    ("Stiftung Rheinland Vorsorge", "Institutionnel", "Allemagne", "Allemand"),
    ("Caja de Pensiones Ibérica", "Institutionnel", "Espagne", "Espagnol"),
    ("Sovereign Reserve Authority", "Institutionnel", "Singapour", "Anglais"),
    ("Université de Genève — Dotation", "Institutionnel", "Suisse", "Français"),
    ("Mutuelle Santé Rhône", "Institutionnel", "France", "Français"),
    ("Institution de Prévoyance Loire", "Institutionnel", "France", "Français"),
    ("Danske Pension Foreningen", "Institutionnel", "Danemark", "Anglais"),
    ("Banque Privée du Léman", "Distributeur", "Suisse", "Français"),
    ("Groupe Financier Bellecour", "Distributeur", "France", "Français"),
    ("Nordbank Wealth", "Distributeur", "Allemagne", "Allemand"),
    ("Plateforme Épargne Digitale", "Distributeur", "France", "Français"),
    ("Iberia Private Wealth", "Distributeur", "Espagne", "Espagnol"),
    ("Albion Wealth Partners", "Distributeur", "Royaume-Uni", "Anglais"),
    ("Banca Patrimoniale Veneta", "Distributeur", "Italie", "Italien"),
    ("Luxembourg Fund Platform", "Distributeur", "Luxembourg", "Anglais"),
    ("Assurance Vie Méditerranée", "Distributeur", "France", "Français"),
    ("Helvetia Private Banking", "Distributeur", "Suisse", "Allemand"),
    ("Cabinet Meridian Consulting", "Consultant", "Royaume-Uni", "Anglais"),
    ("Kestrel Investment Advisory", "Consultant", "Royaume-Uni", "Anglais"),
    ("Conseil Actuariel Lutèce", "Consultant", "France", "Français"),
    ("Delta Manager Research", "Consultant", "États-Unis", "Anglais"),
]

# Cabinets intermédiaires. La majorité des dossiers arrive en direct : un
# consultant systématiquement renseigné serait un signal faux.
_CONSULTANTS: list[tuple[str, float]] = [
    (VALEUR_INCONNUE, 0.52),              # dossier reçu en direct
    ("Meridian Consulting", 0.11),
    ("Kestrel Investment Advisory", 0.09),
    ("Delta Manager Research", 0.07),
    ("Northgate Investment Counsel", 0.06),
    ("Conseil Actuariel Lutèce", 0.05),
    ("Benelux Fiduciary Advisors", 0.04),
    ("Alpine Pension Advisors", 0.03),
    ("Iberian Manager Selection", 0.03),
]

# (fonds, classe d’actifs, sous-classe, expertise, forme juridique)
# Les expertises reprennent le vocabulaire de pilotage du pôle : ce sont des
# équipes de gestion, pas des catégories de produit.
_FONDS: list[tuple[str, str, str, str, str]] = [
    ("Horizon Actions Europe ISR", "Actions", "Actions Europe", "Actions Europe", "SICAV"),
    ("Horizon Actions Monde", "Actions", "Actions internationales", "Actions Internationales", "SICAV"),
    ("Sélection Small Caps Euro", "Actions", "Petites capitalisations", "Actions Europe", "FCP"),
    ("Convictions Actions Émergentes", "Actions", "Marchés émergents", "Actions Internationales", "SICAV Luxembourg"),
    ("Actions Thématiques Climat", "Actions", "Thématique climat", "Climate", "SICAV Luxembourg"),
    ("Rendement Obligations Euro", "Obligataire", "Obligations souveraines", "Diversified Euro", "FCP"),
    ("Crédit Investment Grade Euro", "Obligataire", "Crédit investment grade", "Credit IG", "SICAV"),
    ("Crédit Haut Rendement", "Obligataire", "Crédit haut rendement", "Credit HY", "SICAV Luxembourg"),
    ("Obligations Vertes Souveraines", "Obligataire", "Obligations vertes", "Climate", "FCP"),
    ("Dette Émergente Devises Fortes", "Obligataire", "Dette émergente", "Global Credit", "SICAV Luxembourg"),
    ("Crédit Global Agrégé", "Obligataire", "Crédit global", "Global Credit", "SICAV Luxembourg"),
    ("Obligations Datées 2029", "Obligataire", "Fonds à échéance", "Maturity Funds", "FCP"),
    ("Obligations Datées 2031", "Obligataire", "Fonds à échéance", "Maturity Funds", "FCP"),
    ("Allocation Patrimoine Équilibré", "Diversifié", "Allocation équilibrée", "Investment Solutions", "FCP"),
    ("Allocation Flexible Prudent", "Diversifié", "Allocation flexible", "Investment Solutions", "SICAV"),
    ("Retraite Horizon 2040", "Diversifié", "Épargne retraite", "Investment Solutions", "Fonds dédié"),
    ("Performance Absolue Market Neutral", "Alternatif", "Performance absolue", "Corporate", "SICAV Luxembourg"),
    ("Stratégie Global Macro", "Alternatif", "Global macro", "Corporate", "FIA"),
    ("Infrastructures Durables Europe", "Actifs réels", "Infrastructure", "Climate", "FIA"),
    ("Immobilier Core Zone Euro", "Actifs réels", "Immobilier core", "Corporate", "FIA"),
    ("Trésorerie Court Terme Euro", "Monétaire", "Monétaire standard", "Diversified Euro", "FCP"),
]

_ANALYSTES: list[tuple[str, float, float]] = [
    # (nom, part de la charge, coefficient de vitesse : < 1 = plus rapide)
    ("Camille Rousseau", 0.20, 0.86),
    ("Thomas Lefèvre", 0.18, 0.94),
    ("Inès Marchand", 0.16, 0.90),
    ("Julien Bertrand", 0.14, 1.08),
    ("Sofia Almeida", 0.13, 1.00),
    ("Marc Dubreuil", 0.11, 1.15),
    ("Léa Nguyen", 0.08, 1.05),
]

_SAISONNALITE = {1: 1.18, 2: 1.10, 3: 1.22, 4: 0.96, 5: 0.94, 6: 1.06,
                 7: 0.78, 8: 0.32, 9: 1.26, 10: 1.30, 11: 1.16, 12: 0.82}



def _logistique(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _repartir_sur_annee(rng: np.random.Generator, total: int, annee: int,
                        aujourdhui: pd.Timestamp) -> list[pd.Timestamp]:
    """Distribue `total` réceptions sur les jours ouvrés de l’année, en suivant
    la saisonnalité du pôle. L’année en cours est ramenée au prorata."""
    debut = pd.Timestamp(year=annee, month=1, day=1)
    fin = min(pd.Timestamp(year=annee, month=12, day=31), aujourdhui)
    if fin < debut:
        return []
    jours = pd.date_range(debut, fin, freq="B")
    if len(jours) == 0:
        return []
    if annee == aujourdhui.year:
        ecoule = sum(_SAISONNALITE[m] for m in range(1, aujourdhui.month)) \
            + _SAISONNALITE[aujourdhui.month] * aujourdhui.day / 30.0
        total = int(round(total * ecoule / sum(_SAISONNALITE.values())))
    if total <= 0:
        return []
    poids = np.array([_SAISONNALITE[j.month] for j in jours], dtype=float)
    poids /= poids.sum()
    return [pd.Timestamp(d) for d in rng.choice(jours.to_numpy(), size=total, p=poids)]


# Le classeur du pôle parle anglais pour plusieurs colonnes : la démonstration
# reproduit ce vocabulaire pour exercer les mêmes traductions que le vrai fichier.
_PAYS_EN = {"France": "France", "Suisse": "Switzerland", "Pays-Bas": "Netherlands",
            "Suède": "Sweden", "Italie": "Italy", "Allemagne": "Germany", "Espagne": "Spain",
            "Singapour": "Singapore", "Danemark": "Denmark", "Royaume-Uni": "UK",
            "Luxembourg": "Luxembourg", "États-Unis": "USA"}
_CLASSES_EN = {"Actions": "Equity", "Obligataire": "Fixed Income", "Diversifié": "Diversified",
               "Alternatif": "Hedge Funds", "Actifs réels": "Real assets", "Monétaire": "Money market"}
_FORMES_EN = {"SICAV": "Open-ended Fund", "FCP": "Open-ended Fund", "SICAV Luxembourg": "Open-ended Fund",
              "Fonds dédié": "Dedicated Fund", "FIA": "Dedicated Fund", "Mandat": "Mandate"}
_EXPERTISES_REELLES = {"Investment Solutions": "Open Architecture", "Corporate": "Corporate"}
_SEGMENTS_PAR_TYPE = {
    "Institutionnel": ["Pension/Retirement", "Insurance company", "Corporate", "Mutual", "Pension/Retirement"],
    "Distributeur": ["Private Bank", "Banking Network", "Asset management company", "Private Bank"],
    "Consultant": ["Consultant"],
}
_COMMERCIAUX: list[tuple[str, float]] = [
    ("Arnaud Perrier", 0.30), ("Jean-Michel Réau", 0.26), ("Vincent Priou", 0.22),
    ("Lionel Deny", 0.14), ("Claire Fontaine", 0.08),
]
# En-têtes du classeur, dans l’ordre du fichier : c’est le format que la
# démonstration produit et que le moteur lit.
COLONNES_CLASSEUR: tuple[str, ...] = (
    "Numero", "Année", "Month", "Date de réception", "Date de fin", "Client", "Segment",
    "Type de client", "Country", "Consultant", "Writer", "Reviewer", "Type", "Volume", "Number",
    "Step_1", "Step_2", "ORAL_RFP", "Status", "Qvidian Update", "Result", "Expertise",
    "Legal form", "Asset class", "Sub-asset class", "4Change", "SRI", "% ESG", "Reference fund",
    "Sales", "Language",
)


def generate_fake_data(seed: int = FAKE_SEED,
                       aujourdhui: dt.date | None = None) -> pd.DataFrame:
    """Jeu de données de démonstration couvrant VOLUMES_ANNUELS, au format
    exact du classeur du pôle (COLONNES_CLASSEUR)."""
    rng = np.random.default_rng(seed)
    today = pd.Timestamp(aujourdhui or dt.date.today()).normalize()

    poids_analystes = np.array([a[1] for a in _ANALYSTES], dtype=float)
    poids_analystes /= poids_analystes.sum()
    poids_consultants = np.array([c[1] for c in _CONSULTANTS], dtype=float)
    poids_consultants /= poids_consultants.sum()
    poids_commerciaux = np.array([c[1] for c in _COMMERCIAUX], dtype=float)
    poids_commerciaux /= poids_commerciaux.sum()
    appetence = {"Institutionnel": 7.0, "Distributeur": 6.0, "Consultant": 4.5}
    poids_clients = rng.dirichlet(np.array([appetence[c[1]] for c in _CLIENTS]))
    poids_fonds = rng.dirichlet(np.full(len(_FONDS), 6.0))
    # Un client garde son segment et son commercial d’un dossier à l’autre.
    segment_client = {c[0]: str(rng.choice(_SEGMENTS_PAR_TYPE[c[1]])) for c in _CLIENTS}
    commercial_client = {c[0]: _COMMERCIAUX[int(rng.choice(len(_COMMERCIAUX), p=poids_commerciaux))][0]
                         for c in _CLIENTS}

    lignes: list[dict[str, Any]] = []
    for annee, (n_dd, n_rfp) in VOLUMES_ANNUELS.items():
        if annee > today.year:
            continue
        for famille, total in ((FAMILLE_DD, n_dd), (FAMILLE_RFP, n_rfp)):
            for reception in _repartir_sur_annee(rng, total, annee, today):
                type_demande = famille
                i_client = int(rng.choice(len(_CLIENTS), p=poids_clients))
                client, type_client, pays, langue = _CLIENTS[i_client]
                i_fonds = int(rng.choice(len(_FONDS), p=poids_fonds))
                fonds, classe, sous_classe, expertise_equipe, forme = _FONDS[i_fonds]
                expertise = _EXPERTISES_REELLES.get(expertise_equipe, "High Conviction")
                i_analyste = int(rng.choice(len(_ANALYSTES), p=poids_analystes))
                analyste, _, vitesse = _ANALYSTES[i_analyste]
                relecteur = _ANALYSTES[int(rng.choice(len(_ANALYSTES)))][0] if rng.random() < 0.7 else None
                if relecteur == analyste:
                    relecteur = None
                if famille == FAMILLE_RFP or rng.random() < 0.18:
                    consultant = _CONSULTANTS[int(rng.choice(len(_CONSULTANTS), p=poids_consultants))][0]
                else:
                    consultant = VALEUR_INCONNUE

                # La charge de rédaction pilote le délai ; elle n’est pas exportée.
                base_q = {FAMILLE_RFP: 4.85, FAMILLE_DD: 4.35}[famille]
                nb_questions = int(np.clip(rng.lognormal(base_q, 0.42), 8, 600))

                pente_esg = _logistique((annee - 2020.5) / 1.9)
                if annee < 2017 and rng.random() < 0.55:
                    part_esg = float("nan")
                else:
                    moyenne = 0.10 + 0.72 * pente_esg + (0.10 if expertise_equipe == "Climate" else 0)
                    part_esg = float(np.clip(rng.beta(2.2, max(0.6, 2.2 * (1 - moyenne) / max(moyenne, 1e-3))), 0, 1))
                sri = (part_esg == part_esg) and (part_esg >= 0.5 or "ISR" in fonds or "Vertes" in fonds
                                                  or "Climat" in fonds)

                attendu = (2.5 + 0.062 * nb_questions * vitesse
                           + {FAMILLE_RFP: 2.0, FAMILLE_DD: 1.0}[famille]
                           + (1.8 if langue != "Français" else 0.0))
                delai = int(np.clip(round(rng.gamma(shape=6.0, scale=max(attendu, 1.0) / 6.0)), 1, 90))
                if rng.random() < 0.04:
                    delai = int(min(90, delai * rng.uniform(1.8, 3.0)))
                envoi = pd.Timestamp(np.busday_offset(reception.date(), delai, roll="forward"))

                etape_1 = etape_2 = oral = None
                if famille == FAMILLE_DD:
                    if rng.random() < 0.012:
                        statut, envoi_final = STATUT_ABANDONNE, pd.NaT
                    elif envoi > today:
                        statut, envoi_final = STATUT_EN_COURS, pd.NaT
                    else:
                        statut, envoi_final = STATUT_ENVOYE, envoi
                else:
                    sla = SLA_JOURS_OUVRES.get(type_demande, SLA_DEFAUT)
                    if rng.random() < 0.05:
                        statut, envoi_final = STATUT_ABANDONNE, pd.NaT
                        etape_1 = etape_2 = oral = 0
                    elif envoi > today:
                        statut, envoi_final = STATUT_EN_COURS, pd.NaT
                        etape_1 = etape_2 = oral = 0
                    else:
                        envoi_final = envoi
                        z = (-0.95
                             + {"Institutionnel": 0.08, "Distributeur": 0.22, "Consultant": -0.18}[type_client]
                             + {"Actions": 0.10, "Obligataire": 0.16, "Diversifié": 0.02,
                                "Alternatif": -0.22, "Actifs réels": -0.05, "Monétaire": 0.24}[classe]
                             - 0.050 * max(0, delai - sla)
                             + (0.14 if vitesse < 0.95 else 0.0))
                        decision = envoi + pd.Timedelta(days=int(rng.integers(45, 240)))
                        if decision > today:
                            statut = STATUT_ENVOYE
                        else:
                            statut = STATUT_GAGNE if rng.random() < _logistique(z) else STATUT_PERDU
                        # Le chemin : remis, puis présélectionné, puis soutenu à l’oral.
                        # Un mandat gagné a presque toujours passé les trois étapes.
                        etape_1 = 1
                        gagne = statut == STATUT_GAGNE
                        etape_2 = 1 if rng.random() < (0.92 if gagne else 0.48) else 0
                        oral = 1 if (etape_2 and rng.random() < (0.85 if gagne else 0.55)) else 0

                lignes.append({
                    "date_reception": reception, "date_envoi": envoi_final,
                    "type_demande": type_demande, "client": client, "segment": segment_client[client],
                    "consultant": consultant, "type_client": type_client, "pays": pays,
                    "fonds": fonds, "classe_actifs": classe, "sous_classe_actifs": sous_classe,
                    "forme_juridique": forme, "expertise": expertise, "statut": statut,
                    "analyste": analyste, "relecteur": relecteur, "commercial": commercial_client[client],
                    "etape_1": etape_1, "etape_2": etape_2, "oral": oral, "sri": sri,
                    "qvidian": (rng.random() < 0.4) if (famille == FAMILLE_RFP and statut != STATUT_EN_COURS) else None,
                    "part_esg": part_esg if part_esg == part_esg else np.nan,
                    "langue": langue, "montant_potentiel": float("nan"),
                    "_annee": annee, "_famille": famille,
                })

    propre = pd.DataFrame(lignes).sort_values("date_reception").reset_index(drop=True)
    propre = _attribuer_encours(propre, rng)
    propre = propre.drop(columns=["_annee", "_famille"])
    return _salir(propre, rng)


def _attribuer_encours(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Répartit l’encours gagné de chaque année sur ses RFP remportés, et donne
    aux RFP encore ouverts un encours potentiel du même ordre de grandeur.

    La collecte est très concentrée : une année se joue souvent sur un mandat.
    """
    df = df.copy()
    for annee, total in AUM_GAGNE_ANNUEL.items():
        gagnes = df.index[(df["_annee"] == annee) & (df["statut"] == STATUT_GAGNE)]
        if len(gagnes) == 0 or total <= 0:
            continue
        parts = rng.dirichlet(np.full(len(gagnes), 0.8))    # alpha < 1 : forte concentration
        df.loc[gagnes, "montant_potentiel"] = np.round(parts * total, 2)

    reference = df.loc[df["statut"] == STATUT_GAGNE, "montant_potentiel"].dropna()
    mediane = float(reference.median()) if len(reference) else 60.0
    ouverts = df.index[(df["_famille"] == FAMILLE_RFP) & (df["statut"] != STATUT_GAGNE)]
    if len(ouverts):
        df.loc[ouverts, "montant_potentiel"] = np.round(
            np.clip(rng.lognormal(math.log(max(mediane, 1.0)), 1.05, len(ouverts)), 2, 4000), 2)
    return df


_VARIANTES_STATUS_CLASSEUR = {
    STATUT_EN_COURS: ["In progress", "In Progress", "in progress", "IN PROGRESS"],
    STATUT_ENVOYE: ["Done", "done", "DONE", "Done "],
    STATUT_GAGNE: ["Done", "done", "Done"],
    STATUT_PERDU: ["Done", "done", "DONE"],
    STATUT_ABANDONNE: ["Cancelled", "Canceled", "cancelled"],
}
_VARIANTES_RESULT = {
    STATUT_GAGNE: ["Won", "won", "WON", "Won "],
    STATUT_PERDU: ["Lost", "lost", "LOST"],
}
_VARIANTES_TYPE_CLASSEUR = {
    "RFP": ["RFP", "RFP", "rfp", "RFP "],
    "Due Diligence": ["Due Diligence", "Due Diligence", "Due diligence", "due diligence"],
}
_VARIANTES_TYPE_CLIENT_CLASSEUR = {
    "Institutionnel": ["Instit.", "Instit.", "Instit", "instit."],
    "Distributeur": ["Distr.", "Distr.", "Distr", "distr."],
    "International": ["Intern.", "Intern.", "Intern", "intern."],
}


def _salir(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Le classeur tel qu’il sort d’Excel : en-têtes du pôle, vocabulaire
    anglais, casse hétérogène, dates et montants parfois en texte, doublons."""
    brut = pd.DataFrame(index=df.index)

    def variante(valeurs: pd.Series, table: dict[str, list[str]]) -> list[Any]:
        return [rng.choice(table[v]) if v in table else v for v in valeurs]

    def dates_mixtes(col: pd.Series) -> list[Any]:
        out: list[Any] = []
        for v in col:
            if pd.isna(v):
                out.append(pd.NaT)
            elif rng.random() < 0.08:
                out.append(f"{v.day:02d}/{v.month:02d}/{v.year}")
            else:
                out.append(v)
        return out

    def binaire(col: pd.Series) -> list[Any]:
        out: list[Any] = []
        for v in col:
            if v is None or (isinstance(v, float) and math.isnan(v)):
                out.append(np.nan)
            elif isinstance(v, (bool, np.bool_)):
                out.append(("Yes" if v else "No") if rng.random() < 0.85 else (1 if v else 0))
            else:
                out.append(int(v))
        return out

    est_rfp = df["type_demande"].eq("RFP")
    brut["Numero"] = np.arange(1, len(df) + 1)
    brut["Année"] = df["date_reception"].dt.year.to_numpy()
    brut["Month"] = df["date_reception"].dt.month.to_numpy()
    brut["Date de réception"] = dates_mixtes(df["date_reception"])
    brut["Date de fin"] = dates_mixtes(df["date_envoi"])
    brut["Client"] = [v.upper() if rng.random() < 0.05 else (v + " " if rng.random() < 0.05 else v)
                      for v in df["client"]]
    brut["Segment"] = df["segment"].to_numpy()
    # Le classeur distingue l’international du reste : un client hors de France
    # est « Intern. », les autres gardent leur nature commerciale.
    type_client = [("International" if (p != "France" and rng.random() < 0.8)
                    else ("Institutionnel" if t == "Consultant" else t))
                   for t, p in zip(df["type_client"], df["pays"])]
    brut["Type de client"] = variante(pd.Series(type_client), _VARIANTES_TYPE_CLIENT_CLASSEUR)
    brut["Country"] = [np.nan if rng.random() < 0.02 else _PAYS_EN.get(v, v) for v in df["pays"]]
    brut["Consultant"] = ["None" if v == VALEUR_INCONNUE else v for v in df["consultant"]]
    brut["Writer"] = df["analyste"].to_numpy()
    brut["Reviewer"] = [np.nan if v is None else v for v in df["relecteur"]]
    brut["Type"] = variante(df["type_demande"], _VARIANTES_TYPE_CLASSEUR)
    # Volume = encours en M€ ; une due diligence porte 0, comme dans le classeur.
    brut["Volume"] = [
        (0 if not r else (f"{v:,.1f}".replace(",", " ").replace(".", ",") if pd.notna(v) and rng.random() < 0.08
                          else (round(float(v), 1) if pd.notna(v) else np.nan)))
        for v, r in zip(df["montant_potentiel"], est_rfp)]
    brut["Number"] = 1
    brut["Step_1"] = binaire(df["etape_1"])
    brut["Step_2"] = binaire(df["etape_2"])
    brut["ORAL_RFP"] = binaire(df["oral"])
    brut["Status"] = variante(df["statut"], _VARIANTES_STATUS_CLASSEUR)
    brut["Qvidian Update"] = binaire(df["qvidian"])
    brut["Result"] = [rng.choice(_VARIANTES_RESULT[s]) if s in _VARIANTES_RESULT
                      else rng.choice(["NA", "NA", "N/A", np.nan]) for s in df["statut"]]
    brut["Expertise"] = df["expertise"].to_numpy()
    brut["Legal form"] = [_FORMES_EN.get(v, v) for v in df["forme_juridique"]]
    brut["Asset class"] = [_CLASSES_EN.get(v, v) for v in df["classe_actifs"]]
    brut["Sub-asset class"] = df["sous_classe_actifs"].to_numpy()
    brut["4Change"] = np.nan
    brut["SRI"] = [np.nan if (s is None or s is False and rng.random() < 0.1) else ("Yes" if s else "No")
                   for s in df["sri"]]
    esg: list[Any] = []
    for v in df["part_esg"]:
        if pd.isna(v):
            esg.append(np.nan)
        else:
            tirage = rng.random()
            if tirage < 0.70:                         # la tranche écrite du classeur
                esg.append("< 25% ESG" if v < 0.25 else ("25-50%" if v < 0.5
                           else ("50-75%" if v < 0.75 else "75%")))
            elif tirage < 0.90:
                esg.append(f"{round(float(v) * 100)} %")
            else:
                esg.append(round(float(v), 3))
    brut["% ESG"] = esg
    brut["Reference fund"] = df["fonds"].to_numpy()
    brut["Sales"] = df["commercial"].to_numpy()
    brut["Language"] = ["FR" if v == "Français" else ("EN" if v == "Anglais" else v) for v in df["langue"]]
    brut = brut[list(COLONNES_CLASSEUR)]
    doublons = brut.sample(frac=0.012, random_state=int(rng.integers(0, 10_000)))
    return pd.concat([brut, doublons], ignore_index=True).sample(
        frac=1.0, random_state=7).reset_index(drop=True)

# =============================================================================
#  CHARGEMENT, NORMALISATION, ENRICHISSEMENT
# =============================================================================
class DonneesInvalides(RuntimeError):
    """Levée quand le fichier source est inexploitable — message actionnable."""


@dataclass
class LoadReport:
    """Journal de qualité des données, affiché tel quel dans l’application."""
    source: str = ""
    n_lignes_source: int = 0
    n_lignes_retenues: int = 0
    colonnes_absentes: list[str] = field(default_factory=list)
    colonnes_ignorees: list[str] = field(default_factory=list)
    lignes_sans_date: int = 0
    doublons_supprimes: int = 0
    dates_illisibles: dict[str, int] = field(default_factory=dict)
    valeurs_inconnues: dict[str, list[str]] = field(default_factory=dict)
    incoherences: dict[str, int] = field(default_factory=dict)
    horodatage: dt.datetime = field(default_factory=dt.datetime.now)
    # "demo" (données de démonstration) ou "fichier" (classeur branché)
    mode: str = "demo"
    fichier: str = ""
    onglet: str = ""
    correspondance: dict[str, str] = field(default_factory=dict)

    @property
    def est_demo(self) -> bool:
        return self.mode == "demo"

    @property
    def alertes(self) -> list[str]:
        msgs: list[str] = []
        if self.colonnes_absentes:
            libelles = ", ".join(COLUMN_MAP.get(c, c) for c in self.colonnes_absentes)
            msgs.append(f"Colonnes absentes du fichier, analyses correspondantes masquées : {libelles}.")
        if self.lignes_sans_date:
            a = accord(self.lignes_sans_date)
            msgs.append(f"{pluriel(self.lignes_sans_date, 'ligne')} sans date de "
                        f"réception exploitable, écartée{a}.")
        if self.doublons_supprimes:
            a = accord(self.doublons_supprimes)
            msgs.append(f"{pluriel(self.doublons_supprimes, 'doublon')} strict{a} "
                        f"supprimé{a}.")
        for col, n in self.dates_illisibles.items():
            msgs.append(f"{pluriel(n, 'date')} illisible{accord(n)} dans "
                        f"« {COLUMN_MAP.get(col, col)} ».")
        for col, vals in self.valeurs_inconnues.items():
            if col == "type_demande":
                # Le vocabulaire est fermé : l’intitulé étranger n’est pas recopié,
                # il a rejoint la due diligence.
                a = accord(len(vals))
                msgs.append(f"{pluriel(len(vals), 'intitulé')} de type non reconnu{a}, "
                            f"rattaché{a} à la due diligence.")
                continue
            apercu = ", ".join(f"« {v} »" for v in vals[:5])
            suite = " …" if len(vals) > 5 else ""
            a = accord(len(vals))
            msgs.append(f"Modalité{a} non reconnue{a} dans "
                        f"« {COLUMN_MAP.get(col, col)} » : {apercu}{suite} "
                        f"→ à ajouter dans la table de normalisation.")
        for libelle, n in self.incoherences.items():
            msgs.append(f"{pluriel(n, 'ligne')} : {libelle}.")
        return msgs

    @property
    def est_propre(self) -> bool:
        return not self.alertes


def _strip_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte)
                   if not unicodedata.combining(c))


def _cle(valeur: Any) -> str:
    """Clé de comparaison tolérante : minuscules, sans accent, sans ponctuation
    de séparation. « Date Réception » == « date_reception » == « DATE-RECEPTION »."""
    if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
        return ""
    texte = _strip_accents(str(valeur)).lower().strip()
    texte = re.sub(r"[\s_\-./'\u2019]+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def _resoudre_colonnes(colonnes: Iterable[str],
                       forcees: Mapping[str, str] | None = None
                       ) -> tuple[dict[str, str], list[str], list[str]]:
    """Associe chaque champ interne à la colonne réelle du fichier.

    `forcees` : correspondance décidée par l’utilisateur (écran « Données » ou
    data/branchement.json) ; elle prime sur la reconnaissance automatique.
    Une colonne forcée absente du fichier est ignorée, jamais inventée.
    """
    colonnes = list(colonnes)
    index = {}
    for col in colonnes:
        index.setdefault(_cle(col), col)
    # Second passage, sans le contenu des parenthèses ni les unités en fin
    # d’intitulé : « Ticket (M€) » et « Montant en EUR » se reconnaissent.
    for col in colonnes:
        court = _cle(re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(col)))
        court = re.sub(r"\b(en|in)?\s*(m€|k€|€|eur|euros?|meur|keur|%|pct|j|jours?|days?)$", "",
                       court).strip()
        if court:
            index.setdefault(court, col)
    trouvees: dict[str, str] = {}
    absentes: list[str] = []
    presentes = set(colonnes)
    for champ, nom_attendu in COLUMN_MAP.items():
        forcee = (forcees or {}).get(champ)
        if forcee and forcee in presentes:
            trouvees[champ] = forcee
            continue
        candidats = [nom_attendu, champ, *COLUMN_ALIASES.get(champ, [])]
        reelle = next((index[c] for c in map(_cle, candidats) if c in index), None)
        if reelle is None:
            absentes.append(champ)
        else:
            trouvees[champ] = reelle
    utilisees = set(trouvees.values())
    ignorees = [c for c in colonnes if c not in utilisees]
    return trouvees, absentes, ignorees


def _vers_datetime(serie: pd.Series) -> tuple[pd.Series, int]:
    """Parse une colonne de dates hétérogène : datetime, texte jj/mm/aaaa,
    numéro de série Excel. Retourne la série et le nombre d’échecs."""
    if serie.empty:
        return pd.to_datetime(serie, errors="coerce"), 0
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie.dt.tz_localize(None) if getattr(serie.dtype, "tz", None) else serie, 0

    brut = serie.copy()
    resultat = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")

    numerique = pd.to_numeric(brut, errors="coerce")
    masque_serie_excel = numerique.between(20000, 60000) & brut.map(
        lambda v: not isinstance(v, str) or _cle(v).replace(" ", "").isdigit())
    if masque_serie_excel.any():
        resultat.loc[masque_serie_excel] = pd.to_datetime(
            numerique[masque_serie_excel], unit="D", origin="1899-12-30", errors="coerce")

    reste = ~masque_serie_excel
    if reste.any():
        try:
            # format="mixed" n’existe qu’à partir de pandas 2.0 : sur 1.x il
            # serait pris pour un format littéral et produirait des NaT muets.
            parse = (pd.to_datetime(brut[reste], errors="coerce", dayfirst=True, format="mixed")
                     if _PANDAS_2 else
                     pd.to_datetime(brut[reste], errors="coerce", dayfirst=True))
        except (ValueError, TypeError):
            parse = pd.to_datetime(brut[reste], errors="coerce", dayfirst=True)
        resultat.loc[reste] = parse

    non_vide = brut.notna() & (brut.astype(str).str.strip() != "")
    echecs = int((non_vide & resultat.isna()).sum())
    return resultat.dt.normalize(), echecs


def _vers_nombre(serie: pd.Series) -> pd.Series:
    """Accepte 12500, « 12 500,50 € », « 12,500.50 » et les cellules vides."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    def convertir(v: Any) -> float:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return float("nan")
        if isinstance(v, (int, float, np.integer, np.floating)):
            return float(v)
        texte = re.sub(r"[^\d,.\-]", "", str(v).replace(" ", "").replace(" ", ""))
        if not texte or texte in {"-", ".", ","}:
            return float("nan")
        if "," in texte and "." in texte:               # 12.500,50 ou 12,500.50
            texte = (texte.replace(".", "").replace(",", ".")
                     if texte.rfind(",") > texte.rfind(".") else texte.replace(",", ""))
        elif "," in texte:
            texte = texte.replace(",", ".")
        try:
            return float(texte)
        except ValueError:
            return float("nan")

    return serie.map(convertir).astype(float)


def _vers_esg(serie: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Part ESG d’un questionnaire → (fraction 0-1, tranche).

    Plusieurs écritures coexistent : une fraction (0,45), un pourcentage
    (« 45 % »), une tranche (« < 25% ESG », « 25-50% », « 50-75% », « 75% »,
    « > 75 % ESG »). Une tranche ne donne QUE la tranche : en déduire un
    pourcentage précis serait inventer une donnée absente.
    """
    def _bande(fraction: float) -> str:
        return ESG_FORT if fraction >= ESG_SEUIL_FORT else (ESG_MOYEN if fraction >= 0.25 else ESG_FAIBLE)

    parts: list[float] = []
    bandes: list[str] = []
    for valeur in serie:
        if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
            parts.append(float("nan")); bandes.append(ESG_INCONNU); continue
        if isinstance(valeur, (int, float, np.integer, np.floating)):
            fraction = float(valeur)
            if fraction > 1.0:
                fraction /= 100.0
            fraction = min(max(fraction, 0.0), 1.0)
            parts.append(fraction); bandes.append(_bande(fraction)); continue

        texte = str(valeur).strip()
        cle = _cle(texte)
        if cle in ("", "na", "n a", "none", "nan", "non renseigne", "non renseigné"):
            parts.append(float("nan")); bandes.append(ESG_INCONNU); continue
        nombres = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", texte)]
        est_tranche = any(m in cle for m in ("<", ">", "moins", "plus", "under", "over", "below",
                                              "above", "esg", "high", "low", "medium", "entre")) \
            or len(nombres) >= 2 or "-" in texte or "–" in texte
        if not nombres:
            # Tranche écrite sans chiffre : « high ESG », « low ESG »
            if any(m in cle for m in ("high", "fort", "forte", "eleve", "élevé")):
                parts.append(float("nan")); bandes.append(ESG_FORT); continue
            if any(m in cle for m in ("low", "faible", "bas")):
                parts.append(float("nan")); bandes.append(ESG_FAIBLE); continue
            if any(m in cle for m in ("medium", "moyen", "moyenne", "intermediaire")):
                parts.append(float("nan")); bandes.append(ESG_MOYEN); continue
            parts.append(float("nan")); bandes.append(ESG_INCONNU); continue
        if len(nombres) >= 2:                          # « 25-50% » : le milieu de la tranche
            repere = (nombres[0] + nombres[1]) / 2
        elif any(m in cle for m in ("<", "moins", "under", "below")):
            repere = nombres[0] / 2                    # « < 25% » : sous le seuil
        else:
            repere = nombres[0]                        # « 75% », « > 75 % » : au seuil ou au-dessus
        fraction = repere / 100.0 if repere > 1.0 else repere
        fraction = min(max(fraction, 0.0), 1.0)
        parts.append(float("nan") if est_tranche else fraction)
        bandes.append(_bande(fraction))
    return (pd.Series(parts, index=serie.index, dtype=float),
            pd.Series(bandes, index=serie.index, dtype=object))


def _nettoyer_texte(serie: pd.Series) -> pd.Series:
    """Espaces normalisés ; « None », « NA », « - » et consorts valent une absence."""
    texte = serie.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    vide = texte.str.lower().isin(["", "nan", "none", "null", "na", "n/a", "n.a.", "-", "—", "–",
                                   "aucun", "aucune", "non renseigne", "non renseigné", "?"])
    return texte.mask(vide, pd.NA)


def _vers_binaire(serie: pd.Series) -> pd.Series:
    """Oui / non sous toutes leurs écritures → 1.0, 0.0 ou NaN (non renseigné)."""
    def convertir(v: Any) -> float:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return float("nan")
        if isinstance(v, (bool, np.bool_)):
            return 1.0 if v else 0.0
        if isinstance(v, (int, float, np.integer, np.floating)):
            return 1.0 if float(v) > 0 else 0.0
        cle = _cle(v)
        if cle in ("", "na", "n a", "nan", "none"):
            return float("nan")
        if cle in ("1", "yes", "y", "oui", "o", "true", "x", "done", "ok", "fait", "won", "vrai"):
            return 1.0
        if cle in ("0", "no", "n", "non", "false", "faux", "lost"):
            return 0.0
        try:
            return 1.0 if float(cle.replace(",", ".")) > 0 else 0.0
        except ValueError:
            return float("nan")
    return serie.map(convertir).astype(float)


def _oui_non(binaire: pd.Series) -> pd.Series:
    return pd.Series(np.where(binaire == 1.0, "Oui", np.where(binaire == 0.0, "Non", VALEUR_INCONNUE)),
                     index=binaire.index, dtype=object)


def _unifier_libelles(serie: pd.Series) -> pd.Series:
    """« BNP PARIBAS », « bnp paribas » et « BNP Paribas  » désignent le même
    client : on retient l’orthographe la plus fréquente."""
    valides = serie.dropna()
    if valides.empty:
        return serie
    cles = valides.map(_cle)
    canon: dict[str, str] = {}
    for cle, groupe in valides.groupby(cles, sort=False):
        canon[cle] = groupe.value_counts().index[0]
    return serie.map(lambda v: canon.get(_cle(v), v) if pd.notna(v) else v)


def _appliquer_normalisation(serie: pd.Series, table: Mapping[str, str],
                             champ: str, rapport: LoadReport,
                             titre_par_defaut: bool = True,
                             defaut: str | None = None) -> pd.Series:
    """Applique une table de normalisation ; journalise les modalités inconnues
    sans jamais les faire disparaître (elles restent visibles, titrées).

    `defaut` : la valeur que prend une modalité inconnue quand le champ n’admet
    qu’un vocabulaire fermé — le type de demande, par exemple, ne connaît que
    RFP et Due Diligence : tout intitulé étranger rejoint la due diligence."""
    index = {_cle(k): v for k, v in table.items()}
    inconnues: dict[str, None] = {}

    def convertir(v: Any) -> Any:
        if pd.isna(v):
            return VALEUR_INCONNUE if defaut is None else defaut
        cle = _cle(v)
        if cle in index:
            return index[cle]
        inconnues.setdefault(str(v).strip(), None)
        if defaut is not None:
            return defaut
        return str(v).strip().capitalize() if titre_par_defaut else str(v).strip()

    resultat = serie.map(convertir)
    if inconnues:
        rapport.valeurs_inconnues[champ] = sorted(inconnues)
    return resultat


def normalize(brut: pd.DataFrame, source: str = "",
              correspondance: Mapping[str, str] | None = None
              ) -> tuple[pd.DataFrame, LoadReport]:
    """Fichier brut → table canonique. Aucune ligne n’est écartée silencieusement."""
    rapport = LoadReport(source=source, n_lignes_source=len(brut))
    brut = brut.copy()
    brut.columns = [str(c).strip() for c in brut.columns]
    colonnes, absentes, ignorees = _resoudre_colonnes(list(brut.columns), correspondance)
    rapport.colonnes_absentes = absentes
    rapport.colonnes_ignorees = ignorees

    # Une date de réception absente se reconstruit depuis Année + Month ; un
    # statut absent se déduit de Result. Ni l’un ni l’autre n’est alors « manquant ».
    reconstructibles = set()
    if "date_reception" in absentes and "annee_source" in colonnes:
        reconstructibles.add("date_reception")
    if "statut" in absentes and "resultat_brut" in colonnes:
        reconstructibles.add("statut")
    manquantes_critiques = [c for c in REQUIRED_FIELDS if c in absentes and c not in reconstructibles]
    if manquantes_critiques:
        a = accord(len(manquantes_critiques))
        attendues = ", ".join(f"« {COLUMN_MAP[c]} »" for c in manquantes_critiques)
        presentes = ", ".join(f"« {c} »" for c in list(brut.columns)[:20]) or "aucune"
        raise DonneesInvalides(
            f"Colonne{a} indispensable{a} introuvable{a} : {attendues}.\n"
            f"Colonnes présentes dans le fichier : {presentes}.\n"
            f"→ Indiquer la bonne colonne dans l’écran « Données », ou ajouter "
            f"l’intitulé à COLUMN_ALIASES en tête de core.py."
        )

    df = pd.DataFrame(index=brut.index)
    for champ, colonne in colonnes.items():
        df[champ] = brut[colonne]

    # --- Dates -------------------------------------------------------------
    for champ in ("date_reception", "date_envoi"):
        if champ in df:
            df[champ], echecs = _vers_datetime(df[champ])
            if echecs:
                rapport.dates_illisibles[champ] = echecs
        else:
            df[champ] = pd.NaT
    if "annee_source" in df:
        annee = pd.to_numeric(df["annee_source"], errors="coerce")
        mois = (pd.to_numeric(df["mois_source"], errors="coerce") if "mois_source" in df
                else pd.Series(np.nan, index=df.index)).fillna(1).clip(1, 12)
        cadre = pd.DataFrame({"year": annee, "month": mois, "day": 1})
        reconstruite = pd.to_datetime(cadre.where(annee.notna()), errors="coerce")
        a_completer = df["date_reception"].isna() & reconstruite.notna()
        if a_completer.any():
            df.loc[a_completer, "date_reception"] = reconstruite[a_completer]
            rapport.incoherences["date de réception reconstituée depuis Année et Month"] = int(a_completer.sum())
    for champ in ("annee_source", "mois_source"):
        if champ in df:
            df = df.drop(columns=champ)

    # --- Identifiant -------------------------------------------------------
    if "numero" in df:
        df["numero"] = _nettoyer_texte(df["numero"]).astype(object)
    else:
        df["numero"] = pd.NA

    # --- Nombres -----------------------------------------------------------
    for champ in ("nb_questions", "montant_potentiel"):
        df[champ] = _vers_nombre(df[champ]) if champ in df else np.nan
    df.loc[df["nb_questions"] <= 0, "nb_questions"] = np.nan
    # Un encours nul ou négatif n’est pas un encours : c’est une absence
    # (une due diligence porte 0 dans le classeur).
    df.loc[df["montant_potentiel"] <= 0, "montant_potentiel"] = np.nan

    # --- Binaires : étapes du processus, ISR, Qvidian -----------------------
    for champ in ("etape_1", "etape_2", "oral", "sri", "qvidian"):
        df[champ] = _vers_binaire(df[champ]) if champ in df else np.nan

    # --- Part ESG ----------------------------------------------------------
    if "part_esg" in df:
        df["part_esg"], df["bande_esg"] = _vers_esg(df["part_esg"])
    else:
        df["part_esg"] = np.nan
        df["bande_esg"] = ESG_INCONNU

    # --- Modalités ---------------------------------------------------------
    for champ in ("type_demande", "statut", "type_client", "langue", "resultat_brut",
                  "client", "pays", "fonds", "classe_actifs", "analyste", "relecteur",
                  "consultant", "sous_classe_actifs", "forme_juridique", "expertise",
                  "segment", "commercial"):
        df[champ] = _nettoyer_texte(df[champ]) if champ in df else pd.Series(pd.NA, index=df.index, dtype="string")

    df["type_demande"] = _appliquer_normalisation(df["type_demande"], TYPE_NORMALIZATION,
                                                  "type_demande", rapport, defaut=FAMILLE_DD)
    df["type_client"] = _appliquer_normalisation(df["type_client"], CLIENT_TYPE_NORMALIZATION, "type_client", rapport)
    df["langue"] = _appliquer_normalisation(df["langue"], LANGUE_NORMALIZATION, "langue", rapport)
    df["segment"] = _appliquer_normalisation(df["segment"], SEGMENT_NORMALIZATION, "segment", rapport)
    df["pays"] = _appliquer_normalisation(df["pays"], PAYS_NORMALIZATION, "pays", rapport,
                                          titre_par_defaut=False)
    df["classe_actifs"] = _appliquer_normalisation(df["classe_actifs"], CLASSE_NORMALIZATION,
                                                   "classe_actifs", rapport, titre_par_defaut=False)
    df["forme_juridique"] = _appliquer_normalisation(df["forme_juridique"], FORME_NORMALIZATION,
                                                     "forme_juridique", rapport, titre_par_defaut=False)

    # Statut : la colonne Status, tranchée par Result quand elle dit gagné ou perdu.
    statut_present = "statut" in colonnes
    if statut_present:
        df["statut"] = _appliquer_normalisation(df["statut"], STATUS_NORMALIZATION, "statut", rapport)
    resultat = pd.Series(VALEUR_INCONNUE, index=df.index, dtype=object)
    if "resultat_brut" in colonnes:
        resultat = _appliquer_normalisation(df["resultat_brut"], RESULT_NORMALIZATION,
                                            "resultat_brut", rapport)
        tranche = resultat.isin([STATUT_GAGNE, STATUT_PERDU])
        if not statut_present:
            df["statut"] = np.where(tranche, resultat,
                                    np.where(df["date_envoi"].notna(), STATUT_ENVOYE, STATUT_EN_COURS))
        else:
            df.loc[tranche, "statut"] = resultat[tranche]
            sans_suite = resultat.eq("Sans suite") & ~df["statut"].isin([STATUT_GAGNE, STATUT_PERDU])
            df.loc[sans_suite, "statut"] = STATUT_ABANDONNE
    df = df.drop(columns=[c for c in ("resultat_brut",) if c in df.columns])
    df["statut"] = df["statut"].astype(object)

    for champ in ("client", "fonds", "analyste", "relecteur", "consultant", "sous_classe_actifs",
                  "expertise", "commercial"):
        df[champ] = _unifier_libelles(df[champ]).fillna(VALEUR_INCONNUE).astype(object)
    for champ in ("pays", "classe_actifs", "forme_juridique", "segment"):
        df[champ] = df[champ].astype(object)

    # --- Hygiène -----------------------------------------------------------
    avant = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c != "numero"])
    rapport.doublons_supprimes = avant - len(df)

    sans_date = df["date_reception"].isna()
    rapport.lignes_sans_date = int(sans_date.sum())
    df = df.loc[~sans_date].copy()

    envoi_anterieur = df["date_envoi"].notna() & (df["date_envoi"] < df["date_reception"])
    if envoi_anterieur.any():
        rapport.incoherences["date d’envoi antérieure à la réception (envoi ignoré)"] = int(envoi_anterieur.sum())
        df.loc[envoi_anterieur, "date_envoi"] = pd.NaT

    futur = df["date_reception"] > pd.Timestamp.today().normalize()
    if futur.any():
        rapport.incoherences["date de réception dans le futur (ligne conservée)"] = int(futur.sum())

    df = df.sort_values("date_reception").reset_index(drop=True)
    rapport.n_lignes_retenues = len(df)
    return df, rapport


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les champs dérivés : calendrier, délais ouvrés, SLA, jalons."""
    df = df.copy()
    aujourdhui = pd.Timestamp.today().normalize()

    reception = df["date_reception"]
    df["mois"] = reception.dt.to_period("M").dt.to_timestamp()
    df["annee"] = reception.dt.year.astype("Int64")
    df["mois_num"] = reception.dt.month.astype("Int64")
    df["mois_nom"] = reception.dt.month.map(lambda m: MOIS_FR_LONG[int(m) - 1] if pd.notna(m) else VALEUR_INCONNUE)
    df["trimestre"] = reception.dt.to_period("Q").astype(str).str.replace(r"(\d{4})Q(\d)", r"T\2 \1", regex=True)
    df["semaine"] = reception.dt.isocalendar().week.astype("Int64")

    # Délai de traitement en jours OUVRÉS (le seul qui ait un sens en gestion)
    envoye = df["date_envoi"].notna()
    df["delai_ouvre"] = np.nan
    if envoye.any():
        debut = df.loc[envoye, "date_reception"].to_numpy("datetime64[D]")
        fin = df.loc[envoye, "date_envoi"].to_numpy("datetime64[D]")
        df.loc[envoye, "delai_ouvre"] = np.busday_count(debut, fin).astype(float)
    df["delai_calendaire"] = (df["date_envoi"] - df["date_reception"]).dt.days.astype(float)

    df["sla_cible"] = df["type_demande"].map(SLA_JOURS_OUVRES).fillna(SLA_DEFAUT).astype(float)
    df["dans_sla"] = np.where(df["delai_ouvre"].notna(), df["delai_ouvre"] <= df["sla_cible"], np.nan)
    df["dans_sla"] = pd.to_numeric(df["dans_sla"], errors="coerce")

    # --- Lecture métier : famille, résultat commercial, tranche ESG --------
    # La manager pilote en deux familles : celles de la colonne Type du classeur.
    df["famille"] = df["type_demande"].map(FAMILLE_PAR_TYPE).fillna(VALEUR_INCONNUE).astype(object)
    df["est_rfp"] = df["famille"].eq(FAMILLE_RFP)
    df["est_dd"] = df["famille"].eq(FAMILLE_DD)

    # Le résultat commercial n’existe que pour un appel d’offres : une due
    # diligence ne se gagne pas, elle se traite.
    correspondance = {
        STATUT_GAGNE: RESULTAT_GAGNE, STATUT_PERDU: RESULTAT_PERDU,
        STATUT_EN_COURS: RESULTAT_ATTENTE, STATUT_ENVOYE: RESULTAT_ATTENTE,
        STATUT_ABANDONNE: RESULTAT_SANS_SUITE,
    }
    df["resultat"] = np.where(
        df["est_rfp"], df["statut"].map(correspondance).fillna(VALEUR_INCONNUE),
        RESULTAT_HORS_RFP)

    df["est_envoye"] = df["statut"].isin(STATUTS_ENVOYES) | df["date_envoi"].notna()
    df["est_decide"] = df["statut"].isin(STATUTS_DECIDES)
    df["est_gagne"] = df["statut"].eq(STATUT_GAGNE)
    df["est_perdu"] = df["statut"].eq(STATUT_PERDU)
    df["est_en_cours"] = df["statut"].eq(STATUT_EN_COURS)
    df["est_abandonne"] = df["statut"].eq(STATUT_ABANDONNE)

    # Ancienneté des dossiers encore ouverts (jours ouvrés depuis la réception)
    df["anciennete_ouvree"] = np.nan
    ouverts = df["est_en_cours"]
    if ouverts.any():
        debut = df.loc[ouverts, "date_reception"].to_numpy("datetime64[D]")
        fin = np.full(int(ouverts.sum()), np.datetime64(aujourdhui.date(), "D"))
        df.loc[ouverts, "anciennete_ouvree"] = np.maximum(np.busday_count(debut, fin), 0).astype(float)
    df["en_retard"] = (df["est_en_cours"] & (df["anciennete_ouvree"] > df["sla_cible"])).fillna(False)

    # AUM gagné : l’encours d’un RFP remporté. C’est la métrique de valeur
    # commerciale suivie au comité — un dossier perdu n’apporte aucun encours.
    df["aum_gagne"] = np.where(df["est_gagne"] & df["est_rfp"], df["montant_potentiel"], np.nan)
    df["montant_gagne"] = df["aum_gagne"]          # nom historique, conservé
    df["esg_fort"] = df["bande_esg"].eq(ESG_FORT)
    df["montant_en_jeu"] = np.where(df["statut"].isin([STATUT_EN_COURS, STATUT_ENVOYE]),
                                    df["montant_potentiel"], np.nan)

    # --- Processus d’un appel d’offres : les étapes franchies -----------------
    # Les trois indicateurs binaires du classeur deviennent des drapeaux, et une
    # dimension lisible (« Soutenance orale : Oui / Non ») pour filtrer.
    for champ in ("etape_1", "etape_2", "oral", "sri", "qvidian"):
        if champ not in df.columns:
            df[champ] = np.nan
    df["a_remis"] = df["est_rfp"] & ((df["etape_1"] == 1.0) | df["est_envoye"])
    df["a_preselection"] = df["est_rfp"] & (df["etape_2"] == 1.0)
    df["a_oral"] = df["est_rfp"] & (df["oral"] == 1.0)
    df["soutenance"] = np.where(df["est_rfp"], _oui_non(df["oral"]), RESULTAT_HORS_RFP)
    df["sri"] = _oui_non(df["sri"])
    df["qvidian"] = _oui_non(df["qvidian"])
    return df


# =============================================================================
#  BRANCHEMENT DES DONNÉES — dossier data/ et data/branchement.json
# -----------------------------------------------------------------------------
#  Trois façons de brancher un classeur, de la plus simple à la plus précise :
#    1. déposer un fichier .xlsx / .xls / .csv dans data/ : s’il est seul, il
#       est lu automatiquement (premier onglet, colonnes reconnues par
#       COLUMN_MAP et COLUMN_ALIASES) ;
#    2. depuis l’application, écran « Données » : déposer le fichier, choisir
#       l’onglet, vérifier ou corriger la correspondance des colonnes, activer ;
#    3. écrire data/branchement.json à la main (même contenu que 2).
#  Les données réelles ne rejoignent jamais le dépôt : data/ est ignoré par git.
# =============================================================================
DOSSIER_DONNEES = Path(__file__).resolve().parent / "data"
FICHIER_BRANCHEMENT = DOSSIER_DONNEES / "branchement.json"
EXTENSIONS_DONNEES = (".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt")


@dataclass
class Branchement:
    """Ce qu’il faut savoir pour lire le classeur : où, quel onglet, quelles
    colonnes. `colonnes` : champ interne → intitulé réel, seulement pour les
    champs que la reconnaissance automatique ne trouve pas d’elle-même."""
    fichier: str | None = None
    onglet: str | None = None
    colonnes: dict[str, str] = field(default_factory=dict)
    actif: bool = True

    @property
    def chemin(self) -> Path | None:
        if not self.fichier:
            return None
        p = Path(self.fichier)
        return p if p.is_absolute() else DOSSIER_DONNEES / p

    def to_dict(self) -> dict[str, Any]:
        return {"fichier": self.fichier, "onglet": self.onglet,
                "colonnes": dict(self.colonnes), "actif": self.actif}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Branchement":
        return cls(fichier=d.get("fichier") or None, onglet=d.get("onglet") or None,
                   colonnes={str(k): str(v) for k, v in (d.get("colonnes") or {}).items() if v},
                   actif=bool(d.get("actif", True)))


def lire_branchement() -> Branchement | None:
    """Le branchement écrit sur le disque, ou None s’il n’y en a pas."""
    try:
        return Branchement.from_dict(json.loads(FICHIER_BRANCHEMENT.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def ecrire_branchement(branchement: Branchement) -> Path:
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    FICHIER_BRANCHEMENT.write_text(
        json.dumps(branchement.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return FICHIER_BRANCHEMENT


def fichiers_disponibles() -> list[Path]:
    """Classeurs et fichiers CSV présents dans data/, du plus récent au plus ancien."""
    if not DOSSIER_DONNEES.is_dir():
        return []
    fichiers = [p for p in DOSSIER_DONNEES.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSIONS_DONNEES
                and not p.name.startswith((".", "~$"))]
    return sorted(fichiers, key=lambda p: p.stat().st_mtime, reverse=True)


def onglets(chemin: str | Path) -> list[str]:
    """Onglets d’un classeur ; liste vide pour un fichier texte."""
    chemin = Path(chemin)
    if chemin.suffix.lower() in (".csv", ".tsv", ".txt"):
        return []
    try:
        with pd.ExcelFile(chemin) as classeur:
            return [str(n) for n in classeur.sheet_names]
    except (OSError, ValueError) as exc:
        raise DonneesInvalides(f"Classeur illisible : « {chemin.name} » ({exc}).") from exc


def lire_brut(chemin: str | Path, onglet: str | None = None) -> pd.DataFrame:
    """Le fichier tel quel, sans aucune interprétation : un tableau de textes.

    CSV : séparateur et encodage détectés (UTF-8 avec ou sans BOM, puis
    Latin-1). Classeur : l’onglet demandé, sinon le premier.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise DonneesInvalides(f"Fichier introuvable : « {chemin} ». Déposer le classeur dans "
                               f"le dossier data/ ou le choisir dans l’écran « Données ».")
    if chemin.suffix.lower() in (".csv", ".tsv", ".txt"):
        derniere: Exception | None = None
        for encodage in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return pd.read_csv(chemin, sep=None, engine="python", encoding=encodage,
                                   dtype=object, keep_default_na=True)
            except UnicodeDecodeError as exc:
                derniere = exc
            except (pd.errors.ParserError, ValueError) as exc:
                derniere = exc
                break
        raise DonneesInvalides(f"Fichier texte illisible : « {chemin.name} » ({derniere}).")
    noms = onglets(chemin)
    if onglet is not None and onglet not in noms:
        raise DonneesInvalides(f"Onglet « {onglet} » introuvable dans « {chemin.name} ». "
                               f"Onglets présents : {', '.join(noms) or 'aucun'}.")
    return pd.read_excel(chemin, sheet_name=onglet if onglet is not None else 0)


def apercu(chemin: str | Path, onglet: str | None = None,
           correspondance: Mapping[str, str] | None = None, n: int = 8) -> dict[str, Any]:
    """Ce que l’écran « Données » montre avant d’activer : colonnes trouvées,
    correspondance proposée, champs indispensables manquants, premières lignes."""
    chemin = Path(chemin)
    brut = lire_brut(chemin, onglet)
    colonnes = [str(c) for c in brut.columns]
    trouvees, absentes, ignorees = _resoudre_colonnes(colonnes, correspondance)
    lignes = brut.head(n).astype(object).where(brut.head(n).notna(), None)
    return {
        "fichier": chemin.name,
        "onglets": onglets(chemin),
        "onglet": onglet,
        "n_lignes": int(len(brut)),
        "colonnes": colonnes,
        "correspondance": trouvees,
        "absentes": absentes,
        "obligatoires_manquants": [c for c in REQUIRED_FIELDS if c in absentes],
        "ignorees": ignorees,
        "lignes": [[(str(v) if v is not None else None) for v in ligne]
                   for ligne in lignes.itertuples(index=False, name=None)],
    }


def resoudre_source(use_fake: bool | None = None) -> tuple[str, Branchement | None]:
    """Quelle source lire : ("demo", None), ("branchement", b) ou ("auto", b).

    Ordre : demande explicite, puis branchement écrit et actif dont le fichier
    existe, puis classeur seul dans data/, puis démonstration (ou erreur si
    USE_FAKE_DATA vaut False).
    """
    choix = USE_FAKE_DATA if use_fake is None else use_fake
    if choix is True:
        return "demo", None
    b = lire_branchement()
    if b is not None and b.actif and b.chemin is not None and b.chemin.exists():
        return "branchement", b
    fichiers = fichiers_disponibles()
    if len(fichiers) == 1:
        return "auto", Branchement(fichier=fichiers[0].name)
    if choix is False:
        if len(fichiers) > 1:
            raise DonneesInvalides(
                f"{len(fichiers)} fichiers dans data/ : choisir lequel lire dans l’écran "
                f"« Données » ({', '.join(p.name for p in fichiers)}).")
        raise DonneesInvalides("Aucun classeur branché : déposer un fichier .xlsx ou .csv dans "
                               "le dossier data/, ou le déposer depuis l’écran « Données ».")
    return "demo", None


def load_data(path: str | None = None, sheet: str | None = None,
              use_fake: bool | None = None,
              correspondance: Mapping[str, str] | None = None
              ) -> tuple[pd.DataFrame, LoadReport]:
    """Point d’entrée unique : renvoie la table enrichie et son journal qualité.

    Sans argument, la source est résolue par `resoudre_source` : le classeur
    branché s’il existe, la démonstration sinon. `path` force un fichier.
    """
    if path is not None:
        mode, branchement = "fichier", Branchement(fichier=path, onglet=sheet,
                                                   colonnes=dict(correspondance or {}))
    else:
        mode, branchement = resoudre_source(use_fake)

    if branchement is None:
        brut = generate_fake_data()
        source = (f"Données de démonstration ({fmt_int(len(brut))} lignes synthétiques, "
                  f"graine {FAKE_SEED})")
        df, rapport = normalize(brut, source=source)
        rapport.mode = "demo"
        return enrich(df), rapport

    chemin = branchement.chemin if path is None else Path(path)
    assert chemin is not None
    onglet = branchement.onglet if sheet is None else sheet
    brut = lire_brut(chemin, onglet)
    if isinstance(brut, dict):                     # sheet_name=None
        brut = pd.concat(brut.values(), ignore_index=True)
    onglet_lu = onglet if onglet is not None else (onglets(chemin)[:1] or [""])[0]
    source = chemin.name + (f" — onglet « {onglet_lu} »" if onglet_lu else "")
    df, rapport = normalize(brut, source=source,
                            correspondance=branchement.colonnes or correspondance)
    rapport.mode = "fichier"
    rapport.fichier = chemin.name
    rapport.onglet = onglet_lu
    rapport.correspondance = _resoudre_colonnes([str(c) for c in brut.columns],
                                                branchement.colonnes or correspondance)[0]
    return enrich(df), rapport


# =============================================================================
#  FILTRES
# =============================================================================
@dataclass
class Filters:
    """Sélection active. `dims` porte les filtres de modalités ; une dimension
    absente ou vide = aucune restriction."""
    date_min: dt.date | None = None
    date_max: dt.date | None = None
    dims: dict[str, list[str]] = field(default_factory=dict)

    def sans_dates(self) -> "Filters":
        return Filters(dims={k: list(v) for k, v in self.dims.items()})

    @property
    def duree_jours(self) -> int | None:
        if self.date_min and self.date_max:
            return (self.date_max - self.date_min).days + 1
        return None

    def periode_precedente(self) -> "Filters":
        """Fenêtre immédiatement antérieure, de même longueur : la seule
        comparaison honnête pour un delta."""
        duree = self.duree_jours
        if not duree or self.date_min is None:
            return Filters(dims=dict(self.dims))
        fin = self.date_min - dt.timedelta(days=1)
        return Filters(date_min=fin - dt.timedelta(days=duree - 1), date_max=fin,
                       dims={k: list(v) for k, v in self.dims.items()})

    def describe(self) -> str:
        morceaux: list[str] = []
        if self.date_min and self.date_max:
            morceaux.append(f"Du {fmt_date(self.date_min)} au {fmt_date(self.date_max)}")
        for champ, valeurs in self.dims.items():
            if valeurs:
                libelle = DIMENSIONS.get(champ, champ)
                apercu = ", ".join(map(str, valeurs[:4])) + (" …" if len(valeurs) > 4 else "")
                morceaux.append(f"{libelle} : {apercu}")
        return " · ".join(morceaux) if morceaux else "Périmètre complet, aucun filtre appliqué"

    @property
    def actif(self) -> bool:
        return bool(self.date_min or self.date_max or any(self.dims.values()))


def filter_data(df: pd.DataFrame, filtres: Filters | None) -> pd.DataFrame:
    if filtres is None or df.empty:
        return df
    masque = pd.Series(True, index=df.index)
    if filtres.date_min is not None:
        masque &= df["date_reception"] >= pd.Timestamp(filtres.date_min)
    if filtres.date_max is not None:
        masque &= df["date_reception"] <= pd.Timestamp(filtres.date_max)
    for champ, valeurs in (filtres.dims or {}).items():
        if valeurs and champ in df.columns:
            masque &= df[champ].isin(valeurs)
    return df.loc[masque].copy()


def _dispo(df: pd.DataFrame, *colonnes: str, min_modalites: int = 1) -> bool:
    """Une analyse n’est construite que si ses colonnes portent une information
    réelle : colonne présente, non vide, et pas uniquement « Non renseigné »."""
    if df.empty:
        return False
    for col in colonnes:
        if col not in df.columns:
            return False
        serie = df[col]
        if pd.api.types.is_numeric_dtype(serie):
            if serie.notna().sum() < 3:
                return False
        else:
            valides = serie[serie.notna() & (serie != VALEUR_INCONNUE)]
            if valides.empty or valides.nunique() < min_modalites:
                return False
    return True


# =============================================================================
#  AGRÉGATIONS
# =============================================================================
def agg_mensuel(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par mois calendaire, sans trou (les mois creux valent 0)."""
    if df.empty:
        return pd.DataFrame()
    base = df.groupby("mois", observed=True).agg(
        volume=("date_reception", "size"),
        envoyees=("est_envoye", "sum"),
        decidees=("est_decide", "sum"),
        gagnees=("est_gagne", "sum"),
        questions=("nb_questions", "sum"),
        delai_median=("delai_calendaire", "median"),
        delai_q1=("delai_calendaire", lambda s: s.quantile(0.25)),
        delai_q3=("delai_calendaire", lambda s: s.quantile(0.75)),
        # En jours ouvrés : la seule base comparable au délai cible.
        delai_ouvre_median=("delai_ouvre", "median"),
        delai_ouvre_q1=("delai_ouvre", lambda s: s.quantile(0.25)),
        delai_ouvre_q3=("delai_ouvre", lambda s: s.quantile(0.75)),
        sla_cible=("sla_cible", "mean"),
        taux_sla=("dans_sla", "mean"),
        montant=("montant_potentiel", "sum"),
        montant_gagne=("montant_gagne", "sum"),
    )
    calendrier = pd.date_range(df["mois"].min(), df["mois"].max(), freq="MS")
    base = base.reindex(calendrier)
    for col in ("volume", "envoyees", "decidees", "gagnees", "questions", "montant", "montant_gagne"):
        base[col] = base[col].fillna(0)
    base.index.name = "mois"
    base["taux_succes"] = np.where(base["decidees"] > 0, base["gagnees"] / base["decidees"], np.nan)
    base["indice"] = np.arange(len(base), dtype=float)
    base["libelle"] = [fmt_mois(m) for m in base.index]
    return base.reset_index()


def agg_dimension(df: pd.DataFrame, colonne: str, min_effectif: int = 1) -> pd.DataFrame:
    """Tableau de bord d’une dimension : volume, conversion, délai, montants.
    Alimente à la fois les graphiques et leur jumeau tableau."""
    if df.empty or colonne not in df.columns:
        return pd.DataFrame()
    g = df.groupby(colonne, dropna=False, observed=True).agg(
        volume=("date_reception", "size"),
        envoyees=("est_envoye", "sum"),
        decidees=("est_decide", "sum"),
        gagnees=("est_gagne", "sum"),
        questions=("nb_questions", "sum"),
        delai_median=("delai_calendaire", "median"),
        taux_sla=("dans_sla", "mean"),
        montant=("montant_potentiel", "sum"),
        montant_gagne=("montant_gagne", "sum"),
    )
    g = g[g["volume"] >= min_effectif].copy()
    if g.empty:
        return g.reset_index()
    g["taux_succes"] = np.where(g["decidees"] > 0, g["gagnees"] / g["decidees"], np.nan)
    ic = [wilson_ci(int(k), int(n)) if n > 0 else (np.nan, np.nan)
          for k, n in zip(g["gagnees"], g["decidees"])]
    g["ic_bas"] = [a for a, _ in ic]
    g["ic_haut"] = [b for _, b in ic]
    g.index.name = colonne
    return g.reset_index().sort_values("volume", ascending=False)


def taux_succes(df: pd.DataFrame) -> tuple[float, int, int, tuple[float, float]]:
    """(taux, gagnées, décidées, IC 95 % de Wilson)."""
    if df.empty:
        return (float("nan"), 0, 0, (float("nan"), float("nan")))
    gagnees, decidees = int(df["est_gagne"].sum()), int(df["est_decide"].sum())
    taux = gagnees / decidees if decidees else float("nan")
    return taux, gagnees, decidees, wilson_ci(gagnees, decidees)


# =============================================================================
#  COUCHE MÉTRIQUE
# -----------------------------------------------------------------------------
#  Une métrique, une définition, un seul endroit. Tout écran et tout rapport
#  appelle ces fonctions : deux graphiques ne peuvent pas compter la même chose
#  de deux façons différentes.
#
#  Les définitions non triviales sont documentées et vérifiées : les KPI de
#  croissance de la fixture reproduisent ceux publiés par le pôle (+49 % sur
#  3 ans, +149 % sur 5 ans, +158 % sur 10 ans), ce qui valide la formule.
# =============================================================================
def nb_questionnaires(df: pd.DataFrame) -> int:
    """Nombre de questionnaires reçus sur la période, toutes familles."""
    return int(len(df))


def nb_famille(df: pd.DataFrame, famille: str) -> int:
    """Nombre de questionnaires d’une famille (RFP ou Due Diligence)."""
    if df.empty or "famille" not in df.columns:
        return 0
    return int((df["famille"] == famille).sum())


def compte_resultats(df: pd.DataFrame) -> pd.Series:
    """Répartition des RFP par résultat commercial, dans l’ordre de lecture.

    Les due diligences sont exclues : elles n’ont pas de résultat commercial.
    """
    if df.empty or "resultat" not in df.columns:
        return pd.Series(dtype=int)
    rfp = df[df["est_rfp"]]
    comptes = rfp["resultat"].value_counts()
    ordre = [r for r in RESULTAT_ORDER if r in comptes.index]
    ordre += [r for r in comptes.index if r not in ordre]
    return comptes.reindex(ordre)


def taux_succes_rfp(df: pd.DataFrame) -> tuple[float, int, int, tuple[float, float]]:
    """(taux, gagnés, tranchés, IC 95 % de Wilson).

    Dénominateur = RFP tranchés (gagnés + perdus). Les dossiers en attente de
    décision sont exclus, jamais comptés comme des échecs ; les dossiers sans
    suite non plus, puisqu’ils n’ont pas été remis.
    """
    if df.empty or "est_rfp" not in df.columns:
        return (float("nan"), 0, 0, (float("nan"), float("nan")))
    rfp = df[df["est_rfp"]]
    gagnes = int((rfp["resultat"] == RESULTAT_GAGNE).sum())
    perdus = int((rfp["resultat"] == RESULTAT_PERDU).sum())
    tranches = gagnes + perdus
    taux = gagnes / tranches if tranches else float("nan")
    return taux, gagnes, tranches, wilson_ci(gagnes, tranches)


def aum_gagne(df: pd.DataFrame) -> float:
    """Encours remporté : somme des montants des RFP gagnés, en millions d’euros."""
    if df.empty or "aum_gagne" not in df.columns:
        return 0.0
    return float(df["aum_gagne"].sum(skipna=True))


def aum_en_jeu(df: pd.DataFrame) -> float:
    """Encours des RFP encore ouverts — le pipeline commercial."""
    if df.empty or "montant_potentiel" not in df.columns:
        return 0.0
    ouverts = df["est_rfp"] & df["resultat"].eq(RESULTAT_ATTENTE)
    return float(df.loc[ouverts, "montant_potentiel"].sum(skipna=True))


def delai_median(df: pd.DataFrame, famille: str | None = None,
                 base: str = "calendaire") -> float:
    """Délai de traitement médian, réception → envoi.

    `base="calendaire"` correspond au « time completion » suivi au comité ;
    `base="ouvre"` sert au pilotage interne du respect des délais cibles.
    """
    if df.empty:
        return float("nan")
    colonne = "delai_calendaire" if base == "calendaire" else "delai_ouvre"
    if colonne not in df.columns:
        return float("nan")
    sous = df if famille is None else df[df["famille"] == famille]
    return float(sous[colonne].median()) if len(sous) else float("nan")


def cadence_mensuelle(df: pd.DataFrame, famille: str | None = None) -> float:
    """Nombre de dossiers TERMINÉS par mois, en moyenne sur les mois observés.

    On compte les envois, pas les réceptions : c’est la capacité de production
    de l’équipe, pas la charge qui lui arrive.
    """
    if df.empty or "date_envoi" not in df.columns:
        return float("nan")
    sous = df if famille is None else df[df["famille"] == famille]
    envoyes = sous.dropna(subset=["date_envoi"])
    if envoyes.empty:
        return float("nan")
    mois = envoyes["date_envoi"].dt.to_period("M")
    n_mois = max(1, mois.nunique())
    return float(len(envoyes) / n_mois)


def volume_annuel(df: pd.DataFrame) -> pd.DataFrame:
    """Volume par année civile et par famille, plus le total."""
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(index=df["date_reception"].dt.year, columns="famille",
                           values="date_reception", aggfunc="size", fill_value=0)
    ordre = [f for f in FAMILLE_ORDER if f in pivot.columns]
    ordre += [c for c in pivot.columns if c not in ordre]
    pivot = pivot[ordre]
    pivot.index.name = "annee"
    pivot["Total"] = pivot.sum(axis=1)
    return pivot


@dataclass(frozen=True)
class Croissance:
    """Évolution du volume entre deux années civiles complètes."""
    horizon: int
    annee_reference: int
    annee_base: int
    volume_reference: int
    volume_base: int
    taux: float
    complete: bool          # False si l’historique ne couvre pas l’horizon

    @property
    def variation_absolue(self) -> int:
        return self.volume_reference - self.volume_base

    @property
    def tcam(self) -> float:
        """Taux de croissance annuel moyen, plus honnête qu’un cumul brut."""
        if self.volume_base <= 0 or self.horizon <= 0:
            return float("nan")
        return (self.volume_reference / self.volume_base) ** (1 / self.horizon) - 1


def croissance(df: pd.DataFrame, horizon: int,
               aujourdhui: dt.date | None = None) -> Croissance | None:
    """Croissance du volume sur `horizon` années.

    Référence = dernière année civile COMPLÈTE ; base = cette année moins
    l’horizon. L’année en cours est exclue : la comparer à une année pleine
    afficherait un effondrement qui n’existe pas.
    """
    if df.empty:
        return None
    annees = volume_annuel(df)["Total"]
    if annees.empty:
        return None
    today = pd.Timestamp(aujourdhui or dt.date.today())
    candidates = [a for a in annees.index if a < today.year]
    if not candidates:
        return None
    reference = max(candidates)
    base = reference - horizon
    complete = base in annees.index
    if not complete:
        base = min(annees.index)
        if base >= reference:
            return None
    v_ref, v_base = int(annees.loc[reference]), int(annees.loc[base])
    taux = (v_ref - v_base) / v_base if v_base else float("nan")
    return Croissance(horizon=reference - base, annee_reference=reference,
                      annee_base=base, volume_reference=v_ref, volume_base=v_base,
                      taux=taux, complete=complete)


def part_esg_forte(df: pd.DataFrame) -> float:
    """Part des questionnaires dont la composante ESG dépasse le seuil fort.

    Calculée sur les seuls dossiers dont la part ESG est renseignée : compter
    les non-renseignés comme « peu ESG » ferait mentir la série historique.
    """
    if df.empty or "bande_esg" not in df.columns:
        return float("nan")
    connus = df[df["bande_esg"] != ESG_INCONNU]
    if connus.empty:
        return float("nan")
    return float((connus["bande_esg"] == ESG_FORT).mean())


# =============================================================================
#  CARNET D’APPELS D’OFFRES — la photographie « où en sommes-nous »
# -----------------------------------------------------------------------------
#  C’est la matière de la page d’accueil. Cinq compartiments EXCLUSIFS qui
#  couvrent la totalité des appels d’offres de la sélection : leur somme vaut le
#  nombre de RFP, ce que l’auto-test vérifie. Aucun dossier ne disparaît entre
#  deux colonnes, aucun n’est compté deux fois.
# =============================================================================
COMPARTIMENTS: tuple[tuple[str, str, str], ...] = (
    # (clé, libellé affiché, ce que le compartiment signifie vraiment)
    ("en_cours", "En rédaction", "chez nous, réponse non partie"),
    ("en_attente", "En attente de décision", "remis au client, non tranché"),
    ("gagnes", "Gagnés", "mandat remporté"),
    ("perdus", "Perdus", "mandat non retenu"),
    ("sans_suite", "Sans suite", "abandonné avant décision"),
)


@dataclass(frozen=True)
class Carnet:
    """État des appels d’offres de la sélection, à la date du jour."""
    compartiments: dict[str, pd.DataFrame]
    total: int

    def __getattr__(self, nom: str) -> pd.DataFrame:      # carnet.gagnes, etc.
        try:
            return self.compartiments[nom]
        except KeyError:
            raise AttributeError(nom) from None

    def n(self, cle: str) -> int:
        return len(self.compartiments.get(cle, ()))

    def part(self, cle: str) -> float:
        return self.n(cle) / self.total if self.total else float("nan")

    @property
    def vivants(self) -> int:
        """Dossiers encore ouverts : ceux sur lesquels on peut encore agir."""
        return self.n("en_cours") + self.n("en_attente")

    def encours(self, cle: str) -> float:
        """Encours associé à un compartiment, en M€ (0 si la colonne manque)."""
        sous = self.compartiments.get(cle)
        if sous is None or sous.empty or "montant_potentiel" not in sous.columns:
            return 0.0
        return float(sous["montant_potentiel"].sum(skipna=True))


def carnet(df: pd.DataFrame) -> Carnet:
    """Ventile les appels d’offres de la sélection par état commercial.

    Le statut fait foi, pas le résultat : « En cours » et « Envoyé » partagent le
    résultat « En attente » alors qu’ils appellent deux actions différentes —
    rédiger d’un côté, attendre la décision du client de l’autre.
    """
    if df.empty or "est_rfp" not in df.columns:
        vide = df.head(0)
        return Carnet({cle: vide for cle, _, _ in COMPARTIMENTS}, vide, 0)

    rfp = df[df["est_rfp"]]
    aujourdhui = pd.Timestamp.today().normalize()
    par_statut = {
        "en_cours": STATUT_EN_COURS, "en_attente": STATUT_ENVOYE,
        "gagnes": STATUT_GAGNE, "perdus": STATUT_PERDU, "sans_suite": STATUT_ABANDONNE,
    }
    def _horloges(sous: pd.DataFrame) -> pd.DataFrame:
        """Deux horloges, deux questions : depuis combien de temps le dossier
        est chez nous, et depuis combien de temps le client ne répond pas."""
        sous = sous.copy()
        sous["jours_chez_nous"] = (aujourdhui - sous["date_reception"]).dt.days
        sous["jours_attente"] = (aujourdhui - sous["date_envoi"]).dt.days
        return sous

    compartiments = {cle: _horloges(rfp[rfp["statut"].eq(statut)])
                     for cle, statut in par_statut.items()}

    # Tri : le plus urgent en tête pour ce qui est ouvert, le plus récent pour
    # ce qui est tranché. Une liste de dix lignes doit montrer les dix bonnes.
    compartiments["en_cours"] = compartiments["en_cours"].sort_values(
        "jours_chez_nous", ascending=False)
    compartiments["en_attente"] = compartiments["en_attente"].sort_values(
        "jours_attente", ascending=False)
    for cle in ("gagnes", "perdus", "sans_suite"):
        colonne = "date_envoi" if compartiments[cle]["date_envoi"].notna().any() else "date_reception"
        compartiments[cle] = compartiments[cle].sort_values(colonne, ascending=False)

    return Carnet(compartiments, len(rfp))


APPEL_OFFRES = "appel d\u2019offres"
APPELS_OFFRES = "appels d\u2019offres"


def identites_carnet(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Ce que valent, exactement, les trois grandeurs du carnet.

    Un chiffre affiché sans sa composition se croit sur parole. Chaque entrée
    porte la grandeur, sa valeur, l’égalité qui la produit et sa réserve de
    lecture. L’écran et le rapport les reprennent tels quels : aucune de ces
    phrases n’est recomposée ailleurs.
    """
    if df.empty:
        return []
    livre = carnet(df)
    taux, gagnes, tranches, ic = taux_succes_rfp(df)
    perdus = tranches - gagnes
    remporte, en_jeu = aum_gagne(df), aum_en_jeu(df)
    sorties: list[dict[str, Any]] = []

    redaction, attente = livre.encours("en_cours"), livre.encours("en_attente")
    if en_jeu > 0:
        sorties.append({
            "cle": "en_jeu", "grandeur": "Encours en jeu", "valeur": fmt_encours(en_jeu),
            "egalite": (f"{fmt_dec(redaction, 1, 'M€')} en rédaction "
                        f"+ {fmt_dec(attente, 1, 'M€')} en attente de décision"),
            "note": "Un pipeline, pas une collecte acquise.",
        })
    if tranches:
        sorties.append({
            "cle": "succes", "grandeur": "Taux de succès", "valeur": fmt_pct(taux, 1),
            "egalite": (f"{pluriel(gagnes, 'mandat remporté', 'mandats remportés')} sur "
                        f"{fmt_int(tranches)} dossiers tranchés ({fmt_int(gagnes)} gagnés "
                        f"+ {fmt_int(perdus)} perdus)"),
            "note": (f"Les {pluriel(livre.vivants, 'dossier')} non tranchés sont exclus du "
                     f"dénominateur, jamais comptés comme des échecs. Intervalle de confiance "
                     f"à 95 % : {fmt_pct(ic[0], 0)} à {fmt_pct(ic[1], 0)}."),
        })
    if gagnes and remporte > 0:
        sorties.append({
            "cle": "remporte", "grandeur": "Encours remporté", "valeur": fmt_encours(remporte),
            "egalite": (f"{pluriel(gagnes, 'mandat')}, ticket moyen "
                        f"{fmt_encours(remporte / gagnes)}"),
            "note": "Rattaché à l’année de réception du dossier.",
        })
    return sorties


def serie_mensuelle(df: pd.DataFrame, masque: pd.Series | None = None,
                    mois: int = 12) -> list[dict[str, Any]]:
    """Les `mois` derniers mois du périmètre, sans trou : un mois sans dossier
    vaut zéro et le dit. Le dernier mois est signalé comme en cours s’il l’est.

    Sert les petites séries de l’écran (sous un indicateur, dans la marge) :
    elles ne sont jamais reconstituées par soustraction côté navigateur.
    """
    if df.empty:
        return []
    sous = df if masque is None else df[masque]
    compte = (sous.assign(_m=sous["date_reception"].dt.to_period("M"))
              .groupby("_m").size() if len(sous) else pd.Series(dtype="int64"))
    fin = df["date_reception"].max().to_period("M")
    debut = max(df["date_reception"].min().to_period("M"), fin - (mois - 1))
    calendrier = pd.period_range(debut, fin, freq="M")
    courant = pd.Timestamp.today().to_period("M")
    return [{"mois": p.to_timestamp().strftime("%Y-%m"), "libelle": fmt_mois(p.to_timestamp()),
             "valeur": int(compte.get(p, 0)), "en_cours": bool(p == courant)}
            for p in calendrier]


def echelle_decomposition(df: pd.DataFrame) -> dict[str, Any] | None:
    """Le facteur qui sépare les appels d’offres du total reçu.

    La décomposition doit montrer cinq états dont certains valent deux dossiers
    à côté d’un total de plusieurs centaines. Le facteur est déclaré, pas caché :
    « × 7,9 — les 25 appels d’offres portés à la hauteur des 197 reçus ».
    """
    total = nb_questionnaires(df)
    n_rfp = nb_famille(df, FAMILLE_RFP)
    if not total or not n_rfp:
        return None
    facteur = total / n_rfp
    return {"facteur": facteur, "affichage": f"× {fmt_dec(facteur, 1)}", "total": total,
            "rfp": n_rfp,
            "phrase": (f"les {pluriel(n_rfp, APPEL_OFFRES, APPELS_OFFRES)} "
                       f"portés à la hauteur des {fmt_int(total)} reçus")}


def aum_perdu(df: pd.DataFrame) -> float:
    """Encours des appels d’offres perdus : ce que l’on n’a pas remporté."""
    if df.empty or "montant_potentiel" not in df.columns:
        return 0.0
    return float(df.loc[df["est_rfp"] & df["est_perdu"], "montant_potentiel"].sum(skipna=True))


def entonnoir(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Le chemin d’un appel d’offres : reçu, Step 1, Step 2, Oral, remporté —
    effectif et encours à chaque étape, taux de passage depuis l’étape
    précédente. Les noms d’étape sont ceux du classeur.

    Une étape dont la colonne n’est pas renseignée dans le classeur n’apparaît
    pas : on ne dessine pas un entonnoir sur une donnée absente.
    """
    if df.empty or "est_rfp" not in df.columns:
        return []
    rfp = df[df["est_rfp"]]
    if rfp.empty:
        return []
    etapes: list[tuple[str, str, pd.Series]] = [("recus", "Reçus", pd.Series(True, index=rfp.index)),
                                                ("remis", "Step 1", rfp["a_remis"])]
    if rfp["etape_2"].notna().any():
        etapes.append(("preselection", "Step 2", rfp["a_preselection"]))
    if rfp["oral"].notna().any():
        etapes.append(("oral", "Oral", rfp["a_oral"]))
    etapes.append(("gagnes", "Remportés", rfp["est_gagne"]))

    sortie: list[dict[str, Any]] = []
    precedent: int | None = None
    for cle, libelle, masque in etapes:
        masque = masque.fillna(False).astype(bool)
        n = int(masque.sum())
        encours = float(rfp.loc[masque, "montant_potentiel"].sum(skipna=True))
        sortie.append({"cle": cle, "libelle": libelle, "n": n, "encours": encours,
                       "part_du_total": n / len(rfp) if len(rfp) else float("nan"),
                       "passage": (n / precedent) if precedent else float("nan")})
        precedent = n
    return sortie



def sla_libelle() -> str:
    """Engagement de délai en toutes lettres : « RFP : 15 j ouvrés · Due
    Diligence : 12 j ouvrés »."""
    morceaux = [f"{famille} : {SLA_JOURS_OUVRES[famille]} j ouvrés"
                for famille in FAMILLE_ORDER[::-1] if famille in SLA_JOURS_OUVRES]
    return " · ".join(morceaux)


def repartition_type(df: pd.DataFrame) -> pd.Series:
    """Volume par type de demande : appels d’offres et due diligence."""
    if df.empty or "famille" not in df.columns:
        return pd.Series(dtype="int64")
    comptes = df["famille"].value_counts()
    ordre = [t for t in TYPE_ORDER if t in comptes.index]
    ordre += [t for t in comptes.index if t not in ordre]
    return comptes.reindex(ordre)


# =============================================================================
#  CHARGE UTILE — la même pour l’écran et pour le rapport
# -----------------------------------------------------------------------------
#  L’application lit ces structures par HTTP, le rapport HTML les lit en
#  mémoire : c’est le MÊME calcul. Une phrase affichée à l’écran et la phrase
#  imprimée dans le rapport ne peuvent pas diverger — elles sortent d’ici.
# =============================================================================
COLONNES_DOSSIER = [
    "numero", "date_reception", "date_envoi", "famille", "statut", "resultat",
    "client", "segment", "type_client", "pays", "consultant", "commercial",
    "fonds", "classe_actifs", "sous_classe_actifs", "forme_juridique", "expertise",
    "langue", "montant_potentiel", "a_remis", "a_preselection", "a_oral", "soutenance", "sri",
    "qvidian", "nb_questions", "part_esg", "bande_esg", "delai_calendaire", "delai_ouvre",
    "sla_cible", "dans_sla", "anciennete_ouvree", "en_retard", "aum_gagne",
]
LIBELLES_DOSSIER = {
    "date_reception": "Réception", "date_envoi": "Envoi", "famille": "Famille",
    "statut": "Statut", "resultat": "Résultat", "client": "Client",
    "consultant": "Consultant", "type_client": "Type de client", "pays": "Pays",
    "fonds": "Fonds de référence", "classe_actifs": "Classe d’actifs",
    "sous_classe_actifs": "Sous-classe", "forme_juridique": "Forme juridique",
    "expertise": "Expertise", "langue": "Langue",
    "nb_questions": "Questions", "part_esg": "Part ESG", "bande_esg": "Tranche ESG",
    "montant_potentiel": "Encours (M€)", "delai_calendaire": "Délai (j)",
    "delai_ouvre": "Délai (j ouvrés)", "sla_cible": "Délai cible (j ouvrés)",
    "dans_sla": "Dans le délai cible", "anciennete_ouvree": "Ancienneté (j ouvrés)",
    "en_retard": "En retard", "aum_gagne": "Encours remporté (M€)",
    "jours_attente": "Jours d’attente", "jours_chez_nous": "Jours chez nous",
    "numero": "Numéro", "segment": "Segment", "commercial": "Commercial",
    "a_remis": "Step 1", "a_preselection": "Step 2", "a_oral": "Oral",
    "soutenance": "Oral", "sri": "ISR", "qvidian": "Mise à jour Qvidian",
}
# Ce qu’un dossier du carnet emporte avec lui : de quoi écrire une ligne de
# tableau sans repasser par la table complète.
COLONNES_CARNET = [
    "numero", "client", "segment", "consultant", "commercial", "pays", "classe_actifs",
    "sous_classe_actifs", "fonds", "expertise", "statut", "resultat",
    "montant_potentiel", "date_reception", "date_envoi", "jours_attente", "jours_chez_nous",
    "anciennete_ouvree", "en_retard", "sla_cible", "a_remis", "a_preselection", "a_oral",
]
# Nombre de dossiers listés par compartiment (gagnés, perdus, sans suite…),
# à l’écran comme dans le rapport.
LIGNES_COMPARTIMENT = 7
# Les indicateurs de la vue d’ensemble, dans l’ordre où l’écran et le rapport
# les donnent : l’issue commerciale d’abord, la production ensuite.
CHOIX_KPI_SITUATION: tuple[str, ...] = ("succes", "aum", "aum_perdu", "pipeline", "oral",
                                        "preselection", "delai_rfp", "sla", "delai_dd", "esg")


def valeur_json(v: Any) -> Any:
    """Une valeur pandas/numpy rendue transmissible : ni NaN, ni NaT, ni type
    numpy. Les dates deviennent AAAA-MM-JJ."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if math.isfinite(float(v)) else None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [valeur_json(x) for x in v]
    if isinstance(v, dict):
        return {str(k): valeur_json(x) for k, x in v.items()}
    if isinstance(v, np.ndarray):
        return [valeur_json(x) for x in v.tolist()]
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def dossiers_json(table: pd.DataFrame, colonnes: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Lignes de dossiers sérialisées, l’identifiant étant l’index de la table
    enrichie (stable tant que la source ne change pas)."""
    if table.empty:
        return []
    cols = [c for c in (colonnes or COLONNES_DOSSIER) if c in table.columns]
    sortie = []
    for idx, ligne in zip(table.index, table[cols].itertuples(index=False, name=None)):
        d: dict[str, Any] = {"id": int(idx)}
        for c, v in zip(cols, ligne):
            d[c] = valeur_json(v)
        sortie.append(d)
    return sortie


def carnet_detaille(df: pd.DataFrame, n_lignes: int = LIGNES_COMPARTIMENT) -> dict[str, Any]:
    """Le carnet, ses cinq compartiments et leurs dossiers.

    « ouverts » rassemble les deux états vivants — en rédaction chez nous, en
    attente de décision du client — l’encours le plus important d’abord, et
    SANS troncature : c’est la liste qui ouvre la lecture de la semaine.
    """
    livre = carnet(df)
    compartiments: dict[str, Any] = {}
    for cle, libelle, sens in COMPARTIMENTS:
        sous = livre.compartiments[cle]
        compartiments[cle] = {
            "libelle": libelle, "sens": sens, "n": livre.n(cle),
            "encours": livre.encours(cle),
            "dossiers": dossiers_json(sous.head(n_lignes), COLONNES_CARNET),
        }
    ouverts = pd.concat([livre.compartiments["en_cours"], livre.compartiments["en_attente"]])
    if len(ouverts):
        ouverts = ouverts.sort_values("montant_potentiel", ascending=False, na_position="last")
    somme = lambda t: float(t["montant_potentiel"].sum(skipna=True)) if len(t) else 0.0
    return {
        "total": livre.total, "vivants": livre.vivants,
        "ouverts": {"n": int(len(ouverts)), "encours": somme(ouverts),
                    "dossiers": dossiers_json(ouverts, COLONNES_CARNET)},
        "compartiments": compartiments,
    }


def repere_historique(df: pd.DataFrame) -> dict[str, Any]:
    """Les mêmes grandeurs sur TOUT l’historique : ce à quoi se compare le
    périmètre courant."""
    if df is None or df.empty:
        return {}
    taux, gagnes, tranches, _ = taux_succes_rfp(df)
    return {
        "questionnaires": int(len(df)),
        "rfp": nb_famille(df, FAMILLE_RFP),
        "dd": nb_famille(df, FAMILLE_DD),
        "taux_succes": taux, "gagnes": gagnes, "tranches": tranches,
        "encours_remporte": aum_gagne(df),
        "annee_min": int(df["date_reception"].min().year),
        "annee_max": int(df["date_reception"].max().year),
    }


def resume_situation(df: pd.DataFrame, df_total: pd.DataFrame | None = None,
                     repere: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Tout ce que la lecture d’ouverture affiche, calculé ici et nulle part
    ailleurs : ni l’écran ni le rapport ne déduisent une série, un facteur
    d’échelle ou une identité par soustraction."""
    if df.empty:
        return {}
    taux, gagnes, tranches, ic = taux_succes_rfp(df)
    return {
        "questionnaires": int(len(df)),
        "dd": nb_famille(df, FAMILLE_DD),
        "rfp": nb_famille(df, FAMILLE_RFP),
        "taux_succes": taux, "gagnes": gagnes, "tranches": tranches, "ic": list(ic),
        "encours_remporte": aum_gagne(df), "encours_en_jeu": aum_en_jeu(df),
        "encours_perdu": aum_perdu(df),
        "entonnoir": entonnoir(df),
        "delai_dd": delai_median(df, FAMILLE_DD),
        "delai_rfp": delai_median(df, FAMILLE_RFP),
        "mix_types": {str(k): int(v) for k, v in repartition_type(df).items()},
        "date_min_donnees": df["date_reception"].min(),
        "date_max_donnees": df["date_reception"].max(),
        "identites": identites_carnet(df),
        "echelle": echelle_decomposition(df),
        "series": {
            "questionnaires": serie_mensuelle(df, None, 12),
            "rfp": serie_mensuelle(df, df["est_rfp"], 12),
            "dd": serie_mensuelle(df, df["est_dd"], 12),
        },
        "repere": dict(repere) if repere is not None
                  else repere_historique(df if df_total is None else df_total),
    }


# =============================================================================
#  INDICATEURS CLÉS
# =============================================================================
@dataclass
class Kpi:
    cle: str
    libelle: str
    affichage: str
    valeur: float | None = None
    detail: str = ""
    delta_affichage: str = ""
    delta_sens: str = "neutre"      # "bon" | "mauvais" | "neutre"
    delta_direction: str = "plat"   # "hausse" | "baisse" | "plat"
    aide: str = ""
    serie: list[float] = field(default_factory=list)   # mini-tendance
    cible: str | None = None        # page ouverte au clic (drill-down)
    groupe: str = "activite"        # activite | commercial | operations


def _delta(courant: float | None, precedent: float | None, *,
           mode: str = "relatif", n: int = 0, unite: str = "",
           sens_hausse: str = "bon") -> tuple[str, str, str]:
    """Calcule l’affichage d’une variation et sa lecture métier."""
    if courant is None or precedent is None or pd.isna(courant) or pd.isna(precedent):
        return ("", "neutre", "plat")
    ecart = float(courant) - float(precedent)
    if mode == "relatif":
        if not precedent:
            return ("", "neutre", "plat")
        ratio = ecart / abs(float(precedent))
        texte = f"{'+' if ratio >= 0 else '−'}{fmt_dec(abs(ratio) * 100, 1, '%')}"
    elif mode == "points":
        texte = f"{'+' if ecart >= 0 else '−'}{fmt_dec(abs(ecart) * 100, 1)}{ESP_UNITE}pt"
    else:
        if abs(ecart) < 0.5 * 10 ** (-n):        # s’arrondirait à « −0 »
            return ("stable", "neutre", "plat")
        texte = f"{'+' if ecart >= 0 else '−'}{fmt_dec(abs(ecart), n, unite)}"
    if abs(ecart) < 1e-12:
        return ("stable", "neutre", "plat")
    direction = "hausse" if ecart > 0 else "baisse"
    if sens_hausse == "neutre":
        sens = "neutre"
    elif sens_hausse == "bon":
        sens = "bon" if ecart > 0 else "mauvais"
    else:
        sens = "mauvais" if ecart > 0 else "bon"
    return (texte, sens, direction)


def _serie_mensuelle(df: pd.DataFrame, masque: pd.Series | None = None,
                     n: int = 18) -> list[float]:
    """Derniers mois de volume, pour la mini-tendance d’une carte."""
    if df.empty:
        return []
    sous = df if masque is None else df[masque]
    if sous.empty:
        return []
    serie = (sous.assign(_m=sous["date_reception"].dt.to_period("M"))
             .groupby("_m").size().sort_index())
    return [float(v) for v in serie.tail(n)]


def compute_kpis(df: pd.DataFrame, df_precedent: pd.DataFrame | None = None) -> list[Kpi]:
    """Indicateurs de pilotage, comparés à la période immédiatement antérieure
    de même durée — la seule comparaison qui ne mente pas.

    Chaque indicateur porte sa définition (`aide`), sa mini-tendance (`serie`)
    et la page qu’il ouvre au clic (`cible`).
    """
    if df.empty:
        return []
    prec = df_precedent if df_precedent is not None and not df_precedent.empty else None

    def val(f: Callable[[pd.DataFrame], float]) -> float | None:
        if prec is None:
            return None
        try:
            v = float(f(prec))
        except (ValueError, TypeError, ZeroDivisionError):
            return None
        return v if math.isfinite(v) else None

    kpis: list[Kpi] = []

    # ---- Volume et mix ---------------------------------------------------
    total = nb_questionnaires(df)
    n_dd, n_rfp = nb_famille(df, FAMILLE_DD), nb_famille(df, FAMILLE_RFP)
    d = _delta(total, val(nb_questionnaires), mode="relatif")
    kpis.append(Kpi("questionnaires", "Questionnaires reçus", fmt_int(total), float(total),
                    detail=f"{fmt_pct(n_dd / total, 0)} de due diligence" if total else "",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    serie=_serie_mensuelle(df), cible="activite",
                    aide="Nombre de questionnaires reçus sur la période filtrée, "
                         "appels d’offres et due diligence confondus."))

    d = _delta(n_dd, val(lambda f: nb_famille(f, FAMILLE_DD)), mode="relatif")
    kpis.append(Kpi("dd", "Due diligence", fmt_int(n_dd), float(n_dd),
                    detail=f"{fmt_dec(cadence_mensuelle(df, FAMILLE_DD), 1)} terminées par mois",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    serie=_serie_mensuelle(df, df["est_dd"]), cible="dd",
                    aide="Questionnaires de due diligence, quel qu’en soit le format. "
                         "Ils n’ont pas de résultat commercial : une due diligence se "
                         "traite, elle ne se gagne pas."))

    d = _delta(n_rfp, val(lambda f: nb_famille(f, FAMILLE_RFP)), mode="relatif")
    kpis.append(Kpi("rfp", "Appels d’offres", fmt_int(n_rfp), float(n_rfp),
                    detail=f"{fmt_dec(cadence_mensuelle(df, FAMILLE_RFP), 1)} remis par mois",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    serie=_serie_mensuelle(df, df["est_rfp"]), cible="rfp",
                    aide="Appels d’offres (RFP) : les seuls dossiers porteurs d’un "
                         "résultat commercial."))

    # ---- Résultat commercial --------------------------------------------
    taux, gagnes, tranches, ic = taux_succes_rfp(df)
    comptes = compte_resultats(df)
    attente = int(comptes.get(RESULTAT_ATTENTE, 0))
    d = _delta(gagnes, val(lambda f: taux_succes_rfp(f)[1]), mode="relatif")
    kpis.append(Kpi("rfp_gagnes", "Mandats remportés", fmt_int(gagnes), float(gagnes),
                    detail=f"{pluriel(attente, 'dossier')} non tranché{accord(attente)}",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="aum", groupe="commercial",
                    aide="Appels d’offres gagnés sur la période. " + NOTE_CENSURE))

    d = _delta(taux, val(lambda f: taux_succes_rfp(f)[0]), mode="points")
    kpis.append(Kpi("succes", "Taux de succès", fmt_pct(taux, 1),
                    None if pd.isna(taux) else float(taux),
                    detail=(f"{fmt_int(gagnes)} sur {fmt_int(tranches)} tranchés · "
                            f"IC 95{NBSP}% {fmt_pct(ic[0], 0)}–{fmt_pct(ic[1], 0)}"),
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="rfp", groupe="commercial",
                    aide="Gagnés / (gagnés + perdus). Les dossiers en attente de décision "
                         "sont exclus du dénominateur, jamais comptés comme des échecs."))

    encours = aum_gagne(df)
    d = _delta(encours, val(aum_gagne), mode="relatif")
    kpis.append(Kpi("aum", "Encours remporté", fmt_encours(encours), float(encours),
                    detail=(f"ticket moyen {fmt_encours(encours / gagnes)}"
                            if gagnes else "aucun mandat remporté"),
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="aum", groupe="commercial",
                    aide="Somme des encours des appels d’offres remportés, rattachés à "
                         "l’année de réception du dossier. " + NOTE_CENSURE))

    pipeline = aum_en_jeu(df)
    d = _delta(pipeline, val(aum_en_jeu), mode="relatif")
    kpis.append(Kpi("pipeline", "Encours en jeu", fmt_encours(pipeline), float(pipeline),
                    detail=f"{pluriel(attente, 'dossier')} non tranché{accord(attente)}",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="rfp", groupe="commercial",
                    aide="Encours des appels d’offres encore ouverts : le pipeline "
                         "commercial, à ne pas confondre avec une collecte acquise."))

    # ---- Capacité opérationnelle ----------------------------------------
    delai_dd = delai_median(df, FAMILLE_DD)
    d = _delta(delai_dd, val(lambda f: delai_median(f, FAMILLE_DD)),
               mode="absolu", n=0, unite="j", sens_hausse="mauvais")
    kpis.append(Kpi("delai_dd", "Délai due diligence", fmt_dec(delai_dd, 0, "j"),
                    None if pd.isna(delai_dd) else float(delai_dd),
                    detail=f"9e décile à {fmt_dec(df.loc[df['est_dd'], 'delai_calendaire'].quantile(0.9), 0, 'j')}",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="activite", groupe="operations",
                    aide="Délai médian réception → envoi, en jours calendaires."))

    delai_rfp = delai_median(df, FAMILLE_RFP)
    d = _delta(delai_rfp, val(lambda f: delai_median(f, FAMILLE_RFP)),
               mode="absolu", n=0, unite="j", sens_hausse="mauvais")
    kpis.append(Kpi("delai_rfp", "Délai appel d’offres", fmt_dec(delai_rfp, 0, "j"),
                    None if pd.isna(delai_rfp) else float(delai_rfp),
                    detail=f"9e décile à {fmt_dec(df.loc[df['est_rfp'], 'delai_calendaire'].quantile(0.9), 0, 'j')}",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="activite", groupe="operations",
                    aide="Délai médian réception → envoi, en jours calendaires."))

    sla = df["dans_sla"].mean()
    d = _delta(sla, val(lambda f: f["dans_sla"].mean()), mode="points")
    kpis.append(Kpi("sla", "Respect du délai cible", fmt_pct(sla, 1),
                    None if pd.isna(sla) else float(sla),
                    detail=(lambda n: f"sur {pluriel(n, 'dossier')} traité{accord(n)}")(
                        int(df["dans_sla"].notna().sum())),
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="activite", groupe="operations",
                    aide="Part des dossiers traités dans le délai cible interne "
                         f"({sla_libelle()})."))

    # L’encours perdu dit ce que valait ce que l’on n’a pas remporté.
    perdu = aum_perdu(df)
    d = _delta(perdu, val(aum_perdu), mode="relatif", sens_hausse="mauvais")
    kpis.append(Kpi("aum_perdu", "Encours perdu", fmt_encours(perdu), float(perdu),
                    detail=(lambda n: f"sur {pluriel(n, 'dossier')} perdu{accord(n)}")(
                        int((df["est_rfp"] & df["est_perdu"]).sum())),
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="aum", groupe="commercial",
                    aide="Somme des encours des appels d’offres perdus sur la période."))

    # Le chemin de l’appel d’offres : Step 2 et Oral, quand le classeur les code.
    remis = df[df["a_remis"]] if "a_remis" in df.columns else df.head(0)
    if len(remis) and df["etape_2"].notna().any():
        part = float(remis["a_preselection"].mean()) if len(remis) else float("nan")
        d = _delta(part, val(lambda f: f.loc[f["a_remis"], "a_preselection"].mean()
                            if f["a_remis"].any() else float("nan")), mode="points")
        kpis.append(Kpi("preselection", "Step 2", fmt_pct(part, 0),
                        None if pd.isna(part) else float(part),
                        detail=f"{fmt_int(int(remis['a_preselection'].sum()))} sur {fmt_int(len(remis))} en Step 1",
                        delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                        cible="rfp", groupe="commercial",
                        aide="Colonne Step_2 du classeur : part des appels d’offres déposés "
                             "(Step 1) retenus après lecture du dossier."))
    if len(remis) and df["oral"].notna().any():
        part = float(remis["a_oral"].mean()) if len(remis) else float("nan")
        d = _delta(part, val(lambda f: f.loc[f["a_remis"], "a_oral"].mean()
                            if f["a_remis"].any() else float("nan")), mode="points")
        kpis.append(Kpi("oral", "Oral", fmt_pct(part, 0),
                        None if pd.isna(part) else float(part),
                        detail=f"{fmt_int(int(remis['a_oral'].sum()))} sur {fmt_int(len(remis))} en Step 1",
                        delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                        cible="rfp", groupe="commercial",
                        aide="Colonne ORAL_RFP du classeur : part des appels d’offres déposés "
                             "(Step 1) ayant donné lieu à une présentation devant le client."))

    # Le volume de questions n’existe que si le classeur le porte.
    if df["nb_questions"].notna().any():
        charge = df["nb_questions"].sum(skipna=True)
        d = _delta(charge, val(lambda f: f["nb_questions"].sum(skipna=True)), mode="relatif")
        kpis.append(Kpi("questions", "Questions traitées", fmt_int(charge), float(charge),
                        detail=f"{fmt_dec(df['nb_questions'].mean(), 0)} par dossier en moyenne",
                        delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                        cible="activite", groupe="operations",
                        aide="Volume de questions : la mesure réelle de la charge, un RFP "
                             "pesant plusieurs fois une due diligence courte."))

    part_esg = part_esg_forte(df)
    d = _delta(part_esg, val(part_esg_forte), mode="points")
    kpis.append(Kpi("esg", "Forte composante ESG", fmt_pct(part_esg, 0),
                    None if pd.isna(part_esg) else float(part_esg),
                    detail=f"part ESG supérieure à {fmt_pct(ESG_SEUIL_FORT, 0)}",
                    delta_affichage=d[0], delta_sens=d[1], delta_direction=d[2],
                    cible="esg", groupe="activite",
                    aide="Part des questionnaires à forte composante ESG, calculée sur "
                         "les seuls dossiers dont la part ESG est renseignée."))
    return kpis


# =============================================================================
#  INSIGHTS — phrases déterministes, calculées, jamais rédigées d’avance
# =============================================================================
@dataclass(frozen=True)
class Insight:
    cle: str
    texte: str
    appui: str                     # la métrique qui soutient l’affirmation
    ton: str = "info"              # info | positif | alerte
    cible: str | None = None       # page ouverte au clic
    serie: tuple[float, ...] = ()


def generer_insights(df: pd.DataFrame, df_precedent: pd.DataFrame | None = None,
                     maximum: int = 8) -> list[Insight]:
    """Constats tirés des données, dans l’ordre de ce qui mérite attention.

    Aucun texte n’est écrit d’avance : chaque phrase est produite par un calcul,
    et l’insight disparaît si la donnée ne permet pas de l’établir.
    """
    if df.empty:
        return []
    insights: list[Insight] = []
    prec = df_precedent if df_precedent is not None and not df_precedent.empty else None

    # 1. Volume par rapport à la période précédente
    if prec is not None and len(prec) > 0:
        variation = (len(df) - len(prec)) / len(prec)
        if abs(variation) >= 0.05:
            sens = "progresse de" if variation > 0 else "recule de"
            insights.append(Insight(
                "volume",
                f"Le volume de questionnaires {sens} {fmt_pct(abs(variation), 0)} par "
                f"rapport à la période précédente de même durée.",
                f"{fmt_int(len(df))} contre {fmt_int(len(prec))}",
                ton="info", cible="activite",
                serie=tuple(_serie_mensuelle(df))))

    # 2. Croissance structurelle
    for horizon in HORIZONS_CROISSANCE:
        c = croissance(df, horizon)
        if c is not None and c.complete and abs(c.taux) >= 0.15:
            insights.append(Insight(
                f"croissance{horizon}",
                f"La charge a {'augmenté' if c.taux > 0 else 'diminué'} de "
                f"{fmt_pct(abs(c.taux), 0)} en {c.horizon} ans, soit "
                f"{fmt_pct(c.tcam, 1)} par an.",
                f"{c.volume_base} questionnaires en {c.annee_base}, "
                f"{c.volume_reference} en {c.annee_reference}",
                ton="info", cible="activite"))
            break

    # 3. Déformation du mix
    annuel = volume_annuel(df)
    if len(annuel) >= 4 and FAMILLE_DD in annuel.columns:
        parts = annuel[FAMILLE_DD] / annuel["Total"].replace(0, np.nan)
        parts = parts.dropna()
        if len(parts) >= 4 and abs(parts.iloc[-1] - parts.iloc[0]) >= 0.05:
            insights.append(Insight(
                "mix",
                f"La due diligence est passée de {fmt_pct(parts.iloc[0], 0)} à "
                f"{fmt_pct(parts.iloc[-1], 0)} de la charge entre {parts.index[0]} "
                f"et {parts.index[-1]}.",
                "le nombre d’appels d’offres, lui, reste stable"
                if annuel[FAMILLE_RFP].std() < annuel[FAMILLE_RFP].mean() * 0.35 else "",
                ton="info", cible="activite"))

    # 4. Délai de traitement
    if prec is not None:
        actuel, avant = delai_median(df), delai_median(prec)
        if all(map(math.isfinite, (actuel, avant))) and abs(actuel - avant) >= 2:
            sens = "allongé" if actuel > avant else "raccourci"
            insights.append(Insight(
                "delai",
                f"Le délai médian de traitement s’est {sens} de "
                f"{pluriel(round(abs(actuel - avant)), 'jour')} par rapport à la "
                f"période précédente.",
                f"{fmt_dec(actuel, 0, 'j')} contre {fmt_dec(avant, 0, 'j')}",
                ton="alerte" if actuel > avant else "positif", cible="activite"))

    # 5. Encours en attente de décision
    attente = df[df["est_rfp"] & df["resultat"].eq(RESULTAT_ATTENTE)]
    if len(attente):
        montant = float(attente["montant_potentiel"].sum(skipna=True))
        if montant > 0:
            # « Non tranché » et non « en attente de décision » : le compte
            # réunit les dossiers en rédaction et ceux remis au client, qui
            # appellent deux actions différentes. Le carnet les distingue.
            insights.append(Insight(
                "pipeline",
                f"{fmt_int(len(attente))} appel{accord(len(attente))} d’offres non "
                f"tranché{accord(len(attente))} "
                f"{'représente' if len(attente) < 2 else 'représentent'} "
                f"{fmt_encours(montant)} d’encours potentiel.",
                f"soit {fmt_dec(montant / max(aum_gagne(df), 1) * 100, 0, '%')} "
                f"de l’encours déjà remporté sur la période",
                ton="info", cible="rfp"))

    # 6. Concentration client
    if _dispo(df, "client", min_modalites=3):
        comptes = df["client"].value_counts()
        part = comptes.iloc[0] / len(df)
        if part >= 0.08:
            insights.append(Insight(
                "concentration",
                f"« {comptes.index[0]} » concentre {fmt_pct(part, 0)} des questionnaires "
                f"reçus sur la période.",
                f"{fmt_int(int(comptes.iloc[0]))} dossiers",
                ton="info", cible="explorateur"))

    # 7. Mois le plus chargé de l’année en cours
    annee = df["date_reception"].dt.year.max()
    courante = df[df["date_reception"].dt.year == annee]
    if len(courante) >= 12:
        par_mois = courante.groupby(courante["date_reception"].dt.month).size()
        if len(par_mois) >= 3:
            pic = int(par_mois.idxmax())
            insights.append(Insight(
                "pic",
                f"{MOIS_FR_LONG[pic - 1]} est le mois le plus chargé de {annee} avec "
                f"{int(par_mois.max())} questionnaires.",
                f"contre {fmt_dec(par_mois.mean(), 0)} en moyenne mensuelle",
                ton="info", cible="activite"))

    # 7 bis. Le chemin des appels d’offres déposés
    chemin = entonnoir(df)
    par_cle = {e["cle"]: e for e in chemin}
    if "remis" in par_cle and par_cle["remis"]["n"] >= 8 and ("oral" in par_cle or "preselection" in par_cle):
        remis = par_cle["remis"]["n"]
        morceaux = []
        if "preselection" in par_cle:
            morceaux.append(f"{fmt_int(par_cle['preselection']['n'])} "
                            f"({fmt_pct(par_cle['preselection']['n'] / remis, 0)}) en Step 2")
        if "oral" in par_cle:
            morceaux.append(f"{fmt_int(par_cle['oral']['n'])} "
                            f"({fmt_pct(par_cle['oral']['n'] / remis, 0)}) en Oral")
        gagnes_n = par_cle["gagnes"]["n"]
        insights.append(Insight(
            "chemin",
            f"Sur {fmt_int(remis)} appels d’offres en Step 1, {' et '.join(morceaux)}, "
            f"{fmt_int(gagnes_n)} remporté{accord(gagnes_n)}.",
            f"{fmt_encours(par_cle['gagnes']['encours'])} d’encours remporté" if par_cle["gagnes"]["encours"] else "",
            ton="info", cible="rfp"))


    # 8. ESG
    connus = df[df["bande_esg"] != ESG_INCONNU]
    if len(connus) >= 30:
        parts = connus.groupby(connus["date_reception"].dt.year)["esg_fort"].mean()
        if len(parts) >= 3 and (parts.iloc[-1] - parts.iloc[0]) >= 0.05:
            insights.append(Insight(
                "esg",
                f"Les questionnaires à forte composante ESG sont passés de "
                f"{fmt_pct(parts.iloc[0], 0)} à {fmt_pct(parts.iloc[-1], 0)} des "
                f"dossiers renseignés depuis {parts.index[0]}.",
                f"{int(connus['esg_fort'].sum())} dossiers concernés sur la période",
                ton="info", cible="esg"))

    return insights[:maximum]


# =============================================================================
#  BLOCS D’ANALYSE (figure + narration + jumeau tableau)
#  Chaque bloc est autonome et renvoie None si la donnée ne le permet pas :
#  l’écran s’adapte au fichier, il n’impose rien.
# =============================================================================
# Architecture de l’information : une section = une question de pilotage.
SECTIONS: dict[str, str] = {
    "synthese": "Vue d’ensemble",
    "activite": "Activité",
    "rfp": "Appels d’offres",
    "dd": "Due diligence",
    "aum": "Encours & gains",
    "esg": "ESG",
    "diagnostic": "Diagnostic",
}

# Le produit est en DEUX parties. La première se lit debout, en trois minutes,
# et suffit à un dirigeant. La seconde répond aux « pourquoi » et aux
# « combien exactement ». Cette partition vaut pour l’écran comme pour le
# rapport : c’est la même architecture de l’information.
PARTIES: dict[str, tuple[str, str]] = {
    "direction": ("Direction", "Où en sommes-nous, et qu’est-ce qui a bougé."),
    "analyse": ("Analyse", "Le détail, dimension par dimension."),
}
PARTIE_PAR_SECTION: dict[str, str] = {
    "synthese": "direction",
    "activite": "analyse", "rfp": "analyse", "dd": "analyse",
    "aum": "analyse", "esg": "analyse", "diagnostic": "analyse",
}


@dataclass
class Block:
    cle: str
    section: str
    titre: str
    accroche: str
    # None = le bloc EST un tableau. Certaines réponses ne sont pas des formes :
    # « quels mandats avons-nous remportés » se lit ligne à ligne, pas en barres.
    figure: go.Figure | None
    tableau: pd.DataFrame
    note: str = ""
    large: bool = False
    # Dimension filtrable portée par l’axe des catégories : renseignée, elle
    # rend le graphique cliquable — un clic sur « France » filtre tout l’écran.
    dimension: str | None = None
    # Un tableau triable : un clic sur l’en-tête réordonne les lignes, à
    # l’écran comme dans le rapport. Réservé aux tableaux sans ligne de total.
    triable: bool = False


def _fig(hauteur: int = 340, **layout: Any) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(template=TEMPLATE_NAME, height=hauteur, **layout)
    return fig


def _marque(couleur: str | Sequence[str], largeur: float = 1.5) -> dict[str, Any]:
    """Couleur + anneau de la couleur de fond : c’est l’écart de 2 px entre
    marques adjacentes, jamais une bordure décorative."""
    return dict(color=couleur, line=dict(color=SURFACE, width=largeur))


def _rgba(hex_couleur: str, alpha: float) -> str:
    h = hex_couleur.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _axe_mois(fig: go.Figure, mois: Sequence[Any], max_libelles: int = 13) -> None:
    """Libellés de mois en français, espacés pour ne jamais se chevaucher."""
    mois = list(mois)
    if not mois:
        return
    pas = max(1, math.ceil(len(mois) / max_libelles))
    ticks = mois[::pas]
    fig.update_xaxes(tickmode="array", tickvals=ticks,
                     ticktext=[fmt_mois(m) for m in ticks], tickangle=0)


def _axe_valeurs(fig: go.Figure, maxi: float, formateur: Callable[[float], str],
                 axe: str = "x", n_ticks: int = 5) -> None:
    """Graduations rondes libellées en français — « 5 Md€ » plutôt que « 5G »."""
    if not (isinstance(maxi, (int, float)) and math.isfinite(maxi)) or maxi <= 0:
        return
    brut = maxi / n_ticks
    exposant = 10.0 ** math.floor(math.log10(brut))
    pas = next((m * exposant for m in (1, 2, 2.5, 5, 10) if brut <= m * exposant), exposant * 10)
    valeurs = np.arange(0, maxi + pas * 0.5, pas)
    reglage = dict(tickmode="array", tickvals=list(valeurs),
                   ticktext=[formateur(v) for v in valeurs])
    (fig.update_xaxes if axe == "x" else fig.update_yaxes)(**reglage)


def _labels_exterieurs(fig: go.Figure, valeurs: Sequence[float], marge: float = 1.18) -> None:
    """Réserve la place des libellés posés en bout de barre (jamais rognés)."""
    maxi = max([v for v in valeurs if pd.notna(v)] or [0])
    if maxi > 0:
        fig.update_xaxes(range=[0, maxi * marge])


def _mois_complets(mensuel: pd.DataFrame) -> pd.DataFrame:
    """Écarte le mois en cours : un mois à moitié écoulé tire toute tendance
    vers le bas et fausserait aussi bien l’ajustement que le commentaire."""
    if mensuel.empty:
        return mensuel
    courant = pd.Timestamp.today().normalize().replace(day=1)
    complets = mensuel[mensuel["mois"] < courant]
    return complets if len(complets) >= 4 else mensuel


# --- Fabriques communes -------------------------------------------------------
GRANULARITES = {"mois": "Mensuel", "trimestre": "Trimestriel", "annee": "Annuel"}
# Le nom de la période au singulier, pour les phrases : « 3 de plus par mois ».
NOM_PERIODE = {"mois": "mois", "trimestre": "trimestre", "annee": "an"}


def _periode(df: pd.DataFrame, granularite: str) -> pd.Series:
    """Ramène la date de réception au début de sa période d’agrégation."""
    dates = df["date_reception"]
    if granularite == "annee":
        return dates.dt.to_period("Y").dt.to_timestamp()
    if granularite == "trimestre":
        return dates.dt.to_period("Q").dt.to_timestamp()
    return dates.dt.to_period("M").dt.to_timestamp()


def _libelle_periode(horodatage: Any, granularite: str) -> str:
    ts = pd.Timestamp(horodatage)
    if granularite == "annee":
        return str(ts.year)
    if granularite == "trimestre":
        return f"T{(ts.month - 1) // 3 + 1} {ts.year}"
    return fmt_mois(ts)


def _axe_periode(fig: go.Figure, valeurs: Sequence[Any], granularite: str,
                 max_libelles: int = 14) -> None:
    valeurs = list(valeurs)
    if not valeurs:
        return
    pas = max(1, math.ceil(len(valeurs) / max_libelles))
    ticks = valeurs[::pas]
    fig.update_xaxes(tickmode="array", tickvals=ticks,
                     ticktext=[_libelle_periode(t, granularite) for t in ticks], tickangle=0)


def _pivot_famille(df: pd.DataFrame, granularite: str) -> pd.DataFrame:
    """Volume par période et par famille, sans trou dans le calendrier."""
    if df.empty:
        return pd.DataFrame()
    travail = df.assign(_periode=_periode(df, granularite))
    pivot = travail.pivot_table(index="_periode", columns="famille",
                                values="date_reception", aggfunc="size", fill_value=0)
    freq = {"mois": "MS", "trimestre": "QS", "annee": "YS"}[granularite]
    pivot = pivot.reindex(pd.date_range(pivot.index.min(), pivot.index.max(), freq=freq),
                          fill_value=0)
    ordre = [f for f in FAMILLE_ORDER if f in pivot.columns]
    ordre += [c for c in pivot.columns if c not in ordre]
    pivot = pivot[ordre]
    pivot.index.name = "periode"
    return pivot


FAMILLE_COULEURS = {}          # rempli par appliquer_theme via _couleurs_famille()


def _couleurs_famille() -> dict[str, str]:
    """La due diligence est la masse (ton clair), l’appel d’offres l’enjeu
    commercial (encre pleine). Deux séries seulement : la distinction reste
    lisible partout, et le libellé l’accompagne."""
    return {FAMILLE_DD: SERIES[2], FAMILLE_RFP: SERIES[0]}


def _couleurs_resultat() -> dict[str, str]:
    """Le résultat d’un RFP est un état : ton du carnet, libellé et valeur
    écrits sur la marque."""
    return {RESULTAT_GAGNE: COMPARTIMENT_COLORS["gagnes"],
            RESULTAT_ATTENTE: COMPARTIMENT_COLORS["en_attente"],
            RESULTAT_PERDU: COMPARTIMENT_COLORS["perdus"],
            RESULTAT_SANS_SUITE: COMPARTIMENT_COLORS["sans_suite"]}


def _couleurs_esg() -> dict[str, str]:
    """Rampe ordinale : plus la composante ESG est forte, plus le ton est
    soutenu. L’ESG n’est ni un succès ni un échec."""
    return {ESG_FORT: teinte(1.0), ESG_MOYEN: teinte(0.58), ESG_FAIBLE: teinte(0.28),
            ESG_INCONNU: teinte(0.10)}


def _figure_rang(labels: Sequence[str], valeurs: Sequence[float],
                 formateur: Callable[[float], str], couleur: str | None = None,
                 top: int = 12, survol: Sequence[str] | None = None,
                 titre_axe: str = "") -> tuple[go.Figure, pd.DataFrame]:
    """Classement en barres horizontales, queue regroupée dans « Autres ».

    Remplace le camembert à vingt parts : au-delà de sept catégories, aucune
    part d’un disque n’est comparable à l'œil.
    """
    donnees = pd.DataFrame({"label": list(labels), "valeur": list(valeurs)})
    donnees["survol"] = list(survol) if survol is not None else donnees["valeur"].map(formateur)
    donnees = donnees.sort_values("valeur", ascending=False)
    complet = donnees.copy()
    if len(donnees) > top:
        queue = donnees.iloc[top:]
        donnees = donnees.iloc[:top]
        donnees = pd.concat([donnees, pd.DataFrame([{
            "label": f"Autres ({len(queue)})", "valeur": queue["valeur"].sum(),
            "survol": f"{pluriel(len(queue), 'modalité')} "
                      f"regroupée{accord(len(queue))}"}])], ignore_index=True)
    donnees = donnees.sort_values("valeur")

    fig = _fig(max(280, 30 * len(donnees) + 96))
    fig.add_trace(go.Bar(
        y=donnees["label"], x=donnees["valeur"], orientation="h",
        marker=_marque(couleur or SERIES[0]),
        text=[formateur(v) for v in donnees["valeur"]],
        textposition="outside", cliponaxis=False, textfont=dict(color=INK_2, size=11.5),
        customdata=donnees["survol"],
        hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
    ))
    fig.update_xaxes(title_text=titre_axe)
    _labels_exterieurs(fig, list(donnees["valeur"]), 1.24)
    return fig, complet


def _empiler(fig: go.Figure, index: Sequence[Any], pivot: pd.DataFrame,
             couleurs: dict[str, str], suffixe: str = "") -> None:
    """Empilement ordonné avec écart de surface entre segments."""
    for i, colonne in enumerate(pivot.columns):
        fig.add_trace(go.Bar(
            x=list(index), y=pivot[colonne], name=str(colonne),
            marker=_marque(couleurs.get(colonne, SERIES[i % len(SERIES)]), 1.2),
            hovertemplate="%{y:,.0f} " + str(colonne) + suffixe + "<extra></extra>",
        ))


# =============================================================================
#  01 — VUE D’ENSEMBLE
# =============================================================================
def _bloc_flux_famille(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Le graphique central du pilotage : combien arrive, et de quelle nature."""
    granularite = stats.get("granularite", "mois")
    pivot = _pivot_famille(df, granularite)
    if pivot.empty or len(pivot) < 2:
        return None

    fig = _fig(390, barmode="stack", hovermode="x unified")
    _empiler(fig, pivot.index, pivot, _couleurs_famille())
    total = pivot.sum(axis=1)

    # Tendance ajustée sur les périodes complètes uniquement.
    complet = total.iloc[:-1] if _periode_en_cours(pivot.index[-1], granularite) else total
    reg = ols(np.arange(len(complet), dtype=float), complet.to_numpy(dtype=float))
    stats["tendance_volume"] = reg
    if reg is not None and len(complet) >= 4:
        fig.add_trace(go.Scatter(
            x=list(complet.index), y=reg.predire(np.arange(len(complet))),
            mode="lines", name="Tendance", line=dict(color=INK, width=2),
            hovertemplate="Tendance : %{y:.1f}<extra></extra>"))
    if len(complet) < len(total):
        # Repère posé dans l’espace du cadre : il ne recouvre jamais une barre.
        fig.add_annotation(xref="paper", yref="paper", x=1, y=1.04, xanchor="right",
                           yanchor="bottom", text="dernière période partielle",
                           font=dict(size=10.5, color=INK_MUTED))
    _axe_periode(fig, pivot.index, granularite)
    fig.update_yaxes(title_text="Questionnaires reçus", rangemode="tozero")
    fig.update_layout(bargap=0.22)

    part_dd = pivot.get(FAMILLE_DD, pd.Series(dtype=float)).sum() / max(total.sum(), 1)
    accroche = (f"{fmt_int(int(total.sum()))} questionnaires sur la période, "
                f"dont {fmt_pct(part_dd, 0)} de due diligence.")
    if reg is not None and reg.significatif:
        sens = "progression" if reg.pente > 0 else "recul"
        accroche += (f" Flux en {sens} de {fmt_dec(abs(reg.pente), 1)} "
                     f"questionnaire{accord(reg.pente)} "
                     f"par {NOM_PERIODE[granularite]} ({fmt_p(reg.p_value)}).")
    tableau = pivot.copy()
    tableau.insert(0, "Période", [_libelle_periode(i, granularite) for i in pivot.index])
    tableau["Total"] = total.to_numpy()
    return Block("flux_famille", "activite", "Flux de questionnaires", accroche, fig,
                 tableau.reset_index(drop=True),
                 note="Volume reçu, et non traité : c’est la charge qui arrive au pôle. "
                      "La tendance est ajustée sur les périodes complètes uniquement.",
                 large=True)


def _bloc_annees(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Année par année : la lecture de la vue d’ensemble, une ligne par exercice
    du périmètre. Le tableau se trie sur n’importe quelle colonne."""
    annees = sorted({int(a) for a in df["date_reception"].dt.year.dropna().unique()}, reverse=True)
    if len(annees) < 2:
        return None                      # une seule année : la vue d’ensemble suffit
    courante = pd.Timestamp.today().year
    lignes = []
    meilleure = (None, -1.0)
    for annee in annees:
        sous = df[df["date_reception"].dt.year == annee]
        taux, gagnes, tranches, _ = taux_succes_rfp(sous)
        remporte = aum_gagne(sous)
        if remporte > meilleure[1]:
            meilleure = (annee, remporte)
        lignes.append({
            "Année": f"{annee} · en cours" if annee == courante else str(annee),
            "Reçus": fmt_int(len(sous)),
            "DD": fmt_int(nb_famille(sous, FAMILLE_DD)),
            "RFP": fmt_int(nb_famille(sous, FAMILLE_RFP)),
            "Gagnés": fmt_int(gagnes),
            "Perdus": fmt_int(tranches - gagnes),
            "Succès": fmt_pct(taux, 0),
            "Remporté": fmt_encours(remporte),
            "Perdu": fmt_encours(aum_perdu(sous)),
            "En jeu": fmt_encours(aum_en_jeu(sous)),
            "Délai": fmt_int(delai_median(sous, FAMILLE_RFP), "j"),
        })
    table = pd.DataFrame(lignes)
    charge = max(annees, key=lambda a: int((df["date_reception"].dt.year == a).sum()))
    n_charge = int((df["date_reception"].dt.year == charge).sum())
    accroche = (f"{pluriel(len(annees), 'exercice')} sur la période. La meilleure année "
                f"pour les appels d’offres est {meilleure[0]} ({fmt_encours(meilleure[1])} "
                f"remportés) ; la charge la plus forte est celle de {charge} "
                f"({pluriel(n_charge, 'questionnaire')}).")
    return Block("annees", "synthese", "Année par année", accroche, None, table,
                 note="Chaque ligne se lit comme la vue d’ensemble, sur l’année de réception "
                      "des dossiers : questionnaires reçus, dont due diligence (DD) et appels "
                      "d’offres (RFP) ; mandats gagnés et perdus, taux de succès ; encours "
                      "remporté, perdu et en jeu ; délai médian de réponse aux appels d’offres. "
                      "Un clic sur un en-tête trie le tableau. L’année en cours est incomplète : "
                      "elle ne se compare pas aux autres.",
                 large=True, triable=True)


def _bloc_classes_actifs(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Les classes d’actifs : ce que chacune pèse dans l’activité, ce qu’elle
    reçoit, remporte, perd et coûte en délai. Une ligne par classe, l’encours
    remporté le plus haut d’abord."""
    if not _dispo(df, "classe_actifs", min_modalites=2):
        return None
    lignes = []
    total_remporte = aum_gagne(df)
    total_recus = len(df)
    for classe, sous in df.groupby("classe_actifs", observed=True):
        taux, gagnes, _, _ = taux_succes_rfp(sous)
        remporte = aum_gagne(sous)
        rfp = sous[sous["est_rfp"]]
        lignes.append({
            "Classe": str(classe),
            "Reçus": fmt_int(len(sous)),
            "Part": fmt_pct(len(sous) / total_recus if total_recus else float("nan"), 0),
            "DD": fmt_int(nb_famille(sous, FAMILLE_DD)),
            "RFP": fmt_int(len(rfp)),
            "Gagnés": fmt_int(gagnes),
            "Succès": fmt_pct(taux, 0),
            "Remporté": fmt_encours(remporte),
            "Perdu": fmt_encours(aum_perdu(sous)),
            "En jeu": fmt_encours(aum_en_jeu(sous)),
            "Délai": fmt_jours(delai_median(sous)),
            "_tri": (remporte, len(sous)),
        })
    lignes.sort(key=lambda l: l["_tri"], reverse=True)
    # « Non renseigné » ferme la marche : il n’est pas une classe.
    lignes.sort(key=lambda l: l["Classe"] == VALEUR_INCONNUE)
    for l in lignes:
        l.pop("_tri")
    table = pd.DataFrame(lignes)
    tete = next((l for l in lignes if l["Classe"] != VALEUR_INCONNUE), lignes[0])
    part_gagnee = (aum_gagne(df[df["classe_actifs"] == tete["Classe"]]) / total_remporte
                   if total_remporte else float("nan"))
    accroche = (f"{pluriel(len(lignes), 'classe d’actifs', 'classes d’actifs')} sur la période. "
                f"« {tete['Classe']} » porte {fmt_pct(part_gagnee, 0)} de l’encours "
                f"remporté ({tete['Remporté']}) pour {tete['Part']} des questionnaires reçus, "
                f"avec un taux de succès de {tete['Succès']}."
                if total_remporte else
                f"{pluriel(len(lignes), 'classe d’actifs', 'classes d’actifs')} sur la période, "
                f"aucun mandat remporté.")
    return Block("classes_actifs", "synthese", "Les classes d’actifs", accroche, None, table,
                 note="Questionnaires reçus et leur part du total, dont due diligence (DD) et "
                      "appels d’offres (RFP) ; mandats gagnés et taux de succès sur les "
                      "dossiers tranchés de la classe ; encours remporté et encours perdu ; "
                      "encours en jeu des appels d’offres encore ouverts ; délai médian de "
                      "traitement, en jours calendaires. Un clic sur un en-tête trie le tableau.",
                 large=True, dimension="classe_actifs", triable=True)


def _bloc_decomposition(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """La décomposition que lit la manager : combien de questionnaires arrivent,
    de quelle famille, et — pour les appels d’offres seuls — ce qu’ils deviennent.

    Forme retenue : un arbre de nombres reliés, pas un pavage. Les effectifs vont
    de 6 à 1 400 ; toute forme proportionnelle rendrait les petites branches
    illisibles, alors que ce sont justement celles qui appellent une décision.
    La proportion reste encodée, par la barre sous chaque nombre.

    Une due diligence n’a pas de branche fille : elle n’a pas de résultat
    commercial. L’arbre montre la règle au lieu de l’écrire.
    """
    total = nb_questionnaires(df)
    if not total:
        return None
    n_dd, n_rfp = nb_famille(df, FAMILLE_DD), nb_famille(df, FAMILLE_RFP)
    sans_famille = total - n_dd - n_rfp          # jamais masqué : il resterait un trou
    livre = carnet(df)
    couleurs_f = _couleurs_famille()
    couleurs_compartiment = dict(COMPARTIMENT_COLORS)

    # --- construction de l’arbre -------------------------------------------
    # Un nœud = (clé, libellé, effectif, couleur, niveau, clé du parent).
    noeuds: list[dict[str, Any]] = [
        dict(cle="total", libelle="Questionnaires reçus", valeur=total,
             couleur=INK_2, niveau=0, parent=None)]
    feuilles: list[str] = []
    if n_dd:
        noeuds.append(dict(cle="dd", libelle=FAMILLE_DD, valeur=n_dd,
                           couleur=couleurs_f[FAMILLE_DD], niveau=1, parent="total"))
        feuilles.append("dd")
    if n_rfp:
        noeuds.append(dict(cle="rfp", libelle="Appels d’offres", valeur=n_rfp,
                           couleur=couleurs_f[FAMILLE_RFP], niveau=1, parent="total"))
        reste = n_rfp
        for cle, libelle, _ in COMPARTIMENTS:
            if livre.n(cle):
                noeuds.append(dict(cle=f"c_{cle}", libelle=libelle, valeur=livre.n(cle),
                                   couleur=couleurs_compartiment[cle], niveau=2,
                                   parent="rfp"))
                feuilles.append(f"c_{cle}")
            reste -= livre.n(cle)
        if reste > 0:      # un statut hors nomenclature ne disparaît pas
            noeuds.append(dict(cle="c_reste", libelle="Statut non renseigné",
                               valeur=reste, couleur=INK_MUTED, niveau=2, parent="rfp"))
            feuilles.append("c_reste")
    if sans_famille > 0:
        noeuds.append(dict(cle="autre", libelle="Famille non renseignée",
                           valeur=sans_famille, couleur=INK_MUTED, niveau=1,
                           parent="total"))
        feuilles.append("autre")
    if len(noeuds) < 3:
        return None

    # --- mise en page : les feuilles régulièrement espacées, les parents
    #     centrés sur leurs enfants. C’est la disposition d’arbre classique.
    par_cle = {n["cle"]: n for n in noeuds}
    for rang, cle in enumerate(feuilles):
        par_cle[cle]["y"] = 1 - (rang + 0.5) / len(feuilles)
    for cle in ("rfp", "total"):
        noeud = par_cle.get(cle)
        if noeud is None:
            continue
        enfants = [n["y"] for n in noeuds if n["parent"] == cle and "y" in n]
        noeud["y"] = sum(enfants) / len(enfants) if enfants else 0.5

    # Largeur de barre par niveau : la dernière colonne garde de la place pour
    # le pourcentage posé à sa droite, qui serait sinon rogné.
    COLONNES = {0: (0.00, 0.20), 1: (0.31, 0.20), 2: (0.62, 0.26)}
    TAILLES = {0: 25, 1: 21, 2: 17}
    fig = _fig(max(320, 74 * len(feuilles) + 52),
               margin=dict(l=2, r=2, t=10, b=6), showlegend=False)
    fig.update_xaxes(visible=False, range=[0, 1], fixedrange=True)
    fig.update_yaxes(visible=False, range=[0, 1], fixedrange=True)

    tranches = livre.n("gagnes") + livre.n("perdus")
    bases, longueurs, hauteurs, teintes, survols = [], [], [], [], []

    for noeud in noeuds:
        x, largeur = COLONNES[noeud["niveau"]]
        y, part = noeud["y"], noeud["valeur"] / total
        parent = par_cle.get(noeud["parent"])
        if parent is not None:
            # Lien parent → enfant : une courbe fine, jamais une flèche.
            xp, lp = COLONNES[parent["niveau"]]
            depart, arrivee = xp + lp, x - 0.015
            milieu = (depart + arrivee) / 2
            fig.add_shape(type="path", layer="below",
                          path=(f"M {depart},{parent['y']} C {milieu},{parent['y']} "
                                f"{milieu},{y} {arrivee},{y}"),
                          line=dict(color=AXIS, width=1))
        # Piste de la barre de proportion (fond), puis la marque elle-même —
        # une vraie marque de données, pour qu’elle porte le survol.
        fig.add_shape(type="rect", x0=x, x1=x + largeur, y0=y - 0.058, y1=y - 0.044,
                      fillcolor=_rgba(INK, 0.07), line_width=0, layer="below")
        bases.append(x)
        longueurs.append(largeur * max(part, 0.012))
        hauteurs.append(y - 0.051)
        teintes.append(noeud["couleur"])
        detail = f"{pluriel(noeud['valeur'], 'questionnaire')} · {fmt_pct(part, 1)} du total reçu"
        if noeud["cle"] in ("c_gagnes", "c_perdus") and tranches:
            detail += f" · {fmt_pct(noeud['valeur'] / tranches, 0)} des dossiers tranchés"
        survols.append(f"<b>{noeud['libelle']}</b><br>{detail}")
        fig.add_annotation(x=x, y=y + 0.068, text=noeud["libelle"].upper(),
                           showarrow=False, xanchor="left", yanchor="middle",
                           font=dict(size=10.5, color=INK_MUTED, family=FONT_STACK))
        fig.add_annotation(x=x, y=y + 0.012, text=f"<b>{fmt_int(noeud['valeur'])}</b>",
                           showarrow=False, xanchor="left", yanchor="middle",
                           font=dict(size=TAILLES[noeud["niveau"]], color=INK,
                                     family=FONT_STACK))
        fig.add_annotation(x=x + largeur, y=y - 0.051, text=fmt_pct(part, 1),
                           showarrow=False, xanchor="left", yanchor="middle",
                           xshift=6, font=dict(size=10.5, color=INK_MUTED,
                                               family=FONT_STACK))

    fig.add_trace(go.Bar(
        x=longueurs, base=bases, y=hauteurs, orientation="h", width=0.014,
        marker=dict(color=teintes, line_width=0), customdata=survols,
        hovertemplate="%{customdata}<extra></extra>", showlegend=False))

    gagnes = livre.n("gagnes")
    accroche = (f"{fmt_int(total)} questionnaires reçus : {fmt_pct(n_dd / total, 0)} de due "
                f"diligence, {fmt_int(n_rfp)} appels d’offres")
    accroche += (f", dont {fmt_int(gagnes)} remportés sur {fmt_int(tranches)} tranchés."
                 if tranches else ", aucun encore tranché.")

    tableau = pd.DataFrame([{
        "Niveau": ("Total", "Famille", "Résultat de l’appel d’offres")[n["niveau"]],
        "Catégorie": n["libelle"], "Questionnaires": fmt_int(n["valeur"]),
        "Part du total": fmt_pct(n["valeur"] / total, 1)} for n in noeuds])
    return Block("decomposition", "synthese", "Décomposition de l’activité",
                 accroche, fig, tableau,
                 note="La branche « due diligence » n’a pas de suite : une due diligence "
                      "se traite, elle ne se gagne pas. Les états d’un appel d’offres "
                      "sont exclusifs et couvrent son total. La barre sous chaque nombre "
                      "est sa part du total reçu.",
                 large=True)


def _bloc_trimestre(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Ce qui s’est passé, trimestre après trimestre — huit points de repère.

    Quatre mouvements seulement, et seulement ceux qu’on sait dater : ce qui
    arrive (réception), ce qui part (envoi), et ce que ça rapporte. Une décision
    client n’a pas de date dans la base : elle ne figure donc pas ici, plutôt
    que d’être rattachée à une date qui n’est pas la sienne.
    """
    if df.empty or len(df) < 20:
        return None
    trimestre_courant = pd.Timestamp.today().normalize().to_period("Q")
    recus = df.assign(_t=df["date_reception"].dt.to_period("Q"))
    envoyes = df[df["date_envoi"].notna()].assign(
        _t=df.loc[df["date_envoi"].notna(), "date_envoi"].dt.to_period("Q"))

    fin = recus["_t"].max()
    periodes = pd.period_range(end=fin, periods=min(8, recus["_t"].nunique()), freq="Q")
    if len(periodes) < 3:
        return None

    def serie(source: pd.DataFrame, masque: pd.Series | None = None,
              colonne: str | None = None) -> list[float]:
        sous = source if masque is None else source[masque.reindex(source.index, fill_value=False)]
        if colonne:
            groupe = sous.groupby("_t", observed=True)[colonne].sum()
        else:
            groupe = sous.groupby("_t", observed=True).size()
        # Un trimestre sans mandat remporté vaut zéro, pas « donnée absente » :
        # la distinction compte, et `or 0` laisserait passer un NaN.
        valeurs = [groupe.get(p, 0.0) for p in periodes]
        return [0.0 if pd.isna(v) else float(v) for v in valeurs]

    mouvements = [
        ("Questionnaires reçus", serie(recus), fmt_int, SERIES[0]),
        ("Appels d’offres reçus", serie(recus, recus["est_rfp"]), fmt_int, SERIES[0]),
        ("Réponses envoyées", serie(envoyes), fmt_int, SERIES[0]),
        ("Encours remporté", serie(recus, None, "aum_gagne"),
         lambda v: fmt_encours(v), SERIES[0]),
    ]
    mouvements = [m for m in mouvements if any(m[1])]
    if not mouvements:
        return None

    libelles = [f"T{p.quarter} {p.year}" for p in periodes]
    partiel = periodes[-1] == trimestre_courant
    fig = make_subplots(rows=1, cols=len(mouvements), horizontal_spacing=0.055)
    fig.update_layout(template=TEMPLATE_NAME, height=252, showlegend=False,
                      margin=dict(l=4, r=4, t=64, b=26), bargap=0.34)

    for colonne, (titre, valeurs, formateur, teinte) in enumerate(mouvements, start=1):
        # Le trimestre en cours est incomplet : il se distingue au lieu de se
        # faire passer pour un trimestre plein.
        couleurs = [_rgba(teinte, 0.30) if (partiel and i == len(valeurs) - 1)
                    else _rgba(teinte, 0.85) for i in range(len(valeurs))]
        couleurs[-1] = couleurs[-1] if partiel else teinte
        fig.add_trace(go.Bar(
            x=libelles, y=valeurs, marker=_marque(couleurs, 1.2),
            customdata=[formateur(v) for v in valeurs],
            hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>"),
            row=1, col=colonne)
        fig.update_yaxes(visible=False, rangemode="tozero",
                         range=[0, max(valeurs) * 1.28 or 1], row=1, col=colonne)
        fig.update_xaxes(showgrid=False, tickfont=dict(size=9.5, color=INK_MUTED),
                         tickvals=[libelles[0], libelles[-1]], row=1, col=colonne)
        ancre = "x domain" if colonne == 1 else f"x{colonne} domain"
        ancre_y = "y domain" if colonne == 1 else f"y{colonne} domain"
        fig.add_annotation(xref=ancre, yref=ancre_y, x=0, y=1.36, xanchor="left",
                           text=titre.upper(), showarrow=False,
                           font=dict(size=9.5, color=INK_MUTED, family=FONT_STACK))
        fig.add_annotation(xref=ancre, yref=ancre_y, x=0, y=1.12, xanchor="left",
                           text=f"<b>{formateur(valeurs[-1])}</b>", showarrow=False,
                           font=dict(size=20, color=INK, family=FONT_STACK))
        # Un trimestre en cours ne se compare pas : afficher « −100 % » sur un
        # trimestre à moitié écoulé serait un chiffre faux présenté comme vrai.
        ecart = (("", "neutre", "plat") if partiel else
                 _delta(valeurs[-1], valeurs[-2] if len(valeurs) > 1 else None,
                        mode="relatif"))
        if ecart[0]:
            fig.add_annotation(
                xref=ancre, yref=ancre_y, x=1, y=1.12, xanchor="right",
                text=ecart[0], showarrow=False,
                font=dict(size=11, family=FONT_STACK,
                          color={"bon": TEXTE_BON, "mauvais": TEXTE_MAUVAIS}.get(
                              ecart[1], INK_MUTED)))

    dernier = libelles[-1]
    accroche = (f"{dernier} : {fmt_int(mouvements[0][1][-1])} questionnaires reçus"
                + (" — trimestre en cours, donc incomplet." if partiel
                   else f", contre {fmt_int(mouvements[0][1][-2])} au trimestre précédent."))
    tableau = pd.DataFrame(
        {"Trimestre": libelles}
        | {titre: [formateur(v) for v in valeurs]
           for titre, valeurs, formateur, _ in mouvements}).iloc[::-1]
    return Block("trimestre", "synthese", "Les huit derniers trimestres", accroche, fig,
                 tableau,
                 note=("Le dernier trimestre est en cours : sa barre est atténuée et sa "
                       "comparaison n’a pas de valeur. " if partiel else "")
                      + "« Reçus » se date par la réception, « envoyées » par l’envoi, "
                        "l’encours remporté par la réception du dossier gagné. Une décision "
                        "client n’a pas de date dans la base : elle ne figure pas ici.",
                 large=True)


def _bloc_mandats_remportes(df: pd.DataFrame, mensuel: pd.DataFrame,
                            stats: dict) -> Block | None:
    """Les mandats remportés, un par ligne : qui, par quel canal, sur quelle
    classe d\u2019actifs, pour quel encours. La table de fin de revue.

    Bloc sans figure : cette réponse-là se lit ligne à ligne.
    """
    gagnes = df[df["est_rfp"] & df["est_gagne"]]
    if gagnes.empty:
        return None
    colonnes = [("client", "Client"), ("consultant", "Consultant"), ("pays", "Pays"),
                ("classe_actifs", "Classe d\u2019actifs"),
                ("sous_classe_actifs", "Sous-classe"),
                ("forme_juridique", "Forme juridique"), ("fonds", "Fonds de référence")]
    dispo = [(c, l) for c, l in colonnes if c in gagnes.columns]
    if not dispo:
        return None

    tri = (gagnes.sort_values("montant_potentiel", ascending=False, na_position="last")
           if "montant_potentiel" in gagnes.columns else gagnes)
    tete = tri.head(TOP_MANDATS)
    table = tete[[c for c, _ in dispo]].astype(object).fillna("—")
    table.columns = [l for _, l in dispo]
    if "montant_potentiel" in gagnes.columns:
        table["Encours (M€)"] = [fmt_dec(v, 0) if pd.notna(v) else "—"
                                 for v in tete["montant_potentiel"]]
    table = table.reset_index(drop=True)

    encours_total = aum_gagne(df)
    if len(tri) > len(tete):
        queue = tri.iloc[len(tete):]
        ligne = {c: "" for c in table.columns}
        ligne[table.columns[0]] = f"Autres mandats ({fmt_int(len(queue))})"
        if "Encours (M€)" in table.columns:
            ligne["Encours (M€)"] = fmt_dec(queue["montant_potentiel"].sum(skipna=True), 0)
        table.loc[len(table)] = ligne
    if "Encours (M€)" in table.columns:
        totaux = {c: "" for c in table.columns}
        totaux[table.columns[0]] = f"Total — {fmt_int(len(tri))} mandats"
        totaux["Encours (M€)"] = fmt_dec(encours_total, 0)
        table.loc[len(table)] = totaux

    part = encours_total / len(tri) if len(tri) else float("nan")
    accroche = (f"{fmt_int(len(tri))} mandats remportés, {fmt_encours(encours_total)} "
                f"d\u2019encours, soit {fmt_dec(part, 0, 'M€')} par mandat en moyenne.")
    return Block("mandats_remportes", "aum", "Mandats remportés", accroche,
                 None, table,
                 note=f"Les {TOP_MANDATS} premiers par encours ; le reste est agrégé, le "
                      f"total est exact. La liste complète est dans l\u2019explorateur, "
                      f"filtrée sur les appels d\u2019offres gagnés.",
                 large=True)


def _periode_en_cours(horodatage: Any, granularite: str) -> bool:
    """La dernière période est-elle encore en cours ?"""
    ts, today = pd.Timestamp(horodatage), pd.Timestamp.today().normalize()
    if granularite == "annee":
        return ts.year == today.year
    if granularite == "trimestre":
        return ts.to_period("Q") == today.to_period("Q")
    return ts.to_period("M") == today.to_period("M")


def _bloc_resultats_rfp(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Que deviennent les appels d’offres remis ?"""
    comptes = compte_resultats(df)
    if comptes.empty or comptes.sum() == 0:
        return None
    total = int(comptes.sum())
    couleurs = _couleurs_resultat()
    fig = _fig(300)
    fig.add_trace(go.Bar(
        y=list(comptes.index), x=list(comptes.values), orientation="h",
        marker=_marque([couleurs.get(r, SERIES[0]) for r in comptes.index]),
        text=[f"{fmt_int(v)}   {fmt_pct(v / total, 0)}" for v in comptes.values],
        textposition="outside", cliponaxis=False, textfont=dict(color=INK_2, size=12),
        hovertemplate="%{y} : %{x} RFP<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Appels d’offres")
    _labels_exterieurs(fig, list(comptes.values), 1.32)

    taux, gagnes, tranches, ic = taux_succes_rfp(df)
    attente = int(comptes.get(RESULTAT_ATTENTE, 0))
    accroche = (f"{fmt_int(gagnes)} mandats remportés sur {fmt_int(tranches)} dossiers "
                f"tranchés, soit {fmt_pct(taux, 1)} (IC 95{NBSP}% {fmt_pct(ic[0], 0)}–"
                f"{fmt_pct(ic[1], 0)}).")
    if attente:
        accroche += (f" {pluriel(attente, 'dossier')} encore en attente "
                     f"de décision.")
    tableau = pd.DataFrame({
        "Résultat": list(comptes.index), "Dossiers": list(comptes.values),
        "Part": [fmt_pct(v / total, 1) for v in comptes.values]})
    return Block("resultats_rfp", "rfp", "Résultat des appels d’offres",
                 accroche, fig, tableau,
                 note="Les dossiers en attente de décision sortent du dénominateur du "
                      "taux de succès ; ils ne sont pas des échecs. « Sans suite » "
                      "désigne les dossiers auxquels le pôle n’a pas répondu.")


def _bloc_cadence(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Capacité de production : ce que l’équipe termine, mois après mois."""
    if df.empty or df["date_envoi"].notna().sum() < 12:
        return None
    envoyes = df.dropna(subset=["date_envoi"]).copy()
    envoyes["_mois"] = envoyes["date_envoi"].dt.to_period("M").dt.to_timestamp()
    pivot = envoyes.pivot_table(index="_mois", columns="famille", values="date_envoi",
                                aggfunc="size", fill_value=0)
    pivot = pivot.reindex(pd.date_range(pivot.index.min(), pivot.index.max(), freq="MS"),
                          fill_value=0)
    if len(pivot) < 4:
        return None
    couleurs = _couleurs_famille()
    fig = _fig(340, hovermode="x unified")
    for famille in [f for f in FAMILLE_ORDER if f in pivot.columns]:
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[famille], mode="lines", name=str(famille),
            line=dict(color=couleurs[famille], width=2),
            hovertemplate="%{y:.0f} " + str(famille) + "<extra></extra>"))
    _axe_periode(fig, pivot.index, "mois")
    fig.update_yaxes(title_text="Dossiers terminés", rangemode="tozero")

    cadence_dd = cadence_mensuelle(df, FAMILLE_DD)
    cadence_rfp = cadence_mensuelle(df, FAMILLE_RFP)
    accroche = (f"L’équipe termine en moyenne {fmt_dec(cadence_dd, 1)} due diligences et "
                f"{fmt_dec(cadence_rfp, 1)} appels d’offres par mois.")
    tableau = pivot.copy()
    tableau.insert(0, "Mois", [fmt_mois(i) for i in pivot.index])
    tableau["Total"] = pivot.sum(axis=1).to_numpy()
    return Block("cadence", "activite", "Cadence de traitement", accroche, fig,
                 tableau.reset_index(drop=True),
                 note="Comptage par date d’ENVOI : c’est la production de l’équipe, à "
                      "distinguer de la charge qui lui arrive.")


# =============================================================================
#  02 — ACTIVITÉ
# =============================================================================
def _bloc_volume_annuel(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """La question structurelle : la charge augmente-t-elle, et de quel côté ?"""
    annuel = volume_annuel(df)
    if annuel.empty or len(annuel) < 3:
        return None
    familles = [c for c in annuel.columns if c != "Total"]
    index = list(annuel.index)
    en_cours = index[-1] == pd.Timestamp.today().year

    fig = _fig(400, barmode="stack", hovermode="x unified")
    _empiler(fig, index, annuel[familles], _couleurs_famille())
    if en_cours:
        fig.add_annotation(xref="paper", yref="paper", x=1, y=1.04, xanchor="right",
                           yanchor="bottom", text="année en cours, partielle",
                           font=dict(size=10.5, color=INK_MUTED))
    fig.update_xaxes(tickmode="array", tickvals=index, ticktext=[str(a) for a in index])
    fig.update_yaxes(title_text="Questionnaires reçus", rangemode="tozero")
    fig.update_layout(bargap=0.3)

    croissances = [croissance(df, h) for h in HORIZONS_CROISSANCE]
    croissances = [c for c in croissances if c is not None]
    stats["croissances"] = croissances
    if croissances:
        c = croissances[0]
        accroche = (f"{c.volume_reference} questionnaires en {c.annee_reference}, "
                    f"contre {c.volume_base} en {c.annee_base} : "
                    f"{fmt_pct(c.taux, 0)} sur {c.horizon} ans "
                    f"({fmt_pct(c.tcam, 1)} par an).")
    else:
        accroche = f"{fmt_int(int(annuel['Total'].sum()))} questionnaires sur la période."
    part_dd_debut = annuel[FAMILLE_DD].iloc[0] / max(annuel["Total"].iloc[0], 1) \
        if FAMILLE_DD in annuel.columns else float("nan")
    part_dd_fin = annuel[FAMILLE_DD].iloc[-1] / max(annuel["Total"].iloc[-1], 1) \
        if FAMILLE_DD in annuel.columns else float("nan")
    if math.isfinite(part_dd_debut) and math.isfinite(part_dd_fin):
        accroche += (f" La part de due diligence est passée de {fmt_pct(part_dd_debut, 0)} "
                     f"à {fmt_pct(part_dd_fin, 0)}.")
    tableau = annuel.reset_index()
    tableau["annee"] = tableau["annee"].astype(str)
    tableau = tableau.rename(columns={"annee": "Année"})
    return Block("volume_annuel", "activite", "Évolution annuelle de la charge",
                 accroche, fig, tableau,
                 note="L’année en cours est partielle : elle ne se compare pas aux années "
                      "pleines, et elle est exclue des taux de croissance.", large=True)


def _bloc_delai_famille(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Combien de temps prend un dossier, selon sa nature ?"""
    if not _dispo(df, "delai_calendaire"):
        return None
    familles = [f for f in FAMILLE_ORDER
                if df.loc[df["famille"] == f, "delai_calendaire"].notna().sum() >= 5]
    if not familles:
        return None
    couleurs = _couleurs_famille()
    fig = _fig(max(280, 82 * len(familles) + 80))
    for famille in familles:
        valeurs = df.loc[df["famille"] == famille, "delai_calendaire"].dropna()
        fig.add_trace(go.Box(
            x=valeurs, name=str(famille), orientation="h", boxpoints="outliers",
            marker=dict(color=_rgba(couleurs[famille], 0.45), size=5,
                        line=dict(color=SURFACE, width=1)),
            fillcolor=_rgba(couleurs[famille], 0.18),
            line=dict(color=couleurs[famille], width=1.6), whiskerwidth=0.45,
            hovertemplate="%{x:.0f} jours<extra>" + str(famille) + "</extra>"))
    fig.update_yaxes(
        tickmode="array", tickvals=list(range(len(familles))),
        ticktext=[f"{f}<br><span style='font-size:10.5px;color:{INK_MUTED}'>"
                  f"médiane {fmt_dec(delai_median(df, f), 0)} j</span>" for f in familles],
        autorange="reversed")
    fig.update_xaxes(title_text="Délai de traitement (jours calendaires)", rangemode="tozero")
    fig.update_layout(showlegend=False, boxgap=0.45)

    lignes = []
    for famille in familles:
        sous = df[df["famille"] == famille]
        v = sous["delai_calendaire"].dropna()
        lignes.append({
            "Famille": famille, "Dossiers traités": int(v.size),
            "1er quartile": fmt_dec(v.quantile(0.25), 0, "j"),
            "Médiane": fmt_dec(v.median(), 0, "j"),
            "3e quartile": fmt_dec(v.quantile(0.75), 0, "j"),
            "9e décile": fmt_dec(v.quantile(0.9), 0, "j"),
            "Respect du délai cible": fmt_pct(sous["dans_sla"].mean(), 1),
        })
    plus_long = max(familles, key=lambda f: delai_median(df, f))
    accroche = (f"Un dossier « {plus_long} » demande {fmt_dec(delai_median(df, plus_long), 0)} "
                f"jours calendaires en médiane, contre "
                f"{fmt_dec(delai_median(df, familles[0] if familles[0] != plus_long else familles[-1]), 0)} "
                f"pour l’autre famille.")
    return Block("delai_famille", "activite", "Délais de traitement par famille",
                 accroche, fig, pd.DataFrame(lignes),
                 note="Jours calendaires, comme au comité. Boîte = 1er au 3e quartile, "
                      "moustaches = 1,5 × écart interquartile ; au-delà, chaque point est "
                      "un dossier.")


# =============================================================================
#  03 — PIPELINE RFP
# =============================================================================
def _bloc_rfp_resultats_annee(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Le taux de succès se maintient-il dans le temps ?"""
    rfp = df[df["est_rfp"]]
    if len(rfp) < 12:
        return None
    pivot = rfp.pivot_table(index=rfp["date_reception"].dt.year, columns="resultat",
                            values="date_reception", aggfunc="size", fill_value=0)
    if len(pivot) < 2:
        return None
    ordre = [r for r in RESULTAT_ORDER if r in pivot.columns]
    pivot = pivot[ordre]
    index = list(pivot.index)
    fig = _fig(370, barmode="stack", hovermode="x unified")
    _empiler(fig, index, pivot, _couleurs_resultat(), " RFP")
    fig.update_xaxes(tickmode="array", tickvals=index, ticktext=[str(a) for a in index])
    fig.update_yaxes(title_text="Appels d’offres reçus", rangemode="tozero")
    fig.update_layout(bargap=0.3)

    tranches = pivot.get(RESULTAT_GAGNE, 0) + pivot.get(RESULTAT_PERDU, 0)
    taux_annuel = (pivot.get(RESULTAT_GAGNE, 0) / tranches.replace(0, np.nan)).dropna()
    if len(taux_annuel) >= 2:
        meilleure = taux_annuel.idxmax()
        accroche = (f"Taux de succès le plus élevé en {meilleure} "
                    f"({fmt_pct(taux_annuel.max(), 0)}), le plus bas en "
                    f"{taux_annuel.idxmin()} ({fmt_pct(taux_annuel.min(), 0)}).")
    else:
        accroche = f"{fmt_int(len(rfp))} appels d’offres reçus sur la période."
    tableau = pivot.copy()
    tableau.insert(0, "Année", [str(a) for a in index])
    tableau["Taux de succès"] = [fmt_pct(v, 0) if pd.notna(v) else "—"
                                 for v in (pivot.get(RESULTAT_GAGNE, 0) / tranches.replace(0, np.nan))]
    return Block("rfp_resultats_annee", "rfp", "Résultats par année",
                 accroche, fig, tableau.reset_index(drop=True),
                 note="Les dossiers récents sont surreprésentés en « En attente » : une "
                      "décision client intervient plusieurs mois après la remise.",
                 large=True)


def _bloc_rfp_reception(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Rythme d’arrivée des appels d’offres."""
    rfp = df[df["est_rfp"]]
    if len(rfp) < 12:
        return None
    serie = (rfp.assign(_m=rfp["date_reception"].dt.to_period("M").dt.to_timestamp())
             .groupby("_m").size())
    serie = serie.reindex(pd.date_range(serie.index.min(), serie.index.max(), freq="MS"),
                          fill_value=0)
    if len(serie) < 4:
        return None
    fig = _fig(320, hovermode="x unified")
    fig.add_trace(go.Bar(x=serie.index, y=serie.values, name="Appels d’offres reçus",
                         marker=_marque(SERIES[1], 1.2),
                         hovertemplate="%{y} RFP<extra></extra>"))
    if len(serie) >= 8:
        lissage = serie.rolling(3, min_periods=2).mean()
        fig.add_trace(go.Scatter(x=serie.index, y=lissage, mode="lines",
                                 name="Moyenne mobile 3 mois",
                                 line=dict(color=INK, width=2),
                                 hovertemplate="Moyenne : %{y:.1f}<extra></extra>"))
    _axe_periode(fig, serie.index, "mois")
    fig.update_yaxes(title_text="Appels d’offres reçus", rangemode="tozero")
    pic = serie.idxmax()
    accroche = (f"{fmt_dec(serie.mean(), 1)} appel{accord(serie.mean())} d’offres "
                f"par mois en moyenne ; "
                f"pic à {int(serie.max())} en {fmt_mois(pic)}.")
    tableau = pd.DataFrame({"Mois": [fmt_mois(i) for i in serie.index],
                            "Appels d’offres reçus": serie.values})
    return Block("rfp_reception", "rfp", "Arrivée des appels d’offres", accroche, fig,
                 tableau, note="Comptage par date de réception. La moyenne mobile lisse "
                               "l’irrégularité propre aux appels d’offres.")


def _succes_par(df: pd.DataFrame, champ: str, cle: str, titre: str,
                min_tranches: int = 5) -> Block | None:
    """Où gagne-t-on ? Taux de succès par modalité d’une dimension, avec son
    intervalle de confiance et l’encours remporté."""
    rfp = df[df["est_rfp"] & df["resultat"].isin([RESULTAT_GAGNE, RESULTAT_PERDU])]
    if len(rfp) < 12 or not _dispo(rfp, champ, min_modalites=2):
        return None
    groupe = rfp.groupby(champ, observed=True).agg(
        tranches=("resultat", "size"),
        gagnes=("est_gagne", "sum"),
        aum=("aum_gagne", "sum"),
        perdu=("montant_potentiel", lambda s: float(s[rfp.loc[s.index, "est_perdu"]].sum())))
    groupe = groupe[(groupe["tranches"] >= min_tranches) & (groupe.index != VALEUR_INCONNUE)]
    if len(groupe) < 2:
        return None
    groupe["taux"] = groupe["gagnes"] / groupe["tranches"]
    ic = [wilson_ci(int(g), int(n)) for g, n in zip(groupe["gagnes"], groupe["tranches"])]
    groupe["bas"], groupe["haut"] = [a for a, _ in ic], [b for _, b in ic]
    groupe = groupe.sort_values("taux")

    global_taux = taux_succes_rfp(df)[0]
    x = groupe["taux"] * 100
    fig = _fig(max(300, 50 * len(groupe) + 96))
    fig.add_trace(go.Bar(
        y=groupe.index, x=x, orientation="h", marker=_marque(SERIES[1]),
        error_x=dict(type="data", symmetric=False,
                     array=(groupe["haut"] - groupe["taux"]) * 100,
                     arrayminus=(groupe["taux"] - groupe["bas"]) * 100,
                     color=INK_MUTED, thickness=1.2, width=5),
        customdata=np.stack([groupe["gagnes"], groupe["tranches"], groupe["aum"]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Taux de succès : %{x:.0f} %"
                       "<br>%{customdata[0]:.0f} gagnés sur %{customdata[1]:.0f} tranchés"
                       "<br>Encours remporté : %{customdata[2]:,.0f} M€<extra></extra>")))
    if pd.notna(global_taux):
        fig.add_vline(x=global_taux * 100, line=dict(color=INK, width=1),
                      annotation_text=f"moyenne : {fmt_pct(global_taux, 0)}",
                      annotation_position="top", annotation_font=dict(color=INK_2, size=11))
    borne = float((groupe["haut"] * 100).max())
    for modalite, ligne in groupe.iterrows():
        fig.add_annotation(x=borne * 1.05, y=modalite, xanchor="left",
                           text=f"{fmt_pct(ligne['taux'], 0)}   ·   n = {int(ligne['tranches'])}",
                           font=dict(size=11.5, color=INK_2))
    fig.update_xaxes(title_text="Taux de succès", ticksuffix=ESP_UNITE + "%",
                     range=[0, borne * 1.45])

    meilleure, pire = groupe.iloc[-1], groupe.iloc[0]
    accroche = (f"« {groupe.index[-1]} » convertit {fmt_pct(meilleure['taux'], 0)} des "
                f"dossiers tranchés contre {fmt_pct(pire['taux'], 0)} pour "
                f"« {groupe.index[0]} »"
                + (" — écart significatif au seuil de 5 %."
                   if meilleure["bas"] > pire["haut"]
                   else " — mais les intervalles se recouvrent : l’écart n’est pas établi."))
    tableau = groupe.reset_index()[[champ, "tranches", "gagnes", "taux", "aum", "perdu"]]
    tableau["taux"] = tableau["taux"].map(lambda v: fmt_pct(v, 1))
    tableau["aum"] = tableau["aum"].map(lambda v: fmt_dec(v, 0, "M€"))
    tableau["perdu"] = tableau["perdu"].map(lambda v: fmt_dec(v, 0, "M€"))
    tableau.columns = [DIMENSIONS.get(champ, champ), "Tranchés", "Gagnés", "Taux de succès",
                       "Encours remporté", "Encours perdu"]
    return Block(cle, "rfp", titre, accroche, fig, tableau.sort_values("Tranchés", ascending=False),
                 note="Moustaches = intervalle de confiance de Wilson à 95 %. Deux modalités "
                      "dont les intervalles se recouvrent ne sont pas départageables. "
                      f"Modalités de moins de {min_tranches} décisions écartées.",
                 dimension=champ)


def _bloc_rfp_succes_dimension(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    return _succes_par(df, "classe_actifs", "rfp_succes", "Taux de succès par classe d’actifs")


def _bloc_rfp_segment(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    return _succes_par(df, "segment", "rfp_segment", "Taux de succès par segment de client")


def _bloc_rfp_commercial(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    return _succes_par(df, "commercial", "rfp_commercial", "Taux de succès par commercial")


def _bloc_entonnoir(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Le chemin des appels d’offres : combien franchissent chaque étape, et
    quel encours ils portent."""
    chemin = entonnoir(df)
    if len(chemin) < 3 or chemin[0]["n"] < 5:
        return None
    libelles = [e["libelle"] for e in chemin]
    effectifs = [e["n"] for e in chemin]
    encours = [e["encours"] for e in chemin]
    # Les étapes se lisent de haut en bas ; le ton s’assombrit à mesure qu’on
    # approche du mandat, le libellé et les deux valeurs sont écrits.
    tons = [teinte(t) for t in np.linspace(0.30, 1.0, len(chemin))]
    fig = _fig(max(280, 52 * len(chemin) + 80), margin=dict(l=8, r=16, t=18, b=8))
    fig.add_trace(go.Bar(
        y=libelles, x=effectifs, orientation="h", marker=_marque(tons, 1.2),
        text=[f"{fmt_int(n)}   ·   {fmt_encours(e)}" for n, e in zip(effectifs, encours)],
        textposition="outside", cliponaxis=False, textfont=dict(color=INK_2, size=12),
        customdata=np.stack([encours, [e["part_du_total"] * 100 for e in chemin],
                             [(e["passage"] * 100) if pd.notna(e["passage"]) else float("nan") for e in chemin]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>%{x} appels d’offres · %{customdata[0]:,.0f} M€"
                       "<br>%{customdata[1]:.0f} % des reçus · %{customdata[2]:.0f} % de l’étape précédente"
                       "<extra></extra>")))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Appels d’offres", rangemode="tozero")
    _labels_exterieurs(fig, effectifs, 1.55)
    for i in range(1, len(chemin)):
        p = chemin[i]["passage"]
        if pd.notna(p):
            fig.add_annotation(x=0, y=i - 0.5, xanchor="left", yanchor="middle", xshift=-4,
                               text=f"↓ {fmt_pct(p, 0)}", showarrow=False,
                               font=dict(size=10.5, color=INK_MUTED))

    remis = next((e for e in chemin if e["cle"] == "remis"), chemin[0])
    dernier = chemin[-1]
    accroche = (f"Sur {fmt_int(chemin[0]['n'])} appels d’offres reçus, {fmt_int(remis['n'])} en Step 1 ; "
                f"{fmt_int(dernier['n'])} remporté{accord(dernier['n'])} "
                f"({fmt_pct(dernier['n'] / remis['n'] if remis['n'] else float('nan'), 0)} des Step 1), "
                f"pour {fmt_encours(dernier['encours'])} d’encours.")
    tableau = pd.DataFrame({
        "Étape": libelles, "Appels d’offres": [fmt_int(n) for n in effectifs],
        "Encours (M€)": [fmt_dec(e, 0) for e in encours],
        "Part des reçus": [fmt_pct(e["part_du_total"], 0) for e in chemin],
        "Passage depuis l’étape précédente": [fmt_pct(e["passage"], 0) if pd.notna(e["passage"]) else "—"
                                              for e in chemin]})
    return Block("entonnoir", "rfp", "Le chemin des appels d’offres", accroche, fig, tableau,
                 note="Les étapes portent le nom des colonnes du classeur : Step 1 (Step_1, "
                      "proposition déposée), Step 2 (Step_2, retenu après lecture) et Oral "
                      "(ORAL_RFP, présentation devant le client). Les dossiers encore en attente "
                      "comptent dans les étapes franchies, pas dans les remportés.",
                 large=True)


def _bloc_rfp_ouverts(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Les appels d’offres encore ouverts, un par ligne, l’encours le plus
    important d’abord. Bloc sans figure : cette réponse se lit ligne à ligne."""
    ouverts = df[df["est_rfp"] & df["statut"].isin([STATUT_EN_COURS, STATUT_ENVOYE])]
    if ouverts.empty:
        return None
    aujourdhui = pd.Timestamp.today().normalize()
    tri = ouverts.sort_values("montant_potentiel", ascending=False, na_position="last")
    etat = np.where(tri["statut"].eq(STATUT_EN_COURS), "En rédaction", "En attente")
    depuis = np.where(tri["statut"].eq(STATUT_EN_COURS),
                      (aujourdhui - tri["date_reception"]).dt.days,
                      (aujourdhui - tri["date_envoi"].fillna(tri["date_reception"])).dt.days)
    etape = []
    for _, l in tri.iterrows():
        if l.get("a_oral"):
            etape.append("Oral")
        elif l.get("a_preselection"):
            etape.append("Step 2")
        elif l.get("a_remis"):
            etape.append("Step 1")
        else:
            etape.append("—")
    # Huit colonnes, pas plus : le suivi commercial et le consultant sont sur
    # la fiche du dossier et dans le tableau de l’écran Situation.
    colonnes = {"Client": tri["client"], "Segment": tri["segment"], "Pays": tri["pays"],
                "Classe d’actifs": tri["classe_actifs"], "État": etat, "Étape": etape,
                "Depuis (j)": [fmt_int(v) for v in depuis],
                "Encours (M€)": [fmt_dec(v, 0) if pd.notna(v) else "—" for v in tri["montant_potentiel"]]}
    table = pd.DataFrame(colonnes).replace({VALEUR_INCONNUE: "—"}).reset_index(drop=True)
    for c in ("Segment", "Pays"):
        if (table[c] == "—").all():
            table = table.drop(columns=c)
    total = float(tri["montant_potentiel"].sum(skipna=True))
    ligne = {c: "" for c in table.columns}
    ligne["Client"] = pluriel(len(tri), "dossier")
    ligne["Encours (M€)"] = fmt_dec(total, 0)
    table.loc[len(table)] = ligne
    n_redaction = int(tri["statut"].eq(STATUT_EN_COURS).sum())
    accroche = (f"{pluriel(len(tri), 'appel d’offres', 'appels d’offres')} ouvert{accord(len(tri))}, "
                f"{fmt_encours(total)} d’encours en jeu : {fmt_int(n_redaction)} en rédaction, "
                f"{fmt_int(len(tri) - n_redaction)} en attente de décision.")
    return Block("rfp_ouverts", "rfp", "Les appels d’offres ouverts", accroche, None, table,
                 note="« En attente » : remis au client, non tranché. « Depuis » compte les jours "
                      "depuis la réception pour un dossier en rédaction, depuis la remise pour un "
                      "dossier en attente de décision.", large=True)


def _bloc_rfp_consultants(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Quels cabinets intermédiaires pèsent sur le flux d’appels d’offres ?"""
    rfp = df[df["est_rfp"]]
    if len(rfp) < 10 or not _dispo(rfp, "consultant", min_modalites=2):
        return None
    groupe = rfp.groupby("consultant", observed=True).agg(
        volume=("date_reception", "size"),
        gagnes=("est_gagne", "sum"),
        aum=("aum_gagne", "sum"))
    groupe = groupe[groupe.index != VALEUR_INCONNUE]
    if groupe.empty:
        return None
    survol = [f"{int(v)} RFP · {int(g)} gagné{accord(g)} · {fmt_encours(a)} remportés"
              for v, g, a in zip(groupe["volume"], groupe["gagnes"], groupe["aum"])]
    fig, complet = _figure_rang(groupe.index, groupe["volume"], fmt_int,
                                couleur=SERIES[1], top=10, survol=survol,
                                titre_axe="Appels d’offres")
    direct = int((rfp["consultant"] == VALEUR_INCONNUE).sum())
    accroche = (f"{fmt_int(int(groupe['volume'].sum()))} appels d’offres passent par un "
                f"cabinet ; {fmt_int(direct)} arrivent en direct "
                f"({fmt_pct(direct / max(len(rfp), 1), 0)}).")
    tableau = groupe.reset_index().sort_values("volume", ascending=False)
    tableau["aum"] = tableau["aum"].map(lambda v: fmt_dec(v, 0, "M€"))
    tableau.columns = ["Consultant", "RFP", "Gagnés", "Encours remporté"]
    return Block("rfp_consultants", "rfp", "Appels d’offres par consultant",
                 accroche, fig, tableau,
                 note="Les dossiers reçus en direct ne sont pas comptés dans le "
                      "classement ; leur volume figure dans le commentaire.",
                 dimension="consultant")


# =============================================================================
#  04 — DUE DILIGENCE
# =============================================================================
def _bloc_dd_mensuel(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    dd = df[df["est_dd"]]
    if len(dd) < 12:
        return None
    serie = (dd.assign(_m=dd["date_reception"].dt.to_period("M").dt.to_timestamp())
             .groupby("_m").size())
    serie = serie.reindex(pd.date_range(serie.index.min(), serie.index.max(), freq="MS"),
                          fill_value=0)
    fig = _fig(340, hovermode="x unified")
    fig.add_trace(go.Bar(x=serie.index, y=serie.values, name="Due diligence",
                         marker=_marque(SERIES[0], 1.2),
                         hovertemplate="%{y} due diligences<extra></extra>"))
    if len(serie) >= 8:
        fig.add_trace(go.Scatter(x=serie.index, y=serie.rolling(3, min_periods=2).mean(),
                                 mode="lines", name="Moyenne mobile 3 mois",
                                 line=dict(color=INK, width=2),
                                 hovertemplate="Moyenne : %{y:.1f}<extra></extra>"))
    _axe_periode(fig, serie.index, "mois")
    fig.update_yaxes(title_text="Due diligences reçues", rangemode="tozero")
    accroche = (f"{fmt_dec(serie.mean(), 1)} due diligences par mois en moyenne ; "
                f"pic à {int(serie.max())} en {fmt_mois(serie.idxmax())}.")
    tableau = pd.DataFrame({"Mois": [fmt_mois(i) for i in serie.index],
                            "Due diligences": serie.values})
    return Block("dd_mensuel", "dd", "Volume mensuel de due diligence", accroche, fig,
                 tableau, note="Comptage par date de réception.", large=True)


def _bloc_dd_expertise(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Quelles équipes de gestion absorbent la charge ?"""
    dd = df[df["est_dd"]]
    if len(dd) < 10 or not _dispo(dd, "expertise", min_modalites=2):
        return None
    groupe = dd.groupby("expertise", observed=True).agg(
        volume=("date_reception", "size"),
        delai=("delai_calendaire", "median"))
    total = int(groupe["volume"].sum())
    survol = [f"{int(v)} dossiers · {fmt_pct(v / total, 1)} de la charge · "
              f"délai médian {fmt_dec(d, 0, 'j')}"
              for v, d in zip(groupe["volume"], groupe["delai"])]
    fig, _ = _figure_rang(groupe.index, groupe["volume"], fmt_int, couleur=SERIES[0],
                          top=10, survol=survol, titre_axe="Due diligences")
    tete = groupe.sort_values("volume", ascending=False)
    part_trois = tete["volume"].head(3).sum() / max(total, 1)
    accroche = (f"« {tete.index[0]} » concentre {fmt_pct(tete['volume'].iloc[0] / total, 0)} "
                f"de la due diligence ; les trois premières expertises en absorbent "
                f"{fmt_pct(part_trois, 0)}.")
    tableau = tete.reset_index()
    tableau["part"] = (tete["volume"] / total).map(lambda v: fmt_pct(v, 1)).to_numpy()
    tableau["delai"] = tete["delai"].map(lambda v: fmt_dec(v, 0, "j")).to_numpy()
    tableau.columns = ["Expertise", "Dossiers", "Délai médian", "Part de la charge"]
    return Block("dd_expertise", "dd", "Charge par expertise", accroche, fig,
                 tableau[["Expertise", "Dossiers", "Part de la charge", "Délai médian"]],
                 note="Classement en barres plutôt qu’en camembert : au-delà de sept "
                      "catégories, aucune part d’un disque n’est comparable à l'œil.",
                 dimension="expertise")


def _bloc_dd_pays(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    dd = df[df["est_dd"]]
    if len(dd) < 10 or not _dispo(dd, "pays", min_modalites=2):
        return None
    groupe = dd.groupby("pays", observed=True).agg(volume=("date_reception", "size"),
                                                   clients=("client", "nunique"))
    total = int(groupe["volume"].sum())
    survol = [f"{int(v)} dossiers · {fmt_pct(v / total, 1)} · {pluriel(c, 'client')}"
              for v, c in zip(groupe["volume"], groupe["clients"])]
    fig, _ = _figure_rang(groupe.index, groupe["volume"], fmt_int, couleur=SERIES[0],
                          top=10, survol=survol, titre_axe="Due diligences")
    tete = groupe.sort_values("volume", ascending=False)
    accroche = (f"« {tete.index[0]} » représente {fmt_pct(tete['volume'].iloc[0] / total, 0)} "
                f"de la due diligence, répartie sur {int(tete['clients'].iloc[0])} clients.")
    tableau = tete.reset_index()
    tableau.columns = ["Pays", "Dossiers", "Clients distincts"]
    return Block("dd_pays", "dd", "Origine géographique de la due diligence",
                 accroche, fig, tableau, note="",
                 dimension="pays")


def _bloc_dd_matrice(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Croisement expertise × pays : où se concentre vraiment la charge ?"""
    dd = df[df["est_dd"]]
    if len(dd) < 40 or not (_dispo(dd, "expertise", min_modalites=3)
                            and _dispo(dd, "pays", min_modalites=3)):
        return None
    top_pays = dd["pays"].value_counts().head(8).index.tolist()
    top_exp = dd["expertise"].value_counts().head(8).index.tolist()
    sous = dd[dd["pays"].isin(top_pays) & dd["expertise"].isin(top_exp)]
    table = pd.crosstab(sous["expertise"], sous["pays"]).reindex(index=top_exp,
                                                                 columns=top_pays,
                                                                 fill_value=0)
    z = table.to_numpy(dtype=float, copy=True)
    maxi = z.max() if z.size else 1.0
    fig = _fig(max(300, 40 * len(top_exp) + 120))
    fig.add_trace(go.Heatmap(
        z=z, x=list(table.columns), y=list(table.index),
        colorscale=[[i / (len(SEQUENTIEL) - 1), c] for i, c in enumerate(SEQUENTIEL)],
        xgap=2, ygap=2, hoverongaps=False,
        colorbar=dict(title=dict(text="Dossiers", font=dict(size=11, color=INK_2)),
                      thickness=10, outlinewidth=0,
                      tickfont=dict(size=11, color=INK_MUTED), len=0.85),
        hovertemplate="%{y} · %{x} : %{z:.0f} dossiers<extra></extra>"))
    for i, expertise in enumerate(table.index):
        for j, pays in enumerate(table.columns):
            if z[i, j] > 0:
                fond = couleur_rampe(SEQUENTIEL, z[i, j] / maxi if maxi else 0)
                fig.add_annotation(x=pays, y=expertise, text=fmt_int(z[i, j]),
                                   font=dict(size=11, color=encre_lisible(fond)))
    fig.update_xaxes(showgrid=False, showline=False, ticks="", tickangle=-30)
    fig.update_yaxes(showgrid=False, showline=False, ticks="", autorange="reversed")
    i_max, j_max = np.unravel_index(np.argmax(z), z.shape)
    accroche = (f"Concentration maximale : « {table.index[i_max]} » pour "
                f"« {table.columns[j_max]} », {int(z[i_max, j_max])} dossiers.")
    tableau = table.reset_index()
    return Block("dd_matrice", "dd", "Expertise × pays", accroche, fig, tableau,
                 note="Huit premières expertises et huit premiers pays. Les cases vides "
                      "sont des croisements sans dossier.", large=True)


# =============================================================================
#  05 — ENCOURS & GAINS
# =============================================================================
def _bloc_aum_annuel(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """La collecte issue des appels d’offres, année par année."""
    gagnes = df[df["est_rfp"] & df["est_gagne"] & df["aum_gagne"].notna()]
    if len(gagnes) < 3:
        return None
    annuel = gagnes.groupby(gagnes["date_reception"].dt.year).agg(
        aum=("aum_gagne", "sum"), mandats=("aum_gagne", "size"))
    if len(annuel) < 2:
        return None
    index = list(annuel.index)
    fig = _fig(380, hovermode="x unified")
    fig.add_trace(go.Bar(
        x=index, y=annuel["aum"], name="Encours remporté",
        marker=_marque(SERIES[1], 1.2),
        customdata=np.stack([[pluriel(m, "mandat") for m in annuel["mandats"]],
                             (annuel["aum"] / annuel["mandats"]).map(
                                 lambda v: fmt_encours(v))], axis=-1),
        hovertemplate=("%{y:,.0f} M€<br>%{customdata[0]}"
                       "<br>Ticket moyen : %{customdata[1]}<extra></extra>")))
    moyenne = annuel["aum"].mean()
    fig.add_hline(y=moyenne, line=dict(color=INK, width=1),
                  annotation_text=f"moyenne : {fmt_dec(moyenne, 0, 'M€')}",
                  annotation_position="top left",
                  annotation_font=dict(color=INK_2, size=11))
    fig.update_xaxes(tickmode="array", tickvals=index, ticktext=[str(a) for a in index])
    fig.update_yaxes(title_text="Encours remporté (M€)", rangemode="tozero")
    fig.update_layout(bargap=0.32)
    _axe_valeurs(fig, float(annuel["aum"].max()) * 1.1,
                 lambda v: fmt_encours(v), axe="y")

    meilleure = annuel["aum"].idxmax()
    part = annuel["aum"].max() / max(annuel["aum"].sum(), 1)
    accroche = (f"{fmt_encours(annuel['aum'].sum())} remportés sur la période. "
                f"L’année {meilleure} en concentre {fmt_pct(part, 0)} à elle seule "
                f"({fmt_encours(annuel['aum'].max())}).")
    tableau = annuel.reset_index()
    tableau["ticket"] = (annuel["aum"] / annuel["mandats"]).to_numpy()
    tableau.columns = ["Année", "Encours remporté (M€)", "Mandats", "Ticket moyen (M€)"]
    tableau["Année"] = tableau["Année"].astype(str)
    return Block("aum_annuel", "aum", "Encours remporté par année", accroche, fig,
                 tableau.round(0),
                 note="Encours rattaché à l’année de RÉCEPTION du dossier. La collecte "
                      "issue des appels d’offres est par nature irrégulière : un mandat "
                      "peut représenter plusieurs fois le total d’une année ordinaire.",
                 large=True)


def _bloc_aum_clients(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    gagnes = df[df["est_rfp"] & df["est_gagne"] & df["aum_gagne"].notna()]
    if len(gagnes) < 3 or not _dispo(gagnes, "client", min_modalites=2):
        return None
    groupe = gagnes.groupby("client", observed=True).agg(
        aum=("aum_gagne", "sum"), mandats=("aum_gagne", "size"))
    survol = [f"{fmt_encours(a)} · {pluriel(m, 'mandat')}"
              for a, m in zip(groupe["aum"], groupe["mandats"])]
    fig, _ = _figure_rang(groupe.index, groupe["aum"],
                          lambda v: fmt_encours(v), couleur=SERIES[1], top=10,
                          survol=survol, titre_axe="Encours remporté (M€)")
    tete = groupe.sort_values("aum", ascending=False)
    part = tete["aum"].iloc[0] / max(groupe["aum"].sum(), 1)
    accroche = (f"« {tete.index[0]} » représente {fmt_pct(part, 0)} de l’encours remporté "
                f"({fmt_encours(tete['aum'].iloc[0])}).")
    tableau = tete.reset_index()
    tableau["aum"] = tableau["aum"].map(lambda v: fmt_dec(v, 0, "M€"))
    tableau.columns = ["Client", "Encours remporté", "Mandats"]
    return Block("aum_clients", "aum", "Clients par encours remporté", accroche, fig,
                 tableau, note="",
                 dimension="client")


def _bloc_aum_segment(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Où l’encours se joue : remporté, perdu et encore en jeu, par segment."""
    rfp = df[df["est_rfp"] & df["montant_potentiel"].notna()]
    if len(rfp) < 5 or not _dispo(rfp, "segment", min_modalites=2):
        return None
    g = rfp.groupby("segment", observed=True).apply(lambda s: pd.Series({
        "remporte": float(s.loc[s["est_gagne"], "montant_potentiel"].sum()),
        "perdu": float(s.loc[s["est_perdu"], "montant_potentiel"].sum()),
        "en_jeu": float(s.loc[s["statut"].isin([STATUT_EN_COURS, STATUT_ENVOYE]), "montant_potentiel"].sum()),
        "dossiers": int(len(s))}), include_groups=False)
    g = g[g.index != VALEUR_INCONNUE]
    g["total"] = g["remporte"] + g["perdu"] + g["en_jeu"]
    g = g[g["total"] > 0].sort_values("total")
    if len(g) < 2:
        return None
    fig = _fig(max(300, 44 * len(g) + 96), barmode="stack")
    series = [("remporte", "Remporté", COMPARTIMENT_COLORS["gagnes"]),
              ("en_jeu", "En jeu", COMPARTIMENT_COLORS["en_attente"]),
              ("perdu", "Perdu", COMPARTIMENT_COLORS["perdus"])]
    for cle, nom, ton in series:
        fig.add_trace(go.Bar(y=g.index, x=g[cle], orientation="h", name=nom, marker=_marque(ton, 1.2),
                             hovertemplate=f"<b>%{{y}}</b><br>{nom} : %{{x:,.0f}} M€<extra></extra>"))
    fig.update_xaxes(title_text="Encours (M€)")
    _axe_valeurs(fig, float(g["total"].max()), fmt_eur_tick)
    tete = g.sort_values("total", ascending=False)
    accroche = (f"« {tete.index[0]} » concentre {fmt_encours(tete['total'].iloc[0])} d’encours "
                f"en jeu, remporté ou perdu, soit {fmt_pct(tete['total'].iloc[0] / g['total'].sum(), 0)} "
                f"du total.")
    tableau = tete.reset_index()[["segment", "dossiers", "remporte", "en_jeu", "perdu"]].copy()
    for c in ("remporte", "en_jeu", "perdu"):
        tableau[c] = tableau[c].map(lambda v: fmt_dec(v, 0, "M€"))
    tableau.columns = ["Segment", "Appels d’offres", "Remporté", "En jeu", "Perdu"]
    return Block("aum_segment", "aum", "Encours par segment de client", accroche, fig, tableau,
                 note="Le ton dit l’état ; la légende et la valeur au survol le nomment. "
                      "L’encours en jeu est celui des dossiers encore ouverts.",
                 dimension="segment")



def _bloc_aum_strategies(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    gagnes = df[df["est_rfp"] & df["est_gagne"] & df["aum_gagne"].notna()]
    champ = "sous_classe_actifs" if _dispo(gagnes, "sous_classe_actifs", min_modalites=2) \
        else "classe_actifs"
    if len(gagnes) < 3 or not _dispo(gagnes, champ, min_modalites=2):
        return None
    groupe = gagnes.groupby(champ, observed=True).agg(
        aum=("aum_gagne", "sum"), mandats=("aum_gagne", "size"))
    survol = [f"{fmt_encours(a)} · {pluriel(m, 'mandat')}"
              for a, m in zip(groupe["aum"], groupe["mandats"])]
    fig, _ = _figure_rang(groupe.index, groupe["aum"],
                          lambda v: fmt_encours(v), couleur=SERIES[1], top=10,
                          survol=survol, titre_axe="Encours remporté (M€)")
    tete = groupe.sort_values("aum", ascending=False)
    accroche = (f"« {tete.index[0]} » concentre "
                f"{fmt_pct(tete['aum'].iloc[0] / max(groupe['aum'].sum(), 1), 0)} de "
                f"l’encours remporté.")
    tableau = tete.reset_index()
    tableau["aum"] = tableau["aum"].map(lambda v: fmt_dec(v, 0, "M€"))
    tableau.columns = [DIMENSIONS.get(champ, champ), "Encours remporté", "Mandats"]
    return Block("aum_strategies", "aum", "Stratégies par encours remporté",
                 accroche, fig, tableau,
                 note="Ventilation par sous-classe d’actifs lorsque l’information est "
                      "disponible, par classe d’actifs sinon.")


# =============================================================================
#  06 — ESG
# =============================================================================
def _bloc_esg_evolution(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """La composante ESG des questionnaires monte-t-elle, et à quelle vitesse ?"""
    if df.empty or "bande_esg" not in df.columns:
        return None
    if (df["bande_esg"] != ESG_INCONNU).sum() < 20:
        return None
    pivot = df.pivot_table(index=df["date_reception"].dt.year, columns="bande_esg",
                           values="date_reception", aggfunc="size", fill_value=0)
    ordre = [b for b in ESG_ORDER if b in pivot.columns]
    pivot = pivot[ordre]
    if len(pivot) < 2:
        return None
    mode = stats.get("esg_mode", "part")
    affiche = pivot.div(pivot.sum(axis=1).replace(0, np.nan), axis=0) * 100 \
        if mode == "part" else pivot
    index = list(pivot.index)
    fig = _fig(380, barmode="stack", hovermode="x unified")
    for i, colonne in enumerate(affiche.columns):
        fig.add_trace(go.Bar(
            x=index, y=affiche[colonne], name=str(colonne),
            marker=_marque(_couleurs_esg().get(colonne, SERIES[i % len(SERIES)]), 1.2),
            customdata=pivot[colonne],
            hovertemplate=("%{y:.0f} % — %{customdata} dossiers<extra>" + str(colonne) + "</extra>"
                           if mode == "part" else
                           "%{y:.0f} dossiers<extra>" + str(colonne) + "</extra>")))
    fig.update_xaxes(tickmode="array", tickvals=index, ticktext=[str(a) for a in index])
    fig.update_yaxes(title_text="Part des questionnaires" if mode == "part" else "Questionnaires",
                     ticksuffix=ESP_UNITE + "%" if mode == "part" else "",
                     rangemode="tozero")
    fig.update_layout(bargap=0.3)

    connus = df[df["bande_esg"] != ESG_INCONNU]
    parts = (connus.groupby(connus["date_reception"].dt.year)["esg_fort"].mean().dropna())
    if len(parts) >= 2:
        premiere, derniere = parts.index[0], parts.index[-1]
        accroche = (f"Les questionnaires à forte composante ESG sont passés de "
                    f"{fmt_pct(parts.iloc[0], 0)} des dossiers renseignés en {premiere} "
                    f"à {fmt_pct(parts.iloc[-1], 0)} en {derniere}.")
    else:
        accroche = f"{fmt_pct(part_esg_forte(df), 0)} des questionnaires sont à forte composante ESG."
    tableau = pivot.reset_index()
    tableau.columns = ["Année"] + [str(c) for c in pivot.columns]
    tableau["Année"] = tableau["Année"].astype(str)
    tableau["Total"] = pivot.sum(axis=1).to_numpy()
    return Block("esg_evolution", "esg", "Évolution de la composante ESG", accroche, fig,
                 tableau,
                 note="Tranches telles que suivies au comité. Les dossiers dont la part "
                      "ESG n’est pas renseignée forment une catégorie à part : les "
                      "compter comme « peu ESG » fausserait la série.", large=True)


def _bloc_sri(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """La part des dossiers à dimension ISR, année après année."""
    if "sri" not in df.columns or not _dispo(df, "sri", min_modalites=2):
        return None
    connus = df[df["sri"].isin(["Oui", "Non"])]
    if len(connus) < 20:
        return None
    pivot = connus.pivot_table(index=connus["date_reception"].dt.year, columns="sri",
                               values="date_reception", aggfunc="size", fill_value=0)
    if len(pivot) < 2:
        return None
    part = pivot.get("Oui", 0) / pivot.sum(axis=1)
    fig = _fig(320)
    fig.add_trace(go.Bar(x=[str(a) for a in pivot.index], y=part * 100,
                         marker=_marque(SERIES[0], 1.2),
                         text=[fmt_pct(v, 0) for v in part], textposition="outside",
                         cliponaxis=False, textfont=dict(color=INK_2, size=11.5),
                         customdata=np.stack([pivot.get("Oui", 0), pivot.sum(axis=1)], axis=-1),
                         hovertemplate="%{x} : %{customdata[0]} dossiers ISR sur %{customdata[1]}<extra></extra>"))
    fig.update_yaxes(title_text="Part des dossiers ISR", ticksuffix=ESP_UNITE + "%",
                     range=[0, min(100, float(part.max() * 100) * 1.25 + 5)])
    accroche = (f"{fmt_pct(part.iloc[-1], 0)} des dossiers de {pivot.index[-1]} portent une dimension "
                f"ISR, contre {fmt_pct(part.iloc[0], 0)} en {pivot.index[0]}.")
    tableau = pd.DataFrame({"Année": [str(a) for a in pivot.index],
                            "Dossiers ISR": pivot.get("Oui", 0).to_numpy(),
                            "Dossiers renseignés": pivot.sum(axis=1).to_numpy(),
                            "Part": [fmt_pct(v, 1) for v in part]})
    return Block("sri", "esg", "La part des dossiers ISR", accroche, fig, tableau,
                 note="Calculée sur les seuls dossiers dont la colonne SRI est renseignée.",
                 dimension="sri")



def _bloc_esg_dimension(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Quelles expertises portent réellement l’exigence ESG ?"""
    connus = df[df["bande_esg"] != ESG_INCONNU]
    champ = "expertise" if _dispo(connus, "expertise", min_modalites=3) else "classe_actifs"
    if len(connus) < 20 or not _dispo(connus, champ, min_modalites=2):
        return None
    groupe = connus.groupby(champ, observed=True).agg(
        volume=("esg_fort", "size"), forts=("esg_fort", "sum"))
    groupe = groupe[groupe["volume"] >= 8]
    if len(groupe) < 2:
        return None
    groupe["part"] = groupe["forts"] / groupe["volume"]
    survol = [f"{fmt_pct(p, 0)} à forte composante ESG · {int(f)} sur {int(v)} dossiers"
              for p, f, v in zip(groupe["part"], groupe["forts"], groupe["volume"])]
    fig, _ = _figure_rang(groupe.index, groupe["part"] * 100,
                          lambda v: fmt_dec(v, 0, "%"), couleur=SEQUENTIEL[-2], top=10,
                          survol=survol, titre_axe="Part des dossiers à forte composante ESG")
    tete = groupe.sort_values("part", ascending=False)
    accroche = (f"« {tete.index[0]} » est l’expertise la plus sollicitée sur l’ESG : "
                f"{fmt_pct(tete['part'].iloc[0], 0)} de ses questionnaires dépassent "
                f"{fmt_pct(ESG_SEUIL_FORT, 0)} de contenu ESG.")
    tableau = tete.reset_index()
    tableau["part"] = tableau["part"].map(lambda v: fmt_pct(v, 0))
    tableau.columns = [DIMENSIONS.get(champ, champ), "Dossiers renseignés",
                       "Dont forte composante", "Part"]
    return Block("esg_dimension", "esg", "Exigence ESG par expertise", accroche, fig,
                 tableau,
                 note="Calculé sur les seuls dossiers dont la part ESG est renseignée, et "
                      "sur les modalités comptant au moins huit dossiers.")


# =============================================================================
#  BLOCS CONSERVÉS — analyses de la version précédente, reclassées
# =============================================================================
def _bloc_delai_evolution(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    if mensuel.empty or mensuel["delai_ouvre_median"].notna().sum() < 3:
        return None
    # Ce bloc compare au délai cible : il raisonne en jours OUVRÉS, et le dit.
    m = _mois_complets(mensuel).dropna(subset=["delai_ouvre_median"])
    m = m.assign(delai_median=m["delai_ouvre_median"], delai_q1=m["delai_ouvre_q1"],
                 delai_q3=m["delai_ouvre_q3"])
    fig = _fig(360, hovermode="x unified")
    fig.add_trace(go.Scatter(x=m["mois"], y=m["delai_q1"], mode="lines",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=m["mois"], y=m["delai_q3"], mode="lines", fill="tonexty",
                             fillcolor=_rgba(SERIES[0], 0.12), line=dict(width=0),
                             name="Intervalle interquartile",
                             hovertemplate="3e quartile : %{y:.1f} j<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=m["mois"], y=m["delai_median"], mode="lines+markers", name="Délai médian",
        line=dict(color=SERIES[0], width=2),
        marker=dict(size=8, color=SERIES[0], line=dict(color=SURFACE, width=2)),
        hovertemplate="Délai médian : %{y:.1f} j<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=m["mois"], y=m["sla_cible"], mode="lines", name="Délai cible (mix du mois)",
        line=dict(color=INK, width=1.4),
        hovertemplate="Cible : %{y:.1f} j<extra></extra>"))
    _axe_mois(fig, m["mois"])
    fig.update_yaxes(title_text="Jours ouvrés", rangemode="tozero")

    reg = ols(m["indice"], m["delai_median"])
    stats["tendance_delai"] = reg
    if reg is not None and reg.significatif:
        sens = "se dégrade" if reg.pente > 0 else "s’améliore"
        accroche = (f"Le délai médian {sens} de {fmt_dec(abs(reg.pente) * 12, 1)} "
                f"jour{accord(reg.pente * 12)} par an "
                    f"({fmt_p(reg.p_value)}).")
    else:
        accroche = (f"Délai médian stable autour de {fmt_jours(m['delai_median'].median())} "
                    f"ouvrés ; aucune dérive significative sur la période.")
    derniers = m.tail(1).iloc[0]
    accroche += (f" Dernier mois complet ({fmt_mois(derniers['mois'])}) : "
                 f"{fmt_jours(derniers['delai_median'])} pour une cible de "
                 f"{fmt_jours(derniers['sla_cible'])}.")
    tableau = m[["libelle", "volume", "envoyees", "delai_q1", "delai_median", "delai_q3",
                 "sla_cible", "taux_sla"]].copy()
    for col in ("delai_q1", "delai_median", "delai_q3", "sla_cible"):
        tableau[col] = tableau[col].map(fmt_jours)
    tableau["taux_sla"] = tableau["taux_sla"].map(lambda v: fmt_pct(v, 1))
    tableau.columns = ["Mois", "Demandes", "Réponses envoyées", "1er quartile", "Délai médian",
                       "3e quartile", "Délai cible", "Respect du délai"]
    return Block("delai_evolution", "activite", "Évolution du délai de traitement",
                 accroche, fig, tableau,
                 note="La bande claire couvre la moitié centrale des dossiers du mois. "
                      "Le délai cible varie légèrement d’un mois à l’autre : il suit le mix "
                      "questionnaire reçu, appel d’offres comme due diligence. Le mois en "
                      "cours est exclu : seuls les dossiers "
                      "déjà envoyés y figureraient, ce qui ferait artificiellement baisser "
                      "la médiane.", large=True)


def _bloc_saisonnalite(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    if df.empty or df["annee"].nunique() < 2:
        return None
    pivot = (df.pivot_table(index="annee", columns="mois_num", values="date_reception",
                            aggfunc="size", fill_value=0)
             .reindex(columns=range(1, 13), fill_value=0).sort_index())
    # On masque les mois hors période observée : un 0 « faute de données »
    # n’est pas un 0 d’activité.
    debut, fin = df["date_reception"].min(), df["date_reception"].max()
    z = pivot.astype(float).to_numpy(copy=True)   # copie : pandas 3 renvoie une vue figée
    for i, annee in enumerate(pivot.index):
        for j, mois in enumerate(range(1, 13)):
            borne = pd.Timestamp(year=int(annee), month=mois, day=1)
            if borne < debut.replace(day=1) or borne > fin.replace(day=1):
                z[i, j] = np.nan
    fig = _fig(max(260, 46 * len(pivot) + 110))
    fig.add_trace(go.Heatmap(
        z=z, x=MOIS_FR, y=[str(a) for a in pivot.index],
        colorscale=[[i / (len(SEQUENTIEL) - 1), c] for i, c in enumerate(SEQUENTIEL)],
        xgap=2, ygap=2, hoverongaps=False,
        colorbar=dict(title=dict(text="Demandes", font=dict(size=11, color=INK_2)),
                      thickness=10, outlinewidth=0, tickfont=dict(size=11, color=INK_MUTED),
                      len=0.85),
        hovertemplate="%{x} %{y} : %{z:.0f} demandes<extra></extra>",
    ))
    maxi = np.nanmax(z) if np.isfinite(np.nanmax(z)) else 1.0
    for i, annee in enumerate(pivot.index):
        for j in range(12):
            if np.isfinite(z[i, j]):
                # Encre déduite de la couleur réelle de la cellule : valable
                # quel que soit le thème et quel que soit le sens de la rampe.
                fond = couleur_rampe(SEQUENTIEL, z[i, j] / maxi if maxi else 0.0)
                fig.add_annotation(x=MOIS_FR[j], y=str(annee), text=fmt_int(z[i, j]),
                                   font=dict(size=11, color=encre_lisible(fond)))
    fig.update_xaxes(showgrid=False, showline=False, ticks="")
    fig.update_yaxes(showgrid=False, showline=False, ticks="", autorange="reversed")

    profil = (df.groupby(["annee", "mois_num"], observed=True).size()
                .groupby("mois_num").mean())   # moyenne des années où le mois existe
    creux, pic = int(profil.idxmin()), int(profil.idxmax())
    accroche = (f"Activité maximale en {MOIS_FR_LONG[pic - 1].lower()} "
                f"({fmt_dec(profil.max(), 0)} demandes en moyenne) et minimale en "
                f"{MOIS_FR_LONG[creux - 1].lower()} ({fmt_dec(profil.min(), 0)}) : "
                f"un rapport de 1 à {fmt_dec(profil.max() / max(profil.min(), 1e-9), 1)}.")
    tableau = pivot.reset_index()
    tableau.columns = ["Année"] + MOIS_FR
    tableau["Total"] = pivot.sum(axis=1).to_numpy()
    return Block("saisonnalite", "activite", "Saisonnalité de l’activité", accroche, fig, tableau,
                 note="Les mois antérieurs ou postérieurs à la période observée sont laissés vides "
                      "plutôt que comptés à zéro. Une seule teinte, du clair au foncé : "
                      "l’intensité code la magnitude.", large=True)


def _bloc_regression_delai(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    if not (_dispo(df, "delai_ouvre") and _dispo(df, "nb_questions")):
        return None
    sous = df.dropna(subset=["delai_ouvre", "nb_questions"])
    if len(sous) < 30:
        return None
    reg = ols(sous["nb_questions"], sous["delai_ouvre"])
    stats["regression_questions"] = reg
    if reg is None:
        return None
    fig = _fig(400)
    grille = np.linspace(sous["nb_questions"].min(), sous["nb_questions"].max(), 140)
    bas, haut = reg.bande(grille)
    fig.add_trace(go.Scatter(x=grille, y=bas, mode="lines", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=grille, y=haut, mode="lines", fill="tonexty",
                             fillcolor=_rgba(INK, 0.09), line=dict(width=0),
                             name="IC 95 % de la droite", hoverinfo="skip"))
    # Nuage coloré par FAMILLE (deux teintes, les deux premiers slots validés en
    # toutes-paires) et non par type fin : c’est la lecture du pilotage, et le
    # rapport diffusé ne connaît que ces deux familles.
    couleurs_f = _couleurs_famille()
    for f in [f for f in FAMILLE_ORDER if f in sous["famille"].unique()]:
        part = sous[sous["famille"] == f]
        fig.add_trace(go.Scatter(
            x=part["nb_questions"], y=part["delai_ouvre"], mode="markers", name=str(f),
            marker=dict(size=8, color=_rgba(couleurs_f.get(f, SERIES[0]), 0.55),
                        line=dict(color=SURFACE, width=1)),
            hovertemplate="%{x:.0f} questions · %{y:.0f} jours ouvrés<extra>" + str(f) + "</extra>",
        ))
    fig.add_trace(go.Scatter(x=grille, y=reg.predire(grille), mode="lines",
                             name="Ajustement MCO", line=dict(color=INK, width=2),
                             hovertemplate="Délai attendu : %{y:.1f} j<extra></extra>"))
    fig.update_xaxes(title_text="Nombre de questions")
    fig.update_yaxes(title_text="Délai de traitement (jours ouvrés)", rangemode="tozero")
    fig.add_annotation(
        xref="paper", yref="paper", x=0.99, y=0.06, xanchor="right", align="right",
        text=(f"délai ≈ {fmt_dec(reg.ordonnee, 1)} + {fmt_dec(reg.pente, 3)} × questions"
              f"<br>R² = {fmt_dec(reg.r2, 2)} · {fmt_p(reg.p_value)} · n = {fmt_int(reg.n)}"),
        bgcolor=VOILE, bordercolor=AXIS, borderwidth=1, borderpad=6,
        font=dict(size=11.5, color=INK_2))

    par_dix = reg.pente * 10
    accroche = (f"Chaque tranche de 10 questions supplémentaires ajoute "
                f"{fmt_dec(par_dix, 1)} jour{accord(par_dix)} ouvré{accord(par_dix)} "
                f"de traitement "
                f"(IC 95 % : {fmt_dec(reg.ic_pente[0] * 10, 1)} à {fmt_dec(reg.ic_pente[1] * 10, 1)}). "
                f"Le volume de questions explique {fmt_pct(reg.r2, 0)} de la variance des délais.")
    tableau = pd.DataFrame({
        "Grandeur": ["Pente (jour par question)", "Effet de 10 questions", "Ordonnée à l’origine",
                     "R²", "R² ajusté", "p-value", "Observations"],
        "Valeur": [fmt_dec(reg.pente, 4), fmt_dec(par_dix, 2) + " j", fmt_dec(reg.ordonnee, 2) + " j",
                   fmt_dec(reg.r2, 3), fmt_dec(reg.r2_ajuste, 3), fmt_p(reg.p_value), fmt_int(reg.n)],
    })
    return Block("reg_questions", "diagnostic",
                 "Le volume de questions explique-t-il le délai ?", accroche, fig, tableau,
                 note="Moindres carrés ordinaires. La bande grise est l’intervalle de confiance à "
                      "95 % de la droite de régression, pas celui d’un dossier individuel. "
                      "Corrélation n’est pas causalité : d’autres facteurs sont testés ci-dessous.",
                 large=True)


def _bloc_facteurs(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    """Régression multiple : quels facteurs pèsent réellement sur le délai,
    une fois les autres tenus constants ?"""
    if not (_dispo(df, "delai_ouvre") and _dispo(df, "nb_questions")):
        return None
    sous = df.dropna(subset=["delai_ouvre"]).copy()
    if len(sous) < 60:
        return None
    volumes = sous.groupby("mois", observed=True)["date_reception"].transform("size")
    X = pd.DataFrame(index=sous.index)
    X["Questions (+10)"] = sous["nb_questions"] / 10.0
    # Une seule indicatrice de nature, sur la FAMILLE : modalité de référence,
    # la due diligence. Le pilotage ne connaît que ces deux familles.
    if int(sous["est_rfp"].sum()) >= 15 and int(sous["est_dd"].sum()) >= 15:
        X["Appel d’offres"] = sous["est_rfp"].astype(float)
    if _dispo(sous, "langue", min_modalites=2):
        X["Langue étrangère"] = (~sous["langue"].isin(["Français", VALEUR_INCONNUE])).astype(float)
    X["Charge du mois (+10 demandes)"] = volumes / 10.0
    if _dispo(sous, "montant_potentiel"):
        X["Montant (+10 M€)"] = sous["montant_potentiel"] / 1e7
    if X.shape[1] < 2:
        return None

    modele = ols_multiple(X, sous["delai_ouvre"], cible="Délai de traitement (jours ouvrés)")
    stats["modele_delai"] = modele
    if modele is None:
        return None

    coefs = sorted(modele.explicatives, key=lambda c: c.valeur)
    couleurs = [SERIES[0] if c.valeur > 0 else SERIES[2] for c in coefs]
    fig = _fig(max(300, 44 * len(coefs) + 110))
    # Significativité encodée par le remplissage ET par le libellé : jamais
    # par la seule couleur.
    fig.add_trace(go.Scatter(
        x=[c.valeur for c in coefs],
        y=[c.nom + ("" if c.significatif else "  (non significatif)") for c in coefs],
        mode="markers",
        marker=dict(size=[13 if c.significatif else 11 for c in coefs],
                    color=[coul if c.significatif else SURFACE for c, coul in zip(coefs, couleurs)],
                    line=dict(color=couleurs, width=2)),
        error_x=dict(type="data", symmetric=False,
                     array=[c.ic_haut - c.valeur for c in coefs],
                     arrayminus=[c.valeur - c.ic_bas for c in coefs],
                     color=INK_MUTED, thickness=1.2, width=5),
        customdata=np.stack([[c.ic_bas for c in coefs], [c.ic_haut for c in coefs],
                             [c.p_value for c in coefs]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Effet : %{x:+.2f} j"
                       "<br>IC 95 % : %{customdata[0]:+.2f} à %{customdata[1]:+.2f}"
                       "<br>p = %{customdata[2]:.4f}<extra></extra>"),
        showlegend=False,
    ))
    fig.add_vline(x=0, line=dict(color=INK, width=1.2))
    fig.update_xaxes(title_text="Effet sur le délai, toutes choses égales par ailleurs (jours ouvrés)")
    fig.update_yaxes(showgrid=False)
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=1.10, xanchor="right",
                       text=f"R² ajusté = {fmt_dec(modele.r2_ajuste, 2)} · n = {fmt_int(modele.n)}",
                       font=dict(size=11.5, color=INK_MUTED))

    significatifs = [c for c in modele.explicatives if c.significatif]
    if significatifs:
        dominant = max(significatifs, key=lambda c: abs(c.valeur))
        sens = "allonge" if dominant.valeur > 0 else "raccourcit"
        muets = [c.nom for c in modele.explicatives if not c.significatif]
        accroche = (f"Facteur dominant : « {dominant.nom} » {sens} le délai de "
                    f"{fmt_dec(abs(dominant.valeur), 1)} jour{accord(dominant.valeur)} "
                    f"({fmt_p(dominant.p_value)})."
                    + (f" Sans effet mesurable : {', '.join(muets[:3])}." if muets else ""))
    else:
        accroche = "Aucun des facteurs testés n’a d’effet statistiquement significatif sur le délai."
    tableau = pd.DataFrame([{
        "Facteur": c.nom, "Effet (jours)": fmt_dec(c.valeur, 3),
        "Erreur type": fmt_dec(c.stderr, 3), "IC 95 %": f"{fmt_dec(c.ic_bas, 2)} à {fmt_dec(c.ic_haut, 2)}",
        "t": fmt_dec(c.t_stat, 2), "p-value": fmt_p(c.p_value),
        "Significatif à 5 %": "Oui" if c.significatif else "Non",
    } for c in modele.coefficients])
    return Block("facteurs", "diagnostic", "Facteurs explicatifs du délai de traitement",
                 accroche, fig, tableau,
                 note="Régression linéaire multiple. Chaque effet s’interprète à autres facteurs "
                      "constants. La modalité de référence est la due diligence : « appel "
                      "d’offres » se lit donc comme l’écart de délai face à elle. "
                      "Un point vide signale un effet non distinguable de zéro au seuil de 5 %.",
                 large=True)


def _bloc_projection(df: pd.DataFrame, mensuel: pd.DataFrame, stats: dict) -> Block | None:
    if mensuel.empty or len(mensuel) < 8:
        return None
    # Le mois en cours est partiel : il fausserait l’ajustement.
    mois_courant = pd.Timestamp.today().normalize().replace(day=1)
    hist = mensuel[mensuel["mois"] < mois_courant]
    if len(hist) < 6:
        hist = mensuel
    reg = ols(hist["indice"], hist["volume"])
    if reg is None:
        return None
    stats["projection"] = reg

    futur_idx = np.arange(hist["indice"].max() + 1, hist["indice"].max() + 1 + PROJECTION_MOIS)
    futur_mois = [hist["mois"].max() + pd.DateOffset(months=int(k))
                  for k in range(1, PROJECTION_MOIS + 1)]
    attendu = np.maximum(reg.predire(futur_idx), 0)
    bas, haut = reg.bande(futur_idx, prediction=True)
    bas, haut = np.maximum(bas, 0), np.maximum(haut, 0)

    fig = _fig(380, hovermode="x unified")
    fig.add_trace(go.Scatter(x=futur_mois, y=bas, mode="lines", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=futur_mois, y=haut, mode="lines", fill="tonexty",
                             fillcolor=_rgba(SERIES[0], 0.14), line=dict(width=0),
                             name="Intervalle de prédiction 95 %",
                             hovertemplate="Borne haute : %{y:.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=hist["mois"], y=hist["volume"], mode="lines+markers", name="Volume observé",
        line=dict(color=SERIES[0], width=2),
        marker=dict(size=7, color=SERIES[0], line=dict(color=SURFACE, width=1.5)),
        hovertemplate="Observé : %{y:.0f} demandes<extra></extra>"))
    fig.add_trace(go.Scatter(x=hist["mois"], y=reg.predire(hist["indice"]), mode="lines",
                             name="Tendance ajustée", line=dict(color=INK, width=1.6),
                             hovertemplate="Tendance : %{y:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=[hist["mois"].max()] + futur_mois,
        y=np.concatenate([[reg.predire([hist["indice"].max()])[0]], attendu]),
        mode="lines+markers", name="Projection",
        line=dict(color=SERIES[0], width=2, dash="dot"),
        marker=dict(size=8, color=SURFACE, line=dict(color=SERIES[0], width=2)),
        hovertemplate="Projection : %{y:.0f} demandes<extra></extra>"))
    _axe_mois(fig, list(hist["mois"]) + futur_mois)
    fig.update_yaxes(title_text="Demandes reçues", rangemode="tozero")

    total_projete = float(np.sum(attendu))
    if reg.significatif:
        accroche = (f"À tendance inchangée, {fmt_int(total_projete)} demandes sont attendues sur "
                    f"les {PROJECTION_MOIS} prochains mois, soit {fmt_dec(total_projete / PROJECTION_MOIS, 0)} "
                    f"par mois en moyenne (tendance significative, {fmt_p(reg.p_value)}).")
    else:
        accroche = (f"La tendance n’est pas significative ({fmt_p(reg.p_value)}) : la projection "
                    f"de {fmt_int(total_projete)} demandes sur {PROJECTION_MOIS} mois vaut comme "
                    f"prolongement de la moyenne, pas comme prévision.")
    tableau = pd.DataFrame({
        "Mois": [fmt_mois(m) for m in futur_mois],
        "Volume attendu": [fmt_int(v) for v in attendu],
        "Borne basse (95 %)": [fmt_int(v) for v in bas],
        "Borne haute (95 %)": [fmt_int(v) for v in haut],
    })
    return Block("projection", "diagnostic",
                 f"Projection du flux à {PROJECTION_MOIS} mois", accroche, fig, tableau,
                 note="Prolongement linéaire de la tendance observée, avec intervalle de prédiction "
                      "à 95 %. Ce modèle ignore la saisonnalité : il donne un ordre de grandeur, "
                      "pas un budget. Le mois en cours, incomplet, est exclu de l’ajustement.",
                 large=True)

_CONSTRUCTEURS: tuple[Callable[[pd.DataFrame, pd.DataFrame, dict], Block | None], ...] = (
    # 01 Vue d’ensemble
    # Quatre blocs, pas un de plus : où on en est, ce qui a bougé, la tendance
    # longue, ce qu’on a gagné. Tout le reste appartient à la partie Analyse.
    _bloc_annees, _bloc_classes_actifs, _bloc_decomposition, _bloc_trimestre,
    _bloc_flux_famille, _bloc_mandats_remportes,
    # 02 Activité
    _bloc_volume_annuel, _bloc_cadence, _bloc_delai_famille, _bloc_delai_evolution,
    _bloc_saisonnalite,
    # 03 Appels d’offres
    _bloc_rfp_ouverts, _bloc_entonnoir, _bloc_resultats_rfp, _bloc_rfp_resultats_annee,
    _bloc_rfp_reception, _bloc_rfp_succes_dimension, _bloc_rfp_segment, _bloc_rfp_consultants,
    _bloc_rfp_commercial,
    # 04 Due diligence
    _bloc_dd_mensuel, _bloc_dd_expertise, _bloc_dd_pays,
    _bloc_dd_matrice,
    # 05 Encours & gains
    _bloc_aum_annuel, _bloc_aum_segment, _bloc_aum_clients, _bloc_aum_strategies,
    # 06 ESG
    _bloc_esg_evolution, _bloc_esg_dimension, _bloc_sri,
    # 07 Diagnostic
    _bloc_regression_delai, _bloc_facteurs, _bloc_projection,
)


@dataclass
class Analysis:
    """Résultat complet d’une analyse : c’est le seul objet que consomment
    server.py (écran) et export.py (rapport HTML)."""
    df: pd.DataFrame
    filtres: Filters
    rapport: LoadReport | None
    kpis: list[Kpi]
    blocs: list[Block]
    # Tout l’historique, quand le périmètre n’en est qu’une tranche : le repère
    # historique de la lecture d’ouverture s’y calcule.
    df_total: pd.DataFrame | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    erreurs: list[str] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)
    genere_le: dt.datetime = field(default_factory=dt.datetime.now)

    @property
    def vide(self) -> bool:
        return self.df.empty

    def section(self, cle: str, pour_rapport: bool = False) -> list[Block]:
        """Les blocs d’une section. `pour_rapport` est conservé pour la clarté
        des appels : l’écran et le rapport montrent désormais les mêmes."""
        return [b for b in self.blocs if b.section == cle]

    @property
    def sections(self) -> list[tuple[str, str]]:
        return [(cle, libelle) for cle, libelle in SECTIONS.items() if self.section(cle)]

    def parties_rapport(self) -> list[tuple[str, str, str, list[tuple[str, str]]]]:
        """Les deux parties du rapport, chacune avec ses sections non vides."""
        groupes = []
        for cle, (libelle, accroche) in PARTIES.items():
            sections = [(s, nom) for s, nom in self.sections_rapport
                        if PARTIE_PAR_SECTION.get(s) == cle]
            if sections:
                groupes.append((cle, libelle, accroche, sections))
        return groupes

    @property
    def sections_rapport(self) -> list[tuple[str, str]]:
        """Sections retenues pour le rapport : les mêmes qu’à l’écran."""
        return self.sections

    @property
    def kpis_rapport(self) -> list[Kpi]:
        """Les indicateurs du rapport : exactement ceux de l’écran."""
        return list(self.kpis)

    @property
    def kpis_situation(self) -> list[Kpi]:
        """Les indicateurs de la vue d’ensemble, dans l’ordre de CHOIX_KPI_SITUATION."""
        par_cle = {k.cle: k for k in self.kpis}
        return [par_cle[c] for c in CHOIX_KPI_SITUATION if c in par_cle]

    @property
    def periode(self) -> str:
        if self.df.empty:
            return "—"
        return f"{fmt_date(self.df['date_reception'].min())} → {fmt_date(self.df['date_reception'].max())}"


def build_analysis(df: pd.DataFrame, filtres: Filters | None = None,
                   rapport: LoadReport | None = None,
                   df_precedent: pd.DataFrame | None = None,
                   options: Mapping[str, Any] | None = None,
                   df_total: pd.DataFrame | None = None) -> Analysis:
    """Chaîne complète : KPI + tous les blocs. Un bloc qui échoue est signalé
    dans `erreurs` mais n’interrompt jamais le reste du tableau de bord."""
    filtres = filtres or Filters()
    stats: dict[str, Any] = dict(options or {})
    erreurs: list[str] = []
    kpis = compute_kpis(df, df_precedent) if not df.empty else []
    blocs: list[Block] = []
    mensuel = agg_mensuel(df) if not df.empty else pd.DataFrame()
    if not df.empty:
        for constructeur in _CONSTRUCTEURS:
            try:
                bloc = constructeur(df, mensuel, stats)
            except Exception as exc:                      # robustesse : un bloc, pas l’écran
                erreurs.append(f"{constructeur.__name__} : {type(exc).__name__} — {exc}")
                continue
            if bloc is not None:
                blocs.append(bloc)
    stats["mensuel"] = mensuel
    if df_precedent is not None and not df_precedent.empty:
        precedente = filtres.periode_precedente()
        stats["comparaison"] = (precedente.date_min, precedente.date_max)
    try:
        insights = generer_insights(df, df_precedent) if not df.empty else []
    except Exception as exc:                          # pragma: no cover
        erreurs.append(f"generer_insights : {type(exc).__name__} — {exc}")
        insights = []
    return Analysis(df=df, filtres=filtres, rapport=rapport, kpis=kpis, blocs=blocs,
                    df_total=df_total, stats=stats, erreurs=erreurs, insights=insights)


# =============================================================================
#  TABLE DÉTAILLÉE (onglet « Données » et export CSV)
# =============================================================================
COLONNES_EXPORT: dict[str, str] = {
    "date_reception": "Date de réception",
    "date_envoi": "Date d’envoi",
    "famille": "Type",
    "statut": "Statut",
    "client": "Client",
    "segment": "Segment",
    "commercial": "Commercial",
    "type_client": "Type de client",
    "pays": "Pays",
    "fonds": "Fonds",
    "classe_actifs": "Classe d’actifs",
    "langue": "Langue",
    "nb_questions": "Questions",
    "delai_ouvre": "Délai (j ouvrés)",
    "sla_cible": "Délai cible",
    "montant_potentiel": "Montant potentiel (€)",
}


CHAMPS_RECHERCHE = ("client", "consultant", "pays", "fonds", "classe_actifs",
                    "sous_classe_actifs", "expertise", "commercial",
                    "segment", "famille", "statut", "resultat", "forme_juridique", "numero")


def cle_recherche(texte: str) -> str:
    """Normalise une saisie de recherche : sans accent, sans casse, sans
    ponctuation de séparation. « leman » retrouve « Banque Privée du Léman »."""
    return _cle(texte)


def index_recherche(df: pd.DataFrame) -> pd.Series:
    """Texte normalisé de chaque dossier, pour la recherche plein texte."""
    champs = [c for c in CHAMPS_RECHERCHE if c in df.columns]
    if df.empty or not champs:
        return pd.Series("", index=df.index, dtype=object)
    concat = df[champs].astype(str).agg(" ".join, axis=1)
    return concat.map(_cle)


def table_detaillee(df: pd.DataFrame, formate: bool = True) -> pd.DataFrame:
    """Vue tabulaire lisible de la sélection (jumeau de tous les graphiques)."""
    if df.empty:
        return pd.DataFrame(columns=list(COLONNES_EXPORT.values()))
    colonnes = [c for c in COLONNES_EXPORT if c in df.columns]
    out = df[colonnes].copy()
    if formate:
        for col in ("date_reception", "date_envoi"):
            if col in out:
                out[col] = out[col].map(fmt_date)
        for col in ("nb_questions", "delai_ouvre", "sla_cible"):
            if col in out:
                out[col] = out[col].map(lambda v: "—" if pd.isna(v) else fmt_int(v))
        if "montant_potentiel" in out:
            out["montant_potentiel"] = out["montant_potentiel"].map(lambda v: fmt_eur(v, court=False))
    return out.rename(columns=COLONNES_EXPORT)


# =============================================================================
#  AUTO-TEST — `python core.py` valide la chaîne de bout en bout
# =============================================================================
def _autotest() -> None:
    print("1. Outils statistiques")
    assert abs(t_sf_two_sided(2.228, 10) - 0.050) < 1e-3
    assert abs(t_sf_two_sided(2.0, 10) - 0.0734) < 1e-3
    assert abs(t_ppf(0.975, 10) - 2.228) < 1e-3
    assert abs(z_ppf(0.975) - 1.95996) < 1e-4
    bas, haut = wilson_ci(50, 100)
    assert abs(bas - 0.4038) < 1e-3 and abs(haut - 0.5962) < 1e-3
    r = ols([1, 2, 3, 4, 5], [2.0, 4.0, 6.0, 8.0, 10.0])
    assert r is not None and abs(r.pente - 2.0) < 1e-9 and abs(r.r2 - 1.0) < 1e-9
    m = ols_multiple(pd.DataFrame({"a": [1, 2, 3, 4, 5, 6.0], "b": [1, 0, 1, 0, 1, 0.0]}),
                     pd.Series([3.0, 4.0, 7.0, 8.0, 11.0, 12.0]))
    assert m is not None and abs(m.r2 - 1.0) < 1e-6
    print("   ✓ p-values, quantiles, Wilson, MCO simple et multiple")

    print("2. Chargement et normalisation")
    df, rapport = load_data(use_fake=True)
    assert len(df) > 1000 and rapport.n_lignes_retenues == len(df)
    assert set(df["statut"].unique()) <= set(STATUT_ORDER + [VALEUR_INCONNUE])
    assert set(df["famille"].unique()) <= {FAMILLE_RFP, FAMILLE_DD, VALEUR_INCONNUE}
    assert df["date_reception"].notna().all()
    assert not rapport.valeurs_inconnues, rapport.valeurs_inconnues
    assert rapport.doublons_supprimes > 0
    # La part ESG arrive en fraction, en pourcentage ou en tranche écrite :
    # les trois formes doivent aboutir à une tranche exploitable.
    essai = pd.Series([0.82, "45 %", "> 75 % ESG", None, 12])
    parts, bandes = _vers_esg(essai)
    assert list(bandes) == [ESG_FORT, ESG_MOYEN, ESG_FORT, ESG_INCONNU, ESG_FAIBLE], list(bandes)
    assert math.isnan(parts.iloc[2]), "une tranche écrite ne donne pas un pourcentage"
    print(f"   ✓ {fmt_int(len(df))} lignes, trois écritures ESG absorbées")

    print("3. Cohérence métier")
    # Une due diligence n’a pas de résultat commercial.
    assert set(df.loc[df["est_dd"], "resultat"].unique()) == {RESULTAT_HORS_RFP}
    # L’encours gagné n’existe que sur un RFP remporté.
    assert df.loc[df["aum_gagne"].notna(), "est_gagne"].all()
    assert df.loc[df["aum_gagne"].notna(), "est_rfp"].all()
    taux, gagnes, tranches, _ = taux_succes_rfp(df)
    assert 0 < taux < 1 and tranches <= int(df["est_rfp"].sum())
    print(f"   ✓ résultat réservé aux RFP, taux de succès {fmt_pct(taux, 1)}")

    print("4. Métriques de croissance")
    # Les volumes de la démonstration reproduisent la trajectoire du pôle : ces
    # trois taux doivent retomber sur les chiffres publiés au comité.
    attendus = {3: 0.49, 5: 1.49, 10: 1.58}
    for horizon, cible in attendus.items():
        c = croissance(df, horizon)
        assert c is not None and abs(c.taux - cible) < 0.02, (horizon, c.taux if c else None)
        print(f"   ✓ {horizon:2d} ans : {fmt_pct(c.taux, 0)} "
              f"({c.annee_base} → {c.annee_reference}), attendu {fmt_pct(cible, 0)}")

    print("5. Filtres et drill-down")
    filtres = Filters(date_min=(dt.date.today() - dt.timedelta(days=730)),
                      date_max=dt.date.today(), dims={"famille": [FAMILLE_RFP]})
    sel = filter_data(df, filtres)
    assert 0 < len(sel) < len(df) and set(sel["famille"].unique()) == {FAMILLE_RFP}
    prec = filter_data(df, filtres.periode_precedente())
    assert prec.empty or prec["date_reception"].max() < sel["date_reception"].min()
    index = index_recherche(df)
    assert index.str.contains(cle_recherche("leman"), regex=False).any()
    print(f"   ✓ {fmt_int(len(sel))} lignes filtrées, recherche plein texte opérante")

    print("6. Analyse complète")
    analyse = build_analysis(df, Filters(), rapport, None, options={"granularite": "annee"})
    assert not analyse.erreurs, analyse.erreurs
    assert len(analyse.kpis) >= 10
    manquantes = [c for c in SECTIONS if not analyse.section(c)]
    assert not manquantes, f"sections vides : {manquantes}"
    for bloc in analyse.blocs:
        assert (bloc.figure is None or bloc.figure.data
                or bloc.figure.layout.shapes), f"{bloc.cle} : figure vide"
        assert not bloc.tableau.empty, f"{bloc.cle} : tableau vide"
        assert bloc.accroche and bloc.titre
        assert bloc.dimension is None or bloc.dimension in DIMENSIONS
    cliquables = [b.cle for b in analyse.blocs if b.dimension]
    assert len(cliquables) >= 4, cliquables
    assert analyse.insights, "aucun constat produit sur l’historique complet"
    print(f"   ✓ {len(analyse.blocs)} blocs sur {len(SECTIONS)} sections, "
          f"{len(cliquables)} cliquables, {len(analyse.insights)} constats")

    print("7. Carnet d’appels d’offres")
    livre = carnet(df)
    # Les cinq compartiments sont exclusifs et couvrent tous les RFP : c’est
    # l’invariant qui autorise à lire la page d’accueil comme un état complet.
    total = sum(livre.n(cle) for cle, _, _ in COMPARTIMENTS)
    assert total == livre.total == int(df["est_rfp"].sum()), (total, livre.total)
    identifiants = [i for cle, _, _ in COMPARTIMENTS
                    for i in livre.compartiments[cle].index]
    assert len(identifiants) == len(set(identifiants)), "un dossier compté deux fois"
    assert livre.vivants == livre.n("en_cours") + livre.n("en_attente")
    assert livre.gagnes["est_gagne"].all() and livre.perdus["est_perdu"].all()
    # Un dossier ouvert porte son horloge, sinon le carnet afficherait « — ».
    for cle in ("en_cours", "en_attente"):
        horloges = livre.compartiments[cle][["jours_chez_nous", "jours_attente"]]
        assert horloges.notna().any(axis=1).all(), f"un dossier {cle} sans horloge"
    types = repartition_type(df)
    assert types.sum() == len(df) and set(types.index) <= set(TYPE_ORDER)
    print(f"   ✓ {fmt_int(livre.total)} RFP ventilés sans perte, "
          f"{fmt_int(livre.vivants)} vivants")

    print("8. Le rapport montre exactement ce que montre l’écran")
    # La promesse du produit : aucun bloc, aucun indicateur réservé à l’écran.
    # Le rapport diffusé et l’application disent la même chose, mot pour mot.
    ecran = {b.cle for b in analyse.blocs}
    diffuse = {b.cle for cle, _ in analyse.sections_rapport
               for b in analyse.section(cle, pour_rapport=True)}
    assert ecran == diffuse, f"blocs réservés à l’écran : {sorted(ecran - diffuse)}"
    assert [k.cle for k in analyse.kpis] == [k.cle for k in analyse.kpis_rapport]
    assert set(repartition_type(df).index) <= {FAMILLE_RFP, FAMILLE_DD}, "type fin résiduel"
    assert "RFI" not in sla_libelle(), sla_libelle()
    print(f"   ✓ {pluriel(len(diffuse), 'bloc')} et "
          f"{pluriel(len(analyse.kpis), 'indicateur')} communs à l’écran et au rapport")

    print("9. Une teinte, ses tons")
    # Toute couleur du produit sort de `teinte` : on le vérifie sur les jetons
    # exposés au CSS et sur les séries des figures.
    import re as _re
    admis = {teinte(t / 1000).lower() for t in range(0, 1001)} | {MARQUE_BLANC.lower()}
    css = jetons_css()
    for couleur in _re.findall(r"#[0-9a-fA-F]{6}", css):
        assert couleur.lower() in admis, f"couleur hors teinte dans les jetons : {couleur}"
    for couleur in SERIES + SEQUENTIEL + ORDINAL + list(STATUT_COLORS.values()):
        assert couleur.lower() in admis, couleur
    assert encre_lisible(MARQUE_BLEU).lower() == "#ffffff"
    a = build_analysis(df.head(400), Filters(), rapport)
    assert not a.erreurs, a.erreurs
    print(f"   ✓ {len(admis)} tons admis, jetons et séries conformes, figures reconstruites")

    print("10. Branchement d’un classeur aux en-têtes différents")
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as dossier:
        brut = generate_fake_data().head(300).rename(columns={
            "Date de réception": "Réception", "Type": "Nature de la demande",
            "Status": "État du dossier", "Client": "Prospect", "Volume": "Ticket (M€)",
            "% ESG": "Composante ESG", "Country": "Juridiction"})
        chemin = Path(dossier) / "extraction.xlsx"
        brut.to_excel(chemin, sheet_name="Suivi", index=False)
        vue = apercu(chemin, "Suivi")
        assert vue["onglets"] == ["Suivi"] and not vue["obligatoires_manquants"], vue
        assert vue["correspondance"]["date_reception"] == "Réception"
        assert vue["correspondance"]["statut"] == "État du dossier"
        assert "montant_potentiel" in vue["correspondance"], vue["absentes"]
        # Une colonne que rien ne reconnaît se branche par correspondance forcée.
        brut2 = brut.rename(columns={"Ticket (M€)": "Col_42"})
        chemin2 = Path(dossier) / "extraction.csv"
        brut2.to_csv(chemin2, index=False, sep=";", encoding="utf-8-sig")
        vue2 = apercu(chemin2)
        assert "montant_potentiel" in vue2["absentes"]
        d2, r2 = load_data(path=str(chemin2), correspondance={"montant_potentiel": "Col_42"})
        assert r2.mode == "fichier" and d2["montant_potentiel"].notna().any()
        assert r2.correspondance["montant_potentiel"] == "Col_42"
    print("   ✓ classeur et CSV lus, correspondance automatique et forcée")

    print("11. Cas limites")
    vide = build_analysis(df.head(0), Filters(), rapport)
    assert vide.vide and not vide.blocs and not vide.erreurs and not vide.insights
    minuscule = build_analysis(df.head(3), Filters(), rapport)
    assert not minuscule.erreurs, minuscule.erreurs
    ampute = df.copy()
    for colonne in ("expertise", "consultant", "sous_classe_actifs", "part_esg", "bande_esg"):
        ampute[colonne] = VALEUR_INCONNUE if ampute[colonne].dtype == object else np.nan
    partiel = build_analysis(ampute, Filters(), rapport)
    assert not partiel.erreurs, partiel.erreurs
    assert "dd_expertise" not in [b.cle for b in partiel.blocs] and "rfp_segment" in [b.cle for b in analyse.blocs]
    print("   ✓ sélection vide, échantillon minuscule et dimensions absentes gérés")

    print("\nTous les contrôles sont passés.")


if __name__ == "__main__":
    _autotest()
