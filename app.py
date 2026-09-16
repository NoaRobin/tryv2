# =============================================================================
#  app.py — RFP Intelligence : interface
# -----------------------------------------------------------------------------
#  Lancement :  streamlit run app.py     →  http://localhost:8501
#
#  Ce fichier ne contient AUCUN calcul métier. Il assemble : navigation,
#  filtres globaux, mise en page, drill-down, export. Toute métrique vient de
#  core.py — un chiffre affiché ici est un chiffre calculé là-bas.
# =============================================================================
from __future__ import annotations

import datetime as dt
import inspect
import json
from html import escape
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import core

st.set_page_config(
    page_title=f"{core.MARQUE_PRODUIT} — {core.MARQUE_NOM}",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"about": "RFP Intelligence — pilotage de l'activité RFP et due diligence."},
)


# --- Compatibilité des versions de Streamlit ---------------------------------
def _kw_largeur(fonction) -> dict[str, object]:
    """`use_container_width` est déprécié au profit de `width` : on choisit le
    bon mot-clé au lieu de parier sur la version installée."""
    params = inspect.signature(fonction).parameters
    return {"width": "stretch"} if "width" in params else {"use_container_width": True}


KW_PLOT = _kw_largeur(st.plotly_chart)
KW_TABLE = _kw_largeur(st.dataframe)
KW_BOUTON = _kw_largeur(st.button)
SELECTION_DISPONIBLE = "on_select" in inspect.signature(st.plotly_chart).parameters

# Architecture de l'information : chaque page répond à une question de pilotage.
# Le produit est en DEUX parties. « Direction » se lit debout, en trois
# minutes, et suffit à un dirigeant ; « Analyse » répond aux pourquoi et aux
# combien exactement. Deux niveaux de navigation, pas cinq.
PAGES: list[tuple[str, str, str, str]] = [
    # (clé, libellé, partie, sous-titre)
    ("synthese", "Vue d'ensemble", "Direction",
     "La décomposition de l'activité, ce qui a bougé ce trimestre, et ce que "
     "l'effort commercial a rapporté."),
    ("accueil", "Aujourd'hui", "Direction",
     "L'état du carnet à l'instant : qui attend une décision, qui vient d'être "
     "gagné, qui est à relancer."),
    ("activite", "Activité", "Analyse",
     "Volumes reçus, capacité de traitement et délais."),
    ("rfp", "Pipeline RFP", "Analyse",
     "Appels d'offres : flux, résultats et valeur commerciale."),
    ("dd", "Due diligence", "Analyse",
     "Charge de due diligence par expertise et par géographie."),
    ("aum", "Encours & gains", "Analyse",
     "Ce que l'effort commercial rapporte réellement."),
    ("esg", "ESG", "Analyse",
     "Poids de la composante ESG dans les questionnaires."),
    ("insights", "Diagnostic", "Analyse",
     "Constats calculés sur la sélection courante, et analyse des causes."),
    ("explorateur", "Explorateur", "Analyse",
     "Du chiffre agrégé au dossier individuel."),
    ("donnees", "Qualité & export", "Analyse",
     "Journal d'import, définitions et rapport autonome."),
]
LIBELLES_PAGES = {cle: libelle for cle, libelle, _, _ in PAGES}
GROUPES = ["Direction", "Analyse"]

# Indicateurs mis en avant par page — la couche métrique les produit tous, la
# page choisit ceux qui répondent à sa question.
KPIS_PAR_PAGE = {
    "accueil": [],                 # la page « Aujourd'hui » a son propre relevé
    # Vue d'ensemble : quatre indicateurs, pas huit. Le reste est dans Analyse.
    "synthese": ["questionnaires", "rfp", "succes", "aum"],
    "activite": ["questionnaires", "dd", "rfp", "questions",
                 "delai_dd", "delai_rfp", "sla", "esg"],
    "rfp": ["rfp", "rfp_gagnes", "succes", "pipeline", "aum", "delai_rfp"],
    "dd": ["dd", "rfi", "ddq", "delai_dd", "sla", "questions"],
    "aum": ["aum", "rfp_gagnes", "succes", "pipeline"],
    "esg": ["esg", "questionnaires", "dd", "rfp"],
    "insights": [],
    "explorateur": [],
    "donnees": [],
}


# =============================================================================
#  THÈME — appliqué avant toute génération de style
# =============================================================================
THEMES_LISIBLES = {"maison": f"{core.MARQUE_NOM} (sombre)", "sombre": "Sombre neutre",
                   "institutionnel": "Institutionnel", "clair": "Clair (impression)"}

# L'apparence se transporte dans l'URL (`?theme=clair`) : un lien envoyé pour
# impression n'oblige pas le destinataire à chercher le sélecteur.
_theme_demande = (st.query_params.get("theme")
                  or st.session_state.get("theme", core.THEME_DEFAUT))
if _theme_demande not in core.THEMES:
    _theme_demande = core.THEME_DEFAUT
st.session_state["theme"] = _theme_demande
core.appliquer_theme(_theme_demande)
EST_SOMBRE = _theme_demande in ("sombre", "maison")


# Le thème Streamlit (config.toml) est STATIQUE : il ne peut pas suivre le
# sélecteur d'apparence. Ces règles repeignent les surfaces des widgets à partir
# des variables du thème actif — elles s'appliquent donc dans tous les cas.
WIDGETS_CSS = """
/* Streamlit rend ses contrôles avec react-aria (ComboBox) dans les versions
   récentes, avec baseweb dans les précédentes : on couvre les deux plutôt que
   de parier sur la version installée. */
[data-testid="stSidebar"],
[class*="react-aria-ComboBox"] > div,
div[data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input,
[data-testid="stPopoverButton"], [data-testid="stPopoverBody"],
div[data-baseweb="popover"] div, [class*="react-aria-Popover"],
[class*="react-aria-ListBox"], [data-testid="stExpander"] details {
  background-color: var(--surface) !important; color: var(--ink) !important;
  border-color: var(--border) !important; }

/* Le texte des contrôles : valeur choisie, options du menu, libellé de bouton. */
[class*="react-aria-ComboBox"] input, [class*="react-aria-ComboBox"] span,
[class*="react-aria-ListBox"] *, [data-testid="stPopoverButton"] p,
div[data-baseweb="select"] span { color: var(--ink) !important; }

/* Chevrons et croix : encre secondaire, ils ne sont pas du contenu. */
[class*="react-aria-ComboBox"] svg, [data-testid="stPopoverButton"] svg,
div[data-baseweb="select"] svg { color: var(--ink-2) !important; fill: var(--ink-2) !important; }

/* Une modalité retenue est un jeton d'accent atténué, pas un aplat de marque :
   l'encre doit y rester lisible dans les quatre thèmes. */
[data-testid="stMultiSelectTagsContainer"] > div,
[data-testid="stMultiSelectTagsContainer"] > span {
  background-color: color-mix(in srgb, var(--accent) 20%, transparent) !important;
  color: var(--ink) !important; }

/* Survol d'une option de menu. */
[class*="react-aria-ListBox"] [data-focused],
[class*="react-aria-ListBox"] [data-hovered],
div[data-baseweb="popover"] li:hover { background-color: var(--elevation) !important; }

[data-testid="stElementContainer"] .js-plotly-plot .bg { fill: transparent !important; }
label, .stSelectbox label p, .stMultiSelect label p { color: var(--ink-2) !important; }
"""


# Feuille de style : jetons partagés avec core.py, puis le système lui-même.
# Aucune valeur en dur ici — espacements, corps, rayons, ombres et courbes de
# mouvement viennent tous de `core.jetons_css()`.
BASE_CSS = r"""
*,*::before,*::after{box-sizing:border-box}
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{
  background:var(--plane);color:var(--ink);font-family:var(--police);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  font-feature-settings:"cv05","ss01"}

/* Nappe d'ambiance : deux sources très basses, dans les teintes de la maison.
   Fixée, sans pointer-events, sous tout le reste. */
[data-testid="stAppViewContainer"]::before{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background:var(--ambiance)}
[data-testid="stHeader"]{background:transparent}
.block-container{padding:var(--e5) var(--e6) var(--e9);max-width:1680px;
  position:relative;z-index:1}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:var(--rayon-s)}
::selection{background:color-mix(in srgb,var(--accent) 28%,transparent);color:var(--ink)}

/* Barres de défilement : discrètes, accordées au thème. */
*{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--ink) 18%,transparent) transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--ink) 14%,transparent);
  border-radius:99px;border:3px solid transparent;background-clip:content-box}
::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--ink) 26%,transparent);
  background-clip:content-box}

/* ---------------------------------------------------------- mouvement ----- */
@keyframes surgir{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes apparaitre{from{opacity:0}to{opacity:1}}
@keyframes luire{0%{background-position:-460px 0}100%{background-position:460px 0}}
.surgir{animation:surgir var(--moyen) var(--sortie) both}
.surgir-1{animation-delay:40ms}.surgir-2{animation-delay:80ms}
.surgir-3{animation-delay:120ms}.surgir-4{animation-delay:160ms}

/* --------------------------------------------------------- typographie ---- */
.sur-titre{font-size:var(--t-xs);letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.nav-groupe{font-size:var(--t-xs);letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);font-weight:700;margin:0;padding:var(--e5) 0 var(--e3) 2px;
  line-height:1}
[data-testid="stSidebar"] .nav-groupe:first-of-type{padding-top:var(--e4)}
.note-lecture{font-size:var(--t-s);color:var(--muted);border-left:2px solid var(--border);
  padding-left:var(--e3);margin:var(--e4) 0 var(--e1);line-height:1.6;max-width:110ch}

/* ------------------------------------------------------------- en-tête ---- */
.entete{display:flex;align-items:flex-end;gap:var(--e5);padding:0 0 var(--e4);
  margin-bottom:var(--e3);border-bottom:1px solid var(--border);animation:surgir var(--moyen) var(--sortie) both}
.entete__titre{font-size:var(--t-3xl);font-weight:600;letter-spacing:-.032em;
  margin:var(--e2) 0 6px;line-height:1.05;color:var(--ink)}
.entete__sous{font-size:var(--t-m);color:var(--ink-2);max-width:78ch;line-height:1.55}
.entete__meta{margin-left:auto;text-align:right;font-size:var(--t-s);color:var(--muted);
  line-height:1.85;white-space:nowrap}
.entete__meta b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}
.entete__logo{width:52px;height:52px;flex:none;color:var(--accent)}
.entete__logo svg{width:100%;height:100%;display:block}

/* ------------------------------------------------------ filtres actifs ---- */
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:var(--e1) 0 var(--e3)}
.chip{display:inline-flex;align-items:center;gap:7px;font-size:var(--t-s);font-weight:560;
  padding:4px 10px;border-radius:99px;background:color-mix(in srgb,var(--accent) 12%,transparent);
  color:var(--ink);border:1px solid color-mix(in srgb,var(--accent) 24%,transparent)}
.chip b{font-weight:700;color:var(--muted);font-size:9.5px;letter-spacing:.09em;
  text-transform:uppercase}
.chip--vide{background:transparent;border-color:var(--border);color:var(--muted)}

/* ------------------------------------------------------------ exercices --- */
.annees{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
a.annee{display:inline-flex;align-items:baseline;gap:7px;padding:7px 12px;
  border-radius:99px;border:1px solid var(--border);background:var(--surface);
  text-decoration:none;color:var(--ink-2);font-size:var(--t-m);
  transition:border-color var(--rapide) var(--etat),color var(--rapide) var(--etat),
             transform var(--rapide) var(--sortie)}
a.annee:hover{color:var(--ink);border-color:color-mix(in srgb,var(--accent) 50%,transparent);
  transform:translateY(-1px)}
.annee b{font-weight:640;font-variant-numeric:tabular-nums;color:inherit}
.annee__n{font-size:var(--t-xs);color:var(--muted);font-variant-numeric:tabular-nums}
a.annee--actif{background:var(--accent);border-color:var(--accent);color:var(--sur-accent);
  box-shadow:var(--ombre-1)}
.annee--actif .annee__n{color:color-mix(in srgb,var(--sur-accent) 70%,transparent)}

/* ---------------------------------------------------------- indicateurs --- */
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--e3)}
.kpis+.kpis{margin-top:var(--e3)}
@media (max-width:1400px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:1040px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:620px){.kpis{grid-template-columns:1fr}}
a.kpi,div.kpi{display:block;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--rayon);padding:var(--e4) var(--e4) var(--e3);text-decoration:none;
  color:inherit;height:100%;box-shadow:var(--ombre-1);position:relative;overflow:hidden;
  transition:box-shadow var(--moyen) var(--etat),border-color var(--moyen) var(--etat),
             transform var(--moyen) var(--sortie)}
a.kpi::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:radial-gradient(420px 160px at 50% -40%,color-mix(in srgb,var(--accent) 14%,transparent),transparent 70%);
  opacity:0;transition:opacity var(--moyen) var(--etat)}
a.kpi:hover{transform:translateY(-2px);box-shadow:var(--ombre-2);
  border-color:color-mix(in srgb,var(--accent) 42%,transparent)}
a.kpi:hover::after{opacity:1}
.kpi__tete{display:flex;align-items:baseline;gap:var(--e2)}
.kpi__label{font-size:var(--t-xs);letter-spacing:.11em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.kpi__info{margin-left:auto;font-size:var(--t-xs);color:var(--muted);opacity:.45}
.kpi__corps{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--e3);
  margin-top:var(--e2)}
.kpi__valeur{font-size:var(--t-2xl);font-weight:600;letter-spacing:-.022em;line-height:1;
  font-variant-numeric:tabular-nums;color:var(--ink)}
.kpi__bas{display:flex;align-items:center;gap:var(--e2);margin-top:var(--e3);flex-wrap:wrap}
.kpi__detail{font-size:var(--t-xs);color:var(--muted);line-height:1.45}
.puce{display:inline-flex;gap:4px;font-size:var(--t-xs);font-weight:700;padding:3px 8px;
  border-radius:99px;white-space:nowrap;font-variant-numeric:tabular-nums}
.puce--bon{background:color-mix(in srgb,var(--bon) 15%,transparent);color:var(--bon)}
.puce--mauvais{background:color-mix(in srgb,var(--mauvais) 15%,transparent);color:var(--mauvais)}
.puce--neutre{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink-2)}

/* -------------------------------------------------------------- cartes ---- */
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--surface);
  border:1px solid var(--border)!important;border-radius:var(--rayon);
  box-shadow:var(--ombre-1);
  transition:box-shadow var(--moyen) var(--etat),border-color var(--moyen) var(--etat)}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{box-shadow:var(--ombre-2)}
/* Une colonne prend par défaut la largeur de son contenu : un graphique Plotly
   élargirait donc la ligne au-delà de l'écran sur un poste étroit. */
[data-testid="stColumn"]{min-width:0}
[data-testid="stColumn"]>div,
[data-testid="stColumn"]>div>[data-testid="stVerticalBlock"],
[data-testid="stColumn"] div[data-testid="stVerticalBlockBorderWrapper"]{height:100%}
.carte__titre{font-size:var(--t-l);font-weight:620;letter-spacing:-.014em;color:var(--ink)}
.carte__accroche{font-size:var(--t-m);color:var(--ink-2);margin:6px 0 2px;line-height:1.55}
.carte__note{font-size:var(--t-xs);color:var(--muted);line-height:1.55;margin-top:var(--e3);
  padding-top:var(--e3);border-top:1px solid var(--border)}
.carte__clic{font-size:var(--t-xs);color:var(--muted);margin-top:var(--e1)}
.carte--phare div[data-testid="stVerticalBlockBorderWrapper"]{box-shadow:var(--ombre-2)}

/* ------------------------------------------------------------- insights --- */
.alerte{background:color-mix(in srgb,var(--mauvais) 9%,var(--surface));
  border:1px solid color-mix(in srgb,var(--mauvais) 26%,transparent);
  border-left:3px solid var(--mauvais);border-radius:var(--rayon);
  padding:var(--e3) var(--e4);font-size:var(--t-m);color:var(--ink);line-height:1.55}
.insights{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--e3);
  margin-bottom:var(--e1)}
@media (max-width:1180px){.insights{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:700px){.insights{grid-template-columns:1fr}}
a.insight,div.insight{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--rayon);padding:var(--e4);height:100%;text-decoration:none;color:inherit;
  display:flex;flex-direction:column;border-left:3px solid var(--serie1);
  box-shadow:var(--ombre-1);
  transition:transform var(--moyen) var(--sortie),box-shadow var(--moyen) var(--etat),
             border-color var(--moyen) var(--etat)}
a.insight:hover{transform:translateY(-2px);box-shadow:var(--ombre-2);
  border-color:color-mix(in srgb,var(--accent) 40%,transparent);border-left-color:var(--serie1)}
.insight__lien{margin-top:auto;padding-top:var(--e3);font-size:var(--t-s);font-weight:620;
  color:var(--accent)}
.insight--alerte{border-left-color:var(--mauvais)}
.insight--alerte .insight__lien{color:var(--mauvais)}
.insight--positif{border-left-color:var(--bon)}
.insight__texte{font-size:var(--t-l);color:var(--ink);line-height:1.5;font-weight:520;
  letter-spacing:-.008em}
.insight__appui{font-size:var(--t-s);color:var(--muted);margin-top:7px}

/* -------------------------------------------------------- barre latérale -- */
[data-testid="stSidebar"]{background:var(--verre);border-right:1px solid var(--border);
  backdrop-filter:blur(18px) saturate(140%);-webkit-backdrop-filter:blur(18px) saturate(140%)}
[data-testid="stSidebar"] .block-container{padding-top:var(--e4)}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:var(--e1)}
[data-testid="stSidebar"] hr{margin:var(--e4) 0 var(--e3);border-color:var(--border)}
.marque{display:flex;align-items:center;gap:var(--e3);padding:2px 0 var(--e3)}
.marque__logo{width:34px;height:34px;flex:none;color:var(--accent)}
.marque__logo svg{width:100%;height:100%;display:block}
.marque__texte{font-size:var(--t-m);font-weight:640;letter-spacing:-.012em;line-height:1.2;
  color:var(--ink)}
.marque__texte span{display:block;font-size:9px;letter-spacing:.17em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin-top:4px}
.side-info{font-size:var(--t-xs);color:var(--muted);line-height:1.7;margin-top:var(--e3)}
.side-info b{color:var(--ink-2);font-weight:600}

/* Navigation : des lignes, pas des boutons — mais le confort d'un bouton. */
[data-testid="stSidebar"] .stButton button{width:100%;justify-content:flex-start;
  text-align:left;padding:8px 11px;border-radius:var(--rayon-s);font-size:var(--t-m);
  font-weight:520;border:1px solid transparent;background:transparent;color:var(--muted);
  box-shadow:none;transition:background var(--rapide) var(--etat),color var(--rapide) var(--etat),
             padding-left var(--rapide) var(--sortie)}
[data-testid="stSidebar"] .stButton button:hover{
  background:color-mix(in srgb,var(--ink) 7%,transparent);color:var(--ink);padding-left:14px}
[data-testid="stSidebar"] .stButton button[kind="primary"]{
  background:color-mix(in srgb,var(--accent) 13%,transparent);color:var(--accent);
  font-weight:660;border-color:transparent;box-shadow:inset 2px 0 0 var(--accent);
  border-radius:0 var(--rayon-s) var(--rayon-s) 0}
[data-testid="stSidebar"] .stButton button p{font-size:var(--t-m)!important}

/* ------------------------------------------------- boutons et contrôles --- */
[data-testid="stExpander"] details{border:none!important;background:transparent}
[data-testid="stExpander"] summary{font-size:var(--t-s);color:var(--muted);
  transition:color var(--rapide) var(--etat)}
[data-testid="stExpander"] summary:hover{color:var(--ink-2)}
.stDownloadButton button,.block-container .stButton button{border-radius:var(--rayon-s);
  font-size:var(--t-m);font-weight:600;border:1px solid var(--border);
  background:var(--elevation);color:var(--ink);box-shadow:var(--ombre-1);
  transition:transform var(--rapide) var(--sortie),box-shadow var(--rapide) var(--etat)}
.stDownloadButton button:hover,.block-container .stButton button:hover{
  transform:translateY(-1px);box-shadow:var(--ombre-2)}
.stDownloadButton button:active,.block-container .stButton button:active{transform:translateY(0)}
.block-container .stButton button[kind="primary"]{background:var(--accent);
  border-color:var(--accent);color:var(--sur-accent)}
[data-testid="stAlert"],[data-testid="stAlertContainer"]{
  background:color-mix(in srgb,var(--ink) 5%,transparent)!important;
  border:1px solid var(--border);border-radius:var(--rayon);color:var(--ink-2)!important}
[data-testid="stAlert"] p,[data-testid="stAlertContainer"] p{
  font-size:var(--t-m)!important;color:var(--ink-2)!important}
[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:var(--rayon);
  overflow:hidden}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
#MainMenu,footer,[data-testid="stAppDeployButton"]{display:none}

/* Segmented control : une vraie pastille coulissante. */
[data-testid="stSegmentedControl"] button{transition:background var(--rapide) var(--etat),
  color var(--rapide) var(--etat)}

/* ------------------------------------------------------------- squelette -- */
.squelette{border-radius:var(--rayon);background:linear-gradient(90deg,
  color-mix(in srgb,var(--ink) 5%,transparent) 0%,
  color-mix(in srgb,var(--ink) 10%,transparent) 50%,
  color-mix(in srgb,var(--ink) 5%,transparent) 100%);
  background-size:460px 100%;animation:luire 1.25s linear infinite}

/* ---------------------------------------------------------- responsive ---- */
@media (max-width:900px){
  .block-container{padding:var(--e4) var(--e4) var(--e8)}
  .entete{flex-wrap:wrap;gap:var(--e3)}
  .entete__meta{margin-left:0;text-align:left}
  .entete__titre{font-size:var(--t-2xl)}
  .annees{justify-content:flex-start}
}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{transition:none!important;animation:none!important}
}
"""


# Composants propres aux pages de direction : le relevé, le ruban du carnet,
# les registres nommés, la bande de mix.
ACCUEIL_CSS = r"""
.hero{display:flex;align-items:center;gap:var(--e5);padding:0 0 var(--e5);
  border-bottom:1px solid var(--border);margin-bottom:var(--e4);
  animation:surgir var(--moyen) var(--sortie) both}
.hero__logo{width:58px;height:58px;flex:none;color:var(--accent)}
.hero__logo svg{width:100%;height:100%;display:block}
.hero__maison{font-size:var(--t-xs);letter-spacing:.22em;text-transform:uppercase;
  color:var(--or);font-weight:700}
.hero__titre{font-size:var(--t-3xl);font-weight:600;letter-spacing:-.034em;line-height:1.05;
  margin:var(--e2) 0 7px;color:var(--ink)}
.hero__sous{font-size:var(--t-m);color:var(--ink-2);max-width:78ch;line-height:1.55}
.hero__meta{margin-left:auto;text-align:right;font-size:var(--t-s);color:var(--muted);
  line-height:1.9;white-space:nowrap}
.hero__meta b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}

/* Relevé : une seule surface, des filets pour séparer — pas quatre cartes. */
.releve{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:var(--surface);
  border:1px solid var(--border);border-radius:var(--rayon);overflow:hidden;
  box-shadow:var(--ombre-1);animation:surgir var(--moyen) var(--sortie) both;
  animation-delay:40ms}
@media (max-width:1040px){.releve{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:620px){.releve{grid-template-columns:1fr}}
.releve>div{padding:var(--e4) var(--e5);border-left:1px solid var(--border);
  transition:background var(--moyen) var(--etat)}
.releve>div:first-child{border-left:0}
.releve>div:hover{background:var(--elevation)}
.releve__label{font-size:var(--t-xs);letter-spacing:.15em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.releve__valeur{font-size:var(--t-3xl);font-weight:600;letter-spacing:-.034em;line-height:1;
  margin-top:var(--e3);font-variant-numeric:tabular-nums;color:var(--ink)}
.releve__valeur--or{color:var(--or)}
.releve__detail{font-size:var(--t-xs);color:var(--muted);margin-top:var(--e2);line-height:1.5}

/* Le ruban : tout le carnet d'appels d'offres sur une ligne. */
.ruban{display:flex;gap:2px;height:10px;margin-top:var(--e5)}
.ruban i{display:block;border-radius:2px;transition:filter var(--rapide) var(--etat)}
.ruban:hover i{filter:saturate(.55)}
.ruban i:hover{filter:none}
.ruban-legende{display:flex;flex-wrap:wrap;gap:var(--e2) var(--e6);margin-top:var(--e3)}
.ruban-legende div{display:flex;align-items:center;gap:var(--e2);font-size:var(--t-s)}
.ruban-legende i{width:8px;height:8px;border-radius:2px;flex:none}
.ruban-legende em{font-style:normal;font-weight:660;color:var(--ink);
  font-variant-numeric:tabular-nums}
.ruban-legende span{color:var(--muted)}

/* Registres : qui attend, qui est gagné, qui est perdu. */
.registres{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--e3);
  margin-top:var(--e6)}
@media (max-width:1150px){.registres{grid-template-columns:1fr}}
.registre{background:var(--surface);border:1px solid var(--border);border-radius:var(--rayon);
  display:flex;flex-direction:column;overflow:hidden;box-shadow:var(--ombre-1);
  transition:box-shadow var(--moyen) var(--etat)}
.registre:hover{box-shadow:var(--ombre-2)}
.registre__tete{display:flex;align-items:center;gap:var(--e2);padding:var(--e3) var(--e4);
  border-bottom:1px solid var(--border)}
.registre__pastille{width:8px;height:8px;border-radius:2px;flex:none}
.registre__titre{font-size:var(--t-xs);letter-spacing:.15em;text-transform:uppercase;
  font-weight:700;color:var(--ink-2)}
.registre__n{margin-left:auto;font-size:var(--t-m);font-weight:660;color:var(--ink);
  font-variant-numeric:tabular-nums}
.registre__colonnes{display:flex;justify-content:space-between;padding:var(--e2) var(--e4) 7px;
  font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);
  font-weight:700;border-bottom:1px solid color-mix(in srgb,var(--border) 55%,transparent)}
.registre__colonnes+a.ligne{border-top:0}
a.ligne{display:flex;align-items:flex-start;gap:var(--e3);padding:var(--e2) var(--e4);
  text-decoration:none;color:inherit;
  border-top:1px solid color-mix(in srgb,var(--border) 55%,transparent);
  transition:background var(--rapide) var(--etat),padding-left var(--rapide) var(--sortie)}
.registre a.ligne:first-of-type{border-top:0}
a.ligne:hover{background:var(--elevation);padding-left:var(--e5)}
.ligne__nom{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1}
.ligne__nom b{font-size:var(--t-m);font-weight:560;color:var(--ink);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.ligne__meta{font-size:var(--t-xs);color:var(--muted);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.ligne__val{font-size:var(--t-m);font-variant-numeric:tabular-nums;color:var(--ink-2);
  white-space:nowrap;text-align:right;padding-top:1px}
.ligne__val--alerte{color:var(--mauvais);font-weight:660}
.ligne__val em{font-style:normal;display:block;font-size:var(--t-xs);color:var(--muted);
  margin-top:3px}
.registre__pied{margin-top:auto;padding:var(--e3) var(--e4);border-top:1px solid var(--border)}
.registre__pied a{font-size:var(--t-s);font-weight:620;color:var(--accent);text-decoration:none;
  border-bottom:1px solid transparent;transition:border-color var(--rapide) var(--etat)}
.registre__pied a:hover{border-bottom-color:var(--accent)}
.registre__vide{padding:var(--e5) var(--e4);font-size:var(--t-m);color:var(--muted);
  line-height:1.55}
.registre--large{margin-top:var(--e3)}
.registre--large .lignes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
@media (max-width:1150px){.registre--large .lignes{grid-template-columns:1fr}}
.registre--large .lignes>a.ligne:nth-child(2){border-top:0}
.registre--large .lignes>a.ligne:nth-child(odd){
  border-right:1px solid color-mix(in srgb,var(--border) 55%,transparent)}

/* Bande de mix : le détail RFI / DDQ, à l'écran seulement. */
.bande{background:var(--surface);border:1px solid var(--border);border-radius:var(--rayon);
  padding:var(--e4) var(--e5) var(--e5);margin-top:var(--e6);box-shadow:var(--ombre-1)}
.bande__tete{display:flex;align-items:baseline;gap:var(--e3);margin-bottom:var(--e4)}
.bande__titre{font-size:var(--t-xs);letter-spacing:.15em;text-transform:uppercase;
  font-weight:700;color:var(--ink-2)}
.bande__note{margin-left:auto;font-size:var(--t-xs);color:var(--muted)}
.bande__ligne{display:grid;grid-template-columns:130px 1fr 96px;align-items:center;
  gap:var(--e4);padding:6px 0}
.bande__nom{font-size:var(--t-m);color:var(--ink)}
.bande__piste{height:8px;background:color-mix(in srgb,var(--ink) 7%,transparent);
  border-radius:99px;overflow:hidden}
.bande__piste i{display:block;height:100%;border-radius:99px;
  transition:width var(--lent) var(--sortie)}
.bande__val{font-size:var(--t-m);text-align:right;font-variant-numeric:tabular-nums;
  color:var(--ink-2)}
.bande__val em{font-style:normal;color:var(--muted);font-size:var(--t-xs);margin-left:7px}
@media (max-width:700px){.bande__ligne{grid-template-columns:96px 1fr 76px;gap:var(--e3)}}
"""


def feuille_de_style() -> str:
    """La police, les jetons du thème actif, puis le système lui-même."""
    return ("<style>" + core.police_css() + core.jetons_css()
            + BASE_CSS + ACCUEIL_CSS + WIDGETS_CSS + "</style>")


st.markdown(feuille_de_style(), unsafe_allow_html=True)


# =============================================================================
#  PETITS COMPOSANTS
# =============================================================================
FLECHES = {"hausse": "▲", "baisse": "▼", "plat": ""}


def sparkline(valeurs: list[float], largeur: int = 96, hauteur: int = 24) -> str:
    """Mini-tendance en SVG : la forme de la série, sans axes ni promesse de
    précision. Le chiffre exact reste dans le graphique de la page."""
    valeurs = [v for v in valeurs if v == v]
    if len(valeurs) < 4:
        return ""
    mini, maxi = min(valeurs), max(valeurs)
    etendue = (maxi - mini) or 1.0
    pas = largeur / (len(valeurs) - 1)
    points = [(i * pas, hauteur - 2 - (v - mini) / etendue * (hauteur - 5))
              for i, v in enumerate(valeurs)]
    trace = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    fin_x, fin_y = points[-1]
    return (f'<svg width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}" '
            f'aria-hidden="true" style="overflow:visible">'
            f'<polyline points="{trace}" fill="none" stroke="{core.SERIES[0]}" '
            f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" opacity=".75"/>'
            f'<circle cx="{fin_x:.1f}" cy="{fin_y:.1f}" r="2.4" fill="{core.SERIES[0]}"/></svg>')


@st.cache_data(show_spinner=False)
def _logo() -> str:
    return core.logo_svg()


def pluriel(n: int, mot: str, forme: str | None = None) -> str:
    """« 1 dossier », « 7 dossiers » — le produit n'écrit jamais « dossier(s) »."""
    return core.pluriel(n, mot, forme)


def lien(page: str, **parametres: str) -> str:
    """URL interne portant un filtre : c'est ce que consomme `_etat_depuis_url`.
    Chaque ligne cliquable du produit passe par là, donc chaque état est
    partageable par simple copie du lien."""
    suite = "".join(f"&{c}={quote(str(v))}" for c, v in parametres.items())
    return f"?page={page}{suite}"


def marque_html(classe: str) -> str:
    """Le logo de la maison, inline. Vide si `assets/logo.svg` est absent :
    l'écran perd la marque, jamais son contenu."""
    svg = _logo()
    return f"<div class='{classe}'>{svg}</div>" if svg else ""


def carte_kpi(kpi: core.Kpi) -> str:
    """Carte d'indicateur. Cliquable quand elle mène quelque part : le chiffre
    ouvre la page qui l'explique."""
    puce = ""
    if kpi.delta_affichage:
        fleche = FLECHES.get(kpi.delta_direction, "")
        puce = (f"<span class='puce puce--{kpi.delta_sens}'>"
                f"{fleche + ' ' if fleche else ''}{kpi.delta_affichage}</span>")
    corps = (f"<div class='kpi__tete'><span class='kpi__label'>{kpi.libelle}</span>"
             f"<span class='kpi__info' aria-hidden='true'>i</span></div>"
             f"<div class='kpi__corps'><span class='kpi__valeur'>{kpi.affichage}</span>"
             f"{sparkline(kpi.serie)}</div>"
             f"<div class='kpi__bas'>{puce}"
             f"<span class='kpi__detail'>{kpi.detail}</span></div>")
    titre = kpi.aide.replace('"', "'")
    if kpi.cible and kpi.cible in LIBELLES_PAGES:
        return (f"<a class='kpi' href='?page={kpi.cible}' target='_self' title=\"{titre}\">"
                f"{corps}</a>")
    return f"<div class='kpi' title=\"{titre}\">{corps}</div>"


def bandeau_kpis(analyse: core.Analysis, cles: list[str]) -> None:
    par_cle = {k.cle: k for k in analyse.kpis}
    choisis = [par_cle[c] for c in cles if c in par_cle]
    for depart in range(0, len(choisis), 4):
        ligne = choisis[depart:depart + 4]
        st.markdown(f"<div class='kpis'>{''.join(carte_kpi(k) for k in ligne)}</div>",
                    unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _html_animation(nom: str, taille: int, boucle: bool = True) -> str:
    donnees, lecteur = core.animation(nom), core.lecteur_lottie()
    if not donnees or not lecteur:
        return ""
    return (
        f'<div id="a" style="width:{taille}px;height:{taille}px"></div>'
        f"<script>{lecteur}</script><script>"
        "var sobre=window.matchMedia('(prefers-reduced-motion: reduce)').matches;"
        f"var anim=lottie.loadAnimation({{container:document.getElementById('a'),"
        f"renderer:'svg',loop:{str(boucle).lower()},autoplay:!sobre,"
        f"animationData:{json.dumps(donnees, separators=(',', ':'))}}});"
        "if(sobre){anim.goToAndStop(anim.totalFrames-1,true);}</script>")


def animation(nom: str, taille: int, boucle: bool = True) -> None:
    code = _html_animation(nom, taille, boucle)
    if code:
        components.html(code, height=taille + 4, width=taille + 4)


# =============================================================================
#  DONNÉES
# =============================================================================
@st.cache_data(show_spinner="Chargement des données…")
def charger() -> tuple[pd.DataFrame, core.LoadReport]:
    return core.load_data()


def ecran_erreur(message: str) -> None:
    st.markdown("<div class='entete'><div><div class='entete__fil'>Configuration</div>"
                "<div class='entete__titre'>Données inaccessibles</div></div></div>",
                unsafe_allow_html=True)
    st.error(message)
    st.markdown(
        "**Pour brancher le produit sur vos données**, ouvrir `core.py` et modifier le "
        "bloc `[BRANCHEMENT PRINCIPAL]` en tête de fichier :\n\n"
        "1. `DATA_PATH` — chemin du classeur ; 2. `SHEET_NAME` — onglet ; "
        "3. `COLUMN_MAP` — nom réel de chaque colonne (la correspondance ignore casse, "
        "accents et espaces) ; 4. `USE_FAKE_DATA = False`.")
    st.stop()


try:
    df_complet, rapport = charger()
except core.DonneesInvalides as exc:
    ecran_erreur(str(exc))
except Exception as exc:                                    # pragma: no cover
    ecran_erreur(f"Erreur inattendue au chargement : {type(exc).__name__} — {exc}")

if df_complet.empty:
    ecran_erreur("Le fichier ne contient aucune ligne exploitable après normalisation.")

DATE_MIN = df_complet["date_reception"].min().date()
DATE_MAX = df_complet["date_reception"].max().date()
ANNEES = sorted(df_complet["date_reception"].dt.year.unique(), reverse=True)

# Nombre d'exercices proposés dans la bande d'années de la vue d'ensemble.
PROFONDEUR_ANNEES = 5

# Années civiles présentes dans la base, de la plus récente à la plus ancienne.
# Le pilotage se fait en exercices — « 2025 » — autant que sur des fenêtres
# glissantes ; la rétrospective de la manager est annuelle.
ANNEES = sorted(range(DATE_MIN.year, DATE_MAX.year + 1), reverse=True)[:PROFONDEUR_ANNEES]

PERIODES: dict[str, tuple[str, int | None]] = {
    "12 derniers mois": ("glissante", 12),
    "24 derniers mois": ("glissante", 24),
    "36 derniers mois": ("glissante", 36),
    "Historique complet": ("tout", None),
    **{str(a): ("annee", a) for a in ANNEES},
}
INDEX_HISTORIQUE = list(PERIODES).index("Historique complet")


def bornes_periode(choix: str) -> tuple[dt.date, dt.date]:
    """Traduit une fenêtre en deux dates. Une année civile est bornée au 1er
    janvier et au 31 décembre, ramenés à la profondeur réelle des données."""
    mode, valeur = PERIODES.get(choix, PERIODES["Historique complet"])
    if mode == "tout":
        return DATE_MIN, DATE_MAX
    if mode == "annee":
        return (max(DATE_MIN, dt.date(valeur, 1, 1)),
                min(DATE_MAX, dt.date(valeur, 12, 31)))
    # Fenêtre glissante alignée sur le 1er du mois : un seul mois partiel,
    # celui en cours.
    ancre = pd.Timestamp(DATE_MAX).replace(day=1) - pd.DateOffset(months=valeur - 1)
    return max(DATE_MIN, ancre.date()), DATE_MAX


# =============================================================================
#  ÉTAT — page dans l'URL, filtres en session
# =============================================================================
def page_courante() -> str:
    demandee = st.query_params.get("page", st.session_state.get("page", "synthese"))
    if demandee not in LIBELLES_PAGES:
        demandee = "synthese"
    st.session_state["page"] = demandee
    return demandee


def _etat_filtres() -> tuple[dict[str, list[str]], str | None]:
    """L'état des widgets de la génération courante : dimensions et fenêtre."""
    generation = st.session_state.get("generation", 0)
    dims = {d: list(st.session_state.get(f"dim_{d}_{generation}", []))
            for d in core.DIMENSIONS}
    return ({d: v for d, v in dims.items() if v},
            st.session_state.get(f"periode_{generation}"))


def _rejouer(dims: dict[str, list[str]], periode: str | None) -> None:
    """Streamlit interdit d'écrire dans la clé d'un widget déjà affiché : on
    recrée donc la génération de widgets en reportant l'état voulu. C'est le
    seul mécanisme par lequel le produit modifie un filtre à la place de
    l'utilisateur — drill-down, lien, réinitialisation."""
    suivante = st.session_state.get("generation", 0) + 1
    st.session_state["generation"] = suivante
    for dimension, valeurs in dims.items():
        st.session_state[f"dim_{dimension}_{suivante}"] = valeurs
    if periode is not None:
        st.session_state[f"periode_{suivante}"] = periode


def ajouter_filtre(champ: str, valeur: str, page: str | None = None) -> bool:
    """Ajoute une modalité aux filtres actifs — c'est le drill-down."""
    dims, periode = _etat_filtres()
    deja = dims.get(champ, [])
    if valeur in deja:
        return False
    dims[champ] = deja + [valeur]
    _rejouer(dims, periode)
    if page:
        st.query_params["page"] = page
        st.session_state["page"] = page
    return True


def definir_periode(choix: str) -> bool:
    """Change la fenêtre d'observation sans toucher aux filtres de dimension.
    C'est ce qu'actionne la bande d'années de la vue d'ensemble."""
    if choix not in PERIODES:
        return False
    dims, periode = _etat_filtres()
    if periode == choix:
        return False
    _rejouer(dims, choix)
    return True


def aller_a(page: str, **filtres_supplementaires: object) -> None:
    """Navigue, en emportant éventuellement un filtre."""
    for champ, valeur in filtres_supplementaires.items():
        ajouter_filtre(champ, str(valeur))
    st.query_params["page"] = page
    st.session_state["page"] = page
    st.rerun()


def _reinitialiser_filtres() -> None:
    """Incrémenter la génération recrée des widgets neufs, donc vierges :
    supprimer les clés ne suffit pas, Streamlit restaurerait la valeur portée
    par le widget déjà affiché."""
    for cle in [k for k in st.session_state if k.startswith(("dim_", "periode", "bornes"))]:
        st.session_state.pop(cle, None)
    st.session_state["generation"] = st.session_state.get("generation", 0) + 1


def _etat_depuis_url() -> None:
    """Un lien peut porter un filtre ou une recherche :
    `?page=explorateur&statut=Gagné`. C'est ce qui rend cliquable chaque ligne
    de la page d'accueil, et chaque lien partageable.

    Les paramètres sont consommés une seule fois — signature mémorisée — puis
    retirés de l'URL : rien ne se rejoue, et retirer un filtre à la main ne le
    voit pas revenir au rerun suivant.
    """
    portes = {c: st.query_params[c] for c in core.DIMENSIONS if st.query_params.get(c)}
    recherche = st.query_params.get("q")
    fenetre = st.query_params.get("periode")
    if not portes and recherche is None and fenetre is None:
        return
    signature = (tuple(sorted(portes.items())), recherche, fenetre)
    if st.session_state.get("_url_lue") == signature:
        return
    st.session_state["_url_lue"] = signature
    if fenetre is not None:
        definir_periode(fenetre)
        del st.query_params["periode"]
    for champ, valeur in portes.items():
        ajouter_filtre(champ, valeur)
        del st.query_params[champ]
    if recherche is not None:
        # Écrit AVANT l'instanciation du champ de recherche : Streamlit
        # interdirait l'inverse.
        st.session_state["recherche"] = recherche
        del st.query_params["q"]


PAGE = page_courante()
_etat_depuis_url()


# =============================================================================
#  BARRE LATÉRALE — marque, navigation, source
# =============================================================================
def barre_laterale() -> None:
    with st.sidebar:
        # Le logo est un SVG inline plutôt qu'une animation en iframe : net à
        # toutes les tailles, sans cadre parasite, et il ne se rejoue pas à
        # chaque rerun. Le mouvement reste là où il signifie quelque chose —
        # l'attente pendant la génération du rapport, la confirmation ensuite.
        st.markdown(
            f"<div class='marque'>{marque_html('marque__logo')}"
            f"<div class='marque__texte'>{escape(core.MARQUE_NOM)}"
            f"<span>{escape(core.MARQUE_PRODUIT)}</span></div></div>",
            unsafe_allow_html=True)

        for groupe in GROUPES:
            pages = [p for p in PAGES if p[2] == groupe]
            if not pages:
                continue
            st.markdown(f"<div class='nav-groupe'>{groupe}</div>", unsafe_allow_html=True)
            for cle, libelle, _, _ in pages:
                if st.button(libelle, key=f"nav_{cle}",
                             type="primary" if cle == PAGE else "secondary", **KW_BOUTON):
                    st.query_params["page"] = cle
                    st.session_state["page"] = cle
                    st.rerun()

        st.divider()
        choix = st.selectbox("Apparence", list(THEMES_LISIBLES),
                             format_func=lambda c: THEMES_LISIBLES[c],
                             index=list(THEMES_LISIBLES).index(_theme_demande),
                             key="choix_theme")
        if choix != _theme_demande:
            st.session_state["theme"] = choix
            st.rerun()

        st.markdown(
            f"<div class='side-info'><b>Source</b><br>{rapport.source}<br><br>"
            f"<b>Profondeur</b><br>{core.fmt_date(DATE_MIN)} → {core.fmt_date(DATE_MAX)}<br><br>"
            f"<b>Lignes exploitables</b><br>{core.fmt_int(rapport.n_lignes_retenues)} sur "
            f"{core.fmt_int(rapport.n_lignes_source)}</div>", unsafe_allow_html=True)


barre_laterale()


# =============================================================================
#  FILTRES GLOBAUX — une seule barre, au-dessus de tout ce qu'elle porte
# =============================================================================
def barre_filtres() -> core.Filters:
    generation = st.session_state.setdefault("generation", 0)
    colonnes = st.columns([1.3, 1, 1, 1, 1, 0.8], gap="small")

    with colonnes[0]:
        choix = st.selectbox("Période", list(PERIODES), index=INDEX_HISTORIQUE,
                             key=f"periode_{generation}")
    debut, fin = bornes_periode(choix)

    dims: dict[str, list[str]] = {}
    principales = [c for c in core.DIMENSIONS_PRINCIPALES if c in df_complet.columns][:4]
    for colonne, champ in zip(colonnes[1:5], principales):
        options = _options(champ)
        if len(options) < 2:
            continue
        with colonne:
            dims[champ] = st.multiselect(core.DIMENSIONS[champ], options, default=[],
                                         placeholder="Tous", key=f"dim_{champ}_{generation}")

    with colonnes[5]:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        with st.popover("Plus de filtres", **KW_BOUTON):
            secondaires = [c for c in core.DIMENSIONS
                           if c not in principales and c in df_complet.columns]
            for champ in secondaires:
                options = _options(champ)
                if len(options) < 2:
                    continue
                dims[champ] = st.multiselect(core.DIMENSIONS[champ], options, default=[],
                                             placeholder="Tous",
                                             key=f"dim_{champ}_{generation}")
            st.button("Réinitialiser tous les filtres", on_click=_reinitialiser_filtres,
                      **KW_BOUTON)
    return core.Filters(date_min=debut, date_max=fin, dims=dims)


@st.cache_data(show_spinner=False)
def _options_cache(champ: str, empreinte: int) -> list[str]:
    serie = df_complet[champ].dropna()
    return sorted(v for v in serie.unique().tolist() if v != core.VALEUR_INCONNUE)


def _options(champ: str) -> list[str]:
    return _options_cache(champ, len(df_complet))


def chips_filtres(filtres: core.Filters) -> None:
    """Les filtres actifs, toujours visibles : on ne lit jamais un chiffre sans
    savoir sur quoi il porte."""
    morceaux = []
    if filtres.date_min and filtres.date_max:
        morceaux.append(f"<span class='chip'><b>Période</b>{core.fmt_date(filtres.date_min)}"
                        f" → {core.fmt_date(filtres.date_max)}</span>")
    actifs = 0
    for champ, valeurs in (filtres.dims or {}).items():
        for valeur in valeurs:
            actifs += 1
            morceaux.append(f"<span class='chip'><b>{core.DIMENSIONS.get(champ, champ)}</b>"
                            f"{valeur}</span>")
    if not actifs:
        morceaux.append("<span class='chip chip--vide'>Aucun filtre de dimension</span>")
    st.markdown(f"<div class='chips'>{''.join(morceaux)}</div>", unsafe_allow_html=True)
    return actifs


# L'en-tête est réservé AVANT la barre de filtres, mais rempli après : il a
# besoin du décompte de la sélection, et il doit malgré tout ouvrir la page.
zone_entete = st.container()
filtres = barre_filtres()
df = core.filter_data(df_complet, filtres)
df_precedent = core.filter_data(df_complet, filtres.periode_precedente())
def _granularite_par_defaut(filtres: core.Filters) -> str:
    """Un axe mensuel sur treize ans donne cent cinquante barres illisibles :
    la granularité suit la longueur de la fenêtre, jusqu'à ce que l'utilisateur
    en décide autrement."""
    duree = filtres.duree_jours or 0
    if duree > 6 * 365:
        return "annee"
    if duree > 3 * 365:
        return "trimestre"
    return "mois"


granularite = st.session_state.get("granularite") or _granularite_par_defaut(filtres)
analyse = core.build_analysis(df, filtres, rapport, df_precedent,
                              options={"granularite": granularite,
                                       "esg_mode": st.session_state.get("esg_mode", "part")})


def bande_annees_html() -> str:
    """La rétrospective se lit par exercice, pas en mois glissants.

    Rendue comme du CHROME, dans l'en-tête, à droite du titre : un sélecteur a
    sa place dans la barre de commande, pas au-dessus du contenu qu'il pilote.
    Cliquer un exercice change la fenêtre GLOBALE — il n'y a pas deux notions
    de période dans le produit.
    """
    sans_periode = core.Filters(date_min=DATE_MIN, date_max=DATE_MAX, dims=filtres.dims)
    base = core.filter_data(df_complet, sans_periode)
    volumes = (base.groupby(base["date_reception"].dt.year).size() if not base.empty
               else pd.Series(dtype="int64"))
    courant = (st.session_state.get(f"periode_{st.session_state.get('generation', 0)}")
               or "Historique complet")

    def pastille(libelle: str, cle: str, n: int) -> str:
        actif = " annee--actif" if courant == cle else ""
        return (f"<a class='annee{actif}' href='{lien('synthese', periode=cle)}' "
                f"target='_self' title='{core.pluriel(n, 'questionnaire')}'>"
                f"<b>{escape(libelle)}</b>"
                f"<span class='annee__n'>{core.fmt_int(n)}</span></a>")

    pastilles = [pastille(str(a), str(a), int(volumes.get(a, 0))) for a in ANNEES]
    pastilles.append(pastille("Tout", "Historique complet", len(base)))
    return f"<div class='annees'>{''.join(pastilles)}</div>"


# =============================================================================
#  EN-TÊTE DE PAGE
# =============================================================================
_, titre_page, groupe_page, sous_titre = next(p for p in PAGES if p[0] == PAGE)
with zone_entete:
    if PAGE == "accueil":
        # La page d'accueil porte la marque : c'est le premier écran ouvert le
        # matin, il doit dire de qui il parle et à quelle date il est arrêté.
        st.markdown(
            f"""
            <div class="hero">
              {marque_html("hero__logo")}
              <div>
                <div class="hero__maison">{escape(core.MARQUE_NOM)} &middot;
                  {escape(core.MARQUE_ACTIVITE)}</div>
                <div class="hero__titre">État du carnet au
                  {core.fmt_date_longue(DATE_MAX)}</div>
                <div class="hero__sous">Les appels d'offres en attente de décision, ceux
                  que nous avons remportés, ceux que nous avons perdus — sur le périmètre
                  sélectionné ci-dessous.</div>
              </div>
              <div class="hero__meta">
                <b>{core.fmt_int(len(df))}</b> questionnaires dans la sélection<br>
                {analyse.periode}<br>
                Écran du {core.fmt_date(dt.date.today())}
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        # Sur la vue d'ensemble, la droite de l'en-tête porte le sélecteur
        # d'exercice : le contenu commence donc par l'arbre, pas par un réglage.
        droite = (bande_annees_html() if PAGE == "synthese" else
                  f"""<div class="entete__meta">
                <b>{core.fmt_int(len(df))}</b> questionnaires dans la sélection<br>
                {analyse.periode}<br>
                Données arrêtées au {core.fmt_date(DATE_MAX)}
              </div>""")
        st.markdown(
            f"""
            <div class="entete">
              <div>
                <div class="sur-titre">{groupe_page}</div>
                <div class="entete__titre">{titre_page}</div>
                <div class="entete__sous">{sous_titre}</div>
              </div>
              <div style="margin-left:auto;text-align:right">{droite}</div>
            </div>
            """, unsafe_allow_html=True)

n_filtres = chips_filtres(filtres)

if analyse.vide:
    st.warning("Aucun questionnaire ne correspond à cette sélection. "
               "Élargissez la période ou retirez un filtre.")
    st.button("Réinitialiser les filtres", on_click=_reinitialiser_filtres, type="primary")
    st.stop()


# =============================================================================
#  AFFICHAGE DES BLOCS
# =============================================================================
def afficher_bloc(bloc: core.Block) -> None:
    with st.container(border=True):
        st.markdown(f"<div class='carte__titre'>{bloc.titre}</div>"
                    f"<div class='carte__accroche'>{bloc.accroche}</div>",
                    unsafe_allow_html=True)
        if bloc.figure is None:
            # Le bloc EST un tableau : il s'affiche en entier — une ligne de
            # total qu'il faut aller chercher en faisant défiler ne sert à rien.
            premiere = bloc.tableau.columns[0]
            st.dataframe(
                bloc.tableau, hide_index=True,
                height=min(900, 36 * (len(bloc.tableau) + 1) + 10),
                column_config={premiere: st.column_config.TextColumn(premiere,
                                                                     width="medium")},
                **KW_TABLE)
            if bloc.note:
                st.markdown(f"<div class='carte__note'>{bloc.note}</div>",
                            unsafe_allow_html=True)
            return
        cliquable = bool(bloc.dimension) and SELECTION_DISPONIBLE
        if cliquable:
            # Sans clickmode, Plotly n'émet pas d'événement de sélection au clic.
            bloc.figure.update_layout(clickmode="event+select", dragmode=False)
            evenement = st.plotly_chart(
                bloc.figure, theme=None, config=core.PLOT_CONFIG, key=f"fig_{bloc.cle}",
                on_select="rerun", selection_mode="points", **KW_PLOT)
            _traiter_clic(bloc, evenement)
            # Formulation sans accord à deviner : « cette type de demande »
            # serait la faute que tout le monde remarque.
            st.markdown(f"<div class='carte__clic'>Cliquez une barre : tout le tableau "
                        f"de bord se recalcule sur cette modalité de « "
                        f"{core.DIMENSIONS.get(bloc.dimension, bloc.dimension).lower()} ».</div>",
                        unsafe_allow_html=True)
        else:
            st.plotly_chart(bloc.figure, theme=None, config=core.PLOT_CONFIG, **KW_PLOT)
        with st.expander(f"Voir les données ({core.pluriel(len(bloc.tableau), 'ligne')})"):
            st.dataframe(bloc.tableau, hide_index=True, **KW_TABLE)
        if bloc.note:
            st.markdown(f"<div class='carte__note'>{bloc.note}</div>", unsafe_allow_html=True)


def _traiter_clic(bloc: core.Block, evenement) -> None:
    """Un clic sur une barre ajoute la modalité correspondante aux filtres."""
    points = (evenement or {}).get("selection", {}).get("points", [])
    if not points or not bloc.dimension:
        return
    etiquette = points[0].get("label") or points[0].get("y") or points[0].get("x")
    # « Autres (12) » regroupe une queue de classement : il n'existe pas comme
    # modalité, on ne peut pas filtrer dessus.
    if not isinstance(etiquette, str) or etiquette.startswith("Autres"):
        return
    if ajouter_filtre(bloc.dimension, etiquette):
        st.rerun()


def afficher_bloc_par_cle(cle: str) -> None:
    """Affiche un bloc nommé, s'il a pu être construit. Une page de direction
    compose ses blocs à la main ; une page d'analyse prend toute sa section."""
    bloc = next((b for b in analyse.blocs if b.cle == cle), None)
    if bloc is not None:
        afficher_bloc(bloc)


def afficher_section(cle: str) -> None:
    """Deux colonnes par défaut, pleine largeur pour les blocs qui la méritent."""
    attente: list[core.Block] = []

    def vider() -> None:
        nonlocal attente
        if not attente:
            return
        colonnes = st.columns(2, gap="medium")
        for colonne, bloc in zip(colonnes, attente):
            with colonne:
                afficher_bloc(bloc)
        attente = []

    for bloc in analyse.section(cle):
        if bloc.large:
            vider()
            afficher_bloc(bloc)
        else:
            attente.append(bloc)
            if len(attente) == 2:
                vider()
    vider()


def selecteur_granularite() -> None:
    options = list(core.GRANULARITES)
    courant = granularite
    colonnes = st.columns([3, 1.4])
    with colonnes[1]:
        if hasattr(st, "segmented_control"):
            choix = st.segmented_control(
                "Granularité", options, format_func=lambda c: core.GRANULARITES[c],
                default=courant, key="granularite_widget", label_visibility="collapsed")
        else:                                   # versions antérieures de Streamlit
            choix = st.radio("Granularité", options,
                             format_func=lambda c: core.GRANULARITES[c],
                             index=options.index(courant), horizontal=True,
                             key="granularite_widget", label_visibility="collapsed")
    if choix and choix != courant:
        st.session_state["granularite"] = choix
        st.rerun()


# =============================================================================
#  PAGES
# =============================================================================
# --- Accueil ------------------------------------------------------------------
# Le premier écran répond à une seule question : où en sommes-nous ? Un relevé
# de quatre chiffres, le carnet d'appels d'offres en une ligne, puis les trois
# listes nommées — en attente, gagnés, perdus. Aucun chiffre n'est calculé ici :
# tout vient de la couche métrique de core.py.
COULEURS_COMPARTIMENT = {
    "en_cours": "--neutre", "en_attente": "--attente", "gagnes": "--gagne",
    "perdus": "--perdu", "sans_suite": "--sans-suite",
}
JOURS_ALERTE = 120          # au-delà, une décision qui tarde devient une relance


def _meta(ligne: pd.Series, *champs: str) -> str:
    valeurs = [str(ligne[c]) for c in champs
               if c in ligne.index and pd.notna(ligne[c])
               and str(ligne[c]) != core.VALEUR_INCONNUE]
    return escape(" · ".join(valeurs))


def _ligne_dossier(ligne: pd.Series, valeur: str, appui: str = "",
                   alerte: bool = False, meta: str = "") -> str:
    """Une ligne de registre : le dossier, ce qu'il pèse, et le clic qui ouvre
    sa fiche dans l'explorateur."""
    client = str(ligne.get("client") or "Client non renseigné")
    classe = " ligne__val--alerte" if alerte else ""
    appui_html = f"<em>{escape(appui)}</em>" if appui else ""
    return (f"<a class='ligne' href='{lien('explorateur', q=client)}' target='_self'>"
            f"<span class='ligne__nom'><b>{escape(client)}</b>"
            f"<span class='ligne__meta'>{meta}</span></span>"
            f"<span class='ligne__val{classe}'>{escape(valeur)}{appui_html}</span></a>")


def _registre(cle: str, titre: str, n: int, lignes: list[str], pied: str,
              vide: str, colonne: str = "") -> str:
    """Un compartiment du carnet : sa pastille, son effectif, ses dossiers, et
    la porte vers la liste complète."""
    corps = ("".join(lignes) if lignes
             else f"<div class='registre__vide'>{escape(vide)}</div>")
    pastille = (f"<i class='registre__pastille' "
                f"style='background:var({COULEURS_COMPARTIMENT[cle]})'></i>")
    # La colonne de droite change de sens d'un registre à l'autre : elle porte
    # son intitulé plutôt que de laisser deviner ce que « 88 M€ » signifie.
    entete = (f"<div class='registre__colonnes'><span>Dossier</span>"
              f"<span>{escape(colonne)}</span></div>" if colonne and lignes else "")
    return (f"<div class='registre'><div class='registre__tete'>{pastille}"
            f"<span class='registre__titre'>{escape(titre)}</span>"
            f"<span class='registre__n'>{core.fmt_int(n)}</span></div>{entete}{corps}"
            f"<div class='registre__pied'>{pied}</div></div>")


def _releve(etat: core.Carnet) -> None:
    taux, gagnes, tranches, ic = core.taux_succes_rfp(df)
    remporte, en_jeu = core.aum_gagne(df), core.aum_en_jeu(df)
    cases = [
        ("Appels d'offres vivants", core.fmt_int(etat.vivants), "",
         f"{core.fmt_int(etat.n('en_cours'))} en rédaction · "
         f"{core.fmt_int(etat.n('en_attente'))} remis, décision attendue"),
        ("Encours en jeu", core.fmt_dec(en_jeu, 0, "M€"), "",
         f"sur {pluriel(etat.vivants, 'dossier')} non tranché"
         + ("s" if etat.vivants > 1 else "")),
        ("Taux de succès", core.fmt_pct(taux, 1), "",
         f"{core.fmt_int(gagnes)} gagnés sur {core.fmt_int(tranches)} tranchés · "
         f"IC 95 % {core.fmt_pct(ic[0], 0)}–{core.fmt_pct(ic[1], 0)}"),
        ("Encours remporté", core.fmt_dec(remporte, 0, "M€"), " releve__valeur--or",
         (f"ticket moyen {core.fmt_dec(remporte / gagnes, 0, 'M€')}" if gagnes
          else "aucun mandat remporté sur la période")),
    ]
    st.markdown("<div class='releve'>" + "".join(
        f"<div><div class='releve__label'>{escape(l)}</div>"
        f"<div class='releve__valeur{classe}'>{escape(v)}</div>"
        f"<div class='releve__detail'>{escape(d)}</div></div>"
        for l, v, classe, d in cases) + "</div>", unsafe_allow_html=True)


def _ruban(etat: core.Carnet) -> None:
    """Tout le carnet sur une ligne. Chaque segment porte son libellé et son
    effectif juste dessous : l'identité ne repose jamais sur la seule couleur."""
    if not etat.total:
        return
    segments = "".join(
        f"<i style='flex:{etat.n(cle)};background:var({COULEURS_COMPARTIMENT[cle]})'></i>"
        for cle, _, _ in core.COMPARTIMENTS if etat.n(cle))
    legende = "".join(
        f"<div><i style='background:var({COULEURS_COMPARTIMENT[cle]})'></i>"
        f"<em>{core.fmt_int(etat.n(cle))}</em>&nbsp;<span>{escape(libelle.lower())}"
        f"{'' if etat.n(cle) else ' — aucun'}</span></div>"
        for cle, libelle, _ in core.COMPARTIMENTS)
    st.markdown(f"<div class='ruban'>{segments}</div>"
                f"<div class='ruban-legende'>{legende}</div>", unsafe_allow_html=True)


def _registres(etat: core.Carnet) -> None:
    attente, gagnes, perdus = etat.en_attente, etat.gagnes, etat.perdus

    lignes_attente = [
        _ligne_dossier(
            l, f"{core.fmt_int(l['jours_attente'])} j" if pd.notna(l["jours_attente"]) else "—",
            "d'attente", alerte=pd.notna(l["jours_attente"]) and l["jours_attente"] > JOURS_ALERTE,
            meta=_meta(l, "pays", "classe_actifs"))
        for _, l in attente.head(6).iterrows()]

    def _montant(ligne: pd.Series) -> str:
        montant = ligne.get("montant_potentiel")
        return core.fmt_dec(montant, 0, "M€") if pd.notna(montant) else "—"

    lignes_gagnes = [
        _ligne_dossier(l, _montant(l), core.fmt_date(l.get("date_envoi")),
                       meta=_meta(l, "pays", "classe_actifs"))
        for _, l in gagnes.head(6).iterrows()]
    lignes_perdus = [
        _ligne_dossier(l, _montant(l), core.fmt_date(l.get("date_envoi")),
                       meta=_meta(l, "pays", "classe_actifs"))
        for _, l in perdus.head(6).iterrows()]

    def _pied(cle_statut: str, n: int, mot: str) -> str:
        if not n:
            return "<span class='registre__vide' style='padding:0'>—</span>"
        quantite = "le" if n == 1 else f"les {core.fmt_int(n)}"
        return (f"<a href='{lien('explorateur', statut=cle_statut)}' target='_self'>"
                f"Voir {quantite} {mot if n == 1 else mot + 's'} →</a>")

    st.markdown("<div class='registres'>" + "".join([
        _registre("en_attente", "En attente de décision", len(attente), lignes_attente,
                  _pied(core.STATUT_ENVOYE, len(attente), "dossier"),
                  "Aucun appel d'offres remis n'attend de décision sur cette sélection.",
                  colonne="Attente"),
        _registre("gagnes", "Gagnés", len(gagnes), lignes_gagnes,
                  _pied(core.STATUT_GAGNE, len(gagnes), "mandat"),
                  "Aucun mandat remporté sur cette sélection.",
                  colonne="Encours · décision"),
        _registre("perdus", "Perdus", len(perdus), lignes_perdus,
                  _pied(core.STATUT_PERDU, len(perdus), "dossier"),
                  "Aucun appel d'offres perdu sur cette sélection.",
                  colonne="Encours · décision"),
    ]) + "</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='note-lecture'>{core.NOTE_CENSURE}</div>",
                unsafe_allow_html=True)


def _relances(etat: core.Carnet) -> None:
    urgents = etat.a_relancer
    if urgents.empty:
        return
    lignes = []
    for _, l in urgents.head(6).iterrows():
        if bool(l.get("en_retard")):
            motif, valeur = "délai cible dépassé", f"{core.fmt_int(l.get('anciennete_ouvree'))} j"
        else:
            motif, valeur = "sans réponse du client", f"{core.fmt_int(l.get('jours_attente'))} j"
        lignes.append(_ligne_dossier(l, valeur, motif, alerte=True,
                                     meta=_meta(l, "pays", "classe_actifs", "analyste")))
    montant = float(urgents["montant_potentiel"].sum(skipna=True))
    detail = (f" · {core.fmt_dec(montant, 0, 'M€')} d'encours concernés" if montant else "")
    st.markdown(
        "<div class='registre registre--large'><div class='registre__tete'>"
        "<i class='registre__pastille' style='background:var(--mauvais)'></i>"
        "<span class='registre__titre'>À relancer</span>"
        f"<span class='registre__n'>{core.fmt_int(len(urgents))}</span></div>"
        f"<div class='lignes'>{''.join(lignes)}</div>"
        f"<div class='registre__pied'><a href='{lien('explorateur')}' target='_self'>"
        f"Ouvrir la liste complète dans l'explorateur →</a>"
        f"<span class='ligne__meta' style='display:inline;margin-left:10px'>"
        f"délai cible dépassé, ou décision attendue depuis plus de "
        f"{JOURS_ALERTE} jours{escape(detail)}</span></div></div>",
        unsafe_allow_html=True)


def _bande_types() -> None:
    """Le mix réel — RFP, RFI, DDQ. Détail d'écran : le rapport diffusé s'en
    tient aux deux familles de pilotage, et le dit."""
    volumes = core.repartition_type(df)
    if volumes.empty:
        return
    total = float(volumes.sum())
    lignes = []
    for type_, n in volumes.items():
        couleur = core.TYPE_COLORS.get(type_, core.SERIES[0])
        part = n / total if total else 0.0
        lignes.append(
            f"<div class='bande__ligne'><div class='bande__nom'>{escape(str(type_))}</div>"
            f"<div class='bande__piste'><i style='width:{part * 100:.1f}%;"
            f"background:{couleur}'></i></div>"
            f"<div class='bande__val'>{core.fmt_int(n)}"
            f"<em>{core.fmt_pct(part, 0)}</em></div></div>")
    st.markdown(
        "<div class='bande'><div class='bande__tete'>"
        "<span class='bande__titre'>Le mix réel</span>"
        "<span class='bande__note'>détail d'écran — le rapport diffusé s'en tient "
        "aux deux familles, RFP et due diligence</span></div>"
        + "".join(lignes) + "</div>", unsafe_allow_html=True)


def page_accueil() -> None:
    etat = core.carnet(df)
    _releve(etat)
    _ruban(etat)
    _registres(etat)
    _relances(etat)
    _bande_types()

    flux = next((b for b in analyse.blocs if b.cle == "flux_famille"), None)
    if flux is not None:
        st.markdown("<div class='nav-groupe' style='margin-top:26px'>Ce qui arrive</div>",
                    unsafe_allow_html=True)
        afficher_bloc(flux)

    if analyse.insights:
        st.markdown("<div class='nav-groupe' style='margin-top:22px'>Constats</div>",
                    unsafe_allow_html=True)
        cartes_insights(analyse.insights[:3])


def page_synthese() -> None:
    """Partie I — la rétrospective. Quatre blocs, pas un de plus.

    L'ARBRE D'ABORD : c'est la question du comité — combien arrive, de quelle
    nature, et que deviennent les appels d'offres. Tout le reste la précise.
    """
    afficher_bloc_par_cle("decomposition")
    afficher_bloc_par_cle("trimestre")

    bandeau_kpis(analyse, KPIS_PAR_PAGE["synthese"])
    st.markdown(f"<div class='note-lecture'>{core.NOTE_CENSURE}</div>",
                unsafe_allow_html=True)

    if analyse.insights:
        st.markdown("<div class='nav-groupe'>Ce qu'il faut retenir</div>",
                    unsafe_allow_html=True)
        cartes_insights(analyse.insights[:3])

    st.markdown("<div class='nav-groupe'>La tendance longue</div>", unsafe_allow_html=True)
    selecteur_granularite()
    afficher_bloc_par_cle("flux_famille")
    afficher_bloc_par_cle("mandats_remportes")


def cartes_insights(insights: list[core.Insight]) -> None:
    """Chaque constat est lui-même le lien vers la page qui l'explique : pas de
    bouton suspendu sous la carte, et des hauteurs égales par construction."""
    cartes = []
    for insight in insights:
        corps = (f"<div class='insight__texte'>{insight.texte}</div>"
                 + (f"<div class='insight__appui'>{insight.appui}</div>"
                    if insight.appui else ""))
        if insight.cible and insight.cible in LIBELLES_PAGES:
            corps += (f"<div class='insight__lien'>"
                      f"{LIBELLES_PAGES[insight.cible]} →</div>")
            cartes.append(f"<a class='insight insight--{insight.ton}' "
                          f"href='?page={insight.cible}' target='_self'>{corps}</a>")
        else:
            cartes.append(f"<div class='insight insight--{insight.ton}'>{corps}</div>")
    st.markdown(f"<div class='insights'>{''.join(cartes)}</div>", unsafe_allow_html=True)


def page_avec_blocs(cle: str) -> None:
    kpis = KPIS_PAR_PAGE.get(cle, [])
    if kpis:
        bandeau_kpis(analyse, kpis)
    if cle == "activite":
        selecteur_granularite()
    if cle == "esg":
        colonnes = st.columns([3, 1.4])
        with colonnes[1]:
            mode = st.radio("Affichage", ["part", "volume"],
                            format_func=lambda m: "En part" if m == "part" else "En volume",
                            index=0 if st.session_state.get("esg_mode", "part") == "part" else 1,
                            horizontal=True, label_visibility="collapsed", key="esg_widget")
        if mode != st.session_state.get("esg_mode", "part"):
            st.session_state["esg_mode"] = mode
            st.rerun()
    blocs = analyse.section(cle)
    if not blocs:
        st.info("Aucune analyse disponible sur cette sélection : les colonnes nécessaires "
                "sont absentes du fichier, ou l'effectif est trop faible pour conclure.")
        return
    afficher_section(cle)


def page_insights() -> None:
    if not analyse.insights:
        st.info("Aucun constat ne se dégage de cette sélection.")
    else:
        st.markdown("<div class='note-lecture'>Chaque constat est calculé sur la sélection "
                    "courante. Aucune phrase n'est écrite d'avance : si la donnée ne permet "
                    "pas de l'établir, le constat n'apparaît pas.</div>",
                    unsafe_allow_html=True)
        cartes_insights(analyse.insights)
    diagnostic = analyse.section("diagnostic")
    if diagnostic:
        st.markdown("<div class='nav-groupe' style='margin-top:24px'>Analyse des causes"
                    "</div>", unsafe_allow_html=True)
        st.markdown("<div class='note-lecture'>Ces modèles cherchent ce qui explique les "
                    "délais et ce que la tendance laisse attendre. Ils répondent au "
                    "« pourquoi », pas au « combien ».</div>", unsafe_allow_html=True)
        afficher_section("diagnostic")


# --- Explorateur --------------------------------------------------------------
COLONNES_EXPLORATEUR = [
    ("date_reception", "Réception"), ("famille", "Famille"), ("type_demande", "Type"),
    ("client", "Client"), ("consultant", "Consultant"), ("pays", "Pays"),
    ("classe_actifs", "Classe d'actifs"), ("sous_classe_actifs", "Sous-classe"),
    ("expertise", "Expertise"), ("fonds", "Fonds de référence"),
    ("forme_juridique", "Forme juridique"), ("resultat", "Résultat"),
    ("statut", "Statut"), ("montant_potentiel", "Encours (M€)"),
    ("bande_esg", "ESG"), ("delai_calendaire", "Délai (j)"),
    ("nb_questions", "Questions"), ("analyste", "Analyste"),
    ("date_envoi", "Envoi"), ("langue", "Langue"),
]
# Colonnes affichées d'emblée. L'encours en est volontairement absent : il
# n'existe que pour un appel d'offres remporté, soit moins d'une ligne sur
# vingt — une colonne vide sur tout l'écran n'apprend rien. Elle reste à un
# clic dans le sélecteur de colonnes, et se remplit dès qu'on filtre sur les
# RFP gagnés.
COLONNES_DEFAUT = ["date_reception", "famille", "client", "pays", "classe_actifs",
                   "expertise", "resultat", "delai_calendaire"]


def page_explorateur() -> None:
    disponibles = [(c, l) for c, l in COLONNES_EXPLORATEUR if c in df.columns]
    haut = st.columns([3.4, 1.1, 1.1], gap="small")
    with haut[0]:
        recherche = st.text_input("Rechercher", placeholder="Client, fonds, consultant, pays…",
                                  label_visibility="collapsed", key="recherche")
    with haut[1]:
        with st.popover("Colonnes", **KW_BOUTON):
            colonnes_vues = st.multiselect(
                "Colonnes affichées", [c for c, _ in disponibles],
                default=[c for c in COLONNES_DEFAUT if c in dict(disponibles)],
                format_func=lambda c: dict(disponibles)[c], key="colonnes_vues")
    with haut[2]:
        vue = st.session_state.get("explorateur_vue", "tout")
        seulement_attention = st.toggle("À relancer", value=vue == "attention",
                                        key="filtre_attention")

    table = core.dossiers_a_surveiller(df) if seulement_attention else df
    if recherche:
        motif = core.cle_recherche(recherche)
        table = table[core.index_recherche(table).str.contains(motif, regex=False, na=False)]

    if table.empty:
        st.info("Aucun dossier ne correspond à cette recherche.")
        return

    colonnes_vues = colonnes_vues or COLONNES_DEFAUT
    affichage = table[[c for c in colonnes_vues if c in table.columns]].copy()
    # Les valeurs manquantes s'affichent « None » : c'est le rendu de la grille
    # Streamlit, que ni column_config ni un Styler ne modifient. On arrondit
    # pour éviter en plus les décimales parasites.
    for numerique in ("montant_potentiel", "delai_calendaire", "nb_questions"):
        if numerique in affichage.columns:
            affichage[numerique] = affichage[numerique].round(0)
    affichage = affichage.rename(columns=dict(disponibles))
    config = {}
    for interne, libelle in disponibles:
        if libelle not in affichage.columns:
            continue
        if interne in ("date_reception", "date_envoi"):
            config[libelle] = st.column_config.DateColumn(libelle, format="DD/MM/YYYY")
        elif interne in ("montant_potentiel", "delai_calendaire", "nb_questions"):
            config[libelle] = st.column_config.NumberColumn(libelle, format="%d")

    st.caption(f"{core.pluriel(len(table), 'dossier')} · cliquez une ligne pour ouvrir "
               f"sa fiche")
    evenement = st.dataframe(
        affichage.sort_values(affichage.columns[0], ascending=False),
        hide_index=True, height=560, column_config=config,
        on_select="rerun", selection_mode="single-row", key="table_explorateur",
        **KW_TABLE)

    lignes = (evenement or {}).get("selection", {}).get("rows", [])
    if lignes:
        ordre = affichage.sort_values(affichage.columns[0], ascending=False).index
        fiche_dossier(table.loc[ordre[lignes[0]]])

    st.download_button(
        "Télécharger la sélection (CSV)",
        data=core.table_detaillee(table, formate=False).to_csv(index=False, sep=";")
             .encode("utf-8-sig"),
        file_name=f"rfp_intelligence_{dt.date.today():%Y%m%d}.csv", mime="text/csv",
        **_kw_largeur(st.download_button))


def fiche_dossier(ligne: pd.Series) -> None:
    """Fiche détaillée en panneau, sans quitter la liste ni perdre les filtres."""
    @st.dialog(f"{ligne.get('client', 'Dossier')} — {ligne.get('type_demande', '')}",
               width="large")
    def _fiche() -> None:
        couleurs = {core.RESULTAT_GAGNE: core.TEXTE_BON,
                    core.RESULTAT_PERDU: core.TEXTE_MAUVAIS}
        resultat = ligne.get("resultat", "—")
        st.markdown(
            f"<span class='puce' style='background:color-mix(in srgb,"
            f"{couleurs.get(resultat, core.INK_MUTED)} 15%, transparent);"
            f"color:{couleurs.get(resultat, core.INK_2)}'>{resultat}</span>"
            f"&nbsp;<span class='puce puce--neutre'>{ligne.get('famille', '')}</span>",
            unsafe_allow_html=True)
        gauche, droite = st.columns(2, gap="large")
        champs_gauche = [("Client", "client"), ("Consultant", "consultant"),
                         ("Pays", "pays"), ("Type de client", "type_client"),
                         ("Fonds de référence", "fonds"), ("Forme juridique", "forme_juridique")]
        champs_droite = [("Classe d'actifs", "classe_actifs"),
                         ("Sous-classe", "sous_classe_actifs"), ("Expertise", "expertise"),
                         ("Analyste", "analyste"), ("Langue", "langue"), ("ESG", "bande_esg")]
        for colonne, champs in ((gauche, champs_gauche), (droite, champs_droite)):
            with colonne:
                for libelle, champ in champs:
                    if champ in ligne.index and pd.notna(ligne[champ]):
                        st.markdown(f"<div class='kpi__label'>{libelle}</div>"
                                    f"<div style='font-size:13px;margin-bottom:9px'>"
                                    f"{ligne[champ]}</div>", unsafe_allow_html=True)
        st.divider()
        mesures = st.columns(4)
        mesures[0].metric("Reçu le", core.fmt_date(ligne.get("date_reception")))
        mesures[1].metric("Envoyé le", core.fmt_date(ligne.get("date_envoi")))
        delai = ligne.get("delai_calendaire")
        mesures[2].metric("Délai", core.fmt_dec(delai, 0, "j") if pd.notna(delai) else "—")
        montant = ligne.get("montant_potentiel")
        mesures[3].metric("Encours", core.fmt_dec(montant, 0, "M€") if pd.notna(montant) else "—")
        if pd.notna(ligne.get("nb_questions")):
            st.caption(f"{core.fmt_int(ligne['nb_questions'])} questions · "
                       f"délai cible {core.fmt_int(ligne.get('sla_cible', 0))} jours ouvrés")
    _fiche()


# --- Qualité & export ---------------------------------------------------------
def page_donnees() -> None:
    gauche, droite = st.columns([1, 1], gap="medium")
    with gauche:
        with st.container(border=True):
            st.markdown("<div class='carte__titre'>Qualité des données</div>"
                        "<div class='carte__accroche'>Contrôles passés à l'import. "
                        "Aucune ligne n'est écartée sans être comptée.</div>",
                        unsafe_allow_html=True)
            st.markdown(
                f"<div class='side-info'>Source : <b>{rapport.source}</b><br>"
                f"Lignes lues : <b>{core.fmt_int(rapport.n_lignes_source)}</b> · "
                f"retenues : <b>{core.fmt_int(rapport.n_lignes_retenues)}</b><br>"
                f"Colonnes ignorées : {', '.join(rapport.colonnes_ignorees) or 'aucune'}</div>",
                unsafe_allow_html=True)
            if rapport.colonnes_absentes:
                st.info("Dimensions absentes du fichier, analyses correspondantes masquées : "
                        + ", ".join(core.DIMENSIONS.get(c, c) for c in rapport.colonnes_absentes))
            if rapport.est_propre:
                st.success("Aucune anomalie détectée.")
            else:
                for alerte in rapport.alertes:
                    st.warning(alerte)
            if analyse.erreurs:
                st.error("Blocs non construits : " + " · ".join(analyse.erreurs))

        with st.container(border=True):
            st.markdown("<div class='carte__titre'>Définitions</div>"
                        "<div class='carte__accroche'>Les métriques sont calculées à un "
                        "seul endroit ; voici ce qu'elles recouvrent.</div>",
                        unsafe_allow_html=True)
            for kpi in analyse.kpis:
                with st.expander(kpi.libelle):
                    st.markdown(f"**{kpi.affichage}** — {kpi.aide}")

    with droite:
        with st.container(border=True):
            st.markdown("<div class='carte__titre'>Rapport autonome</div>"
                        "<div class='carte__accroche'>Un fichier HTML unique, paginé, "
                        "graphiques interactifs inclus, qui s'ouvre sans Python ni "
                        "connexion — transmissible en pièce jointe.</div>",
                        unsafe_allow_html=True)
            theme_rapport = st.selectbox(
                "Thème du rapport", list(THEMES_LISIBLES),
                format_func=lambda c: THEMES_LISIBLES[c],
                index=list(THEMES_LISIBLES).index(core.THEME), key="theme_rapport")
            if st.button("Générer le rapport", type="primary", **KW_BOUTON):
                import export
                attente = st.empty()
                with attente.container():
                    animation("chargement", 54, boucle=True)
                theme_initial = core.THEME
                try:
                    core.appliquer_theme(theme_rapport)
                    analyse_export = core.build_analysis(
                        df, filtres, rapport, df_precedent,
                        options={"granularite": granularite})
                    chemin = export.ecrire_rapport(analyse_export, export.CHEMIN_RAPPORT)
                    st.session_state["rapport_html"] = Path(chemin).read_bytes()
                    st.session_state["rapport_chemin"] = str(chemin)
                finally:
                    core.appliquer_theme(theme_initial)
                attente.empty()
            if "rapport_html" in st.session_state:
                colonnes = st.columns([1, 4], gap="small")
                with colonnes[0]:
                    animation("valide", 44, boucle=False)
                with colonnes[1]:
                    poids = len(st.session_state["rapport_html"]) / 1_048_576
                    st.download_button(
                        f"Télécharger rapport.html ({poids:.1f} Mo)",
                        data=st.session_state["rapport_html"],
                        file_name=f"rfp_intelligence_{dt.date.today():%Y%m%d}.html",
                        mime="text/html", **_kw_largeur(st.download_button))
                    st.caption(f"Également écrit sur le disque : "
                               f"`{st.session_state['rapport_chemin']}`")


# =============================================================================
#  ROUTAGE
# =============================================================================
if PAGE == "accueil":
    page_accueil()
elif PAGE == "synthese":
    page_synthese()
elif PAGE == "insights":
    page_insights()
elif PAGE == "explorateur":
    page_explorateur()
elif PAGE == "donnees":
    page_donnees()
else:
    page_avec_blocs(PAGE)

st.markdown(
    f"<div class='note-lecture' style='margin-top:26px'>RFP Intelligence · "
    f"{core.fmt_int(rapport.n_lignes_retenues)} questionnaires dans la base · "
    f"{core.fmt_int(len(df))} dans la sélection · "
    f"Données arrêtées au {core.fmt_date(DATE_MAX)}</div>", unsafe_allow_html=True)
