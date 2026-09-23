# =============================================================================
#  server.py — API et service de l’interface « RFP & Due Diligence »
# -----------------------------------------------------------------------------
#  Lancement :  python server.py            →  http://localhost:8000
#               uvicorn server:app --reload  (développement)
#
#  Ce fichier ne contient AUCUN calcul métier. Il expose core.py : un chiffre
#  servi ici est un chiffre calculé là-bas, le même que dans le rapport.
#
#  Routes :
#    GET  /                          l’application (static/index.html)
#    GET  /api/meta                  source, dimensions, valeurs, périodes, marque
#    GET  /api/analyse               KPI, constats, carnet, blocs (figures + tableaux)
#    GET  /api/dossiers              liste filtrée, recherche plein texte, tri, pages
#    GET  /api/dossiers/{id}         un dossier
#    GET  /api/rapport               rapport HTML autonome sur le périmètre courant
#    GET  /api/donnees               état du branchement, fichiers présents
#    POST /api/donnees/fichier       dépôt d’un classeur dans data/
#    GET  /api/donnees/apercu        colonnes, correspondance proposée, premières lignes
#    POST /api/donnees/activer       écrit data/branchement.json et recharge
#    POST /api/donnees/demo          revient aux données de démonstration
#    GET  /api/tarif                 offres passées, expertises, grille type (simulateur)
#    GET  /api/tarif/offres/{id}     fiche d’une offre, croisée avec l’activité
#    GET  /api/tarif/offres/{id}/candidats   dossiers d’activité candidats au rattachement
#    POST /api/tarif/offres/{id}/rattachement  rattache (ou détache) un dossier
#    POST /api/tarif/libelles        libellé réel d’un client anonymisé
#    GET  /api/tarif/correspondance.csv   la correspondance des clients, à remplir
#    POST /api/tarif/correspondance  dépôt d’une correspondance (CSV ou classeur)
#    GET  /api/tarif/donnees         état du classeur tarifaire branché
#    POST /api/tarif/donnees/fichier dépôt d’un classeur de grilles dans data/tarification/
#    POST /api/tarif/donnees/activer branche ce classeur
#    POST /api/tarif/donnees/demo    revient à l’échantillon de démonstration
#    GET  /vendor/plotly.min.js      Plotly, servi depuis le paquet Python (hors ligne)
# =============================================================================
from __future__ import annotations

import datetime as dt
import json
import math
import re
import threading
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import core
import tarification

RACINE = Path(__file__).resolve().parent
DOSSIER_STATIC = RACINE / "static"

app = FastAPI(title=f"{core.MARQUE_PRODUIT} — {core.MARQUE_NOM}", docs_url=None, redoc_url=None)


# =============================================================================
#  ÉTAT — la table chargée, son journal, et un cache d’analyses
# =============================================================================
class Etat:
    """La table enrichie et son journal, rechargés quand le branchement change.
    `version` invalide le cache d’analyses."""

    def __init__(self) -> None:
        self._verrou = threading.Lock()
        self.df: pd.DataFrame = pd.DataFrame()
        self.rapport: core.LoadReport | None = None
        self.erreur: str | None = None
        self.version = 0
        self._cache: OrderedDict[str, core.Analysis] = OrderedDict()
        self.recharger()

    def recharger(self) -> None:
        with self._verrou:
            try:
                self.df, self.rapport = core.load_data()
                self.erreur = None
            except core.DonneesInvalides as exc:
                self.df, self.rapport, self.erreur = pd.DataFrame(), None, str(exc)
            except Exception as exc:                          # pragma: no cover
                self.df, self.rapport = pd.DataFrame(), None
                self.erreur = f"Erreur inattendue au chargement : {type(exc).__name__} — {exc}"
            self.version += 1
            self._cache.clear()

    def analyse(self, filtres: core.Filters, options: dict[str, Any]) -> core.Analysis:
        cle = json.dumps({"v": self.version, "min": str(filtres.date_min),
                          "max": str(filtres.date_max), "dims": filtres.dims,
                          "opt": options}, sort_keys=True, default=str)
        with self._verrou:
            if cle in self._cache:
                self._cache.move_to_end(cle)
                return self._cache[cle]
        sel = core.filter_data(self.df, filtres)
        prec = core.filter_data(self.df, filtres.periode_precedente())
        analyse = core.build_analysis(sel, filtres, self.rapport, prec, options=options,
                                      df_total=self.df)
        with self._verrou:
            self._cache[cle] = analyse
            while len(self._cache) > 24:
                self._cache.popitem(last=False)
        return analyse


ETAT = Etat()


def _exiger_donnees() -> None:
    if ETAT.df.empty:
        raise HTTPException(status_code=409, detail=ETAT.erreur
                            or "Aucune ligne exploitable dans la source branchée.")


# =============================================================================
#  SÉRIALISATION — JSON propre : NaN → null, dates → ISO, numpy → Python
# =============================================================================
# La sérialisation, les colonnes de dossier et le carnet détaillé vivent dans
# core.py : l’écran et le rapport HTML consomment le même calcul.
_propre = core.valeur_json
_dossiers = core.dossiers_json
COLONNES_DOSSIER = core.COLONNES_DOSSIER
LIBELLES_DOSSIER = core.LIBELLES_DOSSIER


def _tableau(tableau: pd.DataFrame) -> dict[str, Any]:
    if tableau is None or tableau.empty:
        return {"colonnes": [], "lignes": []}
    return {"colonnes": [str(c) for c in tableau.columns],
            "lignes": [[_propre(v) for v in ligne]
                       for ligne in tableau.itertuples(index=False, name=None)]}


def _figure(bloc: core.Block) -> dict[str, Any] | None:
    if bloc.figure is None:
        return None
    return json.loads(bloc.figure.to_json())


# =============================================================================
#  PÉRIMÈTRE — des paramètres d’URL aux filtres du moteur
# =============================================================================
PERIODES_GLISSANTES = {"12m": 12, "24m": 24, "36m": 36}


def _bornes_donnees() -> tuple[dt.date, dt.date]:
    serie = ETAT.df["date_reception"]
    return serie.min().date(), serie.max().date()


def _periodes_disponibles() -> list[dict[str, str]]:
    if ETAT.df.empty:
        return []
    d_min, d_max = _bornes_donnees()
    # Chaque exercice présent dans les données se choisit. Les trois derniers
    # sont nommés en toutes lettres et restent sous la main ; les millésimes
    # plus anciens passent dans un menu, sinon le bandeau tient sur deux lignes.
    annees = list(range(d_max.year, d_min.year - 1, -1))
    return ([{"cle": "12m", "libelle": "12 derniers mois", "groupe": "glissante"},
             {"cle": "24m", "libelle": "24 derniers mois", "groupe": "glissante"},
             {"cle": "36m", "libelle": "36 derniers mois", "groupe": "glissante"}]
            + [{"cle": str(a), "libelle": f"Exercice {a}" if i < 3 else str(a),
                "groupe": "exercice" if i < 3 else "millesime"}
               for i, a in enumerate(annees)]
            + [{"cle": "tout", "libelle": "Tout l’historique", "groupe": "tout"}])


def _bornes_periode(cle: str, date_min: str | None, date_max: str | None
                    ) -> tuple[dt.date, dt.date]:
    d_min, d_max = _bornes_donnees()
    if cle == "perso":
        debut = dt.date.fromisoformat(date_min) if date_min else d_min
        fin = dt.date.fromisoformat(date_max) if date_max else d_max
        return max(d_min, debut), min(d_max, fin)
    if cle in PERIODES_GLISSANTES:
        ancre = pd.Timestamp(d_max).replace(day=1) - pd.DateOffset(months=PERIODES_GLISSANTES[cle] - 1)
        return max(d_min, ancre.date()), d_max
    if cle.isdigit() and len(cle) == 4:
        a = int(cle)
        if a < d_min.year or a > d_max.year:
            raise ValueError(f"aucune donnée sur l’exercice {a}")
        return max(d_min, dt.date(a, 1, 1)), min(d_max, dt.date(a, 12, 31))
    return d_min, d_max


def _filtres_depuis(request: Request) -> tuple[core.Filters, str]:
    q = request.query_params
    periode = q.get("periode") or "12m"
    try:
        debut, fin = _bornes_periode(periode, q.get("date_min"), q.get("date_max"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Période invalide : {exc}") from exc
    dims: dict[str, list[str]] = {}
    for champ in core.DIMENSIONS:
        valeurs = [v for v in q.getlist(champ) if v]
        if valeurs and champ in ETAT.df.columns:
            dims[champ] = valeurs
    return core.Filters(date_min=debut, date_max=fin, dims=dims), periode


def _granularite_defaut(filtres: core.Filters) -> str:
    duree = filtres.duree_jours or 0
    if duree > 6 * 365:
        return "annee"
    if duree > 3 * 365:
        return "trimestre"
    return "mois"


# =============================================================================
#  ROUTES — méta
# =============================================================================
def _source() -> dict[str, Any]:
    r = ETAT.rapport
    if r is None:
        return {"mode": "aucune", "libelle": "", "erreur": ETAT.erreur, "alertes": []}
    return {
        "mode": r.mode, "libelle": r.source, "fichier": r.fichier, "onglet": r.onglet,
        "n_lignes_source": r.n_lignes_source, "n_lignes_retenues": r.n_lignes_retenues,
        "colonnes_absentes": [core.DIMENSIONS.get(c, c) for c in r.colonnes_absentes],
        "colonnes_ignorees": r.colonnes_ignorees, "alertes": r.alertes,
        "correspondance": r.correspondance, "erreur": ETAT.erreur,
        "horodatage": r.horodatage.isoformat(timespec="seconds"),
    }


@app.get("/api/meta")
def meta() -> JSONResponse:
    options: dict[str, list[str]] = {}
    if not ETAT.df.empty:
        for champ in core.DIMENSIONS:
            if champ in ETAT.df.columns:
                serie = ETAT.df[champ].dropna()
                valeurs = sorted(str(v) for v in serie.unique().tolist()
                                 if str(v) != core.VALEUR_INCONNUE)
                if len(valeurs) >= 2:
                    options[champ] = valeurs
    dates = {}
    if not ETAT.df.empty:
        d_min, d_max = _bornes_donnees()
        dates = {"min": d_min.isoformat(), "max": d_max.isoformat()}
    return JSONResponse(_propre({
        "produit": core.MARQUE_PRODUIT,
        "marque": {"nom": core.MARQUE_NOM, "activite": core.MARQUE_ACTIVITE,
                   "bleu": core.MARQUE_BLEU, "logo": core.logo_svg("horizontal")},
        "source": _source(),
        "dates": dates,
        "periodes": _periodes_disponibles(),
        "dimensions": core.DIMENSIONS,
        "dimensions_principales": list(core.DIMENSIONS_PRINCIPALES),
        "options": options,
        "sections": core.SECTIONS,
        "parties": {k: {"libelle": v[0], "accroche": v[1]} for k, v in core.PARTIES.items()},
        "partie_par_section": core.PARTIE_PAR_SECTION,
        "compartiments": [{"cle": c, "libelle": l, "sens": s} for c, l, s in core.COMPARTIMENTS],
        "granularites": core.GRANULARITES,
        "libelles_dossier": LIBELLES_DOSSIER,
        "note_censure": core.NOTE_CENSURE,
        "sla": core.sla_libelle(),
        # Les constantes que l’écran doit connaître viennent du moteur, jamais
        # d’une seconde copie en JavaScript.
        "choix_kpi_situation": list(core.CHOIX_KPI_SITUATION),
        "seuil_attente": core.SEUIL_ATTENTE,
        "lignes_compartiment": core.LIGNES_COMPARTIMENT,
        "aujourdhui": dt.date.today().isoformat(),
        "version": ETAT.version,
    }))


# =============================================================================
#  ROUTES — analyse
# =============================================================================
def _repere_historique() -> dict[str, Any]:
    """Les mêmes grandeurs sur TOUT l’historique : ce à quoi se compare le
    périmètre courant. Calculé une fois par version de la source."""
    global _REPERE
    if _REPERE.get("version") == ETAT.version:
        return _REPERE["valeurs"]
    valeurs = core.repere_historique(ETAT.df)
    _REPERE = {"version": ETAT.version, "valeurs": valeurs}
    return valeurs


_REPERE: dict[str, Any] = {}


@app.get("/api/analyse")
def analyse(request: Request,
            granularite: str | None = Query(default=None),
            esg_mode: str = Query(default="part"),
            sections: str | None = Query(default=None),
            figures: int = Query(default=1),
            lignes: int = Query(default=core.LIGNES_COMPARTIMENT, ge=1, le=200)) -> JSONResponse:
    _exiger_donnees()
    filtres, cle_periode = _filtres_depuis(request)
    gran = granularite if granularite in core.GRANULARITES else _granularite_defaut(filtres)
    esg = esg_mode if esg_mode in ("part", "volume") else "part"
    a = ETAT.analyse(filtres, {"granularite": gran, "esg_mode": esg})
    sel = a.df
    voulues = set(s for s in (sections or "").split(",") if s) or None

    blocs = []
    for b in a.blocs:
        if voulues is not None and b.section not in voulues:
            continue
        blocs.append({
            "cle": b.cle, "section": b.section, "titre": b.titre, "accroche": b.accroche,
            "note": b.note, "large": b.large, "dimension": b.dimension,
            "triable": b.triable,
            "figure": _figure(b) if figures else None,
            "tableau": _tableau(b.tableau),
        })

    precedente = filtres.periode_precedente()
    sortie = {
        "filtres": {"periode": cle_periode, "date_min": filtres.date_min, "date_max": filtres.date_max,
                    "dims": filtres.dims, "description": filtres.describe(), "actif": filtres.actif,
                    "revolue": core.periode_revolue(filtres.date_max, _bornes_donnees()[1])},
        "periode_precedente": {"date_min": precedente.date_min, "date_max": precedente.date_max},
        "granularite": gran, "esg_mode": esg,
        "n": int(len(sel)),
        "n_precedent": int(len(core.filter_data(ETAT.df, precedente))),
        "vide": a.vide,
        "kpis": [asdict(k) for k in a.kpis],
        "insights": [asdict(i) for i in a.insights],
        "carnet": core.carnet_detaille(sel, lignes) if not a.vide else None,
        "resume": core.resume_situation(sel, repere=_repere_historique()) if not a.vide else None,
        "sections": [{"cle": c, "libelle": l} for c, l in a.sections],
        "blocs": blocs,
        "erreurs": a.erreurs,
        "genere_le": a.genere_le.isoformat(timespec="seconds"),
    }
    return JSONResponse(_propre(sortie))


# =============================================================================
#  ROUTES — dossiers
# =============================================================================
@app.get("/api/dossiers")
def dossiers(request: Request,
             q: str = Query(default=""),
             tri: str = Query(default="date_reception"),
             ordre: str = Query(default="desc"),
             page: int = Query(default=1, ge=1),
             taille: int = Query(default=100, ge=1, le=1000)) -> JSONResponse:
    _exiger_donnees()
    filtres, _ = _filtres_depuis(request)
    table = core.filter_data(ETAT.df, filtres)
    if q.strip():
        motif = core.cle_recherche(q)
        if motif:
            table = table[core.index_recherche(table).str.contains(motif, regex=False, na=False)]
    n = int(len(table))
    colonne_tri = tri if tri in table.columns else "date_reception"
    if n:
        table = table.sort_values(colonne_tri, ascending=(ordre == "asc"), na_position="last",
                                  kind="mergesort")
    debut = (page - 1) * taille
    lignes = _dossiers(table.iloc[debut:debut + taille])
    encours = float(table["montant_potentiel"].sum(skipna=True)) if n else 0.0
    return JSONResponse(_propre({
        "n": n, "page": page, "taille": taille, "tri": colonne_tri, "ordre": ordre,
        "encours": encours, "lignes": lignes,
        "colonnes": [c for c in COLONNES_DOSSIER if c in ETAT.df.columns],
        "libelles": LIBELLES_DOSSIER,
    }))


@app.get("/api/dossiers/{identifiant}")
def dossier(identifiant: int) -> JSONResponse:
    _exiger_donnees()
    if identifiant not in ETAT.df.index:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    ligne = ETAT.df.loc[[identifiant]]
    (d,) = _dossiers(ligne, [c for c in ETAT.df.columns if c in LIBELLES_DOSSIER])
    # Le même client : ses autres dossiers, pour situer celui-ci.
    client = ligne["client"].iloc[0]
    autres = ETAT.df[(ETAT.df["client"] == client) & (ETAT.df.index != identifiant)]
    d["autres_dossiers_client"] = _dossiers(
        autres.sort_values("date_reception", ascending=False).head(12),
        ["date_reception", "famille", "resultat", "classe_actifs", "fonds",
         "montant_potentiel"])
    d["n_dossiers_client"] = int(len(autres)) + 1
    return JSONResponse(_propre(d))


# =============================================================================
#  ROUTES — rapport
# =============================================================================
@app.get("/api/rapport")
def rapport(request: Request, granularite: str | None = Query(default=None)) -> Response:
    _exiger_donnees()
    import export                                   # import différé : Plotly.js est lourd
    filtres, _ = _filtres_depuis(request)
    gran = granularite if granularite in core.GRANULARITES else _granularite_defaut(filtres)
    a = ETAT.analyse(filtres, {"granularite": gran, "esg_mode": "part"})
    if a.vide:
        raise HTTPException(status_code=409, detail="Aucune donnée sur ce périmètre.")
    html = export.construire_rapport(a)
    nom = f"rfp-due-diligence_{dt.date.today():%Y-%m-%d}.html"
    return Response(content=html, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


# =============================================================================
#  ROUTES — branchement des données
# =============================================================================
def _etat_donnees() -> dict[str, Any]:
    branchement = core.lire_branchement()
    fichiers = []
    for p in core.fichiers_disponibles():
        st = p.stat()
        fichiers.append({"nom": p.name, "taille": st.st_size,
                         "modifie": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
    return {
        "source": _source(),
        "branchement": branchement.to_dict() if branchement else None,
        "fichiers": fichiers,
        "dossier": str(core.DOSSIER_DONNEES),
        "champs": [{"cle": c, "libelle": LIBELLES_DOSSIER.get(c, core.DIMENSIONS.get(c, c)),
                    "attendu": core.COLUMN_MAP[c], "obligatoire": c in core.REQUIRED_FIELDS,
                    "synonymes": core.COLUMN_ALIASES.get(c, [])}
                   for c in core.COLUMN_MAP],
        "demo_forcee": core.USE_FAKE_DATA is True,
    }


@app.get("/api/donnees")
def donnees() -> JSONResponse:
    return JSONResponse(_propre(_etat_donnees()))


NOM_FICHIER_SUR = re.compile(r"[^A-Za-z0-9._ \-éèàùçêâîôûëïüÉÈÀÇ]+")


@app.post("/api/donnees/fichier")
async def deposer(fichier: UploadFile = File(...)) -> JSONResponse:
    nom = Path(fichier.filename or "classeur.xlsx").name
    nom = NOM_FICHIER_SUR.sub("_", nom).strip() or "classeur.xlsx"
    if Path(nom).suffix.lower() not in core.EXTENSIONS_DONNEES:
        raise HTTPException(status_code=415, detail="Formats acceptés : .xlsx, .xlsm, .xls, .csv, .tsv, .txt")
    contenu = await fichier.read()
    if not contenu:
        raise HTTPException(status_code=422, detail="Le fichier est vide.")
    if len(contenu) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (200 Mo au plus).")
    core.DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    chemin = core.DOSSIER_DONNEES / nom
    chemin.write_bytes(contenu)
    try:
        vue = core.apercu(chemin)
    except core.DonneesInvalides as exc:
        chemin.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(_propre({"fichier": nom, "apercu": vue, "etat": _etat_donnees()}))


@app.get("/api/donnees/apercu")
def apercu(fichier: str, onglet: str | None = None, colonnes: str | None = None) -> JSONResponse:
    chemin = core.DOSSIER_DONNEES / Path(fichier).name
    if not chemin.exists():
        raise HTTPException(status_code=404, detail=f"Fichier introuvable dans data/ : « {fichier} ».")
    correspondance = None
    if colonnes:
        try:
            correspondance = {str(k): str(v) for k, v in json.loads(colonnes).items() if v}
        except (json.JSONDecodeError, AttributeError) as exc:
            raise HTTPException(status_code=422, detail="Correspondance illisible.") from exc
    try:
        vue = core.apercu(chemin, onglet or None, correspondance)
    except core.DonneesInvalides as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(_propre(vue))


@app.post("/api/donnees/activer")
async def activer(request: Request) -> JSONResponse:
    corps = await request.json()
    fichier = Path(str(corps.get("fichier") or "")).name
    if not fichier or not (core.DOSSIER_DONNEES / fichier).exists():
        raise HTTPException(status_code=404, detail="Choisir un fichier présent dans data/.")
    onglet = corps.get("onglet") or None
    colonnes = {str(k): str(v) for k, v in (corps.get("colonnes") or {}).items() if v}
    branchement = core.Branchement(fichier=fichier, onglet=onglet, colonnes=colonnes, actif=True)
    # On valide AVANT d’écrire : un branchement qui casse n’est jamais enregistré.
    try:
        df, rapport_charge = core.load_data(path=str(branchement.chemin), sheet=onglet,
                                            correspondance=colonnes)
    except core.DonneesInvalides as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if df.empty:
        raise HTTPException(status_code=422, detail="Aucune ligne exploitable après normalisation : "
                            "vérifier la colonne de date de réception.")
    core.ecrire_branchement(branchement)
    ETAT.recharger()
    return JSONResponse(_propre({"etat": _etat_donnees(), "n_lignes": int(len(df)),
                                 "alertes": rapport_charge.alertes}))


@app.post("/api/donnees/demo")
def revenir_demo() -> JSONResponse:
    b = core.lire_branchement()
    if b is not None:
        b.actif = False
        core.ecrire_branchement(b)
    # Un fichier seul dans data/ serait relu automatiquement : le renvoi à la
    # démonstration est donc explicite pour la session en cours.
    core.USE_FAKE_DATA = True
    ETAT.recharger()
    return JSONResponse(_propre({"etat": _etat_donnees()}))


@app.post("/api/donnees/reprendre")
def reprendre_fichier() -> JSONResponse:
    """Repasse en mode automatique : classeur branché s’il existe."""
    core.USE_FAKE_DATA = None
    b = core.lire_branchement()
    if b is not None and not b.actif:
        b.actif = True
        core.ecrire_branchement(b)
    ETAT.recharger()
    return JSONResponse(_propre({"etat": _etat_donnees()}))


# =============================================================================
#  TARIFICATION — le simulateur de prix des appels d’offres
# -----------------------------------------------------------------------------
#  Le calcul vit dans tarification.py (et, à l’identique, dans static/js/tarif.js
#  pour l’édition en direct). Ici, on ne fait que servir et persister.
# =============================================================================
class EtatTarif:
    """Les grilles du classeur tarifaire et leur journal."""

    def __init__(self) -> None:
        self._verrou = threading.Lock()
        self.grilles: list[tarification.Grille] = []
        self.journal = tarification.Journal()
        self.recharger()

    def recharger(self) -> None:
        with self._verrou:
            self.grilles, self.journal = tarification.charger()

    def grille(self, gid: str) -> tarification.Grille:
        for g in self.grilles:
            if g.id == gid:
                return g
        raise HTTPException(status_code=404, detail="Offre introuvable.")

    @property
    def clients(self) -> set[str]:
        return {g.client for g in self.grilles}


TARIF = EtatTarif()


def _offre(g: tarification.Grille, libelles: dict[str, str],
           index: dict[str, int], liens: dict[str, str]) -> dict[str, Any]:
    d = g.to_dict()
    d["libelle"] = libelles.get(g.client) or g.client
    d["libelle_edite"] = g.client in libelles
    idx, mode = tarification.dossier_rattache(g, ETAT.df, libelles.get(g.client), index, liens)
    d["rattachement"] = None if idx is None else {
        "id": int(idx), "mode": mode, "cle": tarification.cle_dossier(ETAT.df.loc[idx]),
        "client": str(ETAT.df.loc[idx, "client"]),
        "numero": _propre(ETAT.df.loc[idx].get("numero"))}
    return d


def _contexte_offres() -> tuple[dict[str, str], dict[str, int], dict[str, str]]:
    libelles = tarification.libelles_clients()
    liens = tarification.rattachements()
    index = tarification.index_dossiers(ETAT.df) if liens else {}
    return libelles, index, liens


@app.get("/api/tarif")
def tarif() -> JSONResponse:
    libelles, index, liens = _contexte_offres()
    expertises: dict[str, dict[str, Any]] = {}
    for g in TARIF.grilles:
        e = expertises.setdefault(g.expertise_cle, {"cle": g.expertise_cle, "libelle": g.expertise,
                                                    "n": 0, "n_total": 0})
        e["n_total"] += 1
        e["n"] += 0 if g.exclue else 1
    return JSONResponse(_propre({
        "source": TARIF.journal.to_dict(),
        "offres": [_offre(g, libelles, index, liens) for g in TARIF.grilles],
        "expertises": sorted(expertises.values(), key=lambda e: (-e["n"], e["libelle"])),
        "annees": sorted({g.annee for g in TARIF.grilles if g.annee}),
        "issues": [i for i in tarification.ISSUES if any(g.issue == i for g in TARIF.grilles)],
        "natures": sorted({g.nature for g in TARIF.grilles if g.nature}),
        "grille_type": [{"minimum": a, "maximum": b, "taux": r} for a, b, r in tarification.GRILLE_TYPE],
        "seuils_reference": list(tarification.SEUILS_REFERENCE),
        "correspondance": {"fichier": tarification.FICHIER_CLIENTS.name,
                           "present": tarification.FICHIER_CLIENTS.exists(),
                           "n_libelles": sum(1 for c in TARIF.clients if c in libelles)},
        "activite": {"disponible": not ETAT.df.empty,
                     "source": ETAT.rapport.source if ETAT.rapport else None,
                     "mode": ETAT.rapport.mode if ETAT.rapport else None},
    }))


@app.get("/api/tarif/offres/{gid}")
def fiche_offre(gid: str) -> JSONResponse:
    g = TARIF.grille(gid)
    libelles, _, liens = _contexte_offres()
    index = tarification.index_dossiers(ETAT.df)
    d = _offre(g, libelles, index, liens)
    d["dossier"] = None
    if d["rattachement"]:
        idx = d["rattachement"]["id"]
        (d["dossier"],) = _dossiers(ETAT.df.loc[[idx]], [c for c in ETAT.df.columns if c in LIBELLES_DOSSIER])
    d["contexte"] = tarification.contexte_activite(g, ETAT.df)
    d["autres_offres_client"] = [
        {"id": o.id, "annee": o.annee, "expertise": o.expertise, "issue": o.issue,
         "volume": o.volume, "taux_volume": o.taux_volume}
        for o in TARIF.grilles if o.client == g.client and o.id != g.id]
    return JSONResponse(_propre(d))


@app.get("/api/tarif/offres/{gid}/candidats")
def candidats_offre(gid: str, niveau: int | None = Query(default=None, ge=0, le=3)) -> JSONResponse:
    g = TARIF.grille(gid)
    return JSONResponse(_propre(tarification.candidats(g, ETAT.df, niveau)))


@app.post("/api/tarif/offres/{gid}/rattachement")
async def rattacher_offre(gid: str, request: Request) -> JSONResponse:
    g = TARIF.grille(gid)
    corps = await request.json()
    cle = str(corps.get("dossier") or "").strip() or None
    if cle is not None and cle not in tarification.index_dossiers(ETAT.df):
        raise HTTPException(status_code=404, detail="Dossier d’activité introuvable.")
    tarification.ecrire_rattachement(g.id, cle)
    return fiche_offre(gid)


@app.post("/api/tarif/libelles")
async def libelle_client(request: Request) -> JSONResponse:
    corps = await request.json()
    client = str(corps.get("client") or "").strip()
    libelle = re.sub(r"\s+", " ", str(corps.get("libelle") or "")).strip()
    if client not in TARIF.clients:
        raise HTTPException(status_code=404, detail="Client inconnu du classeur tarifaire.")
    if len(libelle) > 120:
        raise HTTPException(status_code=422, detail="Libellé trop long (120 caractères au plus).")
    libelles = tarification.libelles_clients()
    if libelle and libelle != client:
        libelles[client] = libelle
    else:
        libelles.pop(client, None)
    tarification.ecrire_libelles(libelles, TARIF.clients)
    return JSONResponse({"client": client, "libelle": libelles.get(client, client),
                         "libelle_edite": client in libelles})


@app.get("/api/tarif/correspondance.csv")
def correspondance_csv() -> Response:
    return Response(content=tarification.csv_correspondance(TARIF.clients),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="correspondance_clients.csv"'})


@app.post("/api/tarif/correspondance")
async def deposer_correspondance(fichier: UploadFile = File(...)) -> JSONResponse:
    suffixe = Path(fichier.filename or "correspondance.csv").suffix.lower()
    if suffixe not in tarification.EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formats acceptés : .csv, .txt, .xlsx, .xlsm, .xls")
    contenu = await fichier.read()
    if not contenu or len(contenu) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Fichier vide ou trop volumineux (5 Mo au plus).")
    tarification.DOSSIER.mkdir(parents=True, exist_ok=True)
    temporaire = tarification.DOSSIER / f".depot{suffixe}"
    temporaire.write_bytes(contenu)
    try:
        libelles = tarification.lire_correspondance(temporaire)
    except tarification.ClasseurInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temporaire.unlink(missing_ok=True)
    tarification.ecrire_libelles(libelles, TARIF.clients)
    connus = sum(1 for c in libelles if c in TARIF.clients)
    return JSONResponse({"n_libelles": connus, "n_inconnus": len(libelles) - connus})


def _etat_tarif() -> dict[str, Any]:
    fichiers = []
    for p in tarification.fichiers_disponibles():
        st = p.stat()
        fichiers.append({"nom": p.name, "taille": st.st_size,
                         "modifie": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
    return {
        "source": TARIF.journal.to_dict(),
        "branchement": tarification.lire_branchement(),
        "fichiers": fichiers,
        "dossier": str(tarification.DOSSIER),
        "n_offres": len(TARIF.grilles),
        "n_anomalies": sum(len(g.anomalies) for g in TARIF.grilles),
        "colonnes": [{"cle": c, "attendu": officiel, "synonymes": list(syn),
                      "obligatoire": c in tarification.OBLIGATOIRES}
                     for c, (officiel, syn) in tarification.COLONNES.items()],
    }


@app.get("/api/tarif/donnees")
def donnees_tarif() -> JSONResponse:
    return JSONResponse(_propre(_etat_tarif()))


@app.post("/api/tarif/donnees/fichier")
async def deposer_tarif(fichier: UploadFile = File(...)) -> JSONResponse:
    nom = NOM_FICHIER_SUR.sub("_", Path(fichier.filename or "grilles.xlsx").name).strip() or "grilles.xlsx"
    if Path(nom).suffix.lower() not in tarification.EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formats acceptés : .xlsx, .xlsm, .xls, .csv, .tsv, .txt")
    if nom in (tarification.FICHIER_CLIENTS.name, tarification.FICHIER_EXPERTISES.name):
        raise HTTPException(status_code=422, detail="Ce nom est réservé aux fichiers de correspondance.")
    contenu = await fichier.read()
    if not contenu:
        raise HTTPException(status_code=422, detail="Le fichier est vide.")
    if len(contenu) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (50 Mo au plus).")
    tarification.DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = tarification.DOSSIER / nom
    chemin.write_bytes(contenu)
    try:
        grilles, journal = tarification.lire_classeur(chemin)
    except tarification.ClasseurInvalide as exc:
        chemin.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(_propre({
        "fichier": nom, "journal": journal.to_dict(),
        "apercu": [{"client": g.client, "annee": g.annee, "expertise": g.expertise, "issue": g.issue,
                    "volume": g.volume, "n_tranches": len(g.tranches), "taux_volume": g.taux_volume,
                    "anomalies": [a.texte for a in g.anomalies]} for g in grilles[:12]],
        "n_anomalies": sum(len(g.anomalies) for g in grilles),
        "n_exclues": sum(1 for g in grilles if g.exclue),
        "etat": _etat_tarif()}))


@app.post("/api/tarif/donnees/activer")
async def activer_tarif(request: Request) -> JSONResponse:
    corps = await request.json()
    fichier = Path(str(corps.get("fichier") or "")).name
    chemin = tarification.DOSSIER / fichier
    if not fichier or not chemin.exists():
        raise HTTPException(status_code=404, detail="Choisir un fichier présent dans data/tarification/.")
    onglet = corps.get("onglet") or None
    # On valide AVANT d’écrire : un branchement qui casse n’est jamais enregistré.
    try:
        grilles, _ = tarification.lire_classeur(chemin, onglet)
    except tarification.ClasseurInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tarification.ecrire_branchement({"fichier": fichier, "onglet": onglet, "actif": True,
                                     "active_le": dt.datetime.now().isoformat(timespec="minutes")})
    TARIF.recharger()
    return JSONResponse(_propre({"etat": _etat_tarif(), "n_offres": len(grilles)}))


@app.post("/api/tarif/donnees/demo")
def tarif_demo() -> JSONResponse:
    b = tarification.lire_branchement() or {}
    b["actif"] = False
    tarification.ecrire_branchement(b)
    TARIF.recharger()
    return JSONResponse(_propre({"etat": _etat_tarif()}))


# =============================================================================
#  FICHIERS — application, marque, Plotly hors ligne
# =============================================================================
@app.get("/vendor/plotly.min.js")
def plotly_js() -> Response:
    import export
    return Response(content=export.bibliotheque_plotly(), media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/jetons.css")
def jetons_css() -> Response:
    """Les polices et les jetons du thème, émis par core.py.

    L’écran et le rapport lisent le même bloc : une couleur ne peut pas
    diverger entre les deux surfaces.
    """
    css = core.police_css() + core.jetons_css(":root")
    return Response(content=css, media_type="text/css; charset=utf-8",
                    headers={"Cache-Control": "no-cache"})


@app.get("/")
def index() -> HTMLResponse:
    fichier = DOSSIER_STATIC / "index.html"
    if not fichier.exists():
        return HTMLResponse("<p>static/index.html manquant.</p>", status_code=500)
    return HTMLResponse(fichier.read_text(encoding="utf-8"))


@app.get("/favicon.svg")
def favicon() -> Response:
    """L’emblème officiel s’il a été déposé dans assets/ ; rien sinon."""
    svg = core.logo_svg("embleme")
    if not svg:
        return Response(status_code=204)
    return Response(content=svg, media_type="image/svg+xml")


if (RACINE / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(RACINE / "assets")), name="assets")
if DOSSIER_STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(DOSSIER_STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
