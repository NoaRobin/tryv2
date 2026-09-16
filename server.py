# =============================================================================
#  server.py — API et service de l'interface « RFP & Due Diligence »
# -----------------------------------------------------------------------------
#  Lancement :  python server.py            →  http://localhost:8000
#               uvicorn server:app --reload  (développement)
#
#  Ce fichier ne contient AUCUN calcul métier. Il expose core.py : un chiffre
#  servi ici est un chiffre calculé là-bas, le même que dans le rapport.
#
#  Routes :
#    GET  /                          l'application (static/index.html)
#    GET  /api/meta                  source, dimensions, valeurs, périodes, marque
#    GET  /api/analyse               KPI, constats, carnet, blocs (figures + tableaux)
#    GET  /api/dossiers              liste filtrée, recherche plein texte, tri, pages
#    GET  /api/dossiers/{id}         un dossier
#    GET  /api/rapport               rapport HTML autonome sur le périmètre courant
#    GET  /api/donnees               état du branchement, fichiers présents
#    POST /api/donnees/fichier       dépôt d'un classeur dans data/
#    GET  /api/donnees/apercu        colonnes, correspondance proposée, premières lignes
#    POST /api/donnees/activer       écrit data/branchement.json et recharge
#    POST /api/donnees/demo          revient aux données de démonstration
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

RACINE = Path(__file__).resolve().parent
DOSSIER_STATIC = RACINE / "static"

app = FastAPI(title=f"{core.MARQUE_PRODUIT} — {core.MARQUE_NOM}", docs_url=None, redoc_url=None)


# =============================================================================
#  ÉTAT — la table chargée, son journal, et un cache d'analyses
# =============================================================================
class Etat:
    """La table enrichie et son journal, rechargés quand le branchement change.
    `version` invalide le cache d'analyses."""

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
        analyse = core.build_analysis(sel, filtres, self.rapport, prec, options=options)
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
def _propre(v: Any) -> Any:
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
        return [_propre(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _propre(x) for k, x in v.items()}
    if isinstance(v, np.ndarray):
        return [_propre(x) for x in v.tolist()]
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


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


COLONNES_DOSSIER = [
    "date_reception", "date_envoi", "famille", "type_demande", "statut", "resultat",
    "client", "consultant", "type_client", "pays", "fonds", "classe_actifs",
    "sous_classe_actifs", "forme_juridique", "expertise", "analyste", "langue",
    "nb_questions", "part_esg", "bande_esg", "montant_potentiel", "delai_calendaire",
    "delai_ouvre", "sla_cible", "dans_sla", "anciennete_ouvree", "en_retard", "aum_gagne",
]
LIBELLES_DOSSIER = {
    "date_reception": "Réception", "date_envoi": "Envoi", "famille": "Famille",
    "type_demande": "Type", "statut": "Statut", "resultat": "Résultat", "client": "Client",
    "consultant": "Consultant", "type_client": "Type de client", "pays": "Pays",
    "fonds": "Fonds de référence", "classe_actifs": "Classe d'actifs",
    "sous_classe_actifs": "Sous-classe", "forme_juridique": "Forme juridique",
    "expertise": "Expertise", "analyste": "Analyste", "langue": "Langue",
    "nb_questions": "Questions", "part_esg": "Part ESG", "bande_esg": "Tranche ESG",
    "montant_potentiel": "Encours (M€)", "delai_calendaire": "Délai (j)",
    "delai_ouvre": "Délai (j ouvrés)", "sla_cible": "Délai cible (j ouvrés)",
    "dans_sla": "Dans le délai cible", "anciennete_ouvree": "Ancienneté (j ouvrés)",
    "en_retard": "En retard", "aum_gagne": "Encours remporté (M€)",
    "jours_attente": "Jours d'attente", "jours_chez_nous": "Jours chez nous",
}


def _dossiers(table: pd.DataFrame, colonnes: list[str] | None = None) -> list[dict[str, Any]]:
    """Lignes de dossiers sérialisées, l'identifiant étant l'index de la table
    enrichie (stable tant que la source ne change pas)."""
    if table.empty:
        return []
    cols = [c for c in (colonnes or COLONNES_DOSSIER) if c in table.columns]
    sortie = []
    for idx, ligne in zip(table.index, table[cols].itertuples(index=False, name=None)):
        d = {"id": int(idx)}
        for c, v in zip(cols, ligne):
            d[c] = _propre(v)
        sortie.append(d)
    return sortie


# =============================================================================
#  PÉRIMÈTRE — des paramètres d'URL aux filtres du moteur
# =============================================================================
PERIODES_GLISSANTES = {"12m": 12, "24m": 24, "36m": 36}


def _bornes_donnees() -> tuple[dt.date, dt.date]:
    serie = ETAT.df["date_reception"]
    return serie.min().date(), serie.max().date()


def _periodes_disponibles() -> list[dict[str, str]]:
    if ETAT.df.empty:
        return []
    d_min, d_max = _bornes_donnees()
    annees = list(range(d_max.year, max(d_min.year, d_max.year - 5) - 1, -1))
    return ([{"cle": "12m", "libelle": "12 derniers mois"},
             {"cle": "24m", "libelle": "24 derniers mois"},
             {"cle": "36m", "libelle": "36 derniers mois"}]
            + [{"cle": str(a), "libelle": f"Exercice {a}"} for a in annees]
            + [{"cle": "tout", "libelle": "Tout l'historique"}])


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
                   "bleu": core.MARQUE_BLEU},
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
        "sla": core.sla_libelle(par_famille=True),
        "aujourdhui": dt.date.today().isoformat(),
        "version": ETAT.version,
    }))


# =============================================================================
#  ROUTES — analyse
# =============================================================================
def _carnet(sel: pd.DataFrame, n_lignes: int) -> dict[str, Any]:
    livre = core.carnet(sel)
    colonnes = ["client", "consultant", "pays", "classe_actifs", "sous_classe_actifs",
                "fonds", "expertise", "analyste", "statut", "resultat", "montant_potentiel",
                "date_reception", "date_envoi", "jours_attente", "jours_chez_nous",
                "anciennete_ouvree", "en_retard", "sla_cible"]
    compartiments = {}
    for cle, libelle, sens in core.COMPARTIMENTS:
        sous = livre.compartiments[cle]
        compartiments[cle] = {
            "libelle": libelle, "sens": sens, "n": livre.n(cle),
            "encours": livre.encours(cle),
            "dossiers": _dossiers(sous.head(n_lignes), colonnes),
        }
    relances = livre.a_relancer.copy()
    for d in (_dossiers(relances.head(n_lignes), colonnes)):
        pass
    return {
        "total": livre.total, "vivants": livre.vivants,
        "compartiments": compartiments,
        "a_relancer": {
            "n": len(relances),
            "encours": float(relances["montant_potentiel"].sum(skipna=True)) if len(relances) else 0.0,
            "dossiers": _dossiers(relances.head(n_lignes), colonnes),
        },
    }


@app.get("/api/analyse")
def analyse(request: Request,
            granularite: str | None = Query(default=None),
            esg_mode: str = Query(default="part"),
            sections: str | None = Query(default=None),
            figures: int = Query(default=1),
            lignes: int = Query(default=8, ge=1, le=200)) -> JSONResponse:
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
            "hors_rapport": b.hors_rapport,
            "figure": _figure(b) if figures else None,
            "tableau": _tableau(b.tableau),
        })

    precedente = filtres.periode_precedente()
    taux, gagnes, tranches, ic = core.taux_succes_rfp(sel)
    sortie = {
        "filtres": {"periode": cle_periode, "date_min": filtres.date_min, "date_max": filtres.date_max,
                    "dims": filtres.dims, "description": filtres.describe(), "actif": filtres.actif},
        "periode_precedente": {"date_min": precedente.date_min, "date_max": precedente.date_max},
        "granularite": gran, "esg_mode": esg,
        "n": int(len(sel)),
        "n_precedent": int(len(core.filter_data(ETAT.df, precedente))),
        "vide": a.vide,
        "kpis": [asdict(k) for k in a.kpis],
        "insights": [asdict(i) for i in a.insights],
        "carnet": _carnet(sel, lignes) if not a.vide else None,
        "resume": {
            "questionnaires": int(len(sel)),
            "dd": core.nb_famille(sel, core.FAMILLE_DD),
            "rfp": core.nb_famille(sel, core.FAMILLE_RFP),
            "taux_succes": taux, "gagnes": gagnes, "tranches": tranches, "ic": list(ic),
            "encours_remporte": core.aum_gagne(sel), "encours_en_jeu": core.aum_en_jeu(sel),
            "delai_dd": core.delai_median(sel, core.FAMILLE_DD),
            "delai_rfp": core.delai_median(sel, core.FAMILLE_RFP),
            "mix_types": {str(k): int(v) for k, v in core.repartition_type(sel).items()},
            "date_min_donnees": sel["date_reception"].min() if len(sel) else None,
            "date_max_donnees": sel["date_reception"].max() if len(sel) else None,
        } if not a.vide else None,
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
             attention: int = Query(default=0),
             tri: str = Query(default="date_reception"),
             ordre: str = Query(default="desc"),
             page: int = Query(default=1, ge=1),
             taille: int = Query(default=100, ge=1, le=1000)) -> JSONResponse:
    _exiger_donnees()
    filtres, _ = _filtres_depuis(request)
    table = core.filter_data(ETAT.df, filtres)
    if attention:
        table = core.dossiers_a_surveiller(table)
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
        ["date_reception", "famille", "type_demande", "resultat", "classe_actifs", "fonds",
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
    # On valide AVANT d'écrire : un branchement qui casse n'est jamais enregistré.
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
    """Repasse en mode automatique : classeur branché s'il existe."""
    core.USE_FAKE_DATA = None
    b = core.lire_branchement()
    if b is not None and not b.actif:
        b.actif = True
        core.ecrire_branchement(b)
    ETAT.recharger()
    return JSONResponse(_propre({"etat": _etat_donnees()}))


# =============================================================================
#  FICHIERS — application, marque, Plotly hors ligne
# =============================================================================
@app.get("/vendor/plotly.min.js")
def plotly_js() -> Response:
    import export
    return Response(content=export.bibliotheque_plotly(), media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/")
def index() -> HTMLResponse:
    fichier = DOSSIER_STATIC / "index.html"
    if not fichier.exists():
        return HTMLResponse("<p>static/index.html manquant.</p>", status_code=500)
    return HTMLResponse(fichier.read_text(encoding="utf-8"))


@app.get("/favicon.svg")
def favicon() -> Response:
    return Response(content=core.logo_svg("embleme"), media_type="image/svg+xml")


if (RACINE / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(RACINE / "assets")), name="assets")
if DOSSIER_STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(DOSSIER_STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
