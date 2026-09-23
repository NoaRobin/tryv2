# =============================================================================
#  tarification.py — le moteur du simulateur de tarification des appels d'offres
# -----------------------------------------------------------------------------
#  Une grille de frais est un barème progressif : chaque taux ne s'applique qu'à
#  la part de l'encours qui tombe dans sa tranche. Ce module lit le classeur des
#  grilles proposées (structure de la page 5 de la présentation d'origine), les
#  valide, calcule frais et taux moyens, et rattache chaque offre au classeur
#  d'activité. Le même calcul existe en JavaScript (static/js/tarif.js) pour
#  l'édition en direct ; l'auto-test exige des résultats identiques.
#
#  Décisions et justifications : docs/simulateur-tarification.md.
#  Auto-test : python3 tarification.py
# =============================================================================
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

import core

# =============================================================================
#  [BRANCHEMENT] — où vivent le classeur tarifaire et ses correspondances
# -----------------------------------------------------------------------------
#  Un sous-dossier, et non data/ lui-même : un fichier seul dans data/ est relu
#  automatiquement comme classeur d'activité.
# =============================================================================
DOSSIER = core.DOSSIER_DONNEES / "tarification"
FICHIER_BRANCHEMENT = DOSSIER / "branchement.json"
FICHIER_CLIENTS = DOSSIER / "correspondance_clients.csv"
FICHIER_EXPERTISES = DOSSIER / "correspondance_expertises.csv"
FICHIER_RATTACHEMENTS = DOSSIER / "rattachements.json"
EXTENSIONS = core.EXTENSIONS_DONNEES

# Les colonnes du classeur, telles que la page 5 les nomme, puis leurs synonymes.
# La comparaison se fait sans casse, sans accent, sans ponctuation.
COLONNES: dict[str, tuple[str, tuple[str, ...]]] = {
    "client": ("Client", ("client", "prospect/client", "prospect client", "prospect",
                          "nom du client", "nom client")),
    "minimum": ("Quantite_Minimum", ("quantite minimum", "quantite min", "minimum",
                                     "borne basse", "seuil bas", "tranche minimum",
                                     "encours minimum", "de m€")),
    "maximum": ("Quantite_Maximum", ("quantite maximum", "quantite max", "maximum",
                                     "borne haute", "seuil haut", "tranche maximum",
                                     "encours maximum", "a m€")),
    "taux": ("Frais_par_seuil", ("frais par seuil", "frais", "taux", "taux par seuil",
                                 "frais de gestion", "fee", "fees", "rate")),
    "surperformance": ("Commissions de surperformance", (
        "commissions de surperformance", "commission de surperformance",
        "surperformance", "commission de performance", "performance fee")),
    "volume": ("Volume1", ("volume1", "volume", "encours", "montant", "montant investi",
                           "encours m€", "aum")),
    "annee": ("Annee", ("annee", "year", "exercice", "millesime")),
    "expertise": ("Sub_asset_class", ("sub asset class", "expertise", "classe d actifs",
                                      "sous classe d actifs", "sous classe", "asset class",
                                      "strategie")),
    "issue": ("Client_Prospect", ("client prospect", "statut", "issue", "resultat",
                                  "status", "result")),
    "nature": ("Public_Privé", ("public prive", "public ou prive", "public privee",
                                "nature du client", "nature")),
    "tva": ("TVA", ("tva", "ht ttc", "regime tva", "taxe")),
}
OBLIGATOIRES = ("client", "minimum", "maximum", "taux")
RECOMMANDEES = ("volume", "annee", "expertise", "issue")

ISSUE_GAGNE, ISSUE_PERDU, ISSUE_EN_COURS, ISSUE_INCONNUE = "Gagné", "Perdu", "En cours", "Non renseigné"
ISSUES = (ISSUE_GAGNE, ISSUE_PERDU, ISSUE_EN_COURS, ISSUE_INCONNUE)
_SYNONYMES_ISSUE = {
    ISSUE_GAGNE: ("gagne", "gagnee", "won", "win", "remporte", "oui"),
    ISSUE_PERDU: ("perdu", "perdue", "lost", "lose", "non retenu", "non"),
    ISSUE_EN_COURS: ("en cours", "encours", "en attente", "pending", "in progress",
                     "ouvert", "prospect", "en negociation"),
}

# Les expertises des grilles et celles du classeur d'activité ne partagent pas
# leur vocabulaire. Ce rapprochement par défaut sert à proposer des dossiers
# candidats et à situer une offre dans son contexte ; il est à valider par le
# pôle et se remplace par data/tarification/correspondance_expertises.csv
# (colonnes expertise;dimension;valeur). Une correspondance suffit.
RAPPROCHEMENT_EXPERTISES: dict[str, tuple[tuple[str, str], ...]] = {
    "credit ig": (("sous_classe_actifs", "Crédit investment grade"),),
    "global credit": (("sous_classe_actifs", "Crédit global"),),
    "climate": (("sous_classe_actifs", "Thématique climat"),
                ("sous_classe_actifs", "Obligations vertes")),
    "convertibles": (("sous_classe_actifs", "Convertibles"),),
    "equity": (("classe_actifs", "Actions"),),
    "diversifie": (("classe_actifs", "Diversifié"),),
    "assurantiel": (("segment", "Assureur"), ("segment", "Mutuelle")),
}
# Toute expertise « OA - … » relève de l'architecture ouverte.
RAPPROCHEMENT_PREFIXE_OA = (("expertise", "Open Architecture"),)

# La grille type de la page 2 de la présentation : 0,093 % à 150 M€.
GRILLE_TYPE: tuple[tuple[float, float | None, float], ...] = (
    (0.0, 50.0, 0.12), (50.0, 100.0, 0.09), (100.0, 150.0, 0.07), (150.0, None, 0.05),
)
# Seuils de la grille de référence d'une expertise : ceux de la grille type.
SEUILS_REFERENCE = (0.0, 50.0, 100.0, 150.0, 200.0)

# Sévérité des anomalies. Une grille « bloquante » reste visible, mais sort des
# fourchettes : elle fausserait ce que l'on compare.
BLOQUANTE, ATTENTION, INFO = "bloquante", "attention", "info"


# =============================================================================
#  LE CALCUL — barème progressif, dernière tranche ouverte
# -----------------------------------------------------------------------------
#  Frais(A)      = Σ taux_k × max(0, min(A, max_k) − min_k)
#  Taux_moyen(A) = Frais(A) / A
#  La dernière tranche s'applique au-delà de son plafond : c'est la seule lecture
#  commerciale possible (cf. client 23 de l'échantillon, et la courbe de la page 3
#  qui s'effondrait vers zéro avec un plafond fermé).
#  Taux en pour cent (0,12 veut dire 0,12 %), encours en M€, frais en M€ par an.
# =============================================================================
@dataclass
class Tranche:
    minimum: float
    maximum: float | None      # None : tranche ouverte
    taux: float                # en %


def frais(tranches: Sequence[Tranche], encours: float) -> float:
    """Frais annuels en M€ pour un encours en M€."""
    if encours is None or not math.isfinite(encours) or encours <= 0 or not tranches:
        return 0.0
    total = 0.0
    dernier = len(tranches) - 1
    for i, t in enumerate(tranches):
        haut = math.inf if i == dernier or t.maximum is None else t.maximum
        part = min(encours, haut) - t.minimum
        if part > 0:
            total += part * t.taux / 100.0
    return total


def taux_moyen(tranches: Sequence[Tranche], encours: float) -> float:
    """Taux moyen en % ; à encours nul, le taux de la tranche qui contient zéro."""
    if not tranches:
        return float("nan")
    if encours is None or not math.isfinite(encours) or encours <= 0:
        return tranches[0].taux if tranches[0].minimum <= 0 else 0.0
    return frais(tranches, encours) / encours * 100.0


def taux_marginal(tranches: Sequence[Tranche], bas: float, haut: float) -> float:
    """Taux moyen appliqué à la seule part d'encours comprise entre bas et haut."""
    if haut <= bas:
        return taux_moyen(tranches, bas)
    return (frais(tranches, haut) - frais(tranches, bas)) / (haut - bas) * 100.0


def haut_de_tranche_ouverte(bas: float, encours_client: float | None) -> float:
    """Tranche de comparaison d'une tranche ouverte « au-delà de bas » : jusqu'au
    double de son seuil, 50 M€ au moins, et au moins jusqu'à l'encours visé."""
    return max(2.0 * bas, bas + 50.0, encours_client or 0.0)


def quantile(valeurs: Sequence[float], q: float) -> float:
    """Interpolation linéaire, comme numpy.quantile — et comme tarif.js."""
    x = sorted(v for v in valeurs if v is not None and math.isfinite(v))
    if not x:
        return float("nan")
    h = (len(x) - 1) * q
    bas = math.floor(h)
    haut = min(bas + 1, len(x) - 1)
    return x[bas] + (h - bas) * (x[haut] - x[bas])


def centile(valeurs: Sequence[float], v: float) -> float:
    """Part des valeurs sous v, les égalités comptant pour moitié (0 à 100)."""
    x = [u for u in valeurs if u is not None and math.isfinite(u)]
    if not x or v is None or not math.isfinite(v):
        return float("nan")
    dessous = sum(1 for u in x if u < v - 1e-12)
    egales = sum(1 for u in x if abs(u - v) <= 1e-12)
    return 100.0 * (dessous + 0.5 * egales) / len(x)


def resume(valeurs: Sequence[float]) -> dict[str, float]:
    x = [v for v in valeurs if v is not None and math.isfinite(v)]
    if not x:
        return {"n": 0}
    return {"n": len(x), "min": min(x), "p25": quantile(x, .25), "mediane": quantile(x, .5),
            "p75": quantile(x, .75), "max": max(x), "moyenne": sum(x) / len(x)}


# =============================================================================
#  LES GRILLES
# =============================================================================
@dataclass
class Anomalie:
    code: str
    gravite: str
    texte: str


@dataclass
class Grille:
    id: str
    client: str
    annee: int | None
    expertise: str
    expertise_cle: str
    issue: str
    nature: str
    tva: str
    volume: float | None
    surperformance: float | None
    tranches: list[Tranche]
    plafond_saisi: float | None
    lignes: list[int] = field(default_factory=list)
    anomalies: list[Anomalie] = field(default_factory=list)

    @property
    def exclue(self) -> bool:
        return any(a.gravite == BLOQUANTE for a in self.anomalies)

    @property
    def taux_volume(self) -> float:
        return taux_moyen(self.tranches, self.volume) if self.volume else float("nan")

    @property
    def frais_volume(self) -> float:
        return frais(self.tranches, self.volume) if self.volume else float("nan")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["exclue"] = self.exclue
        d["taux_volume"] = self.taux_volume
        d["frais_volume"] = self.frais_volume
        return d


def identifiant(client: str, annee: int | None, expertise_cle: str) -> str:
    brut = f"{client}-{annee or 'sans-annee'}-{expertise_cle or 'sans-expertise'}"
    return re.sub(r"[^a-z0-9]+", "-", core.cle_recherche(brut)).strip("-")


# =============================================================================
#  LECTURE DU CLASSEUR — tolérante, jamais silencieuse
# =============================================================================
class ClasseurInvalide(ValueError):
    pass


@dataclass
class Journal:
    source: str = ""
    mode: str = "demo"
    fichier: str | None = None
    onglet: str | None = None
    ligne_entetes: int = 1
    colonnes: dict[str, str] = field(default_factory=dict)
    ignorees: list[str] = field(default_factory=list)
    manquantes: list[str] = field(default_factory=list)
    alertes: list[str] = field(default_factory=list)
    n_lignes: int = 0
    n_grilles: int = 0
    unite_taux: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sans_accent(cle: str) -> str:
    return core.cle_recherche(cle)


def _correspondre(entetes: Sequence[Any]) -> tuple[dict[str, int], list[str]]:
    """Champ → indice de colonne. Les égalités exactes passent d'abord, puis les
    préfixes (un en-tête tronqué, « Public_Priv », se reconnaît encore)."""
    normes = [_sans_accent(e) if e is not None else "" for e in entetes]
    pris: dict[str, int] = {}
    utilisees: set[int] = set()
    for passe in ("exact", "prefixe"):
        for champ, (officiel, synonymes) in COLONNES.items():
            if champ in pris:
                continue
            cles = [_sans_accent(officiel), *(_sans_accent(s) for s in synonymes)]
            for j, n in enumerate(normes):
                if j in utilisees or not n:
                    continue
                ok = n in cles if passe == "exact" else any(
                    len(n) >= 6 and len(c) >= 6 and (c.startswith(n) or n.startswith(c))
                    for c in cles)
                if ok:
                    pris[champ] = j
                    utilisees.add(j)
                    break
    ignorees = [str(entetes[j]) for j in range(len(entetes))
                if j not in utilisees and entetes[j] is not None and str(entetes[j]).strip()]
    return pris, ignorees


def _meilleur_entete(brut: pd.DataFrame) -> tuple[int, dict[str, int], list[str]]:
    """La ligne d'en-têtes est celle, parmi les quinze premières, qui reconnaît
    le plus de colonnes : un titre posé au-dessus du tableau ne gêne pas."""
    meilleur = (-1, {}, [])
    for i in range(min(15, len(brut))):
        pris, ignorees = _correspondre(list(brut.iloc[i].values))
        score = len(pris) + 10 * sum(c in pris for c in OBLIGATOIRES)
        if score > (len(meilleur[1]) + 10 * sum(c in meilleur[1] for c in OBLIGATOIRES)):
            meilleur = (i, pris, ignorees)
    return meilleur


def _lire_brut(chemin: Path, onglet: str | None) -> dict[str, pd.DataFrame]:
    ext = chemin.suffix.lower()
    if ext in (".csv", ".tsv", ".txt"):
        for encodage in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                df = pd.read_csv(chemin, sep=None, engine="python", header=None, dtype=object,
                                 encoding=encodage, skip_blank_lines=False)
                return {chemin.stem: df}
            except UnicodeDecodeError:
                continue
        raise ClasseurInvalide(f"Encodage illisible : {chemin.name}")
    try:
        feuilles = pd.read_excel(chemin, sheet_name=onglet if onglet else None,
                                 header=None, dtype=object)
    except Exception as exc:  # classeur corrompu, protégé, format inattendu
        raise ClasseurInvalide(f"Classeur illisible ({chemin.name}) : {exc}") from exc
    return feuilles if isinstance(feuilles, dict) else {str(onglet): feuilles}


def _nombre(v: Any) -> tuple[float | None, bool]:
    """(valeur, écrite en pourcent). « 0,19 % » → (0,19, vrai) ; 0.0019 → (0.0019, faux)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None, False
    if isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v), False
    texte = str(v).strip().replace(" ", " ").replace(" ", " ")
    if not texte:
        return None, False
    pourcent = "%" in texte
    texte = texte.replace("%", "").replace("€", "").replace(" ", "")
    if re.search(r"\d,\d", texte) and "." not in texte:
        texte = texte.replace(",", ".")
    texte = texte.replace(",", "")
    try:
        return float(texte), pourcent
    except ValueError:
        return None, False


def _annee(v: Any) -> int | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (dt.date, dt.datetime, pd.Timestamp)):
        return int(v.year)
    m = re.search(r"(19|20)\d{2}", str(v))
    return int(m.group(0)) if m else None


def _issue(v: Any) -> str:
    cle = _sans_accent(v) if v is not None else ""
    for issue, formes in _SYNONYMES_ISSUE.items():
        if cle in formes:
            return issue
    return ISSUE_INCONNUE if not cle else str(v).strip().capitalize()


def _nature(v: Any) -> str:
    cle = _sans_accent(v) if v is not None else ""
    if cle.startswith("pub"):
        return "Public"
    if cle.startswith("priv"):
        return "Privé"
    return str(v).strip() if cle else ""


def _texte(v: Any) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip()


def lire_classeur(chemin: Path, onglet: str | None = None) -> tuple[list[Grille], Journal]:
    """Lit un classeur de grilles et renvoie les grilles et leur journal."""
    feuilles = _lire_brut(chemin, onglet)
    choix = None
    for nom, brut in feuilles.items():
        i, pris, ignorees = _meilleur_entete(brut)
        score = sum(c in pris for c in OBLIGATOIRES) * 10 + len(pris)
        if choix is None or score > choix[0]:
            choix = (score, nom, brut, i, pris, ignorees)
    if choix is None:
        raise ClasseurInvalide("Le classeur ne contient aucun onglet.")
    _, nom, brut, i, pris, ignorees = choix
    manquantes = [COLONNES[c][0] for c in OBLIGATOIRES if c not in pris]
    if manquantes:
        raise ClasseurInvalide(
            "Colonnes introuvables : " + ", ".join(manquantes) + ". En-têtes attendus : "
            + ", ".join(v[0] for v in COLONNES.values()) + ".")
    journal = Journal(source=chemin.name, mode="fichier", fichier=chemin.name,
                      onglet=None if len(feuilles) == 1 and onglet is None else str(nom),
                      ligne_entetes=i + 1,
                      colonnes={c: str(brut.iloc[i, j]) for c, j in pris.items()},
                      ignorees=ignorees,
                      manquantes=[COLONNES[c][0] for c in RECOMMANDEES if c not in pris])
    corps = brut.iloc[i + 1:].reset_index(drop=True)
    table = pd.DataFrame({c: corps.iloc[:, j] for c, j in pris.items()})
    table["_ligne"] = range(i + 2, i + 2 + len(table))
    return construire(table, journal)


def construire(table: pd.DataFrame, journal: Journal) -> tuple[list[Grille], Journal]:
    """Des lignes (une par tranche) aux grilles (une par client, année, expertise)."""
    for c in COLONNES:
        if c not in table.columns:
            table[c] = None
    if "_ligne" not in table.columns:
        table["_ligne"] = range(2, 2 + len(table))

    # Unité des taux, décidée pour la colonne entière : un classeur Excel au
    # format pourcentage donne 0,0019 pour 0,19 % ; un export texte, « 0,19 % ».
    lus = [_nombre(v) for v in table["taux"]]
    nus = [x for x, p in lus if x is not None and not p]
    en_fraction = bool(nus) and max(abs(x) for x in nus) <= 0.05
    journal.unite_taux = "fraction (format pourcentage d'Excel)" if en_fraction else "pour cent"

    lignes: list[dict[str, Any]] = []
    precedent: dict[str, Any] = {}
    completees = 0
    for k, r in table.iterrows():
        mini, _ = _nombre(r["minimum"])
        # Un plafond illisible (« illimité », « ∞ », vide) se lit comme absent :
        # ouvert s'il est le dernier, déduit du seuil suivant sinon.
        maxi, _ = _nombre(r["maximum"])
        taux_brut, pct = lus[k]
        client = _texte(r["client"])
        if client == "" and mini is None and taux_brut is None:
            continue                                   # ligne vide
        if client == "" and precedent:                 # cellule fusionnée
            client = precedent["client"]
            completees += 1
        if client == "" or mini is None or taux_brut is None:
            journal.alertes.append(f"Ligne {r['_ligne']} ignorée : client, borne basse ou taux absent.")
            continue
        taux = taux_brut if pct else (taux_brut * 100.0 if en_fraction else taux_brut)
        ligne = {
            "client": client, "minimum": mini, "maximum": maxi,
            "taux": taux, "ligne": int(r["_ligne"]),
            "volume": _nombre(r["volume"])[0], "annee": _annee(r["annee"]),
            "expertise": _texte(r["expertise"]), "issue": _texte(r["issue"]),
            "nature": _texte(r["nature"]), "tva": _texte(r["tva"]),
            "surperformance": _nombre(r["surperformance"])[0],
        }
        # Une cellule vide sous un client se lit comme la valeur du dessus.
        if precedent.get("client") == client:
            for c in ("volume", "annee", "expertise", "issue", "nature", "tva"):
                if ligne[c] in (None, ""):
                    ligne[c] = precedent[c]
        lignes.append(ligne)
        precedent = ligne
    if completees:
        journal.alertes.append(f"{core.pluriel(completees, 'ligne')} sans client : rattachée"
                               f"{'s' if completees > 1 else ''} au client de la ligne du dessus.")
    if not lignes:
        raise ClasseurInvalide("Aucune tranche exploitable : vérifier les colonnes de bornes et de taux.")

    # Libellé d'une expertise : l'écriture la plus fréquente, en évitant les
    # capitales intégrales quand une autre écriture existe.
    ecritures: dict[str, dict[str, int]] = {}
    for l in lignes:
        cle = _sans_accent(l["expertise"])
        if cle:
            ecritures.setdefault(cle, {}).setdefault(l["expertise"], 0)
            ecritures[cle][l["expertise"]] += 1
    libelle_expertise = {
        cle: sorted(formes.items(), key=lambda kv: (kv[0].isupper(), -kv[1], kv[0]))[0][0]
        for cle, formes in ecritures.items()}

    groupes: dict[tuple, list[dict[str, Any]]] = {}
    for l in lignes:
        cle = (l["client"], l["annee"], _sans_accent(l["expertise"]))
        groupes.setdefault(cle, []).append(l)

    grilles = [_grille(cle, rangs, libelle_expertise) for cle, rangs in groupes.items()]
    grilles.sort(key=lambda g: (g.expertise_cle, -(g.annee or 0), _ordre_client(g.client)))
    journal.n_lignes = len(lignes)
    journal.n_grilles = len(grilles)
    return grilles, journal


def _ordre_client(client: str) -> tuple:
    """Tri naturel : « Client 2 » avant « Client 10 ». Aucun sens n'est prêté au numéro."""
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", client))


def _grille(cle: tuple, rangs: list[dict[str, Any]], libelles: Mapping[str, str]) -> Grille:
    client, annee, exp_cle = cle
    anomalies: list[Anomalie] = []

    # Doublons exacts : une grille collée deux fois.
    vus, uniques = set(), []
    for r in sorted(rangs, key=lambda r: (r["minimum"], r["maximum"] if r["maximum"] is not None else math.inf)):
        empreinte = (r["minimum"], r["maximum"], round(r["taux"], 6))
        if empreinte in vus:
            continue
        vus.add(empreinte)
        uniques.append(r)
    if len(uniques) < len(rangs):
        anomalies.append(Anomalie("doublon", INFO, f"{len(rangs) - len(uniques)} tranche(s) en double retirée(s)."))

    tranches = [Tranche(r["minimum"], r["maximum"], r["taux"]) for r in uniques]
    deduits = 0
    for i in range(len(tranches) - 1):
        if tranches[i].maximum is None:
            tranches[i] = Tranche(tranches[i].minimum, tranches[i + 1].minimum, tranches[i].taux)
            deduits += 1
    if deduits:
        anomalies.append(Anomalie("plafond_deduit", INFO,
                                  f"{deduits} plafond(s) absent(s), déduit(s) du seuil de la tranche suivante."))
    plafond_saisi = tranches[-1].maximum
    tranches[-1] = Tranche(tranches[-1].minimum, None, tranches[-1].taux)

    if tranches[0].minimum > 0:
        anomalies.append(Anomalie("debut", ATTENTION,
                                  f"La grille commence à {core.fmt_dec(tranches[0].minimum, 0)} M€ : "
                                  f"l'encours en dessous ne paie rien."))
    for a, b in zip(tranches, tranches[1:]):
        if a.maximum is None:
            continue
        if b.minimum > a.maximum + 1e-9:
            anomalies.append(Anomalie("trou", ATTENTION,
                                      f"Aucune tranche entre {core.fmt_dec(a.maximum, 0)} et "
                                      f"{core.fmt_dec(b.minimum, 0)} M€."))
        elif b.minimum < a.maximum - 1e-9:
            anomalies.append(Anomalie("chevauchement", BLOQUANTE,
                                      f"Les tranches se chevauchent entre {core.fmt_dec(b.minimum, 0)} et "
                                      f"{core.fmt_dec(a.maximum, 0)} M€ : l'encours y serait facturé deux fois."))
    if any(abs(a.taux - b.taux) < 1e-9 for a, b in zip(tranches, tranches[1:])):
        anomalies.append(Anomalie("paliers_sans_effet", INFO,
                                  "Des tranches consécutives portent le même taux : leurs seuils ne changent rien au prix."))
    if any(b.taux > a.taux + 1e-9 for a, b in zip(tranches, tranches[1:])):
        anomalies.append(Anomalie("progressive", INFO, "Un taux augmente avec l'encours : grille non dégressive."))
    if any(t.taux <= 0 for t in tranches):
        anomalies.append(Anomalie("taux_nul", ATTENTION, "Une tranche est facturée 0 %."))

    volumes = [r["volume"] for r in rangs if r["volume"] is not None]
    volume = None
    if volumes:
        volume = max(set(volumes), key=volumes.count)
        if len(set(volumes)) > 1:
            anomalies.append(Anomalie("volume_variable", ATTENTION,
                                      "L'encours du mandat diffère d'une tranche à l'autre : valeur la plus fréquente retenue."))
    else:
        anomalies.append(Anomalie("volume_absent", ATTENTION, "Encours du mandat absent : le taux du client ne se calcule pas."))
    if volume is not None and plafond_saisi is not None and volume > plafond_saisi + 1e-9:
        anomalies.append(Anomalie("plafond_depasse", INFO,
                                  f"L'encours ({core.fmt_dec(volume, 0)} M€) dépasse le dernier plafond saisi "
                                  f"({core.fmt_dec(plafond_saisi, 0)} M€) : la dernière tranche est prolongée."))
    if annee is None:
        anomalies.append(Anomalie("annee_absente", INFO, "Année absente."))
    if not exp_cle:
        anomalies.append(Anomalie("expertise_absente", ATTENTION, "Expertise absente : l'offre ne se compare à rien."))

    g = Grille(
        id=identifiant(client, annee, exp_cle), client=client, annee=annee,
        expertise=libelles.get(exp_cle, "Sans expertise"), expertise_cle=exp_cle,
        issue=_issue(rangs[0]["issue"]), nature=_nature(rangs[0]["nature"]),
        tva=(rangs[0]["tva"] or "HT").upper() if rangs[0]["tva"] else "HT",
        volume=volume, surperformance=next((r["surperformance"] for r in rangs
                                            if r["surperformance"] is not None), None),
        tranches=tranches, plafond_saisi=plafond_saisi,
        lignes=[r["ligne"] for r in rangs], anomalies=anomalies)
    if volume is not None and volume > 0 and not (g.taux_volume > 0):
        g.anomalies.append(Anomalie("prix_nul", BLOQUANTE,
                                    "Le taux moyen au volume du mandat vaut 0 % : grille exclue des fourchettes."))
    return g


# =============================================================================
#  L'ÉCHANTILLON — les 48 lignes lisibles de la page 5, transcrites telles quelles
# -----------------------------------------------------------------------------
#  Mêmes en-têtes, mêmes types que le classeur : taux au format pourcentage
#  d'Excel (0,0019), année tantôt texte tantôt nombre. Il passe par la même
#  lecture qu'un vrai classeur.
# =============================================================================
_ECHANTILLON: tuple[tuple, ...] = (
    ("Client 1", 0, 200, 0.0019, 0, 80, "2024", "OA - Diversified", "Gagné", "Privé", "HT"),
    ("Client 2", 0, 100, 0.0009, 0, 100, "2024", "Credit IG", "Perdu", "Public", "HT"),
    ("Client 2", 100, 150, 0.0008, 0, 100, "2024", "Credit IG", "Perdu", "Public", "HT"),
    ("Client 2", 150, 300, 0.0006, 0, 100, "2024", "Credit IG", "Perdu", "Public", "HT"),
    ("Client 3", 0, 50, 0.0014, 0, 50, "2024", "OA - Diversified", "Perdu", "Privé", "HT"),
    ("Client 3", 50, 100, 0.0012, 0, 50, "2024", "OA - Diversified", "Perdu", "Privé", "HT"),
    ("Client 4", 0, 200, 0.0030, 0, 65, "2024", "Global credit", "Perdu", "Privé", "HT"),
    ("Client 5", 0, 200, 0.0021, 0, 50, "2024", "Climate", "Gagné", "Privé", "HT"),
    ("Client 6", 0, 30, 0.0030, 0, 85, "2024", "Climate", "Gagné", "Privé", "HT"),
    ("Client 6", 30, 50, 0.0028, 0, 85, "2024", "Climate", "Gagné", "Privé", "HT"),
    ("Client 6", 50, 100, 0.0024, 0, 85, "2024", "Climate", "Gagné", "Privé", "HT"),
    ("Client 6", 100, 150, 0.0019, 0, 85, "2024", "Climate", "Gagné", "Privé", "HT"),
    ("Client 6", 150, 200, 0.0012, 0, 85, "2024", "Climate", "Gagné", "Privé", "HT"),
    ("Client 7", 0, 50, 0.0014, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 7", 50, 100, 0.0014, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 7", 100, 150, 0.0010, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 7", 150, 200, 0.0010, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 7", 200, 250, 0.0006, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 7", 250, 300, 0.0006, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 7", 300, 350, 0.0006, 0, 350, 2025, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 8", 0, 180, 0.0009, 0, 180, 2025, "Credit IG", "En cours", "Privé", "HT"),
    ("Client 9", 0, 30, 0.0021, 0, 70, 2025, "Credit IG", "En cours", "Privé", "HT"),
    ("Client 9", 30, 60, 0.0019, 0, 70, 2025, "Credit IG", "En cours", "Privé", "HT"),
    ("Client 9", 60, 100, 0.0017, 0, 70, 2025, "Credit IG", "En cours", "Privé", "HT"),
    ("Client 9", 100, 150, 0.0015, 0, 70, 2025, "Credit IG", "En cours", "Privé", "HT"),
    ("Client 10", 0, 100, 0.0010, 0, 100, 2025, "Credit IG", "En cours", "Privé", "HT"),
    ("Client 11", 0, 84, 0.0012, 0, 84, 2025, "OA - ETF", "Perdu", "Privé", "HT"),
    ("Client 12", 0, 25, 0.0030, 0, 37, 2022, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 12", 25, 50, 0.0025, 0, 37, 2022, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 12", 50, 100, 0.0020, 0, 37, 2022, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 13", 0, 50, 0.0019, 0, 90, 2017, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 13", 50, 100, 0.0015, 0, 90, 2017, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 13", 100, 150, 0.0012, 0, 90, 2017, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 14", 0, 40, 0.0025, 0, 90, "2024", "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 14", 40, 60, 0.0020, 0, 90, "2024", "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 14", 60, 100, 0.0015, 0, 90, "2024", "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 15", 0, 50, 0.0016, 0, 73, 2020, "Credit IG", "Gagné", "Privé", "HT"),
    ("Client 15", 50, 100, 0.0012, 0, 73, 2020, "Credit IG", "Gagné", "Privé", "HT"),
    ("Client 16", 0, 150, 0.0015, 0, 395, 2020, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 16", 150, 200, 0.0013, 0, 395, 2020, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 16", 200, 400, 0.0011, 0, 395, 2020, "Assurantiel", "Gagné", "Privé", "HT"),
    ("Client 17", 0, 500, 0.0020, 0, 200, 2024, "OA - Gestion conseillée", "Gagné", "Privé", "HT"),
    ("Client 18", 0, 500, 0.0040, 0, 200, 2024, "OA - GSM", "Gagné", "Privé", "HT"),
    ("Client 19", 0, 300, 0.0015, 0, 200, 2024, "OA - GSM ETF", "Perdu", "Privé", "HT"),
    ("Client 20", 0, 200, 0.0012, 0, 200, 2023, "Global credit", "Gagné", "Privé", "HT"),
    ("Client 21", 0, 60, 0.0015, 0, 60, 2023, "Credit IG", "Perdu", "Privé", "HT"),
    ("Client 22", 0, 45, 0.0040, 0, 45, 2023, "OA - Diversified", "Perdu", "Privé", "HT"),
    ("Client 23", 0, 200, 0.0014, 0, 300, 2023, "Equity", "Perdu", "Privé", "HT"),
)
ENTETES_CLASSEUR = tuple(v[0] for v in COLONNES.values())
SOURCE_ECHANTILLON = ("Échantillon de démonstration : les 48 lignes lisibles de la page 5 de la "
                      "présentation (23 clients anonymisés)")


def echantillon() -> pd.DataFrame:
    """L'échantillon, sous la forme exacte du classeur."""
    return pd.DataFrame(list(_ECHANTILLON), columns=list(ENTETES_CLASSEUR))


def lire_echantillon() -> tuple[list[Grille], Journal]:
    brut = echantillon()
    entetes = pd.DataFrame([list(brut.columns)], columns=range(brut.shape[1]))
    corps = pd.DataFrame(brut.values, columns=range(brut.shape[1]))
    feuille = pd.concat([entetes, corps], ignore_index=True)
    i, pris, ignorees = _meilleur_entete(feuille)
    table = pd.DataFrame({c: feuille.iloc[i + 1:, j].reset_index(drop=True) for c, j in pris.items()})
    journal = Journal(source=SOURCE_ECHANTILLON, mode="demo", ligne_entetes=1,
                      colonnes={c: str(feuille.iloc[i, j]) for c, j in pris.items()},
                      ignorees=ignorees)
    return construire(table, journal)


# =============================================================================
#  BRANCHEMENT DU CLASSEUR TARIFAIRE
# =============================================================================
def lire_branchement() -> dict[str, Any] | None:
    try:
        return json.loads(FICHIER_BRANCHEMENT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def ecrire_branchement(b: Mapping[str, Any]) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER_BRANCHEMENT.write_text(json.dumps(dict(b), ensure_ascii=False, indent=2), encoding="utf-8")


def fichiers_disponibles() -> list[Path]:
    if not DOSSIER.is_dir():
        return []
    reserves = {FICHIER_CLIENTS.name, FICHIER_EXPERTISES.name}
    fichiers = [p for p in DOSSIER.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSIONS and p.name not in reserves
                and not p.name.startswith((".", "~$"))]
    return sorted(fichiers, key=lambda p: p.stat().st_mtime, reverse=True)


def charger(forcer_demo: bool = False) -> tuple[list[Grille], Journal]:
    """Le classeur branché s'il est actif et lisible, l'échantillon sinon. Un
    classeur qui ne se lit plus ne fait jamais tomber l'écran : on retombe sur
    l'échantillon, et le journal le dit."""
    b = None if forcer_demo else lire_branchement()
    if b and b.get("actif") and b.get("fichier"):
        chemin = DOSSIER / Path(b["fichier"]).name
        if chemin.exists():
            try:
                return lire_classeur(chemin, b.get("onglet"))
            except ClasseurInvalide as exc:
                grilles, journal = lire_echantillon()
                journal.alertes.insert(0, f"Le classeur branché ({chemin.name}) ne se lit plus : {exc}")
                return grilles, journal
    return lire_echantillon()


# =============================================================================
#  CORRESPONDANCES — libellés clients, rattachements, expertises
# -----------------------------------------------------------------------------
#  « Client 7 » est une clé, jamais une information. Ses vrais libellés viennent
#  d'un fichier externe, édité à la main ou depuis l'écran.
# =============================================================================
def _lire_csv(chemin: Path) -> list[dict[str, str]]:
    if not chemin.exists():
        return []
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = chemin.read_text(encoding=encodage)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    try:
        dialecte = csv.Sniffer().sniff(texte[:2048], delimiters=";,\t")
    except csv.Error:
        dialecte = csv.excel
        dialecte.delimiter = ";"
    lecteur = csv.DictReader(io.StringIO(texte), dialect=dialecte)
    return [{_sans_accent(k): (v or "").strip() for k, v in ligne.items() if k} for ligne in lecteur]


def libelles_clients() -> dict[str, str]:
    """Client anonymisé → libellé. Les lignes sans libellé sont ignorées."""
    sortie = {}
    for ligne in _lire_csv(FICHIER_CLIENTS):
        client = ligne.get("client", "")
        libelle = ligne.get("libelle", "") or ligne.get("nom", "")
        if client and libelle:
            sortie[client] = libelle
    return sortie


def ecrire_libelles(libelles: Mapping[str, str], clients: Iterable[str]) -> None:
    """Réécrit le fichier de correspondance : une ligne par client connu, libellé
    vide si inconnu, pour que le fichier se remplisse d'un coup dans Excel."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    tous = sorted(set(clients) | set(libelles), key=_ordre_client)
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    ecrivain.writerow(["client", "libelle"])
    for c in tous:
        ecrivain.writerow([c, libelles.get(c, "")])
    FICHIER_CLIENTS.write_text(tampon.getvalue(), encoding="utf-8-sig")


def lire_correspondance(chemin: Path) -> dict[str, str]:
    """Un fichier de correspondance déposé (CSV ou classeur) : colonnes client
    et libellé, en-têtes reconnus sans casse ni accent."""
    if chemin.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        try:
            brut = pd.read_excel(chemin, dtype=object)
        except Exception as exc:
            raise ClasseurInvalide(f"Classeur illisible : {exc}") from exc
        lignes = [{_sans_accent(k): _texte(v) for k, v in r.items()} for r in brut.to_dict("records")]
    else:
        lignes = _lire_csv(chemin)
    if not lignes or "client" not in lignes[0] or not ({"libelle", "nom"} & set(lignes[0])):
        raise ClasseurInvalide("Colonnes attendues : « client » et « libelle ».")
    return {l["client"]: (l.get("libelle") or l.get("nom") or "") for l in lignes
            if l.get("client") and (l.get("libelle") or l.get("nom"))}


def csv_correspondance(clients: Iterable[str]) -> str:
    libelles = libelles_clients()
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    ecrivain.writerow(["client", "libelle"])
    for c in sorted(set(clients), key=_ordre_client):
        ecrivain.writerow([c, libelles.get(c, "")])
    return "﻿" + tampon.getvalue()


def rattachements() -> dict[str, str]:
    """Identifiant de grille → clé de dossier d'activité (numéro)."""
    try:
        d = json.loads(FICHIER_RATTACHEMENTS.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in d.items() if v}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire_rattachement(grille_id: str, dossier: str | None) -> None:
    d = rattachements()
    if dossier:
        d[grille_id] = str(dossier)
    else:
        d.pop(grille_id, None)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER_RATTACHEMENTS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def rapprochement_expertises() -> dict[str, tuple[tuple[str, str], ...]]:
    """La table par défaut, remplacée expertise par expertise par le fichier."""
    table = dict(RAPPROCHEMENT_EXPERTISES)
    fichier: dict[str, list[tuple[str, str]]] = {}
    for ligne in _lire_csv(FICHIER_EXPERTISES):
        exp, dim, val = ligne.get("expertise", ""), ligne.get("dimension", ""), ligne.get("valeur", "")
        if exp and dim and val:
            fichier.setdefault(_sans_accent(exp), []).append((_sans_accent(dim).replace(" ", "_"), val))
    table.update({k: tuple(v) for k, v in fichier.items()})
    return table


def criteres_activite(expertise_cle: str) -> tuple[tuple[str, str], ...]:
    table = rapprochement_expertises()
    if expertise_cle in table:
        return table[expertise_cle]
    if expertise_cle.startswith("oa "):
        return RAPPROCHEMENT_PREFIXE_OA
    return ()


# =============================================================================
#  CROISEMENT AVEC LE CLASSEUR D'ACTIVITÉ
# =============================================================================
def cle_dossier(ligne: Mapping[str, Any]) -> str:
    """Clé stable d'un dossier d'activité : son numéro, sinon client, date et famille."""
    numero = ligne.get("numero")
    if numero is not None and not (isinstance(numero, float) and math.isnan(numero)) and str(numero).strip():
        n = str(numero).strip()
        return n[:-2] if n.endswith(".0") else n
    date = ligne.get("date_reception")
    date = pd.Timestamp(date).strftime("%Y-%m-%d") if date is not None and not pd.isna(date) else ""
    return f"{ligne.get('client', '')}|{date}|{ligne.get('famille', '')}"


def _masque_criteres(activite: pd.DataFrame, criteres: Sequence[tuple[str, str]]) -> pd.Series:
    masque = pd.Series(False, index=activite.index)
    for dim, val in criteres:
        if dim in activite.columns:
            cible = _sans_accent(val)
            masque |= activite[dim].astype(str).map(_sans_accent).eq(cible)
    return masque


def index_dossiers(activite: pd.DataFrame) -> dict[str, int]:
    """Clé stable → index courant de la ligne : l'index change à chaque
    rechargement, le numéro de dossier non."""
    if activite is None or activite.empty:
        return {}
    return {cle_dossier(r): int(i) for i, r in activite.iterrows()}


def dossier_rattache(g: Grille, activite: pd.DataFrame, libelle: str | None,
                     index: Mapping[str, int] | None = None,
                     liens: Mapping[str, str] | None = None) -> tuple[int | None, str]:
    """(index du dossier, mode) : « manuel » si inscrit, « libellé » si le client
    et l'année concordent, (None, "") sinon."""
    if activite is None or activite.empty:
        return None, ""
    cle = (liens if liens is not None else rattachements()).get(g.id)
    if cle:
        idx = (index if index is not None else index_dossiers(activite)).get(cle)
        if idx is not None:
            return idx, "manuel"
    if libelle:
        rfp = activite[activite.get("est_rfp", pd.Series(True, index=activite.index)).astype(bool)]
        memes = rfp[rfp["client"].astype(str).map(_sans_accent).eq(_sans_accent(libelle))]
        if g.annee is not None and "annee" in memes.columns:
            meme_annee = memes[memes["annee"] == g.annee]
            memes = meme_annee if len(meme_annee) else memes.iloc[0:0]
        if len(memes):
            if g.volume and "montant_potentiel" in memes.columns:
                ecart = (memes["montant_potentiel"].fillna(0) - g.volume).abs()
                return int(ecart.idxmin()), "libellé"
            return int(memes.index[0]), "libellé"
    return None, ""


# Les cercles de recherche des candidats, du plus étroit au plus large :
# (libellé, écart d'années admis, famille d'expertise exigée).
NIVEAUX_CANDIDATS: tuple[tuple[str, int, bool], ...] = (
    ("même année, même famille d'expertise", 0, True),
    ("à un an près, même famille d'expertise", 1, True),
    ("même année, toutes expertises", 0, False),
    ("à un an près, toutes expertises", 1, False),
)


def candidats(g: Grille, activite: pd.DataFrame, niveau: int | None = None,
              limite: int = 8) -> dict[str, Any]:
    """Dossiers d'appel d'offres qui pourraient être cette offre, avec la raison
    de chaque proposition. Sans niveau imposé, le cercle le plus étroit qui
    trouve quelque chose. Le choix reste humain."""
    libelles = [n[0] for n in NIVEAUX_CANDIDATS]
    vide = {"niveau": niveau or 0, "libelle": libelles[niveau or 0], "niveaux": libelles, "candidats": []}
    if activite is None or activite.empty or "est_rfp" not in activite.columns:
        return vide
    criteres = criteres_activite(g.expertise_cle)
    essais = [niveau] if niveau is not None else range(len(NIVEAUX_CANDIDATS))
    for i in essais:
        i = max(0, min(int(i), len(NIVEAUX_CANDIDATS) - 1))
        _, ecart, exiger_famille = NIVEAUX_CANDIDATS[i]
        if exiger_famille and not criteres:
            continue
        trouves = _candidats_niveau(g, activite, criteres, ecart, exiger_famille, limite)
        if trouves or niveau is not None:
            return {"niveau": i, "libelle": libelles[i], "niveaux": libelles, "candidats": trouves}
    return vide


def _candidats_niveau(g: Grille, activite: pd.DataFrame, criteres: Sequence[tuple[str, str]],
                      ecart: int, exiger_famille: bool, limite: int) -> list[dict[str, Any]]:
    rfp = activite[activite["est_rfp"]]
    if g.annee is not None:
        rfp = rfp[(rfp["annee"] - g.annee).abs() <= ecart]
    famille = _masque_criteres(rfp, criteres) if criteres else pd.Series(False, index=rfp.index)
    if exiger_famille:
        rfp = rfp[famille]
    if rfp.empty:
        return []
    sortie = []
    for idx, r in rfp.iterrows():
        raisons, score = [], 0.0
        if g.annee is not None and r["annee"] == g.annee:
            score += 3
            raisons.append(f"même année ({g.annee})")
        elif g.annee is not None:
            score += 1
            raisons.append(f"{int(r['annee'])}, à un an près")
        if bool(famille.get(idx, False)):
            score += 2
            libelle = next((v for d, v in criteres if d in r and _sans_accent(r[d]) == _sans_accent(v)), "")
            raisons.append(f"{g.expertise} ≈ {libelle}")
        montant = r.get("montant_potentiel")
        if g.volume and montant is not None and not pd.isna(montant) and montant > 0:
            proche = 1 - min(1.0, abs(math.log(montant / g.volume)))
            score += 2 * proche
            raisons.append(f"encours {core.fmt_encours(montant)} contre {core.fmt_encours(g.volume)}")
        resultat = str(r.get("resultat", ""))
        if (g.issue, resultat) in ((ISSUE_GAGNE, "Gagné"), (ISSUE_PERDU, "Perdu"),
                                   (ISSUE_EN_COURS, core.RESULTAT_ATTENTE)):
            score += 1
            raisons.append("même issue")
        sortie.append({"id": int(idx), "cle": cle_dossier(r), "score": round(score, 3),
                       "raisons": raisons, "client": str(r.get("client", "")),
                       "annee": int(r["annee"]), "montant_potentiel": core.valeur_json(montant),
                       "resultat": resultat, "classe_actifs": str(r.get("classe_actifs", "")),
                       "sous_classe_actifs": str(r.get("sous_classe_actifs", "")),
                       "date_reception": core.valeur_json(r.get("date_reception"))})
    sortie.sort(key=lambda c: -c["score"])
    return sortie[:limite]


def contexte_activite(g: Grille, activite: pd.DataFrame) -> dict[str, Any] | None:
    """La famille de l'offre, la même année, dans le classeur d'activité : ce qui
    se croise même quand le client reste anonyme."""
    if activite is None or activite.empty or "est_rfp" not in activite.columns:
        return None
    criteres = criteres_activite(g.expertise_cle)
    if not criteres:
        return None
    rfp = activite[activite["est_rfp"]]
    if g.annee is not None:
        rfp = rfp[rfp["annee"] == g.annee]
    sel = rfp[_masque_criteres(rfp, criteres)]
    libelles = [f"{core.LIBELLES_DOSSIER.get(d, d)} : {v}" for d, v in criteres]
    if sel.empty:
        return {"criteres": libelles, "annee": g.annee, "n": 0}
    taux, gagnes, tranches, _ = core.taux_succes_rfp(sel)
    return {
        "criteres": libelles,
        "annee": g.annee, "n": int(len(sel)), "gagnes": int(gagnes), "tranches": int(tranches),
        "taux_succes": core.valeur_json(taux),
        "montant_median": core.valeur_json(float(sel["montant_potentiel"].median())),
        "delai_median": core.valeur_json(core.delai_median(sel)),
    }


# =============================================================================
#  AUTO-TEST — python3 tarification.py
# =============================================================================
def _grille_type() -> list[Tranche]:
    return [Tranche(a, b, r) for a, b, r in GRILLE_TYPE]


def _parite_js(grilles: Sequence[Grille]) -> tuple[bool, str]:
    """Exécute static/js/tarif.js sous node sur les grilles de l'échantillon et
    compare au calcul Python. Sans node, le contrôle est sauté, et le dit."""
    node = shutil.which("node")
    module = Path(__file__).resolve().parent / "static" / "js" / "tarif.js"
    if not node or not module.exists():
        return True, "node absent : parité JavaScript non vérifiée"
    montants = [0, 1, 5, 25, 37, 50, 73, 100, 150, 180, 200, 300, 395, 500, 1000]
    cas = [{"tranches": [asdict(t) for t in g.tranches]} for g in grilles]
    script = (
        "import('" + module.as_uri() + "').then(T => {"
        "const cas = JSON.parse(process.argv[1]); const m = JSON.parse(process.argv[2]);"
        "const out = cas.map(c => ({ f: m.map(a => T.frais(c.tranches, a)), t: m.map(a => T.tauxMoyen(c.tranches, a)),"
        " g: T.tauxMarginal(c.tranches, 50, 150) }));"
        "const q = [0.1, 0.25, 0.5, 0.9].map(p => T.quantile(out.map(o => o.t[7]), p));"
        "const c = T.centile(out.map(o => o.t[7]), 0.12);"
        "process.stdout.write(JSON.stringify({ out, q, c }));"
        "});")
    try:
        res = subprocess.run([node, "--input-type=module", "-e", script, json.dumps(cas), json.dumps(montants)],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"node n'a pas pu s'exécuter : {exc}"
    if res.returncode != 0:
        return False, res.stderr.strip()[:400]
    js = json.loads(res.stdout)
    for g, o in zip(grilles, js["out"]):
        for a, fj, tj in zip(montants, o["f"], o["t"]):
            fp, tp = frais(g.tranches, a), taux_moyen(g.tranches, a)
            if abs(fp - fj) > 1e-12 or abs(tp - tj) > 1e-12:
                return False, f"{g.id} à {a} M€ : Python {tp} / JS {tj}"
        if abs(taux_marginal(g.tranches, 50, 150) - o["g"]) > 1e-12:
            return False, f"{g.id} : taux marginal divergent"
    t100 = [taux_moyen(g.tranches, 100) for g in grilles]
    for p, qj in zip([0.1, 0.25, 0.5, 0.9], js["q"]):
        if abs(quantile(t100, p) - qj) > 1e-12 or abs(float(np.quantile(t100, p)) - qj) > 1e-12:
            return False, f"quantile {p} divergent"
    if abs(centile(t100, 0.12) - js["c"]) > 1e-12:
        return False, "centile divergent"
    return True, f"{len(grilles)} grilles × {len(montants)} encours identiques en JavaScript"


def _auto_test() -> None:
    import tempfile

    print("1. Le calcul progressif reproduit la présentation")
    gt = _grille_type()
    assert round(taux_moyen(gt, 150), 4) == 0.0933, taux_moyen(gt, 150)
    voisins = [round(taux_moyen(gt, a), 3) for a in (140, 145, 155, 160)]
    assert 0.093 not in voisins, voisins
    p1 = [Tranche(0, None, 0.12)]
    assert taux_moyen(p1, 25) == taux_moyen(p1, 75) == 0.12
    assert abs(frais(gt, 150) - 0.14) < 1e-12, "0,093 % de 150 M€ = 140 k€"
    assert taux_moyen(gt, 0) == 0.12 and taux_moyen([], 10) != taux_moyen([], 10)
    assert abs(taux_marginal(gt, 50, 100) - 0.09) < 1e-12
    print("   ✓ 0,093 % à 150 M€ et seulement là, 0,12 % à tranche unique, 140 k€ par an")

    print("2. L'échantillon de la page 5 se lit comme un classeur")
    grilles, journal = lire_echantillon()
    par_id = {g.id: g for g in grilles}
    assert journal.n_lignes == 48 and journal.n_grilles == 23, (journal.n_lignes, journal.n_grilles)
    assert len({g.client for g in grilles}) == 23
    assert journal.unite_taux.startswith("fraction"), journal.unite_taux
    c23 = par_id[identifiant("Client 23", 2023, "equity")]
    assert c23.tranches[-1].maximum is None and c23.plafond_saisi == 200
    assert round(c23.taux_volume, 4) == 0.14, c23.taux_volume
    assert any(a.code == "plafond_depasse" for a in c23.anomalies)
    c7 = par_id[identifiant("Client 7", 2025, "credit ig")]
    assert len(c7.tranches) == 7 and any(a.code == "paliers_sans_effet" for a in c7.anomalies)
    c1 = par_id[identifiant("Client 1", 2024, "oa diversified")]
    assert c1.annee == 2024 and c1.issue == ISSUE_GAGNE and c1.nature == "Privé" and c1.tva == "HT"
    assert par_id[identifiant("Client 2", 2024, "credit ig")].nature == "Public"
    exps = {g.expertise_cle: g.expertise for g in grilles}
    assert exps["global credit"] == "Global credit" and len(exps) == 10, exps
    assert not any(g.exclue for g in grilles)
    print(f"   ✓ 48 lignes, 23 grilles, 10 expertises, dernière tranche prolongée pour Client 23 (0,14 %)")

    print("3. Un vrai classeur se branche : en-têtes, titres, types mixtes, unités")
    with tempfile.TemporaryDirectory() as d:
        brut = echantillon()
        chemin = Path(d) / "grilles.xlsx"
        with pd.ExcelWriter(chemin) as w:
            pd.DataFrame([["Grilles proposées — export"]]).to_excel(w, sheet_name="Notes", index=False, header=False)
            # Deux lignes de titre au-dessus du tableau, comme souvent.
            titre = pd.DataFrame([["Grilles tarifaires"], [None]])
            titre.to_excel(w, sheet_name="Grilles", index=False, header=False)
            brut.to_excel(w, sheet_name="Grilles", index=False, startrow=2)
        g2, j2 = lire_classeur(chemin)
        assert j2.onglet == "Grilles" and j2.ligne_entetes == 3, (j2.onglet, j2.ligne_entetes)
        assert [(g.id, [asdict(t) for t in g.tranches], g.volume) for g in g2] == \
               [(g.id, [asdict(t) for t in g.tranches], g.volume) for g in grilles]
        # En-têtes renommés, taux en pour cent écrits en texte, CSV à points-virgules.
        autre = brut.rename(columns={"Quantite_Minimum": "Borne basse", "Quantite_Maximum": "Borne haute",
                                     "Frais_par_seuil": "Taux", "Volume1": "Encours", "Sub_asset_class": "Expertise",
                                     "Client_Prospect": "Statut", "Public_Privé": "Public_Priv"})
        autre["Taux"] = [f"{v * 100:.2f}".replace(".", ",") + " %" for v in autre["Taux"]]
        autre["Borne haute"] = autre["Borne haute"].astype(object)
        autre.loc[autre.index[-1], "Borne haute"] = "illimité"
        csvp = Path(d) / "grilles.csv"
        autre.to_csv(csvp, sep=";", index=False, encoding="cp1252")
        g3, j3 = lire_classeur(csvp)
        assert j3.colonnes["nature"] == "Public_Priv" and j3.unite_taux == "pour cent"
        assert [(g.id, round(g.taux_volume, 9)) for g in g3] == [(g.id, round(g.taux_volume, 9)) for g in grilles]
        try:
            lire_classeur_mauvais = Path(d) / "vide.csv"
            lire_classeur_mauvais.write_text("a;b\n1;2\n", encoding="utf-8")
            lire_classeur(lire_classeur_mauvais)
            raise AssertionError("un classeur sans colonnes de grille doit être refusé")
        except ClasseurInvalide as exc:
            assert "Quantite_Minimum" in str(exc)
    print("   ✓ titre au-dessus, second onglet, en-têtes synonymes ou tronqués, CSV cp1252, taux en texte")

    print("4. Les anomalies sont nommées, jamais corrigées en silence")
    t = pd.DataFrame({
        "client": ["A", "A", "B", "B", "C", "C"], "minimum": [0, 50, 0, 40, 10, 50],
        "maximum": [50, 100, 60, 100, 50, 80], "taux": [0.2, 0.1, 0.2, 0.1, 0.2, 0.3],
        "volume": [80, 90, 70, 70, 40, 40], "annee": [2024] * 6, "expertise": ["X"] * 6,
        "issue": ["gagné"] * 6, "nature": ["privé"] * 6, "tva": ["HT"] * 6})
    g4, _ = construire(t, Journal())
    codes = {g.client: {a.code for a in g.anomalies} for g in g4}
    assert "volume_variable" in codes["A"]
    assert "chevauchement" in codes["B"] and next(g for g in g4 if g.client == "B").exclue
    assert {"debut", "progressive"} <= codes["C"]
    print("   ✓ chevauchement exclu des fourchettes, encours variable, début décalé, grille progressive")

    print("5. Les libellés clients viennent d'un fichier, sans toucher au code")
    global FICHIER_CLIENTS, FICHIER_RATTACHEMENTS, DOSSIER
    sauve = (FICHIER_CLIENTS, FICHIER_RATTACHEMENTS, DOSSIER)
    with tempfile.TemporaryDirectory() as d:
        DOSSIER = Path(d)
        FICHIER_CLIENTS, FICHIER_RATTACHEMENTS = DOSSIER / "c.csv", DOSSIER / "r.json"
        ecrire_libelles({"Client 7": "Caisse Alpha"}, [g.client for g in grilles])
        texte = FICHIER_CLIENTS.read_text(encoding="utf-8-sig")
        assert texte.splitlines()[0] == "client;libelle" and len(texte.splitlines()) == 24
        assert texte.splitlines()[1].startswith("Client 1;") and texte.splitlines()[10].startswith("Client 10;")
        FICHIER_CLIENTS.write_text("Client,Libellé\nClient 3,Fonds Bêta\nClient 99,Inconnu\n", encoding="cp1252")
        assert libelles_clients() == {"Client 3": "Fonds Bêta", "Client 99": "Inconnu"}
        ecrire_rattachement(c7.id, "42")
        assert rattachements() == {c7.id: "42"}
        ecrire_rattachement(c7.id, None)
        assert rattachements() == {}
    FICHIER_CLIENTS, FICHIER_RATTACHEMENTS, DOSSIER = sauve
    print("   ✓ correspondance en CSV (virgule ou point-virgule, UTF-8 ou cp1252), rattachements réversibles")

    print("6. Une offre se croise avec le classeur d'activité")
    activite, _ = core.load_data(use_fake=True)
    rfp = activite[activite["est_rfp"]]

    def respecte(res: dict[str, Any], annee: int, sous_classe: str) -> bool:
        _, ecart, famille = NIVEAUX_CANDIDATS[res["niveau"]]
        return all(abs(c["annee"] - annee) <= ecart and (not famille or c["sous_classe_actifs"] == sous_classe)
                   for c in res["candidats"])

    # Le cercle le plus étroit qui trouve quelque chose, et ses contraintes tenues.
    res = candidats(c7, activite)
    assert res["candidats"] and respecte(res, 2025, "Crédit investment grade"), res["libelle"]
    assert res["candidats"] == sorted(res["candidats"], key=lambda c: -c["score"])
    # Une famille présente l'année même : le premier cercle suffit.
    annee, n = max(rfp[rfp["sous_classe_actifs"] == "Crédit global"].groupby("annee").size().items(),
                   key=lambda kv: kv[1])
    offre = Grille(identifiant("Test", int(annee), "global credit"), "Test", int(annee), "Global credit",
                   "global credit", ISSUE_GAGNE, "Privé", "HT", 50.0, None, [Tranche(0, None, 0.2)], None)
    res0 = candidats(offre, activite)
    assert res0["niveau"] == 0 and len(res0["candidats"]) == min(8, n) and respecte(res0, int(annee), "Crédit global")
    assert candidats(offre, activite, niveau=3)["niveau"] == 3
    ctx = contexte_activite(offre, activite)
    assert ctx and ctx["n"] == n
    cible = activite.loc[res0["candidats"][0]["id"]]
    idx, mode = dossier_rattache(offre, activite, str(cible["client"]))
    assert mode == "libellé" and activite.loc[idx, "annee"] == annee
    assert criteres_activite("oa gsm etf") == RAPPROCHEMENT_PREFIXE_OA
    print(f"   ✓ Client 7 : « {res['libelle']} » ; Global credit {annee} : {n} dossiers au premier cercle, "
          f"rattachement par libellé")

    print("7. Le calcul JavaScript est le même")
    ok, message = _parite_js(grilles)
    assert ok, message
    print(f"   ✓ {message}")
    print("\nTous les contrôles sont passés.")


if __name__ == "__main__":
    _auto_test()
