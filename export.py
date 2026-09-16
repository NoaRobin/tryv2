# =============================================================================
#  export.py — Rapport HTML autonome, paginé
# -----------------------------------------------------------------------------
#  Produit un fichier unique qui embarque tout ce dont il a besoin : la
#  bibliothèque Plotly, les deux polices et la marque en tracés vectoriels. Il
#  s’ouvre d’un double-clic, sans Python, sans serveur et sans réseau — donc
#  transmissible par courriel à un comité d’investissement.
#
#  C’est le MÊME produit que l’écran : mêmes jetons (core.jetons_css), même
#  typographie, mêmes filets, aucune carte, aucune ombre, un seul thème. Rien
#  ici ne fabrique une couleur : tout vient de `var(--b-NN)` et des variables
#  émises par core.py.
#
#  Usage :  python export.py [--sortie CHEMIN]
#           bouton « Rapport » de l’application (périmètre courant)
# =============================================================================
from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd
import plotly.io as pio

import core

CHEMIN_RAPPORT = Path("rapport.html")
# Le rapport est le document DIFFUSÉ : son titre parle le vocabulaire du
# comité — deux familles de dossiers, pas de types fins.
TITRE_RAPPORT = "Activité RFP & Due Diligence"

# Indicateurs mis en avant sur la couverture, dans cet ordre.
CLES_COUVERTURE = ("questionnaires", "dd", "rfp", "aum")
# Blocs qui ouvrent la vue d’ensemble, en pleine largeur et avant les chiffres.
CLES_OUVERTURE = ("decomposition", "trimestre")
# Blocs repris dans les constats quand aucun n’est calculable.
CLES_REPLI = ("flux_famille", "volume_annuel", "resultats_rfp", "rfp_succes",
              "dd_expertise", "aum_annuel", "esg_evolution")

# Espace insécable : le séparateur de core.py, devant une unité comme devant
# le signe %. Une seule convention pour tout le produit.
ESP = core.ESP_UNITE

# Un état d’appel d’offres = un ton du bleu, déjà émis en variable par core.py.
# Le ton n’est jamais seul : le libellé et la valeur l’accompagnent toujours.
VAR_ETAT = {"en_cours": "--redaction", "en_attente": "--attente", "gagnes": "--gagne",
            "perdus": "--perdu", "sans_suite": "--sans-suite"}

# Une variation se lit à son signe, à sa flèche ET à son mot — jamais à sa
# couleur.
FLECHES = {"hausse": "▲", "baisse": "▼", "plat": ""}
MOTS_SENS = {"bon": "favorable", "mauvais": "défavorable", "neutre": "sans effet"}


def bibliotheque_plotly() -> str:
    """Code source de plotly.js, embarqué dans le rapport.

    L’emplacement de la bibliothèque a changé au fil des versions de Plotly :
    on essaie les trois points d’accès connus plutôt que d’en supposer un.
    """
    try:                                  # Plotly <= 6
        return pio.get_plotlyjs()
    except AttributeError:
        pass
    try:                                  # Plotly >= 7
        from plotly.offline import get_plotlyjs
        return get_plotlyjs()
    except Exception:
        pass
    import plotly                         # dernier recours : le fichier livré
    fichier = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if fichier.exists():
        return fichier.read_text(encoding="utf-8")
    raise RuntimeError(
        "Impossible de localiser plotly.min.js dans l’installation de Plotly ; "
        "le rapport autonome ne peut pas être généré. Réinstaller le paquet plotly."
    )


# =============================================================================
#  FEUILLE DE STYLE
# -----------------------------------------------------------------------------
#  Les couleurs viennent toutes de core.jetons_css(':root') : une teinte, ses
#  tons (--b-3 … --b-100). Trois règles, comme à l’écran :
#    1. La hiérarchie est typographique — des filets d’un pixel et du vide.
#    2. Sous 18 px, l’encre est à 72 % au minimum ; les tons plus clairs ne
#       portent que des traits, des filets et des aplats de figure.
#    3. Un état ne se lit jamais à sa seule couleur.
# =============================================================================
CSS = r"""
*,*::before,*::after{box-sizing:border-box}
:root{
  --duree:200ms;--duree-lente:380ms;--courbe:cubic-bezier(.22,1,.36,1);
  --rail:236px;--page:1120px;--gouttiere:44px;
}
@media (prefers-reduced-motion:reduce){
  :root{--duree:0ms;--duree-lente:0ms}
  *,*::before,*::after{animation:none!important;transition-duration:0ms!important}
  html{scroll-behavior:auto}
}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--blanc);color:var(--ink);font-family:var(--police);
  font-size:15px;line-height:1.55;font-feature-settings:"cv05","ss01";
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  font-variant-numeric:tabular-nums lining-nums}
::selection{background:var(--b-12);color:var(--ink)}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px;border-radius:1px}
*{scrollbar-width:thin;scrollbar-color:var(--b-22) transparent}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--b-22);border-radius:99px;
  border:3px solid var(--blanc);background-clip:content-box}
h1,h2,h3,h4,p,dl,dd,ul{margin:0}

/* Micro-libellé : capitales espacées, jamais sous 72 % d’encre. */
.cle{font-size:10.5px;font-weight:620;letter-spacing:.15em;text-transform:uppercase;
  color:var(--b-72)}
.cle--ink{color:var(--ink)}
.serif{font-family:var(--police-serif);font-weight:400;
  font-variant-numeric:lining-nums tabular-nums}

/* ------------------------------------------------------------------ rail --- */
.rail{position:fixed;left:0;top:0;bottom:0;width:var(--rail);z-index:20;
  display:flex;flex-direction:column;gap:20px;padding:26px 22px 20px;
  background:var(--blanc);border-right:1px solid var(--b-12);overflow-y:auto}
.rail__marque{display:block;height:26px;color:var(--ink)}
.rail__marque svg{height:100%;width:auto;display:block}
.rail__produit{margin-top:11px;padding-top:10px;border-top:1px solid var(--b-12)}
.rail__nav{display:flex;flex-direction:column;gap:1px;flex:1 1 auto;min-height:0;
  overflow-y:auto;margin:0 -8px;padding:0 8px}
.rail__partie{padding:14px 0 6px;font-size:10px;font-weight:620;letter-spacing:.15em;
  text-transform:uppercase;color:var(--b-72)}
.rail__partie:first-child{padding-top:0}
.lien{display:flex;align-items:baseline;gap:10px;width:100%;padding:7px 8px;
  border:0;background:none;font:inherit;font-size:13.5px;text-align:left;
  color:var(--b-72);cursor:pointer;border-radius:2px;
  transition:color var(--duree) var(--courbe),background var(--duree) var(--courbe)}
.lien:hover{color:var(--ink);background:var(--b-6)}
.lien[aria-current="page"]{color:var(--ink);font-weight:560;background:var(--b-3);
  box-shadow:inset 2px 0 0 var(--ink)}
.lien__num{flex:none;width:17px;font-size:10.5px;font-weight:620;letter-spacing:.06em;
  color:var(--b-72);font-variant-numeric:tabular-nums}
.lien[aria-current="page"] .lien__num{color:var(--ink)}
.rail__barre{display:flex;align-items:center;gap:8px;padding-top:14px;
  border-top:1px solid var(--b-12)}
.rail__barre button{width:32px;height:28px;padding:0;border:1px solid var(--b-22);
  background:var(--blanc);color:var(--ink);font:inherit;font-size:14px;line-height:1;
  cursor:pointer;border-radius:2px;
  transition:border-color var(--duree) var(--courbe)}
.rail__barre button:hover:not(:disabled){border-color:var(--ink)}
.rail__barre button:disabled{color:var(--b-72);border-color:var(--b-12);cursor:default}
.rail__compteur{margin-left:auto;font-size:12px;letter-spacing:.06em;color:var(--b-72);
  font-variant-numeric:tabular-nums}
.rail__pied{padding-top:14px;border-top:1px solid var(--b-12);font-size:12px;
  line-height:1.65;color:var(--b-72)}
.rail__pied b{color:var(--ink);font-weight:620}

/* ----------------------------------------------------------------- pages --- */
main{margin-left:var(--rail)}
.page{display:none;max-width:var(--page);margin:0 auto;
  padding:46px var(--gouttiere) 104px}
.page.active{display:block;animation:monter var(--duree-lente) var(--courbe) both}
@keyframes monter{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}

.tete{padding-bottom:14px;border-bottom:1px solid var(--b-22);margin-bottom:8px}
.tete__ligne{display:flex;align-items:baseline;gap:24px;margin-top:11px}
.tete h2{flex:1;font-family:var(--police-serif);font-weight:400;font-size:31px;
  line-height:1.15;letter-spacing:-.01em;color:var(--ink)}
.tete__compte{flex:none;font-size:12.5px;color:var(--b-72)}

/* ------------------------------------------------------------ couverture --- */
.page.couv.active{display:flex;flex-direction:column;justify-content:center;
  min-height:calc(100vh - 92px)}
.couv__logo{width:108px;color:var(--ink)}
.couv__logo svg{width:100%;height:auto;display:block}
.couv__maison{margin-top:30px}
.couv h1{margin-top:16px;font-family:var(--police-serif);font-weight:400;
  font-size:clamp(33px,4.6vw,56px);line-height:1.08;letter-spacing:-.014em;
  color:var(--ink);max-width:24ch;text-wrap:balance}
.couv__periode{margin-top:20px;font-size:14px;color:var(--b-72)}
.couv__portee{margin-top:6px;font-size:13px;line-height:1.6;color:var(--b-72);
  max-width:82ch}
.couv__chiffres{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));
  gap:0 36px;margin-top:54px;border-top:1px solid var(--b-22)}
.chiffre{padding:18px 0 0;min-width:0}
.chiffre__v{margin-top:9px;font-family:var(--police-serif);font-weight:400;
  font-size:37px;line-height:1.02;color:var(--ink);
  font-variant-numeric:lining-nums tabular-nums}
.chiffre__d{margin-top:8px;font-size:12.5px;line-height:1.5;color:var(--b-72)}

/* -------------------------------------------------------------- rubrique --- */
.rubrique{margin-top:54px;padding-top:28px;border-top:1px solid var(--b-12)}
.rubrique--nue{border-top:0;padding-top:0}
.rubrique__cle{margin-bottom:22px}
.rubrique__intro{margin:-10px 0 24px;font-family:var(--police-serif);font-size:18px;
  line-height:1.5;color:var(--ink);max-width:74ch;text-wrap:pretty}

/* ------------------------------------------------------------- analyses ---- */
.analyse{padding-top:36px;margin-top:36px;border-top:1px solid var(--b-12)}
.analyse--premiere{padding-top:0;margin-top:0;border-top:0}
.analyse__tete{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;
  align-items:baseline}
.analyse__titre{font-size:16px;font-weight:600;letter-spacing:-.008em;color:var(--ink)}
.analyse__compte{font-size:12px;color:var(--b-72);white-space:nowrap}
.analyse__accroche{margin:9px 0 6px;font-family:var(--police-serif);font-size:18px;
  line-height:1.5;color:var(--ink);max-width:74ch;text-wrap:pretty}
.analyse__note{margin-top:16px;padding-top:12px;border-top:1px solid var(--b-12);
  font-size:12.5px;line-height:1.6;color:var(--b-72);max-width:96ch}
.figure{width:100%;min-width:0;margin-top:10px}
.js-plotly-plot{min-width:0}

details{margin-top:16px;padding-top:11px;border-top:1px solid var(--b-12)}
summary{display:flex;align-items:baseline;gap:8px;list-style:none;cursor:pointer;
  font-size:12.5px;color:var(--b-72);
  transition:color var(--duree) var(--courbe)}
summary::-webkit-details-marker{display:none}
summary::before{content:"+";font-size:13px;font-weight:620;line-height:1}
details[open] summary::before{content:"−"}
summary:hover{color:var(--ink)}

.tableau{overflow-x:auto;margin-top:14px}
/* Un bloc SANS figure est un tableau : il tient dans la colonne, quitte à
   passer à la ligne — on ne fait pas défiler une réponse. */
.tableau--pleine{overflow-x:visible}
.tableau--pleine table.donnees{font-size:12.5px}
.tableau--pleine th,.tableau--pleine td{white-space:normal;overflow-wrap:anywhere;
  hyphens:auto;padding-left:12px}
.tableau--pleine th:last-child,.tableau--pleine td:last-child{white-space:nowrap}
table.donnees{width:100%;border-collapse:collapse;font-size:13px}
table.donnees th{padding:8px 0 8px 16px;text-align:right;font-size:10px;font-weight:620;
  letter-spacing:.12em;text-transform:uppercase;color:var(--b-72);white-space:nowrap;
  border-bottom:1px solid var(--b-22)}
table.donnees td{padding:8px 0 8px 16px;text-align:right;color:var(--ink);
  white-space:nowrap;vertical-align:baseline;border-bottom:1px solid var(--b-12)}
table.donnees th:first-child,table.donnees td:first-child{padding-left:0;
  text-align:left;white-space:normal}
table.donnees tbody tr:last-child td{border-bottom:0}

/* ----------------------------------------------------------- indicateurs --- */
.faits{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 48px}
.fait{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px 16px;
  align-items:baseline;padding:14px 0 15px;border-bottom:1px solid var(--b-12)}
.fait__l{font-size:13.5px;color:var(--b-72)}
.fait__v{font-family:var(--police-serif);font-weight:400;font-size:24px;line-height:1;
  color:var(--ink);white-space:nowrap;font-variant-numeric:lining-nums tabular-nums}
.fait__bas{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.fait__delta{font-size:12.5px;font-weight:560;color:var(--ink);white-space:nowrap}
.fait__delta span{font-weight:400;color:var(--b-72)}
.fait__detail{font-size:12.5px;color:var(--b-72)}
.fait__def{grid-column:1/-1;font-size:12px;line-height:1.55;color:var(--b-72);
  max-width:58ch}
.spark{flex:none;margin-left:auto;color:var(--b-52)}
.censure{margin-top:20px;padding-left:16px;border-left:2px solid var(--b-36);
  font-size:12.5px;line-height:1.65;color:var(--b-72);max-width:104ch}

/* ---------------------------------------------------------------- carnet --- */
.carnet__ruban{display:flex;gap:2px;height:10px}
.carnet__seg{min-width:7px}
.carnet__colonnes{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
  gap:22px 18px;margin-top:16px;padding-top:16px;border-top:1px solid var(--b-12)}
.carnet__col{display:flex;flex-direction:column;gap:4px;min-width:0}
.carnet__tete{display:flex;align-items:center;gap:7px}
.carnet__pastille{width:9px;height:9px;flex:none}
.carnet__nom{font-size:12.5px;line-height:1.3;color:var(--b-72)}
.carnet__n{font-family:var(--police-serif);font-weight:400;font-size:28px;line-height:1;
  color:var(--ink);font-variant-numeric:lining-nums tabular-nums}
.carnet__encours{font-size:12.5px;color:var(--b-72)}
.carnet__sens{font-size:11.5px;line-height:1.35;color:var(--b-72)}

.identites{margin-top:28px;border-top:1px solid var(--b-12)}
.identite{display:grid;grid-template-columns:168px minmax(0,1fr);gap:18px;
  align-items:baseline;padding:14px 0;border-bottom:1px solid var(--b-12);
  font-size:13px;line-height:1.6}
.identite__g{color:var(--b-72)}
.identite__v{color:var(--ink)}
.identite__v b{font-family:var(--police-serif);font-weight:400;font-size:19px;
  margin-right:5px;font-variant-numeric:lining-nums tabular-nums}
.identite__n{display:block;margin-top:3px;color:var(--b-72)}

/* -------------------------------------------------------------- constats --- */
.constat{display:grid;grid-template-columns:minmax(0,1fr) 272px;gap:28px;
  align-items:baseline;padding:18px 0;border-bottom:1px solid var(--b-12)}
.constat:first-child{border-top:1px solid var(--b-12)}
.constat__t{font-family:var(--police-serif);font-size:18px;line-height:1.5;
  color:var(--ink);text-wrap:pretty}
.constat__a{font-size:12.5px;line-height:1.55;color:var(--b-72);text-align:right}

/* ---------------------------------------------------------- méthodologie --- */
.def{display:grid;grid-template-columns:212px minmax(0,1fr);gap:18px;
  padding:14px 0;border-bottom:1px solid var(--b-12)}
.def:first-child{border-top:1px solid var(--b-12)}
.def dt{font-size:13.5px;font-weight:560;color:var(--ink)}
.def dd{font-size:13px;line-height:1.6;color:var(--b-72)}
.def dd b{color:var(--ink);font-weight:620}
.liste{margin:8px 0 0;padding-left:18px;font-size:13px;line-height:1.6;
  color:var(--b-72)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
  padding:1px 5px;border-radius:2px;background:var(--b-6);color:var(--ink)}
.clore{margin-top:34px;padding-top:16px;border-top:1px solid var(--b-22);
  font-size:12.5px;line-height:1.65;color:var(--b-72)}

/* ------------------------------------------------------------ adaptation --- */
@media (max-width:1040px){
  .faits{grid-template-columns:minmax(0,1fr);gap:0}
  .constat{grid-template-columns:minmax(0,1fr);gap:7px}
  .constat__a{text-align:left}
}
@media (max-width:980px){
  .rail{position:static;width:auto;height:auto;flex-direction:row;flex-wrap:wrap;
    align-items:center;gap:12px;padding:13px 20px;border-right:0;
    border-bottom:1px solid var(--b-12);overflow:visible}
  .rail__marque{height:22px}
  .rail__produit{margin:0;padding:0 0 0 13px;border-top:0;border-left:1px solid var(--b-22)}
  .rail__barre{margin-left:auto;padding-top:0;border-top:0}
  .rail__nav{flex:1 1 100%;flex-direction:row;overflow-x:auto;gap:2px;margin:0;
    padding:0 0 2px}
  .rail__partie{flex:none;align-self:center;padding:0 6px 0 0}
  .rail__partie:first-child{padding-top:0}
  .lien{width:auto;flex:none;white-space:nowrap}
  .lien[aria-current="page"]{box-shadow:inset 0 -2px 0 var(--ink)}
  .rail__pied{display:none}
  main{margin-left:0}
  .page{padding:28px 20px 72px}
  .couv{min-height:0}
  .couv__chiffres{grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}
  .chiffre__v{font-size:31px}
  .tete h2{font-size:26px}
  .carnet__colonnes{grid-template-columns:repeat(2,minmax(0,1fr))}
  .identite,.def{grid-template-columns:minmax(0,1fr);gap:4px}
  .rubrique{margin-top:44px}
}
@media (max-width:560px){
  .couv__logo{width:92px}
  .carnet__colonnes{grid-template-columns:minmax(0,1fr)}
  table.donnees{font-size:12.5px}
}

/* ------------------------------------------------------------ impression --- */
@page{margin:14mm}
@media print{
  .rail{display:none!important}
  main{margin-left:0}
  body{font-size:10.5pt;background:var(--blanc)}
  .page{display:block!important;max-width:none;padding:0 0 12px;
    break-after:page;animation:none}
  .page:last-child{break-after:auto}
  .page.couv,.page.couv.active{min-height:0;justify-content:flex-start}
  details:not([open]){display:none}
  summary{display:none}
  .analyse,.fait,.constat,.identite,.carnet__col,.def,.chiffre{break-inside:avoid}
  .tete,.rubrique__cle{break-after:avoid}
}
"""


# =============================================================================
#  FRAGMENTS
# =============================================================================
def _e(texte: object) -> str:
    return html.escape(str(texte), quote=True)


def _cle(texte: str, classe: str = "cle") -> str:
    return f'<div class="{classe}">{_e(texte)}</div>'


def _spark(serie: list[float], largeur: int = 88, hauteur: int = 22) -> str:
    """Mini-tendance : un trait, pas un graphique. Les valeurs exactes sont
    dans les analyses ; ce tracé ne sert qu’à donner la forme."""
    points = [float(v) for v in serie if v is not None and pd.notna(v)]
    if len(points) < 4:
        return ""
    mini, maxi = min(points), max(points)
    etendue = (maxi - mini) or 1.0
    n = len(points)
    coords = " ".join(
        f"{1 + i / (n - 1) * (largeur - 2):.1f},"
        f"{hauteur - 1 - (v - mini) / etendue * (hauteur - 2):.1f}"
        for i, v in enumerate(points))
    return (f'<svg class="spark" width="{largeur}" height="{hauteur}" '
            f'viewBox="0 0 {largeur} {hauteur}" aria-hidden="true" focusable="false">'
            f'<polyline points="{coords}" fill="none" stroke="currentColor" '
            f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _delta_html(kpi: core.Kpi) -> str:
    """La variation : signe, flèche et mot. Jamais une couleur."""
    if not kpi.delta_affichage:
        return ""
    if kpi.delta_direction == "plat":
        return f'<span class="fait__delta">{_e(kpi.delta_affichage)}</span>'
    fleche = FLECHES.get(kpi.delta_direction, "")
    mot = MOTS_SENS.get(kpi.delta_sens, "")
    mot_html = f" <span>{_e(mot)}</span>" if mot else ""
    return (f'<span class="fait__delta">{fleche} {_e(kpi.delta_affichage)}'
            f'{mot_html}</span>')


def _fait_html(kpi: core.Kpi) -> str:
    """Un indicateur = un fait : libellé, valeur, variation, définition."""
    morceaux = [f'<div class="fait__l">{_e(kpi.libelle)}</div>',
                f'<div class="fait__v">{_e(kpi.affichage)}</div>']
    bas = _delta_html(kpi)
    if kpi.detail:
        bas += f'<span class="fait__detail">{_e(kpi.detail)}</span>'
    bas += _spark(kpi.serie)
    if bas:
        morceaux.append(f'<div class="fait__bas">{bas}</div>')
    if kpi.aide:
        morceaux.append(f'<div class="fait__def">{_e(kpi.aide)}</div>')
    return f'<div class="fait">{"".join(morceaux)}</div>'


def _indicateurs_html(analyse: core.Analysis) -> str:
    faits = "".join(_fait_html(k) for k in analyse.kpis_rapport)
    fenetre = analyse.stats.get("comparaison")
    comparaison = ""
    if fenetre:
        comparaison = (" Les variations sont mesurées face à la période précédente de "
                       f"même durée ({core.fmt_date(fenetre[0])} → "
                       f"{core.fmt_date(fenetre[1])}).")
    return (f'<div class="faits">{faits}</div>'
            f'<p class="censure">{_e(core.NOTE_CENSURE)}{_e(comparaison)}</p>')


def _carnet_html(analyse: core.Analysis) -> str:
    """Le carnet : cinq états exclusifs, leur effectif et leur encours.

    Le ruban donne les proportions, les colonnes donnent les nombres. Chaque
    aplat est doublé de son libellé et de sa valeur.
    """
    livre = core.carnet(analyse.df)
    if not livre.total:
        return ""
    segments, colonnes = [], []
    for cle, libelle, sens in core.COMPARTIMENTS:
        n, encours = livre.n(cle), livre.encours(cle)
        var = VAR_ETAT.get(cle, "--ink")
        if n:
            segments.append(
                f'<span class="carnet__seg" style="flex:{n} 1 0;background:var({var})" '
                f'title="{_e(libelle)} — {_e(core.pluriel(n, "dossier"))}"></span>')
        colonnes.append(
            f'<div class="carnet__col">'
            f'<div class="carnet__tete">'
            f'<span class="carnet__pastille" style="background:var({var})"></span>'
            f'<span class="carnet__nom">{_e(libelle)}</span></div>'
            f'<div class="carnet__n">{core.fmt_int(n)}</div>'
            f'<div class="carnet__encours">{_e(core.fmt_dec(encours, 0, "M€"))}</div>'
            f'<div class="carnet__sens">{_e(sens)}</div></div>')
    ruban = f'<div class="carnet__ruban">{"".join(segments)}</div>' if segments else ""
    intro = (f'{core.pluriel(livre.total, core.APPEL_OFFRES, core.APPELS_OFFRES)} '
             f'sur la période, dont {core.fmt_int(livre.vivants)} encore '
             f'ouverts — en rédaction chez nous ou en attente de décision du client.')
    identites = "".join(
        f'<div class="identite"><div class="identite__g">{_e(i["grandeur"])}</div>'
        f'<div class="identite__v"><b>{_e(i["valeur"])}</b> = {_e(i["egalite"])}.'
        f'<span class="identite__n">{_e(i["note"])}</span></div></div>'
        for i in core.identites_carnet(analyse.df))
    bloc_identites = f'<div class="identites">{identites}</div>' if identites else ""
    return (f'<p class="rubrique__intro">{intro}</p>{ruban}'
            f'<div class="carnet__colonnes">{"".join(colonnes)}</div>{bloc_identites}')


def _constats_html(analyse: core.Analysis) -> str:
    """Les constats calculés ; à défaut, la lecture de chaque analyse."""
    if analyse.insights:
        lignes = "".join(
            f'<div class="constat"><div class="constat__t">{_e(i.texte)}</div>'
            f'<div class="constat__a">{_e(i.appui)}</div></div>'
            for i in analyse.insights)
    else:
        blocs = [b for cle in CLES_REPLI
                 for b in analyse.blocs if b.cle == cle and not b.hors_rapport]
        blocs = blocs or [b for b in analyse.blocs if not b.hors_rapport][:5]
        lignes = "".join(
            f'<div class="constat"><div class="constat__t">{_e(b.accroche)}</div>'
            f'<div class="constat__a">{_e(b.titre)}</div></div>' for b in blocs)
    return lignes


def _tableau_html(tableau: pd.DataFrame) -> str:
    if tableau is None or tableau.empty:
        return ""
    return tableau.to_html(index=False, escape=True, border=0, na_rep="—",
                           classes="donnees", justify="right")


def _analyse_html(bloc: core.Block, indice: int, premiere: bool = False) -> str:
    """Une analyse : titre, accroche, figure, tableau jumeau, note.

    Le tableau se déplie à la demande, sauf quand le bloc EST un tableau :
    celui-là n’a pas de figure à attendre, il s’affiche.
    """
    tableau = _tableau_html(bloc.tableau)
    if bloc.figure is None:
        corps = f'<div class="tableau tableau--pleine">{tableau}</div>'
        compte = core.pluriel(len(bloc.tableau), "ligne")
    else:
        figure = pio.to_html(bloc.figure, include_plotlyjs=False, full_html=False,
                             config=core.PLOT_CONFIG, div_id=f"figure-{indice}",
                             default_width="100%")
        jumeau = ""
        if tableau:
            jumeau = (f'<details><summary>Voir les données '
                      f'({core.pluriel(len(bloc.tableau), "ligne")})</summary>'
                      f'<div class="tableau">{tableau}</div></details>')
        corps = f'<div class="figure">{figure}</div>{jumeau}'
        compte = ""
    note = f'<div class="analyse__note">{_e(bloc.note)}</div>' if bloc.note else ""
    tete_compte = f'<span class="analyse__compte">{_e(compte)}</span>' if compte else "<span></span>"
    classe = "analyse analyse--premiere" if premiere else "analyse"
    return (f'<section class="{classe}" id="bloc-{_e(bloc.cle)}">'
            f'<div class="analyse__tete"><h3 class="analyse__titre">{_e(bloc.titre)}</h3>'
            f'{tete_compte}</div>'
            f'<p class="analyse__accroche">{_e(bloc.accroche)}</p>'
            f'{corps}{note}</section>')


def _rubrique(libelle: str, corps: str, nue: bool = False) -> str:
    classe = "rubrique rubrique--nue" if nue else "rubrique"
    return (f'<section class="{classe}">{_cle(libelle, "cle rubrique__cle")}'
            f'{corps}</section>')


def _methodologie_html(analyse: core.Analysis) -> str:
    rapport, stats = analyse.rapport, analyse.stats
    entrees: list[tuple[str, str]] = [
        ("Délai de traitement",
         "Nombre de jours <b>ouvrés</b> entre la date de réception de la demande et la "
         "date d’envoi de la réponse. Les dossiers non envoyés n’entrent dans aucune "
         "statistique de délai."),
        ("Délai cible",
         f"Engagement interne de traitement ({_e(core.sla_libelle(par_famille=True))}). "
         f"Paramétrable dans <code>core.py</code>."),
        ("Taux de succès",
         "Mandats gagnés rapportés aux dossiers tranchés (gagnés + perdus). Les dossiers "
         "en attente de décision sont exclus du dénominateur, jamais comptés comme des "
         "échecs."),
        ("Intervalle de confiance",
         f"Méthode de Wilson à 95{ESP}% pour les proportions ; intervalle de Student à "
         f"95{ESP}% pour les coefficients de régression. Deux intervalles qui se "
         f"recouvrent ne permettent pas de conclure à une différence."),
        ("Limite de lecture", _e(core.NOTE_CENSURE)),
    ]
    modeles: list[tuple[str, str]] = []
    tendance = stats.get("tendance_volume")
    if tendance is not None:
        modeles.append((
            "Tendance du flux mensuel",
            f"Moindres carrés ordinaires du volume mensuel sur le rang du mois (mois en "
            f"cours exclu) : pente {core.fmt_dec(tendance.pente, 2)} "
            f"demande{core.accord(tendance.pente)} par mois, R²{ESP}= "
            f"{core.fmt_dec(tendance.r2, 2)}, {core.fmt_p(tendance.p_value)}, "
            f"n{ESP}= {core.fmt_int(tendance.n)} mois."))
    reg_q = stats.get("regression_questions")
    if reg_q is not None:
        modeles.append((
            "Délai et volume de questions",
            f"Pente {core.fmt_dec(reg_q.pente, 4)} jour par question "
            f"(IC 95{ESP}% : {core.fmt_dec(reg_q.ic_pente[0], 4)} à "
            f"{core.fmt_dec(reg_q.ic_pente[1], 4)}), R²{ESP}= {core.fmt_dec(reg_q.r2, 2)}, "
            f"{core.fmt_p(reg_q.p_value)}, n{ESP}= {core.fmt_int(reg_q.n)} dossiers."))
    modele = stats.get("modele_delai")
    if modele is not None:
        detail = " ; ".join(
            f"{_e(c.nom)} : {core.fmt_dec(c.valeur, 2)} j ({core.fmt_p(c.p_value)})"
            for c in modele.explicatives)
        modeles.append((
            "Facteurs du délai (régression multiple)",
            f"R² ajusté{ESP}= {core.fmt_dec(modele.r2_ajuste, 2)}, "
            f"n{ESP}= {core.fmt_int(modele.n)}. {detail}."))
    modeles.append((
        "Calcul des p-values",
        "Loi de Student bilatérale évaluée par la fonction bêta incomplète régularisée, "
        "sans dépendance externe ; valeurs vérifiées contre les tables de référence à "
        "l’exécution de <code>python core.py</code>."))

    def _dl(paires: list[tuple[str, str]]) -> str:
        return "<dl>" + "".join(
            f'<div class="def"><dt>{_e(terme)}</dt><dd>{texte}</dd></div>'
            for terme, texte in paires) + "</dl>"

    corps = [_rubrique("Définitions", _dl(entrees), nue=True),
             _rubrique("Modèles statistiques", _dl(modeles))]

    if rapport is not None:
        qualite = [(
            "Source",
            f"<b>{_e(rapport.source)}</b>. "
            f"{core.pluriel(rapport.n_lignes_source, 'ligne')} "
            f"lue{core.accord(rapport.n_lignes_source)}, "
            f"<b>{core.fmt_int(rapport.n_lignes_retenues)}</b> "
            f"retenue{core.accord(rapport.n_lignes_retenues)} après normalisation.")]
        if rapport.alertes:
            qualite.append((
                "Anomalies relevées à l’import",
                '<ul class="liste">'
                + "".join(f"<li>{_e(a)}</li>" for a in rapport.alertes) + "</ul>"))
        else:
            qualite.append(("Anomalies relevées à l’import",
                            "Aucune anomalie détectée à l’import."))
        corps.append(_rubrique("Qualité des données", _dl(qualite)))

    if analyse.erreurs:
        corps.append(_rubrique(
            "Blocs non construits",
            _dl([("Détail", '<ul class="liste">'
                  + "".join(f"<li>{_e(e)}</li>" for e in analyse.erreurs) + "</ul>")])))

    corps.append(
        '<p class="clore">Document autonome : la bibliothèque de tracé, les deux polices '
        'et la marque sont embarquées. Les figures restent interactives hors ligne, et '
        'l’impression produit une page par section.</p>')
    return "".join(corps)


# =============================================================================
#  SCRIPT EMBARQUÉ — pagination et mesure des figures
# =============================================================================
SCRIPT = r"""
(function () {
  var pages = Array.prototype.slice.call(document.querySelectorAll('.page'));
  var liens = Array.prototype.slice.call(document.querySelectorAll('.lien'));
  var compteur = document.getElementById('compteur');
  var precedent = document.getElementById('precedent');
  var suivant = document.getElementById('suivant');
  var courante = -1;

  /* Plotly mesure à zéro dans un conteneur masqué : une figure peinte hors
     écran sort écrasée, et les marges calculées pour ses titres d’axes sont
     fausses. Un relayout complet à l’affichage les recalcule — un simple
     resize, lui, garderait les marges de la mesure à zéro. */
  function redimensionner(page) {
    if (!page || !window.Plotly) return;
    var figures = page.querySelectorAll('.js-plotly-plot');
    for (var i = 0; i < figures.length; i++) {
      try { window.Plotly.relayout(figures[i], {autosize: true}); } catch (e) {}
    }
  }

  function afficher(i, silencieux) {
    var cible = Math.max(0, Math.min(pages.length - 1, i));
    if (cible === courante) { redimensionner(pages[cible]); return; }
    courante = cible;
    for (var k = 0; k < pages.length; k++) {
      pages[k].classList.toggle('active', k === courante);
    }
    for (var l = 0; l < liens.length; l++) {
      if (l === courante) { liens[l].setAttribute('aria-current', 'page'); }
      else { liens[l].removeAttribute('aria-current'); }
    }
    compteur.textContent = ('0' + courante).slice(-2) + ' / '
                         + ('0' + (pages.length - 1)).slice(-2);
    precedent.disabled = courante === 0;
    suivant.disabled = courante === pages.length - 1;
    if (!silencieux) {
      window.scrollTo(0, 0);
      if (liens[courante] && liens[courante].scrollIntoView) {
        try { liens[courante].scrollIntoView({block: 'nearest', inline: 'nearest'}); }
        catch (e) {}
      }
    }
    if (history.replaceState) { history.replaceState(null, '', '#page-' + courante); }
    var page = pages[courante];
    requestAnimationFrame(function () { redimensionner(page); });
    setTimeout(function () { redimensionner(page); }, 420);
  }

  liens.forEach(function (lien, k) {
    lien.addEventListener('click', function () { afficher(k); });
  });
  precedent.addEventListener('click', function () { afficher(courante - 1); });
  suivant.addEventListener('click', function () { afficher(courante + 1); });

  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var actif = document.activeElement;
    if (actif && actif.matches && actif.matches('input,textarea,select')) return;
    if (e.key === 'ArrowRight' || e.key === 'PageDown') { afficher(courante + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { afficher(courante - 1); e.preventDefault(); }
    else if (e.key === 'Home') { afficher(0); e.preventDefault(); }
    else if (e.key === 'End') { afficher(pages.length - 1); e.preventDefault(); }
    else if (/^[0-9]$/.test(e.key)) { afficher(parseInt(e.key, 10)); e.preventDefault(); }
  });

  window.addEventListener('resize', function () { redimensionner(pages[courante]); });
  window.addEventListener('beforeprint', function () {
    for (var k = 0; k < pages.length; k++) { redimensionner(pages[k]); }
  });

  var depart = (location.hash.match(/^#page-(\d+)$/) || [])[1];
  afficher(depart ? parseInt(depart, 10) : 0, true);
})();
"""


# =============================================================================
#  ASSEMBLAGE
# =============================================================================
def construire_rapport(analyse: core.Analysis, titre: str = TITRE_RAPPORT) -> str:
    """Retourne le document HTML complet sous forme de chaîne.

    Le rapport est le document DIFFUSÉ : il s’en tient aux deux familles du
    pilotage, RFP et due diligence. Les blocs et indicateurs marqués
    `hors_rapport` — le détail RFI / DDQ — restent à l’écran.

    Il est en deux parties, comme l’application : « Direction » se lit debout,
    « Analyse » répond aux pourquoi.
    """
    if analyse.vide:
        raise ValueError("Aucune donnée à exporter : la sélection est vide.")

    parties = analyse.parties_rapport()
    sections = [s for _, _, _, groupe in parties for s in groupe]
    n_analyses = sum(len(analyse.section(cle, pour_rapport=True)) for cle, _ in sections)
    pages: list[str] = []
    liens: list[str] = []
    indice_figure = 0

    # ---- Page 00 : couverture -------------------------------------------
    par_cle = {k.cle: k for k in analyse.kpis_rapport}
    choisis = [par_cle[c] for c in CLES_COUVERTURE if c in par_cle] or analyse.kpis_rapport[:4]
    chiffres = "".join(
        f'<div class="chiffre">{_cle(kpi.libelle)}'
        f'<div class="chiffre__v">{_e(kpi.affichage)}</div>'
        f'<div class="chiffre__d">{_e(kpi.detail)}</div></div>'
        for kpi in choisis[:4])
    logo_empile = core.logo_svg("empile")
    marque_couv = f'<div class="couv__logo">{logo_empile}</div>' if logo_empile else ""
    # Le périmètre ne s’affiche que s’il restreint quelque chose : sur
    # l’historique complet, il répéterait la période déjà indiquée.
    portee = (f'<p class="couv__portee">Périmètre : {_e(analyse.filtres.describe())}</p>'
              if analyse.filtres.actif else "")
    liens.append('<button class="lien" type="button">'
                 '<span class="lien__num">00</span><span>Couverture</span></button>')
    pages.append(
        '<section class="page couv" aria-label="Couverture">'
        f'{marque_couv}'
        f'{_cle(f"{core.MARQUE_NOM} · {core.MARQUE_ACTIVITE}", "cle couv__maison")}'
        f'<h1>{_e(titre)}</h1>'
        f'<p class="couv__periode">{_e(analyse.periode)}'
        f'{ESP}· {core.pluriel(len(analyse.df), "demande")}'
        f'{ESP}· {core.pluriel(n_analyses, "analyse")}</p>'
        f'{portee}'
        f'<div class="couv__chiffres">{chiffres}</div>'
        '</section>')

    # ---- Pages 01..n : une par section, groupées en deux parties ---------
    numero = 0
    for _, nom_partie, accroche_partie, groupe in parties:
        liens.append(f'<div class="rail__partie">{_e(nom_partie)}</div>')
        for cle, libelle in groupe:
            numero += 1
            blocs = analyse.section(cle, pour_rapport=True)
            corps: list[str] = []
            if cle == "synthese":
                # LA DÉCOMPOSITION D’ABORD : d’où viennent les dossiers et où
                # ils en sont. C’est la question du comité, avant les chiffres.
                ouverture: list[str] = []
                for phare in CLES_OUVERTURE:
                    bloc = next((b for b in blocs if b.cle == phare), None)
                    if bloc is None:
                        continue
                    ouverture.append(_analyse_html(bloc, indice_figure,
                                                   premiere=not ouverture))
                    indice_figure += 1
                    blocs = [b for b in blocs if b is not bloc]
                if ouverture:
                    corps.append('<section class="rubrique rubrique--nue">'
                                 f'{"".join(ouverture)}</section>')
                carnet = _carnet_html(analyse)
                if carnet:
                    corps.append(_rubrique("Le carnet", carnet, nue=not corps))
                corps.append(_rubrique("Les indicateurs", _indicateurs_html(analyse),
                                       nue=not corps))
                constats = _constats_html(analyse)
                if constats:
                    corps.append(_rubrique("Ce qu’il faut retenir", constats))
                if blocs:
                    analyses = "".join(
                        _analyse_html(b, indice_figure + i, premiere=(i == 0))
                        for i, b in enumerate(blocs))
                    indice_figure += len(blocs)
                    corps.append(_rubrique("Les analyses", analyses))
            else:
                analyses = "".join(
                    _analyse_html(b, indice_figure + i, premiere=(i == 0))
                    for i, b in enumerate(blocs))
                indice_figure += len(blocs)
                corps.append(f'<section class="rubrique rubrique--nue">{analyses}</section>')

            entete = (
                f'<header class="tete">'
                f'{_cle(f"{numero:02d} — {nom_partie} · {accroche_partie}")}'
                f'<div class="tete__ligne"><h2>{_e(libelle)}</h2>'
                f'<span class="tete__compte">'
                f'{core.pluriel(len(analyse.section(cle, pour_rapport=True)), "analyse")}'
                f'</span></div></header>')
            liens.append(f'<button class="lien" type="button">'
                         f'<span class="lien__num">{numero:02d}</span>'
                         f'<span>{_e(libelle)}</span></button>')
            pages.append(f'<section class="page">{entete}{"".join(corps)}</section>')

    # ---- Dernière page : méthodologie ------------------------------------
    numero += 1
    liens.append(f'<button class="lien" type="button">'
                 f'<span class="lien__num">{numero:02d}</span>'
                 f'<span>Méthodologie</span></button>')
    pages.append(
        f'<section class="page">'
        f'<header class="tete">{_cle(f"{numero:02d} — Comment lire ce document")}'
        f'<div class="tete__ligne"><h2>Méthodologie et qualité des données</h2>'
        f'</div></header>{_methodologie_html(analyse)}</section>')

    logo_rail = core.logo_svg("horizontal")
    marque_rail = (f'<span class="rail__marque">{logo_rail}</span>' if logo_rail
                   else f'<span class="rail__marque cle cle--ink">{_e(core.MARQUE_NOM)}</span>')
    genere = analyse.genere_le.strftime("%d/%m/%Y à %H:%M")

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titre)} — rapport du {analyse.genere_le:%d/%m/%Y}</title>
<meta name="author" content="{_e(core.MARQUE_NOM)} {_e(core.MARQUE_ACTIVITE)}">
<style>{core.police_css()}{core.jetons_css(':root')}{CSS}</style>
<!-- Plotly doit précéder les figures : chacune s’initialise par un script en
     ligne posé dans la page. -->
<script>{bibliotheque_plotly()}</script>
</head>
<body>
<aside class="rail">
  <div>
    {marque_rail}
    <div class="cle rail__produit">{_e(core.MARQUE_PRODUIT)}</div>
  </div>
  <nav class="rail__nav" aria-label="Pages du rapport">{"".join(liens)}</nav>
  <div class="rail__barre">
    <button id="precedent" type="button" aria-label="Page précédente">←</button>
    <button id="suivant" type="button" aria-label="Page suivante">→</button>
    <span class="rail__compteur" id="compteur">00 / 00</span>
  </div>
  <div class="rail__pied">
    <b>{core.fmt_int(len(analyse.df))}</b> demandes<br>
    {_e(analyse.periode)}<br>
    Édité le {genere}
  </div>
</aside>

<main>{"".join(pages)}</main>

<script>{SCRIPT}</script>
</body>
</html>"""


def ecrire_rapport(analyse: core.Analysis, chemin: str | Path = CHEMIN_RAPPORT,
                   titre: str = TITRE_RAPPORT) -> Path:
    """Écrit le rapport sur le disque et retourne son chemin."""
    chemin = Path(chemin)
    chemin.write_text(construire_rapport(analyse, titre), encoding="utf-8")
    return chemin


def main() -> None:
    """Génération en ligne de commande, sur l’historique complet."""
    parseur = argparse.ArgumentParser(
        description="Rapport d’activité RFP & due diligence, autonome.")
    parseur.add_argument("--sortie", default=str(CHEMIN_RAPPORT),
                         help="chemin du fichier HTML produit")
    options = parseur.parse_args()

    print("Chargement des données…")
    df, rapport = core.load_data()
    # Aucune borne : le rapport en ligne de commande couvre tout l’historique,
    # et la couverture n’a pas à répéter une période déjà affichée.
    print(f"Analyse de {core.fmt_int(len(df))} demandes…")
    analyse = core.build_analysis(df, core.Filters(), rapport)
    if analyse.erreurs:
        print("Blocs non construits :", *analyse.erreurs, sep="\n  - ")
    chemin = ecrire_rapport(analyse, options.sortie)
    poids = chemin.stat().st_size / 1_048_576
    # Compter ce qui part vraiment : les blocs d’écran ne sont pas dans le fichier.
    blocs = [b for cle, _ in analyse.sections_rapport
             for b in analyse.section(cle, pour_rapport=True)]
    figures = sum(1 for b in blocs if b.figure is not None)
    tables = len(blocs) - figures
    print(f"Rapport écrit : {chemin.resolve()}  ({poids:.1f} Mo, "
          f"{core.pluriel(figures, 'figure')}, "
          f"{core.pluriel(tables, 'tableau', 'tableaux')}, "
          f"{core.pluriel(len(analyse.kpis_rapport), 'indicateur')})")
    ecran = len(analyse.blocs) - len(blocs)
    if ecran:
        print(f"{core.pluriel(ecran, 'bloc')} et "
              f"{core.pluriel(len(analyse.kpis) - len(analyse.kpis_rapport), 'indicateur')} "
              f"réservés à l’écran (détail RFI / DDQ) n’y figurent pas.")
    print("Ouvrable d’un double-clic, sans Python ni connexion réseau.")


if __name__ == "__main__":
    main()
