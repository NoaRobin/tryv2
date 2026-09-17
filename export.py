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
import datetime as dt
import html
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.io as pio

import core

CHEMIN_RAPPORT = Path("rapport.html")
# Le rapport est le document DIFFUSÉ : son titre parle le vocabulaire du
# comité — deux familles de dossiers, pas de types fins.
TITRE_RAPPORT = "Activité RFP & Due Diligence"

# Indicateurs mis en avant sur la couverture, dans cet ordre.
CLES_COUVERTURE = ("questionnaires", "dd", "rfp", "aum")

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
MOTS_SENS = {"bon": "favorable", "mauvais": "défavorable", "neutre": ""}


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
  --rail:236px;--page:1180px;--gouttiere:56px;
  --lecture:660px;      /* la colonne de lecture, comme à l’écran */
  --marge:300px;        /* la colonne des repères */
}
@media (prefers-reduced-motion:reduce){
  :root{--duree:0ms;--duree-lente:0ms}
  *,*::before,*::after{animation:none!important;transition-duration:0ms!important}
  html{scroll-behavior:auto}
}
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
.rail__tete{min-width:0}
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
  min-height:760px}
.couv__logo{width:108px;color:var(--ink)}
.couv__logo svg{width:100%;height:auto;display:block}
.couv__maison{margin-top:30px}
.couv h1{margin-top:16px;font-family:var(--police-serif);font-weight:400;
  font-size:52px;line-height:1.08;letter-spacing:-.014em;
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

.tableau{margin-top:14px}
/* Un bloc SANS figure est un tableau : il tient dans la colonne, quitte à
   passer à la ligne — on ne fait pas défiler une réponse. */
.tableau--pleine table.donnees{table-layout:fixed;font-size:12.5px}
.tableau--pleine table.donnees th,.tableau--pleine table.donnees td{white-space:normal;
  overflow-wrap:break-word;hyphens:auto;padding-left:12px}
.tableau--pleine table.donnees th:first-child,
.tableau--pleine table.donnees td:first-child{width:17%}
/* Un tableau triable a des cellules courtes : il se dimensionne seul, rien n’y
   passe à la ligne. */
.tableau--pleine table.triable{table-layout:auto}
.tableau--pleine table.triable th,.tableau--pleine table.triable td{white-space:nowrap;
  width:auto;padding-left:10px}
.tableau--pleine table.triable th:first-child,.tableau--pleine table.triable td:first-child{
  padding-left:0;white-space:nowrap}
table.triable th[role="button"]{cursor:pointer;user-select:none}
table.triable th[role="button"]:hover{color:var(--ink)}
table.triable th[aria-sort]{color:var(--ink);box-shadow:inset 0 -2px 0 var(--ink)}
table.triable th[aria-sort="ascending"]::after{content:" ↑"}
table.triable th[aria-sort="descending"]::after{content:" ↓"}
.tableau--pleine table.donnees th:last-child,
.tableau--pleine table.donnees td:last-child{width:10%;white-space:nowrap}
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
/* Une liste de faits, pas une grille de tuiles : libellé, valeur, variation.
   Les filets font les colonnes ; les définitions sont dans la marge. */
.faits{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 40px}
.fait{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:10px;
  padding:12px 0;border-bottom:1px solid var(--b-12)}
.fait__label{font-size:13.5px;color:var(--b-72)}
.fait__valeur{font-family:var(--police-serif);font-size:23px;color:var(--ink);line-height:1;
  font-variant-numeric:lining-nums tabular-nums;white-space:nowrap}
.fait__bas{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  margin-top:-2px}
.fait__detail{font-size:12.5px;color:var(--b-72)}
.fait__delta{font-size:12.5px;color:var(--ink);font-weight:560;white-space:nowrap}
.fait__delta span{color:var(--b-72);font-weight:400}
.fait .spark{color:var(--b-52);flex:none;margin-left:auto}
.censure{margin-top:20px;padding-left:16px;border-left:2px solid var(--b-36);
  font-size:12.5px;line-height:1.65;color:var(--b-72)}

/* ---------------------------------------------------------------- carnet --- */
.carnet{margin-top:6px}
.carnet__rubans{display:grid;gap:3px}
.carnet__ligne{display:flex;align-items:center;gap:10px}
.carnet__ligne .cle{width:62px;flex:none;text-align:right;font-size:9.5px}
.carnet__ruban{flex:1;display:flex;gap:2px;height:10px}
/* Deux états se distinguent aussi par leur texture : ce qui est encore chez
   nous est hachuré, ce qui n’a pas abouti est un contour vide. */
.texture-redaction{background-image:repeating-linear-gradient(135deg,
  var(--blanc) 0 1.5px,transparent 1.5px 4px)!important}
.texture-sanssuite{background-color:var(--blanc)!important;
  box-shadow:inset 0 0 0 1px var(--b-36)}
.carnet__colonnes{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:1px;
  margin-top:14px;border-top:1px solid var(--b-12);padding-top:12px}
.carnet__col{display:grid;grid-template-rows:auto auto auto 1fr;gap:3px;padding-right:12px;
  align-content:start}
.carnet__col-tete{display:flex;align-items:flex-start;gap:6px;min-height:30px}
.carnet__pastille{width:9px;height:9px;flex:none;margin-top:4px}
.carnet__nom{font-size:12px;color:var(--b-72);line-height:1.3}
.carnet__n{font-family:var(--police-serif);font-size:26px;color:var(--ink);line-height:1;
  font-variant-numeric:lining-nums tabular-nums}
.carnet__encours{font-size:12.5px;color:var(--b-72)}
.carnet__sens{font-size:11.5px;color:var(--b-72);line-height:1.35}
.identites{display:grid;gap:14px;margin-top:22px}
.identite{display:grid;grid-template-columns:148px minmax(0,1fr);gap:16px;
  align-items:baseline;font-size:13px}
.identite__g{color:var(--b-72)}
.identite__v{color:var(--ink)}
.identite__v b{font-family:var(--police-serif);font-size:17px;font-weight:400;margin-right:4px}
.identite__n{display:block;margin-top:3px;color:var(--b-72)}

/* -------------------------------------------------------------- constats --- */
.constat{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;
  align-items:baseline;padding:14px 0;border-bottom:1px solid var(--b-12)}
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

/* ============================================================== l’écran ===
   Les composants de la vue d’ensemble sont ceux de l’application, règle pour
   règle : la lecture du lundi matin s’imprime telle qu’elle s’affiche. */
.lede{font-family:var(--police-serif);font-size:31px;line-height:1.32;
  letter-spacing:-.012em;color:var(--ink);margin:0;text-wrap:pretty;
  font-variant-numeric:lining-nums tabular-nums}
.lede .attenue{color:var(--b-72)}
.lede b{font-weight:500}
.prose{font-family:var(--police-serif);font-size:20px;line-height:1.5;color:var(--ink);
  margin:0;text-wrap:pretty;font-variant-numeric:lining-nums tabular-nums}
.prose b{font-weight:500}
.note{font-size:13px;line-height:1.6;color:var(--b-72)}
.note b,.note strong{color:var(--ink);font-weight:620}
.num{font-variant-numeric:tabular-nums lining-nums}

/* La grille de lecture : une colonne de texte, une marge qui parle. */
.lecture{display:grid;grid-template-columns:minmax(0,var(--lecture)) var(--marge);
  gap:var(--gouttiere);align-items:start}
.lecture>.marge-col{padding-top:4px}
.bloc{display:grid;grid-template-columns:minmax(0,var(--lecture)) var(--marge);
  gap:var(--gouttiere);align-items:start;padding:40px 0 0;margin-top:40px;
  border-top:1px solid var(--b-12)}
.bloc:first-of-type{margin-top:36px}
.bloc__tete{display:flex;align-items:baseline;gap:12px;margin-bottom:18px}
.bloc__num{font-size:10.5px;font-weight:620;letter-spacing:.12em;color:var(--b-72);
  font-variant-numeric:tabular-nums}
.bloc__corps,.bloc__marge{min-width:0}
.bloc__pied{margin-top:12px;display:flex;justify-content:space-between;gap:24px}
.marge-titre{font-size:10.5px;font-weight:620;letter-spacing:.15em;text-transform:uppercase;
  color:var(--b-72);margin-bottom:10px}
.marge-texte{font-size:13px;line-height:1.62;color:var(--b-72);margin:0 0 14px}
.marge-texte:last-child{margin-bottom:0}
.marge-texte b{color:var(--ink);font-weight:620}

/* L’ouverture : la phrase calculée, puis les trois chiffres du matin. */
.ouverture{margin-bottom:4px}
.matin{display:flex;gap:8px 30px;flex-wrap:wrap;margin-top:22px;font-size:13.5px;
  color:var(--b-72);align-items:baseline}
.matin>span{white-space:nowrap}
.matin b{color:var(--ink);font-weight:560}
.barres{display:flex;align-items:flex-end;gap:2px;height:46px;margin:4px 0 6px}
.barres i{flex:1;background:var(--b-52);min-height:1px;display:block}
.barres i.encours{background:repeating-linear-gradient(135deg,var(--b-36) 0 2px,
  transparent 2px 4px);border-top:1px solid var(--b-36)}
.barres-pied{display:flex;justify-content:space-between;font-size:11px;color:var(--b-72)}

/* Une durée : un trait plein sur un filet, puis le nombre de jours. */
.duree{display:flex;gap:10px;align-items:center}
.jauge{display:block;width:84px;height:4px;background:var(--b-12);position:relative;flex:none}
.jauge i{display:block;height:100%;background:var(--b-52)}
.jauge--alerte i{background:var(--ink)}
table.donnees--dossiers th,table.donnees--dossiers td{text-align:left;white-space:normal;
  padding:9px 12px 9px 0}
table.donnees--dossiers th.num,table.donnees--dossiers td.num{text-align:right;
  padding-right:0;white-space:nowrap}
table.donnees--dossiers td.attenue{color:var(--b-72)}
table.donnees--dossiers th:first-child,table.donnees--dossiers td:first-child{padding-left:0}
.cellule-nom{font-weight:500}
.cellule-sous{display:block;font-size:12px;color:var(--b-72);margin-top:1px}

/* Les listes à onglets : gagnés, perdus, sans suite. */
.onglets{display:flex;gap:2px;border-bottom:1px solid var(--b-12);margin-bottom:4px;
  flex-wrap:wrap}
.onglets button{font:inherit;font-size:13.5px;color:var(--b-72);background:none;border:0;
  padding:8px 12px 9px;cursor:pointer;display:flex;align-items:baseline;gap:8px;
  margin-bottom:-1px}
.onglets button:hover{color:var(--ink)}
.onglets button[aria-selected="true"]{color:var(--ink);font-weight:560;
  box-shadow:inset 0 -2px 0 var(--ink)}
.onglets .compte{font-size:12px;color:var(--b-72);font-variant-numeric:tabular-nums}
.onglet-panneau[hidden]{display:none}

/* Un renvoi vers une autre page du document. */
.saut{font:inherit;font-size:13px;color:var(--b-72);background:none;border:0;padding:2px 0;
  cursor:pointer;border-bottom:1px solid var(--b-22)}
.saut:hover{color:var(--ink);border-bottom-color:var(--ink)}
.constat__lien{margin-top:4px}

/* ------------------------------------------------------------ adaptation --- */
/* Aucune : ce document se lit sur un écran d’ordinateur, et s’imprime. La mise
   en page a une largeur minimale plutôt qu’une cascade de points de rupture. */
body{min-width:1180px}

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
  .analyse,.fait,.constat,.identite,.carnet__col,.def,.chiffre,.bloc{break-inside:avoid}
  .onglet-panneau[hidden]{display:block!important}
  .saut{display:none}
  body{min-width:0}
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
    """La variation : flèche, valeur, mot — le gabarit de l’écran (ui.js,
    delta()), jamais une couleur."""
    if not kpi.delta_affichage:
        return ""
    fleche = FLECHES.get(kpi.delta_direction, "")
    mot = MOTS_SENS.get(kpi.delta_sens, "")
    suite = f" · {_e(mot)} sur la période précédente" if mot else " sur la période précédente"
    return (f'<span class="fait__delta">{fleche + ESP if fleche else ""}{_e(kpi.delta_affichage)}'
            f'<span>{suite}</span></span>')


def _fait_html(kpi: core.Kpi) -> str:
    """Un indicateur, exactement comme à l’écran : libellé, valeur, variation,
    mini-tendance. La définition est dans la marge, jamais dans un survol."""
    morceaux = [f'<span class="fait__label">{_e(kpi.libelle)}</span>',
                f'<span class="fait__valeur">{_e(kpi.affichage)}</span>']
    bas = _delta_html(kpi)
    if kpi.detail:
        bas += f'<span class="fait__detail">{_e(kpi.detail)}</span>'
    bas += _spark(kpi.serie, largeur=74, hauteur=18)
    if bas:
        morceaux.append(f'<span class="fait__bas">{bas}</span>')
    return f'<div class="fait">{"".join(morceaux)}</div>'


def _tableau_html(tableau: pd.DataFrame, triable: bool = False) -> str:
    if tableau is None or tableau.empty:
        return ""
    html_table = tableau.to_html(index=False, escape=True, border=0, na_rep="—",
                                 classes="donnees triable" if triable else "donnees",
                                 justify="right")
    if triable:
        html_table = html_table.replace("<th>", '<th role="button" tabindex="0" title="Trier">')
    return html_table


def _figure_html(bloc: core.Block, indice: int) -> str:
    """Le tracé Plotly d’un bloc, prêt à être posé dans la page."""
    return pio.to_html(bloc.figure, include_plotlyjs=False, full_html=False,
                       config=core.PLOT_CONFIG, div_id=f"figure-{indice}",
                       default_width="100%")


def _analyse_html(bloc: core.Block, indice: int, premiere: bool = False) -> str:
    """Une analyse : titre, accroche, figure, tableau jumeau, note.

    Le tableau se déplie à la demande, sauf quand le bloc EST un tableau :
    celui-là n’a pas de figure à attendre, il s’affiche.
    """
    tableau = _tableau_html(bloc.tableau, bloc.triable)
    if bloc.figure is None:
        corps = f'<div class="tableau tableau--pleine">{tableau}</div>'
        compte = core.pluriel(len(bloc.tableau), "ligne")
    else:
        figure = _figure_html(bloc, indice)
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
    return (f'<section class="{classe}" id="analyse-{_e(bloc.cle)}">'
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
         "Nombre de jours <b>calendaires</b> entre la date de réception de la demande et "
         "la date d’envoi de la réponse — comme au comité. Le respect du délai cible, lui, "
         "se mesure en jours ouvrés. Les dossiers non envoyés n’entrent dans aucune "
         "statistique de délai de traitement ; leur ancienneté, elle, est suivie dans "
         "« Les appels d’offres ouverts »."),
        ("Délai cible",
         f"Engagement interne de traitement ({_e(core.sla_libelle())}). "
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

    indicateurs = [(k.libelle, _e(k.aide)) for k in analyse.kpis if k.aide]
    corps = [_rubrique("Définitions", _dl(entrees), nue=True),
             _rubrique("Les indicateurs, un par un", _dl(indicateurs)),
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
#  LA VUE D’ENSEMBLE — l’écran « Situation », à l’identique
# -----------------------------------------------------------------------------
#  Ce que l’application montre le lundi matin, le document l’imprime : même
#  ordre, mêmes phrases, mêmes colonnes, mêmes marges. Les valeurs sortent des
#  mêmes fonctions de core.py que l’écran — `carnet_detaille`, `resume_situation`,
#  `fmt_encours` — donc aucune ne peut différer d’une surface à l’autre.
# =============================================================================
SEUIL_ATTENTE = core.SEUIL_ATTENTE    # au-delà, le trait d’attente s’encre
# Deux états se distinguent aussi par leur texture : le ton ne porte jamais seul.
TEXTURES = {"en_cours": "texture-redaction", "sans_suite": "texture-sanssuite"}
INCONNU = core.VALEUR_INCONNUE


def _marge(titre: str, *paragraphes: str) -> str:
    """La colonne de droite : ce qu’il faut savoir pour lire le bloc."""
    corps = "".join(f'<p class="marge-texte">{p}</p>' for p in paragraphes if p)
    tete = f'<div class="marge-titre">{_e(titre)}</div>' if titre else ""
    return tete + corps


NUMERO = "\x00NUMERO\x00"     # posé par _bloc, remplacé une fois les blocs vides écartés


def _bloc(cle: str, titre: str, corps: str, marge: str = "") -> str:
    return (f'<section class="bloc" id="bloc-{_e(cle)}">'
            f'<div class="bloc__corps">'
            f'<div class="bloc__tete"><span class="bloc__num">{NUMERO}</span>'
            f'<span class="cle cle--ink">{_e(titre)}</span></div>'
            f'{corps}</div>'
            f'<div class="bloc__marge">{marge}</div></section>')


def _val(d: dict, cle: str) -> str | None:
    """La valeur d’un champ de dossier, ou rien si elle n’est pas renseignée."""
    v = d.get(cle)
    if v is None or v == "" or v == INCONNU:
        return None
    return str(v)


def _nom(d: dict, champs: tuple[str, ...] = ("segment", "pays")) -> str:
    """Le client, puis son contexte sur une deuxième ligne."""
    sous = " · ".join(x for x in (_val(d, c) for c in champs) if x)
    ligne = f'<span class="cellule-nom">{_e(d.get("client") or "Client non renseigné")}</span>'
    return ligne + (f'<span class="cellule-sous">{_e(sous)}</span>' if sous else "")


def _jauge(valeur: Any, maxi: float, seuil: float | None = None) -> str:
    """Un trait plein sur un filet : la durée, comparée à la plus longue."""
    if valeur is None or not pd.notna(valeur):
        return ""
    part = min(1.0, float(valeur) / maxi) if maxi else 0.0
    alerte = " jauge--alerte" if seuil is not None and float(valeur) > seuil else ""
    return (f'<span class="jauge{alerte}" role="img" '
            f'aria-label="{core.fmt_int(valeur)} jours"><i style="width:'
            f'{part * 100:.1f}%"></i></span>')


def _duree(valeur: Any, maxi: float, seuil: float | None = None) -> str:
    if valeur is None or not pd.notna(valeur):
        return "—"
    return (f'<span class="duree">{_jauge(valeur, maxi, seuil)}'
            f'<span class="num">{core.fmt_int(valeur)}{ESP}j</span></span>')


def _table(lignes: list[dict], colonnes: list[tuple[str, Any, str]]) -> str:
    """Un tableau de dossiers : (titre, fonction de rendu, classes)."""
    th = "".join(f'<th scope="col" class="{c}">{_e(t)}</th>' for t, _, c in colonnes)
    corps = []
    for d in lignes:
        cellules = "".join(f'<td class="{c}">{rendu(d)}</td>' for _, rendu, c in colonnes)
        corps.append(f"<tr>{cellules}</tr>")
    return (f'<div class="tableau"><table class="donnees donnees--dossiers">'
            f'<thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(corps)}</tbody></table></div>')


def _etape(d: dict) -> str:
    if d.get("a_oral"):
        return "Oral"
    if d.get("a_preselection"):
        return "Step 2"
    if d.get("a_remis"):
        return "Step 1"
    return "—"


def _pied(gauche: str, droite: str = "") -> str:
    return (f'<p class="note bloc__pied"><span>{gauche}</span>'
            f'<span><b>{droite}</b></span></p>' if droite
            else f'<p class="note bloc__pied"><span>{gauche}</span></p>')


# ------------------------------------------------------------- ouverture ----
def _ouverture_html(analyse: core.Analysis, livre: dict, resume: dict) -> str:
    """La phrase calculée, les trois chiffres du matin, et la marge qui porte
    la forme des douze derniers mois."""
    comp = livre["compartiments"]
    redaction, attente = comp["en_cours"], comp["en_attente"]
    perdus = comp["perdus"]
    vivants = livre["vivants"]

    phrase = [f"Au {core.fmt_date_courte(dt.date.today())}, "]
    if vivants:
        phrase.append(f"{core.fmt_int(vivants)} appel{core.accord(vivants)} d’offres "
                      f"{'sont ouverts' if vivants > 1 else 'est ouvert'} pour ")
        phrase.append(f'<b>{_e(core.fmt_encours(resume["encours_en_jeu"]))}</b> d’encours')
        detail = []
        if redaction["n"]:
            detail.append(f'{core.fmt_int(redaction["n"])} en rédaction '
                          f'({core.fmt_encours(redaction["encours"])})')
        if attente["n"]:
            detail.append(f'{core.fmt_int(attente["n"])} en attente de décision '
                          f'({core.fmt_encours(attente["encours"])})')
        if detail:
            phrase.append(" : " + ", ".join(detail))
        phrase.append(". ")
    else:
        phrase.append("aucun appel d’offres n’est ouvert. ")

    debut = analyse.filtres.date_min or resume.get("date_min_donnees")
    fin = analyse.filtres.date_max or resume.get("date_max_donnees")
    suite = [f"Du {core.fmt_date_courte(debut)} au {core.fmt_date_courte(fin)}, "]
    if resume["tranches"]:
        suite.append(f'{core.fmt_int(resume["gagnes"])} mandat{core.accord(resume["gagnes"])} '
                     f'remporté{core.accord(resume["gagnes"])} '
                     f'({core.fmt_encours(resume["encours_remporte"])}) et ')
        suite.append(f'{core.fmt_int(perdus["n"])} perdu{core.accord(perdus["n"])} '
                     f'({core.fmt_encours(resume["encours_perdu"])}) sur '
                     f'{core.fmt_int(resume["tranches"])} tranchés. ')
    else:
        suite.append("aucun appel d’offres n’a encore été tranché. ")
    suite.append(f'Le pôle a aussi traité {core.fmt_int(resume["dd"])} '
                 f'questionnaire{core.accord(resume["dd"])} de due diligence.')
    lede = (f'<p class="lede">{"".join(phrase)}'
            f'<span class="attenue">{"".join(suite)}</span></p>')

    # Les chiffres du matin : ce qui est encore ouvert, ce qui est acquis.
    matin = []
    if attente["n"]:
        matin.append(f'<span><b>{core.fmt_int(attente["n"])}</b> en attente de décision'
                     f'<span> · {_e(core.fmt_encours(attente["encours"]))}</span></span>')
    succes = next((k for k in analyse.kpis if k.cle == "succes"), None)
    if succes is not None and resume["tranches"]:
        matin.append(f'<span><b>{_e(succes.affichage)}</b> de succès<span> · '
                     f'{core.fmt_int(resume["gagnes"])} sur '
                     f'{core.fmt_int(resume["tranches"])} tranchés</span></span>')
    ligne = f'<p class="matin">{"".join(matin)}</p>' if matin else ""

    return (f'<div class="lecture ouverture"><div>{lede}{ligne}</div>'
            f'<div class="marge-col">{_marge_ouverture(resume)}</div></div>')


def _marge_ouverture(resume: dict) -> str:
    serie = (resume.get("series") or {}).get("rfp") or []
    morceaux = []
    if len(serie) >= 3:
        maxi = max([s["valeur"] for s in serie] + [1])
        barres = "".join(
            f'<i class="{"encours" if s["en_cours"] else ""}" '
            f'style="height:{max(2.0, s["valeur"] / maxi * 100):.1f}%" '
            f'title="{_e(s["libelle"])} : {core.fmt_int(s["valeur"])}"></i>' for s in serie)
        dernier = serie[-1]
        legende = ", ".join(f"{x['libelle']} : {x['valeur']}" for x in serie)
        total = sum(x["valeur"] for x in serie)
        texte = (f'De <b>{_e(serie[0]["libelle"])}</b> à <b>{_e(dernier["libelle"])}</b>, '
                 f'{core.pluriel(total, "appel d’offres reçu", "appels d’offres reçus")}.')
        if dernier["en_cours"]:
            texte += " Le dernier mois est en cours : sa barre est hachurée."
        morceaux.append(
            '<div class="marge-titre">Appels d’offres reçus par mois</div>'
            f'<div class="barres" role="img" aria-label="{_e(legende)}">'
            f'{barres}</div>'
            f'<div class="barres-pied"><span>{_e(serie[0]["libelle"])}</span>'
            f'<span>{_e(dernier["libelle"])}</span></div>'
            f'<p class="marge-texte">{texte}</p>')
    rep = resume.get("repere") or {}
    if rep.get("annee_min"):
        morceaux.append(
            '<div class="marge-titre" style="margin-top:22px">Repère</div>'
            f'<p class="marge-texte">Depuis {rep["annee_min"]}, '
            f'<b>{core.fmt_int(rep["rfp"])}</b> appels d’offres et '
            f'<b>{core.fmt_int(rep["dd"])}</b> due diligences, pour un taux de succès de '
            f'<b>{core.fmt_pct(rep["taux_succes"], 1)}</b> et '
            f'<b>{_e(core.fmt_encours(rep["encours_remporte"]))}</b> remportés.</p>')
    return "".join(morceaux)


# -------------------------------------------------- appels d’offres ouverts --
def _bloc_ouverts(livre: dict) -> str:
    o = livre["ouverts"]
    marge = _marge(
        "Lecture",
        "<b>En rédaction</b> : la réponse est chez nous, non partie. "
        "<b>En attente de décision</b> : remise au client, non tranchée.",
        "<b>Étape</b> porte le nom des colonnes du classeur : Step 1 (proposition déposée), "
        "Step 2 (retenu après lecture) et Oral (présentation devant le client).",
        "<b>Depuis</b> compte les jours depuis la réception pour un dossier en rédaction, "
        "depuis la remise pour un dossier en attente, et rappelle sous le compte la date "
        "d’où il part. Le trait s’encre au-delà de quatre mois d’attente.")
    if not o["n"]:
        return _bloc("ouverts", "Les appels d’offres ouverts",
                     '<p class="prose">Aucun appel d’offres n’est ouvert sur ce périmètre.</p>',
                     _marge("Lecture", "Un appel d’offres est ouvert tant qu’il est en rédaction "
                            "chez nous ou remis au client sans décision."))
    dossiers = o["dossiers"]
    maxi = max([(d["jours_chez_nous"] if d["statut"] == core.STATUT_EN_COURS
                 else d["jours_attente"]) or 0 for d in dossiers] + [1])

    def depuis(d: dict) -> str:
        en_redaction = d["statut"] == core.STATUT_EN_COURS
        v = d["jours_chez_nous"] if en_redaction else d["jours_attente"]
        origine = d["date_reception"] if en_redaction else d["date_envoi"]
        duree = _duree(v, maxi, None if en_redaction else SEUIL_ATTENTE)
        if not origine:
            return duree
        return duree + (f'<span class="cellule-sous">'
                        f'{_e(core.fmt_date_courte(origine))}</span>')

    def classe(d: dict) -> str:
        fonds = _val(d, "fonds")
        return (_e(_val(d, "classe_actifs") or "—")
                + (f'<span class="cellule-sous">{_e(fonds)}</span>' if fonds else ""))

    def etat(d: dict) -> str:
        libelle = ("En rédaction" if d["statut"] == core.STATUT_EN_COURS
                   else "En attente de décision")
        return f'{libelle}<span class="cellule-sous">Étape : {_e(_etape(d))}</span>'

    def suivi(d: dict) -> str:
        consultant = _val(d, "consultant")
        return (_e(_val(d, "commercial") or "—")
                + (f'<span class="cellule-sous">via {_e(consultant)}</span>' if consultant else ""))

    table = _table(dossiers, [
        ("Client", _nom, ""),
        ("Classe d’actifs", classe, "attenue"),
        ("État", etat, ""),
        ("Depuis", depuis, ""),
        ("Suivi", suivi, "attenue"),
        ("Encours", lambda d: f'<b>{_e(core.fmt_encours(d["montant_potentiel"]))}</b>', "num"),
    ])
    intro = (f'<p class="prose">{core.pluriel(o["n"], "appel d’offres", "appels d’offres")} '
             f'ouvert{core.accord(o["n"])}, <b>{_e(core.fmt_encours(o["encours"]))}</b> '
             f'd’encours en jeu. L’encours le plus important d’abord.</p>')
    pied = _pied("", f'{core.pluriel(o["n"], "dossier")} · {core.fmt_encours(o["encours"])}')
    return _bloc("ouverts", "Les appels d’offres ouverts",
                 intro + table + pied, marge)


# ----------------------------------------------------------------- carnet ---
def _bloc_carnet(livre: dict, resume: dict) -> str:
    comp = livre["compartiments"]
    total_n = sum(comp[c]["n"] for c, _, _ in core.COMPARTIMENTS)
    total_e = sum(comp[c]["encours"] for c, _, _ in core.COMPARTIMENTS)

    rubans = []
    for titre, champ, total in (("Dossiers", "n", total_n), ("Encours", "encours", total_e)):
        segments = []
        for cle, libelle, _ in core.COMPARTIMENTS:
            v = comp[cle][champ] or 0
            if v <= 0:
                continue
            valeur = (core.pluriel(v, "dossier") if champ == "n"
                      else core.fmt_encours(v))
            segments.append(
                f'<i class="carnet__seg {TEXTURES.get(cle, "")}" '
                f'style="flex:{v};background:var({VAR_ETAT[cle]});min-width:3px" '
                f'title="{_e(libelle)} : {_e(valeur)}"></i>')
        rubans.append(f'<div class="carnet__ligne"><span class="cle">{_e(titre)}</span>'
                      f'<div class="carnet__ruban">{"".join(segments)}</div></div>')

    colonnes = "".join(
        f'<div class="carnet__col">'
        f'<span class="carnet__col-tete">'
        f'<i class="carnet__pastille {TEXTURES.get(cle, "")}" '
        f'style="background:var({VAR_ETAT[cle]})"></i>'
        f'<span class="carnet__nom">{_e(libelle)}</span></span>'
        f'<span class="carnet__n">{core.fmt_int(comp[cle]["n"])}</span>'
        f'<span class="carnet__encours">{_e(core.fmt_encours(comp[cle]["encours"]))}</span>'
        f'<span class="carnet__sens">{_e(sens)}</span></div>'
        for cle, libelle, sens in core.COMPARTIMENTS)

    identites = "".join(
        f'<div class="identite"><div class="identite__g">{_e(i["grandeur"])}</div>'
        f'<div class="identite__v"><b>{_e(i["valeur"])}</b> = {_e(i["egalite"])}.'
        f'<span class="identite__n">{_e(i["note"])}</span></div></div>'
        for i in (resume.get("identites") or []))

    intro = (f'<p class="prose">Des {core.fmt_int(livre["total"])} appels d’offres du '
             f'périmètre, {core.fmt_int(livre["vivants"])} ne sont pas tranchés '
             f'({core.fmt_encours(resume["encours_en_jeu"])}), '
             f'{core.fmt_int(comp["gagnes"]["n"])} remporté{core.accord(comp["gagnes"]["n"])} '
             f'({core.fmt_encours(resume["encours_remporte"])}), '
             f'{core.fmt_int(comp["perdus"]["n"])} perdu{core.accord(comp["perdus"]["n"])} '
             f'({core.fmt_encours(resume["encours_perdu"])}).</p>')
    corps = (f'{intro}<div class="carnet"><div class="carnet__rubans">{"".join(rubans)}</div>'
             f'<div class="carnet__colonnes">{colonnes}</div></div>'
             + (f'<div class="identites">{identites}</div>' if identites else ""))
    return _bloc("carnet", "Le carnet d’appels d’offres", corps, _marge(
        "Lecture",
        "Le ruban du haut compte les dossiers, un trait par dossier. Celui du bas porte "
        "les mêmes états en encours : c’est lui qui dit où se joue l’argent.",
        "<b>En rédaction</b> et <b>en attente de décision</b> partagent le même résultat, "
        "mais ne disent pas la même chose : la réponse se produit d’un côté, se décide de l’autre.",
        _e(core.NOTE_CENSURE)))


# ------------------------------------------------------------ indicateurs ---
def _bloc_indicateurs(analyse: core.Analysis) -> str:
    choisis = analyse.kpis_situation
    if not choisis:
        return ""
    faits = "".join(_fait_html(k) for k in choisis)
    definitions = [f"<b>{_e(k.libelle)}</b> — {_e(k.aide)}" for k in choisis[:5] if k.aide]
    return _bloc("indicateurs", "Les indicateurs", f'<div class="faits">{faits}</div>',
                 _marge("Définitions", *definitions))


# --------------------------------------------------------------- constats ---
def _bloc_constats(analyse: core.Analysis, livre: dict, pages: dict) -> str:
    constats = analyse.insights
    if not constats:
        return ""
    lignes = []
    for i in constats:
        droite = f'<div class="note">{_e(i.appui)}</div>' if i.appui else ""
        cible = "dossiers" if i.cible == "explorateur" else i.cible
        if cible and cible in pages:
            droite += (f'<div class="constat__lien"><button type="button" class="saut" '
                       f'data-page="{pages[cible]}">{_e(core.SECTIONS.get(cible, cible))} →'
                       f'</button></div>')
        lignes.append(f'<div class="constat"><div class="constat__t">{_e(i.texte)}</div>'
                      f'<div class="constat__a">{droite}</div></div>')
    return _bloc("constats", "Ce qui a changé", "".join(lignes), _marge(
        "Méthode",
        "Chaque constat est produit par une fonction d’analyse sur le périmètre courant. "
        "Aucune phrase n’est écrite d’avance : si la donnée ne permet pas de l’établir, "
        "le constat n’apparaît pas.",
        "Les variations sont mesurées face à la période précédente de même durée."))


# ----------------------------------------------------------------- listes ---
def _bloc_listes(livre: dict) -> str:
    comp = livre["compartiments"]
    onglets = [(cle, libelle, sens) for cle, libelle, sens in core.COMPARTIMENTS
               if cle in ("gagnes", "perdus", "sans_suite") and comp[cle]["n"] > 0]
    if not onglets:
        return ""
    boutons, panneaux = [], []
    for rang, (cle, libelle, sens) in enumerate(onglets):
        d = comp[cle]
        boutons.append(
            f'<button type="button" data-onglet="{_e(cle)}" '
            f'aria-selected="{"true" if rang == 0 else "false"}">{_e(libelle)}'
            f'<span class="compte">{core.fmt_int(d["n"])} · '
            f'{_e(core.fmt_encours(d["encours"]))}</span></button>')
        table = _table(d["dossiers"], [
            ("Client", _nom, ""),
            ("Classe d’actifs", lambda x: _e(_val(x, "classe_actifs") or "—"), "attenue"),
            ("Étape atteinte", lambda x: _e(_etape(x)), "attenue"),
            ("Décision", lambda x: _e(core.fmt_date(x["date_envoi"])), "attenue"),
            ("Encours", lambda x: _e(core.fmt_encours(x["montant_potentiel"])), "num"),
        ])
        reste = d["n"] - len(d["dossiers"])
        gauche = (f'{core.pluriel(d["n"], "dossier")} · {_e(sens)}'
                  + (f' — {core.fmt_int(reste)} au-delà de cette liste'
                     if reste > 0 else ""))
        panneaux.append(f'<div class="onglet-panneau" data-panneau="{_e(cle)}"'
                        f'{"" if rang == 0 else " hidden"}>{table}'
                        f'{_pied(gauche, core.fmt_encours(d["encours"]))}</div>')
    corps = (f'<div data-onglets><div class="onglets" role="tablist">{"".join(boutons)}</div>'
             f'{"".join(panneaux)}</div>')
    return _bloc("listes", "Les dossiers tranchés", corps, _marge(
        "Repères",
        "Les mandats remportés, les dossiers perdus et ceux restés sans suite, la décision "
        "la plus récente d’abord.",
        "Les listes montrent les premiers dossiers de chaque compartiment ; le total exact "
        "est sous chaque tableau."))


# ---------------------------------------------------- un bloc à figure ------
def _bloc_figure(analyse: core.Analysis, cle: str, titre: str,
                 marge: str, indice: int) -> tuple[str, int]:
    """Un bloc de l’écran dont le corps est une figure — ou son tableau quand
    le bloc n’en a pas."""
    bloc = next((b for b in analyse.blocs if b.cle == cle), None)
    if bloc is None:
        return "", indice
    corps = []
    if bloc.accroche:
        corps.append(f'<p class="prose" style="margin-bottom:16px">{_e(bloc.accroche)}</p>')
    if bloc.figure is not None:
        corps.append(f'<div class="figure">{_figure_html(bloc, indice)}</div>')
        indice += 1
    elif bloc.tableau is not None:
        corps.append(f'<div class="tableau tableau--pleine">'
                     f'{_tableau_html(bloc.tableau, bloc.triable)}</div>')
    if bloc.note:
        corps.append(f'<div class="analyse__note">{_e(bloc.note)}</div>')
    return _bloc(cle, titre, "".join(corps), marge), indice


def _marge_entonnoir(resume: dict) -> str:
    etapes = resume.get("entonnoir") or []
    remis = next((e for e in etapes if e["cle"] == "remis"), None)
    gagnes = next((e for e in etapes if e["cle"] == "gagnes"), None)
    milieu = None
    if remis and gagnes and remis["n"]:
        milieu = (f'Sur {core.fmt_int(remis["n"])} dossiers en Step 1, '
                  f'{core.fmt_int(gagnes["n"])} ont abouti à un mandat : '
                  f'{core.fmt_pct(gagnes["n"] / remis["n"], 0)} des Step 1.')
    return _marge(
        "Lecture",
        "Chaque barre est une étape franchie ; le pourcentage à gauche est la part de "
        "l’étape précédente qui passe. L’encours suit les dossiers.",
        milieu,
        "Les dossiers encore ouverts comptent dans les étapes qu’ils ont franchies, pas "
        "dans les remportés.")


def _marge_decomposition(resume: dict) -> str:
    e = resume.get("echelle")
    return _marge(
        "Lecture",
        "D’où viennent les dossiers, et où en sont les appels d’offres : chaque état est "
        "exclusif, leur somme fait le total.",
        (f'Facteur d’échelle <b>{_e(e["affichage"])}</b> : {_e(e["phrase"])}.') if e else None)


def _marge_annees() -> str:
    return _marge(
        "Lecture",
        "Une ligne par exercice du périmètre choisi, lue comme la vue d’ensemble : reçus, "
        "tranchés, encours. Un clic sur un en-tête trie le tableau sur cette colonne ; un "
        "second clic inverse l’ordre.",
        "Le périmètre se choisit exercice par exercice ; l’écran et le rapport suivent le "
        "même.")


def _marge_classes() -> str:
    return _marge(
        "Lecture",
        "Ce que chaque classe d’actifs pèse dans l’activité, ce qu’elle reçoit, remporte, "
        "perd et coûte en délai. L’encours remporté le plus haut d’abord ; un clic sur un "
        "en-tête trie autrement.",
        "<b>Part</b> est le poids de la classe dans les questionnaires reçus : à comparer à "
        "son encours remporté, pour voir si elle rend plus que son volume.",
        "Le détail par classe — taux de succès, encours, intervalles — est dans « Appels "
        "d’offres » et « Encours & gains ».")


def _marge_trimestres() -> str:
    return _marge(
        "Lecture",
        "Les mouvements qu’on sait dater, trimestre par trimestre : ce qui arrive, ce qui "
        "part, ce que cela rapporte.",
        "Le trimestre en cours est atténué : il est incomplet, il ne se compare pas.")


def _vue_ensemble_html(analyse: core.Analysis, pages: dict, indice: int) -> tuple[str, int]:
    """La vue d’ensemble entière, dans l’ordre de l’écran."""
    livre = core.carnet_detaille(analyse.df)
    resume = core.resume_situation(analyse.df, analyse.df_total)
    morceaux = [_ouverture_html(analyse, livre, resume)]

    morceaux.append(_bloc_ouverts(livre))
    morceaux.append(_bloc_carnet(livre, resume))
    morceaux.append(_bloc_indicateurs(analyse))
    bloc, indice = _bloc_figure(analyse, "entonnoir",
                                "Le chemin des appels d’offres", _marge_entonnoir(resume), indice)
    morceaux.append(bloc)
    morceaux.append(_bloc_constats(analyse, livre, pages))
    morceaux.append(_bloc_listes(livre))
    bloc, indice = _bloc_figure(analyse, "annees", "Année par année",
                                _marge_annees(), indice)
    morceaux.append(bloc)
    bloc, indice = _bloc_figure(analyse, "classes_actifs", "Les classes d’actifs",
                                _marge_classes(), indice)
    morceaux.append(bloc)
    bloc, indice = _bloc_figure(analyse, "decomposition",
                                "La décomposition de l’activité",
                                _marge_decomposition(resume), indice)
    morceaux.append(bloc)
    bloc, indice = _bloc_figure(analyse, "trimestre",
                                "Les huit derniers trimestres", _marge_trimestres(), indice)
    morceaux.append(bloc)
    # Les numéros ne sont posés qu’aux blocs présents : 01, 02, 03… sans trou,
    # exactement comme l’écran, qui ne compte pas un bloc qu’il n’affiche pas.
    sortie, numero = [], 0
    for m in morceaux:
        if not m:
            continue
        if NUMERO in m:
            numero += 1
            m = m.replace(NUMERO, f"{numero:02d}", 1)
        sortie.append(m)
    return "".join(sortie), indice


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

  /* Les listes à onglets de la vue d’ensemble : gagnés, perdus, sans suite.
     À l’impression, tous les panneaux s’affichent — voir la feuille de style. */
  Array.prototype.forEach.call(document.querySelectorAll('[data-onglets]'), function (zone) {
    var boutons = zone.querySelectorAll('.onglets button');
    var panneaux = zone.querySelectorAll('.onglet-panneau');
    Array.prototype.forEach.call(boutons, function (bouton) {
      bouton.addEventListener('click', function () {
        var vise = bouton.getAttribute('data-onglet');
        Array.prototype.forEach.call(boutons, function (b) {
          b.setAttribute('aria-selected', String(b === bouton));
        });
        Array.prototype.forEach.call(panneaux, function (p) {
          if (p.getAttribute('data-panneau') === vise) { p.removeAttribute('hidden'); }
          else { p.setAttribute('hidden', ''); }
        });
      });
    });
  });

  /* Les tableaux triables : un clic sur un en-tête trie, un second inverse.
     Même règle de lecture des nombres que dans l’application (figures.js). */
  function valeurTri(texte) {
    var t = String(texte == null ? '' : texte).replace(/[\s\u00a0\u202f]/g, '').replace('−', '-');
    if (t === '' || t === '—') return { n: -Infinity, s: '' };
    var date = t.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (date) return { n: Number(date[3] + date[2] + date[1]), s: t };
    var m = t.match(/^([-+]?\d+(?:[.,]\d+)?)(%|M€|Md€|j|pt)?/);
    if (!m) return { n: null, s: t.toLowerCase() };
    var n = Number(m[1].replace(',', '.'));
    if (m[2] === 'Md€') n *= 1000;
    return { n: n, s: t.toLowerCase() };
  }
  function comparerTri(a, b) {
    if (a.n !== null && b.n !== null) return a.n - b.n;
    if (a.n !== null) return 1;
    if (b.n !== null) return -1;
    return a.s.localeCompare(b.s, 'fr');
  }
  Array.prototype.forEach.call(document.querySelectorAll('table.triable'), function (table) {
    var ths = Array.prototype.slice.call(table.querySelectorAll('thead th'));
    ths.forEach(function (th, i) {
      var trier = function () {
        var tbody0 = table.tBodies[0];
        var numerique = Array.prototype.some.call(tbody0.rows, function (tr) {
          return tr.cells[i] && valeurTri(tr.cells[i].textContent).n !== null;
        });
        var actuel = th.getAttribute('aria-sort');
        var sens = actuel ? (actuel === 'descending' ? 'ascending' : 'descending')
                          : (numerique ? 'descending' : 'ascending');
        ths.forEach(function (x) { x.removeAttribute('aria-sort'); });
        th.setAttribute('aria-sort', sens);
        var tbody = table.tBodies[0];
        var lignes = Array.prototype.slice.call(tbody.rows);
        var cle = function (tr) { return valeurTri(tr.cells[i] ? tr.cells[i].textContent : ''); };
        lignes.sort(function (a, b) {
          return comparerTri(cle(a), cle(b)) * (sens === 'ascending' ? 1 : -1);
        });
        lignes.forEach(function (l) { tbody.appendChild(l); });
      };
      th.addEventListener('click', trier);
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); trier(); }
      });
    });
  });

  /* Un constat renvoie à la page qui le détaille. */
  Array.prototype.forEach.call(document.querySelectorAll('.saut'), function (bouton) {
    bouton.addEventListener('click', function () {
      afficher(parseInt(bouton.getAttribute('data-page'), 10));
    });
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

    Le rapport dit EXACTEMENT ce que dit l’application : mêmes indicateurs,
    mêmes phrases calculées, mêmes tableaux, dans le même ordre. Rien n’est
    réservé à l’écran, rien n’est réservé au document.

    Il est en deux parties, comme l’application : « Direction » se lit debout,
    « Analyse » répond aux pourquoi. Il se lit sur ordinateur.
    """
    if analyse.vide:
        raise ValueError("Aucune donnée à exporter : la sélection est vide.")

    parties = analyse.parties_rapport()
    sections = [s for _, _, _, groupe in parties for s in groupe]
    n_analyses = sum(len(analyse.section(cle)) for cle, _ in sections)
    # La couverture est la page 00 : les sections suivent, dans l’ordre.
    pages_par_section = {cle: i + 1 for i, (cle, _) in enumerate(sections)}
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
            blocs = analyse.section(cle)
            corps: list[str] = []
            if cle == "synthese":
                # La vue d’ensemble EST l’écran d’ouverture de l’application :
                # même phrase, mêmes blocs, même ordre, mêmes marges.
                vue, indice_figure = _vue_ensemble_html(analyse, pages_par_section,
                                                        indice_figure)
                corps.append(vue)
                compte = ""
            else:
                analyses = "".join(
                    _analyse_html(b, indice_figure + i, premiere=(i == 0))
                    for i, b in enumerate(blocs))
                indice_figure += len(blocs)
                corps.append(f'<section class="rubrique rubrique--nue">{analyses}</section>')
                compte = core.pluriel(len(blocs), "analyse")

            entete = (
                f'<header class="tete">'
                f'{_cle(f"{numero:02d} — {nom_partie} · {accroche_partie}")}'
                f'<div class="tete__ligne"><h2>{_e(libelle)}</h2>'
                f'<span class="tete__compte">{_e(compte)}</span></div></header>')
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
    analyse = core.build_analysis(df, core.Filters(), rapport, df_total=df)
    if analyse.erreurs:
        print("Blocs non construits :", *analyse.erreurs, sep="\n  - ")
    chemin = ecrire_rapport(analyse, options.sortie)
    poids = chemin.stat().st_size / 1_048_576
    blocs = [b for cle, _ in analyse.sections_rapport for b in analyse.section(cle)]
    figures = sum(1 for b in blocs if b.figure is not None)
    tables = len(blocs) - figures
    print(f"Rapport écrit : {chemin.resolve()}  ({poids:.1f} Mo, "
          f"{core.pluriel(figures, 'figure')}, "
          f"{core.pluriel(tables, 'tableau', 'tableaux')}, "
          f"{core.pluriel(len(analyse.kpis_rapport), 'indicateur')})")
    print("Ouvrable d’un double-clic, sans Python ni connexion réseau.")


if __name__ == "__main__":
    main()
