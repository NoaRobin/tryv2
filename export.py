# =============================================================================
#  export.py — Rapport HTML autonome, paginé et animé
# -----------------------------------------------------------------------------
#  Produit un fichier unique qui embarque tout ce dont il a besoin : la
#  bibliothèque Plotly, le lecteur Lottie, les animations et la police. Il
#  s'ouvre d'un double-clic, sans Python, sans serveur et sans réseau — donc
#  transmissible par courriel à un comité d'investissement.
#
#  Usage :  python export.py              rapport sombre (écran)
#           python export.py --clair      variante claire (impression)
#           python export.py --sortie X   chemin de sortie
#           bouton « Générer le rapport » dans app.py (périmètre filtré)
# =============================================================================
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd
import plotly.io as pio

import core

CHEMIN_RAPPORT = Path("rapport.html")
# Le rapport est le document DIFFUSÉ : son titre parle le vocabulaire du
# comité — deux familles de dossiers, pas de types fins.
TITRE_RAPPORT = "Activité RFP & Due Diligence"

# Blocs repris dans la synthèse quand aucun constat n'est calculable
CLES_SYNTHESE = ("flux_famille", "volume_annuel", "resultats_rfp", "rfp_succes",
                 "dd_expertise", "aum_annuel", "esg_evolution")
# Indicateurs mis en avant sur la couverture
CLES_HEROS = ("questionnaires", "dd", "rfp", "aum")


def bibliotheque_plotly() -> str:
    """Code source de plotly.js, embarqué dans le rapport.

    L'emplacement de la bibliothèque a changé au fil des versions de Plotly :
    on essaie les trois points d'accès connus plutôt que d'en supposer un.
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
        "Impossible de localiser plotly.min.js dans l'installation de Plotly ; "
        "le rapport autonome ne peut pas être généré. Réinstaller le paquet plotly."
    )


# =============================================================================
#  FEUILLE DE STYLE
#  Les couleurs passent par des variables CSS alimentées par le thème actif de
#  core.py : une seule source, l'écran et le rapport ne peuvent pas diverger.
# =============================================================================
# Halo d'ambiance : une seule source lumineuse, très basse intensité. Le thème
# maison s'en passe — un dégradé posé sur le bleu de nuit de la marque le salit.
def variables_css() -> str:
    """Les deux palettes, émises l'une après l'autre.

    Le rapport embarque la palette sombre ET la palette claire : basculer
    l'apparence ne demande donc pas de le régénérer. Les MARQUES, elles, ne
    changent pas — la palette de séries passe les contrôles daltonisme et
    contraste sur les deux surfaces, seul le chrome est repeint.
    """
    initial = core.THEME
    try:
        core.appliquer_theme("maison")
        sombre = core.jetons_css(':root, :root[data-theme="sombre"]')
        core.appliquer_theme("clair")
        clair = core.jetons_css(':root[data-theme="clair"]')
    finally:
        core.appliquer_theme(initial)
    return sombre + clair


def chromes_json() -> str:
    """Tout ce qu'il faut pour rhabiller les figures sans les régénérer :
    le gabarit de chrome de chaque apparence, et la table de substitution des
    couleurs figées dans les annotations, les formes et les anneaux de marque."""
    initial = core.THEME
    sortie: dict[str, dict[str, object]] = {}
    try:
        for nom, cle in (("sombre", "maison"), ("clair", "clair")):
            core.appliquer_theme(cle)
            sortie[nom] = {"chrome": core.chrome_plotly()}
        sortie["sombre"]["paires"] = core.substitutions("clair", "maison")
        sortie["clair"]["paires"] = core.substitutions("maison", "clair")
    finally:
        core.appliquer_theme(initial)
    return json.dumps(sortie, separators=(",", ":"))


CSS = r"""
*,*::before,*::after{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--plane);color:var(--ink);font-family:var(--police);
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;font-feature-settings:"cv05","ss01";overflow:hidden;
  transition:background var(--lent) var(--etat),color var(--lent) var(--etat)}
::selection{background:color-mix(in srgb,var(--accent) 30%,transparent);color:var(--ink)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:var(--rayon-s)}
*{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--ink) 18%,transparent) transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--ink) 14%,transparent);
  border-radius:99px;border:3px solid transparent;background-clip:content-box}

.ambiance{position:fixed;inset:0;pointer-events:none;z-index:0;background:var(--ambiance);
  transition:background var(--lent) var(--etat)}

/* ---------------------------------------------------------------- rail --- */
.rail{position:fixed;left:0;top:0;bottom:0;width:246px;z-index:3;display:flex;
  flex-direction:column;gap:var(--e5);padding:var(--e6) var(--e5) var(--e5);
  border-right:1px solid var(--border);background:var(--verre);
  backdrop-filter:blur(20px) saturate(150%);-webkit-backdrop-filter:blur(20px) saturate(150%)}
.rail__tete{display:flex;align-items:center;gap:var(--e3)}
.rail__marque{width:38px;height:38px;flex:none;color:var(--accent)}
.rail__marque svg{width:100%;height:100%;display:block}
.rail__titre{font-size:var(--t-m);font-weight:640;letter-spacing:-.012em;line-height:1.25}
.rail__titre span{display:block;font-size:9px;letter-spacing:.17em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin-top:4px}
.rail nav{display:flex;flex-direction:column;gap:1px;overflow-y:auto;flex:1;
  margin:0 calc(var(--e3) * -1);padding:0 var(--e3)}
.rail__partie{font-size:9px;letter-spacing:.17em;text-transform:uppercase;color:var(--muted);
  font-weight:700;padding:var(--e4) var(--e3) 6px;line-height:1}
.rail__partie:first-child{padding-top:0}
.lien{display:flex;align-items:baseline;gap:var(--e3);padding:9px var(--e3);
  border-radius:var(--rayon-s);color:var(--muted);text-decoration:none;font-size:var(--t-m);
  cursor:pointer;border:0;background:none;text-align:left;width:100%;font-family:inherit;
  transition:color var(--rapide) var(--etat),background var(--rapide) var(--etat),
             padding-left var(--rapide) var(--sortie)}
.lien .num{font-size:var(--t-xs);font-weight:700;letter-spacing:.08em;opacity:.7;
  font-variant-numeric:tabular-nums}
.lien:hover{color:var(--ink);background:color-mix(in srgb,var(--ink) 7%,transparent);
  padding-left:var(--e4)}
.lien[aria-current="page"]{color:var(--ink);
  background:color-mix(in srgb,var(--accent) 16%,transparent);
  box-shadow:inset 2px 0 0 var(--accent)}
.lien[aria-current="page"] .num{color:var(--accent);opacity:1}
.barre{display:flex;align-items:center;gap:var(--e2);justify-content:space-between;
  border:1px solid var(--border);border-radius:99px;padding:4px 6px;background:var(--surface)}
.barre button{width:32px;height:32px;border-radius:50%;border:0;background:transparent;
  color:var(--ink-2);font-size:19px;line-height:1;cursor:pointer;
  transition:background var(--rapide) var(--etat),color var(--rapide) var(--etat)}
.barre button:hover:not(:disabled){background:color-mix(in srgb,var(--ink) 9%,transparent);
  color:var(--ink)}
.barre button:disabled{opacity:.3;cursor:default}
.compteur{font-size:var(--t-s);color:var(--muted);font-variant-numeric:tabular-nums;
  letter-spacing:.06em}
.rail__pied{font-size:var(--t-xs);color:var(--muted);line-height:1.75}
.rail__pied b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}

/* Bascule d'apparence : un vrai contrôle, pas une icône décorative. */
.apparence{display:flex;gap:2px;padding:3px;border:1px solid var(--border);border-radius:99px;
  background:var(--surface)}
.apparence button{flex:1;border:0;background:transparent;color:var(--muted);cursor:pointer;
  font-family:inherit;font-size:var(--t-xs);font-weight:640;letter-spacing:.06em;
  text-transform:uppercase;padding:6px 8px;border-radius:99px;
  transition:background var(--rapide) var(--etat),color var(--rapide) var(--etat)}
.apparence button[aria-pressed="true"]{background:var(--accent);color:var(--sur-accent)}

/* Jauge de progression : où on en est dans le document. */
.progres{position:fixed;top:0;left:246px;right:0;height:2px;z-index:5;
  background:color-mix(in srgb,var(--ink) 8%,transparent)}
.progres i{display:block;height:100%;width:0;background:var(--accent);
  transition:width var(--moyen) var(--sortie)}

/* ---------------------------------------------------------------- pages -- */
main{margin-left:246px;height:100vh;overflow-y:auto;position:relative;z-index:1;
  scroll-behavior:smooth}
.page{display:none;padding:var(--e7) var(--e7) var(--e9);max-width:1520px;margin:0 auto}
.page.actif{display:block;animation:entrer var(--lent) var(--sortie) both}
@keyframes entrer{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.tete{display:flex;align-items:baseline;gap:var(--e4);margin-bottom:var(--e6);
  padding-bottom:var(--e4);border-bottom:1px solid var(--border)}
.tete .num{font-size:var(--t-3xl);font-weight:600;color:var(--accent);letter-spacing:-.03em;
  font-variant-numeric:tabular-nums;opacity:.9}
.tete h2{font-size:var(--t-2xl);font-weight:600;letter-spacing:-.028em;margin:0;flex:1}
.tete .compte{font-size:var(--t-s);color:var(--muted)}
.partie-sur{font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);
  font-weight:700;display:block;margin-bottom:6px}

/* ---------------------------------------------------------- couverture --- */
.page.couverture.actif{display:flex;flex-direction:column;justify-content:center}
.couverture{min-height:calc(100vh - 96px);padding:var(--e8) var(--e7) var(--e6);
  position:relative}
.couverture__marque{width:92px;height:92px;color:var(--accent);margin-bottom:var(--e5)}
.couverture__marque svg{width:100%;height:100%;display:block}
.couverture__marque path{stroke-dasharray:120;stroke-dashoffset:120;
  animation:tracer .9s var(--sortie) forwards}
.couverture__marque path:nth-child(3n+2){animation-delay:.10s}
.couverture__marque path:nth-child(3n+3){animation-delay:.16s}
.couverture__marque path:nth-child(n+7){animation-delay:.22s}
.couverture__marque path:nth-child(n+13){animation-delay:.34s}
.couverture__marque path:last-child{animation-delay:.52s}
@keyframes tracer{to{stroke-dashoffset:0}}
.sur{font-size:var(--t-s);letter-spacing:.2em;text-transform:uppercase;color:var(--muted);
  font-weight:700;margin-bottom:var(--e4)}
.couverture h1{font-size:clamp(42px,5.2vw,74px);font-weight:600;letter-spacing:-.038em;
  line-height:1.02;margin:0}
.couverture h1 em{font-style:normal;color:var(--accent)}
.couverture .accroche{margin-top:var(--e5);font-size:var(--t-xl);color:var(--ink-2);
  max-width:60ch;font-weight:400}
.couverture .portee{margin-top:var(--e3);font-size:var(--t-m);color:var(--muted);max-width:70ch}
.heros{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin-top:var(--e7);
  background:var(--border);border:1px solid var(--border);border-radius:var(--rayon);
  overflow:hidden;box-shadow:var(--ombre-2)}
.h{background:var(--surface);padding:var(--e5)}
.h__label{font-size:var(--t-xs);letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.h__valeur{font-size:var(--t-3xl);font-weight:600;letter-spacing:-.032em;margin-top:var(--e3);
  line-height:1;font-variant-numeric:tabular-nums}
.h__detail{font-size:var(--t-s);color:var(--muted);margin-top:var(--e3)}
.flux{position:absolute;left:0;right:0;bottom:-10px;height:230px;opacity:.45;
  pointer-events:none;z-index:-1}
.entrer{margin-top:var(--e6);align-self:flex-start;background:var(--accent);
  color:var(--sur-accent);border:0;border-radius:99px;padding:13px 24px;font-family:inherit;
  font-size:var(--t-l);font-weight:620;cursor:pointer;box-shadow:var(--ombre-2);
  transition:transform var(--moyen) var(--sortie),box-shadow var(--moyen) var(--etat)}
.entrer:hover{transform:translateY(-2px);box-shadow:var(--ombre-3)}
.entrer:active{transform:translateY(0)}

/* ---------------------------------------------------------------- cartes - */
.grille{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--e4)}
/* Une piste de grille prend par défaut la largeur de son contenu : un
   graphique Plotly de 700 px élargirait donc la carte au-delà de l'écran. */
.grille>*{min-width:0}
.carte{background:var(--surface);border:1px solid var(--border);border-radius:var(--rayon);
  padding:var(--e5);opacity:0;transform:translateY(16px);box-shadow:var(--ombre-1);
  min-width:0;overflow:hidden;
  transition:opacity var(--lent) var(--sortie),transform var(--lent) var(--sortie),
             box-shadow var(--moyen) var(--etat)}
.carte:hover{box-shadow:var(--ombre-2)}
.carte.vue{opacity:1;transform:none}
.carte--large{grid-column:1 / -1}
.carte--phare{grid-column:1 / -1;box-shadow:var(--ombre-2)}
.carte__titre{font-size:var(--t-xl);font-weight:620;letter-spacing:-.018em}
.carte__accroche{font-size:var(--t-l);color:var(--ink-2);margin:var(--e2) 0 var(--e3);
  line-height:1.55;max-width:90ch}
.carte__note{font-size:var(--t-s);color:var(--muted);line-height:1.6;margin-top:var(--e4);
  padding-top:var(--e3);border-top:1px solid var(--border)}
.js-plotly-plot{margin-top:var(--e2)}

/* Voile de démarrage. Le document pèse 5 Mo : l'attente existe vraiment, elle
   mérite donc un état, pas un écran blanc. Il disparaît quand tout est peint. */
.demarrage{position:fixed;inset:0;z-index:9;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:var(--e5);background:var(--plane);
  transition:opacity var(--lent) var(--etat),visibility var(--lent) var(--etat)}
.demarrage[hidden]{opacity:0;visibility:hidden;display:flex!important}
.demarrage__marque{width:76px;height:76px;color:var(--accent)}
.demarrage__marque svg{width:100%;height:100%;display:block}
.demarrage__marque path{stroke-dasharray:120;stroke-dashoffset:120;
  animation:tracer 1s var(--sortie) infinite alternate}
.demarrage__texte{font-size:var(--t-s);letter-spacing:.2em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.demarrage__jauge{width:180px;height:2px;border-radius:99px;overflow:hidden;
  background:color-mix(in srgb,var(--ink) 10%,transparent)}
.demarrage__jauge i{display:block;height:100%;width:40%;background:var(--accent);
  border-radius:99px;animation:glisser 1.1s var(--etat) infinite}
@keyframes glisser{0%{transform:translateX(-110%)}100%{transform:translateX(260%)}}

/* Squelette : la carte a déjà sa forme avant que Plotly n'ait peint. */
.squelette{height:300px;border-radius:var(--rayon-s);margin-top:var(--e3);
  background:linear-gradient(90deg,color-mix(in srgb,var(--ink) 4%,transparent) 0%,
    color-mix(in srgb,var(--ink) 9%,transparent) 50%,
    color-mix(in srgb,var(--ink) 4%,transparent) 100%);
  background-size:520px 100%;animation:luire 1.3s linear infinite}
@keyframes luire{0%{background-position:-520px 0}100%{background-position:520px 0}}

details{margin-top:var(--e3)}
summary{cursor:pointer;font-size:var(--t-s);color:var(--muted);list-style:none;
  display:flex;align-items:center;gap:7px;transition:color var(--rapide) var(--etat)}
summary::-webkit-details-marker{display:none}
summary::before{content:"›";display:inline-block;transition:transform var(--rapide) var(--sortie)}
details[open] summary::before{transform:rotate(90deg)}
summary:hover{color:var(--ink-2)}

.tableau{overflow-x:auto;margin-top:var(--e3);border:1px solid var(--border);
  border-radius:var(--rayon-s)}
.tableau--bloc{margin-top:var(--e4);max-height:none}
.tableau--bloc table{table-layout:fixed;font-size:var(--t-s)}
.tableau--bloc th,.tableau--bloc td{white-space:normal;padding:8px 10px;
  overflow-wrap:anywhere;hyphens:auto}
.tableau--bloc td:last-child,.tableau--bloc th:last-child{white-space:nowrap;width:9%}
.tableau--bloc td:first-child,.tableau--bloc th:first-child{width:16%}
.tableau--bloc tbody tr:nth-last-child(-n+2) td{font-weight:640;color:var(--ink)}
.tableau--bloc tbody tr:last-child td{border-top:1px solid var(--border)}
table{border-collapse:collapse;width:100%;font-size:var(--t-s);
  font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:8px var(--e3);border-bottom:1px solid var(--border);
  white-space:nowrap}
th{color:var(--muted);font-weight:700;font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;position:sticky;top:0;background:var(--elevation)}
tbody tr:last-child td{border-bottom:0}
th:first-child,td:first-child{text-align:left}
tbody tr{transition:background var(--rapide) var(--etat)}
tbody tr:hover td{background:color-mix(in srgb,var(--accent) 8%,transparent)}

/* ----------------------------------------------------------- indicateurs - */
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--e4);
  margin-bottom:var(--e6)}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:var(--rayon);
  padding:var(--e5) var(--e5) var(--e4);box-shadow:var(--ombre-1);
  transition:box-shadow var(--moyen) var(--etat),transform var(--moyen) var(--sortie)}
.kpi:hover{box-shadow:var(--ombre-2);transform:translateY(-2px)}
.kpi__label{font-size:var(--t-xs);letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.kpi__valeur{font-size:var(--t-2xl);font-weight:600;letter-spacing:-.024em;margin-top:var(--e2);
  line-height:1.05;font-variant-numeric:tabular-nums}
.kpi__bas{display:flex;align-items:center;gap:var(--e2);margin-top:var(--e3);flex-wrap:wrap}
.kpi__detail{font-size:var(--t-s);color:var(--muted);line-height:1.45}
.puce{display:inline-flex;gap:5px;font-size:var(--t-s);font-weight:700;padding:3px 9px;
  border-radius:99px;white-space:nowrap;font-variant-numeric:tabular-nums}
.puce--bon{background:color-mix(in srgb,var(--bon) 15%,transparent);color:var(--bon)}
.puce--mauvais{background:color-mix(in srgb,var(--mauvais) 15%,transparent);color:var(--mauvais)}
.puce--neutre{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink-2)}
.avertissement{font-size:var(--t-s);color:var(--muted);border-left:2px solid var(--border);
  padding-left:var(--e3);margin:0 0 var(--e6);line-height:1.6;max-width:110ch}

/* ------------------------------------------------------------- synthèse -- */
.synthese{background:var(--surface);border:1px solid var(--border);border-radius:var(--rayon);
  padding:var(--e5) var(--e6);margin-bottom:var(--e6);box-shadow:var(--ombre-1)}
.synthese h3{font-size:var(--t-xl);font-weight:620;margin:0 0 var(--e4);letter-spacing:-.016em}
.synthese ul{margin:0;padding:0;list-style:none;display:grid;gap:var(--e3)}
.synthese li{position:relative;padding-left:var(--e4);font-size:var(--t-l);line-height:1.5}
.synthese li::before{content:"";position:absolute;left:0;top:.62em;width:6px;height:6px;
  border-radius:50%;background:var(--accent)}
.synthese .appui{font-size:var(--t-s);color:var(--muted)}

/* --------------------------------------------------------------- annexe -- */
.annexe{background:var(--surface);border:1px solid var(--border);border-radius:var(--rayon);
  padding:var(--e6);box-shadow:var(--ombre-1)}
.annexe h3{font-size:var(--t-l);font-weight:660;letter-spacing:.04em;text-transform:uppercase;
  color:var(--muted);margin:var(--e6) 0 var(--e3)}
.annexe h3:first-child{margin-top:0}
.annexe dl{margin:0;display:grid;gap:var(--e3)}
.annexe dt{font-weight:620;font-size:var(--t-l)}
.annexe dd{margin:4px 0 0;color:var(--ink-2);font-size:var(--t-m);line-height:1.6}
.annexe code{background:color-mix(in srgb,var(--ink) 8%,transparent);padding:2px 6px;
  border-radius:var(--rayon-s);font-size:var(--t-s)}
.annexe ul{margin:var(--e2) 0 0;padding-left:var(--e4);color:var(--ink-2);font-size:var(--t-m)}
.fin{display:flex;align-items:center;gap:var(--e4);margin-top:var(--e6);
  padding-top:var(--e5);border-top:1px solid var(--border);color:var(--muted);
  font-size:var(--t-m)}
.fin__coche{width:46px;height:46px;flex:none}
h3.alerte{color:var(--mauvais)}

/* ----------------------------------------------------------- responsive -- */
@media (max-width:1100px){
  .grille{grid-template-columns:1fr}
  .kpis,.heros{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width:820px){
  .rail{position:static;width:auto;flex-direction:row;flex-wrap:wrap;align-items:center;
    height:auto;border-right:0;border-bottom:1px solid var(--border);gap:var(--e3);
    padding:var(--e3) var(--e4)}
  .rail nav{flex-direction:row;overflow-x:auto;flex:1 1 100%;gap:var(--e1)}
  .rail__partie{padding:var(--e2) var(--e2) var(--e2) 0}
  .rail__pied{display:none}
  .progres{left:0}
  main{margin-left:0;height:auto;overflow:visible}
  .page{padding:var(--e5) var(--e4) var(--e7)}
  .couverture{padding:var(--e6) var(--e4)}
  .kpis,.heros{grid-template-columns:1fr}
}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{transition:none!important;animation:none!important}
  .carte{opacity:1;transform:none}
  main{scroll-behavior:auto}
}

@media print{
  .ambiance,.rail,.barre,.entrer,.flux,.progres{display:none!important}
  main{margin-left:0;height:auto;overflow:visible}
  .page{display:block!important;page-break-after:always;max-width:none}
  .carte{opacity:1;transform:none;break-inside:avoid;box-shadow:none}
  .couverture{min-height:auto}
}
"""


# =============================================================================
#  FRAGMENTS
# =============================================================================
def _e(texte: object) -> str:
    return html.escape(str(texte), quote=True)


FLECHES = {"hausse": "▲", "baisse": "▼", "plat": ""}


def _puce(kpi: core.Kpi) -> str:
    if not kpi.delta_affichage:
        return ""
    fleche = FLECHES.get(kpi.delta_direction, "")
    return (f'<span class="puce puce--{_e(kpi.delta_sens)}">'
            f'{fleche} {_e(kpi.delta_affichage)}</span>')


def _kpi_html(kpi: core.Kpi) -> str:
    return (f'<div class="kpi" title="{_e(kpi.aide)}">'
            f'<div class="kpi__label">{_e(kpi.libelle)}</div>'
            f'<div class="kpi__valeur">{_e(kpi.affichage)}</div>'
            f'<div class="kpi__bas">{_puce(kpi)}'
            f'<span class="kpi__detail">{_e(kpi.detail)}</span></div></div>')


def _heros_html(analyse: core.Analysis) -> str:
    """Les quatre chiffres de couverture, animés au chargement."""
    par_cle = {k.cle: k for k in analyse.kpis_rapport}
    choisis = [par_cle[c] for c in CLES_HEROS if c in par_cle] or analyse.kpis_rapport[:4]
    cases = []
    for kpi in choisis:
        cases.append(
            f'<div class="h"><div class="h__label">{_e(kpi.libelle)}</div>'
            f'<div class="h__valeur" data-compteur="{_e(kpi.valeur if kpi.valeur is not None else "")}">'
            f'{_e(kpi.affichage)}</div>'
            f'<div class="h__detail">{_e(kpi.detail)}</div></div>')
    return f'<div class="heros">{"".join(cases)}</div>'


def _tableau_html(tableau: pd.DataFrame) -> str:
    if tableau is None or tableau.empty:
        return ""
    return tableau.to_html(index=False, escape=True, border=0, na_rep="—",
                           classes="donnees", justify="right")


def _carte_html(bloc: core.Block, indice: int, phare: bool = False) -> str:
    """Une analyse dans sa carte. « Phare » = pleine largeur et relief accru :
    réservé aux blocs qui ouvrent une partie."""
    classe = "carte carte--phare" if phare else ("carte carte--large" if bloc.large
                                                 else "carte")
    note = f'<div class="carte__note">{_e(bloc.note)}</div>' if bloc.note else ""
    tableau = _tableau_html(bloc.tableau)
    if bloc.figure is None:
        # Le bloc EST un tableau : il s'affiche déplié, sans figure à attendre.
        corps = f'<div class="tableau tableau--bloc">{tableau}</div>'
    else:
        details = (f'<details><summary>Voir les données '
                   f'({core.pluriel(len(bloc.tableau), "ligne")})</summary>'
                   f'<div class="tableau">{tableau}</div></details>' if tableau else "")
        corps = pio.to_html(bloc.figure, include_plotlyjs=False, full_html=False,
                            config=core.PLOT_CONFIG, div_id=f"graphique-{indice}",
                            default_width="100%") + details
    return (f'<section class="{classe}" id="bloc-{_e(bloc.cle)}">'
            f'<div class="carte__titre">{_e(bloc.titre)}</div>'
            f'<div class="carte__accroche">{_e(bloc.accroche)}</div>'
            f'{corps}{note}</section>')


def _synthese_html(analyse: core.Analysis) -> str:
    """Les constats calculés d'abord ; à défaut, la lecture de chaque analyse."""
    if analyse.insights:
        items = "".join(
            f"<li><b>{_e(i.texte)}</b>"
            + (f"<br><span class='appui'>{_e(i.appui)}</span>" if i.appui else "")
            + "</li>" for i in analyse.insights)
        titre = "Ce qu'il faut retenir"
    else:
        points = [b for cle in CLES_SYNTHESE for b in analyse.blocs if b.cle == cle]
        points = points or analyse.blocs[:5]
        items = "".join(f"<li><b>{_e(b.titre)}</b> — {_e(b.accroche)}</li>" for b in points)
        titre = "Lecture des analyses"
    return f'<div class="synthese"><h3>{titre}</h3><ul>{items}</ul></div>'


def _annexe_html(analyse: core.Analysis) -> str:
    rapport, stats = analyse.rapport, analyse.stats
    lignes: list[str] = ["<h3>Définitions</h3><dl>"]
    lignes.append("<dt>Délai de traitement</dt><dd>Nombre de jours <b>ouvrés</b> entre la date de "
                  "réception de la demande et la date d'envoi de la réponse. Les dossiers non "
                  "envoyés n'entrent dans aucune statistique de délai.</dd>")
    lignes.append(f"<dt>Délai cible</dt><dd>Engagement interne de traitement "
                  f"({_e(core.sla_libelle(par_famille=True))}). Paramétrable dans "
                  f"<code>core.py</code>.</dd>")
    lignes.append("<dt>Taux de succès</dt><dd>Mandats gagnés rapportés aux dossiers tranchés "
                  "(gagnés + perdus). Les dossiers en attente de décision sont exclus du "
                  "dénominateur, jamais comptés comme des échecs.</dd>")
    lignes.append("<dt>Intervalle de confiance</dt><dd>Méthode de Wilson à 95 % pour les "
                  "proportions ; intervalle de Student à 95 % pour les coefficients de "
                  "régression. Deux intervalles qui se recouvrent ne permettent pas de conclure "
                  "à une différence.</dd>")
    lignes.append(f"<dt>Limite de lecture</dt><dd>{_e(core.NOTE_CENSURE)}</dd></dl>")

    lignes.append("<h3>Modèles statistiques</h3><dl>")
    tendance = stats.get("tendance_volume")
    if tendance is not None:
        lignes.append(
            f"<dt>Tendance du flux mensuel</dt><dd>Moindres carrés ordinaires du volume mensuel "
            f"sur le rang du mois (mois en cours exclu) : pente "
            f"{core.fmt_dec(tendance.pente, 2)} demande{core.accord(tendance.pente)} "
            f"par mois, "
            f"R² = {core.fmt_dec(tendance.r2, 2)}, {core.fmt_p(tendance.p_value)}, "
            f"n = {core.fmt_int(tendance.n)} mois.</dd>")
    reg_q = stats.get("regression_questions")
    if reg_q is not None:
        lignes.append(
            f"<dt>Délai et volume de questions</dt><dd>Pente {core.fmt_dec(reg_q.pente, 4)} jour "
            f"par question (IC 95 % : {core.fmt_dec(reg_q.ic_pente[0], 4)} à "
            f"{core.fmt_dec(reg_q.ic_pente[1], 4)}), R² = {core.fmt_dec(reg_q.r2, 2)}, "
            f"{core.fmt_p(reg_q.p_value)}, n = {core.fmt_int(reg_q.n)} dossiers.</dd>")
    modele = stats.get("modele_delai")
    if modele is not None:
        detail = " ; ".join(
            f"{_e(c.nom)} : {core.fmt_dec(c.valeur, 2)} j ({core.fmt_p(c.p_value)})"
            for c in modele.explicatives)
        lignes.append(
            f"<dt>Facteurs du délai (régression multiple)</dt><dd>R² ajusté = "
            f"{core.fmt_dec(modele.r2_ajuste, 2)}, n = {core.fmt_int(modele.n)}. {detail}.</dd>")
    lignes.append("<dt>Calcul des p-values</dt><dd>Loi de Student bilatérale évaluée par la "
                  "fonction bêta incomplète régularisée, sans dépendance externe ; valeurs "
                  "vérifiées contre les tables de référence à l'exécution de "
                  "<code>python core.py</code>.</dd></dl>")

    if rapport is not None:
        lignes.append("<h3>Qualité des données</h3>")
        lignes.append(
            f"<p>Source : <b>{_e(rapport.source)}</b>. "
            f"{core.pluriel(rapport.n_lignes_source, 'ligne')} "
            f"lue{core.accord(rapport.n_lignes_source)}, "
            f"<b>{core.fmt_int(rapport.n_lignes_retenues)}</b> "
            f"retenue{core.accord(rapport.n_lignes_retenues)} après normalisation.</p>")
        if rapport.alertes:
            lignes.append("<ul>" + "".join(f"<li>{_e(a)}</li>" for a in rapport.alertes) + "</ul>")
        else:
            lignes.append("<p>Aucune anomalie détectée à l'import.</p>")
    if analyse.erreurs:
        lignes.append('<h3 class="alerte">Blocs non construits</h3><ul>'
                      + "".join(f"<li>{_e(e)}</li>" for e in analyse.erreurs) + "</ul>")

    coche = ('<div class="fin__coche" id="lottie-valide"></div>'
             if core.animation("valide") else "")
    lignes.append(
        f'<div class="fin">{coche}'
        '<div>Rapport complet. Graphiques interactifs, aucune connexion requise.<br>'
        'Pour une impression papier : <code>python export.py --clair</code>.</div></div>')
    return f'<div class="annexe">{"".join(lignes)}</div>'


# =============================================================================
#  SCRIPT EMBARQUÉ — pagination, animations, révélation
# =============================================================================
SCRIPT = r"""
(function () {
  const racine = document.documentElement;
  const pages = [...document.querySelectorAll('.page')];
  const liens = [...document.querySelectorAll('.lien')];
  const compteur = document.getElementById('compteur');
  const precedent = document.getElementById('precedent');
  const suivant = document.getElementById('suivant');
  const progres = document.querySelector('.progres i');
  const sobre = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let courante = 0;

  /* ---- Apparence : les deux palettes sont déjà dans le document ----------
     Seul le CHROME des graphiques est repeint ; les marques ne bougent pas,
     leur palette passe les contrôles sur les deux surfaces. */
  function tousLesGraphiques() {
    return [...document.querySelectorAll('.js-plotly-plot')];
  }
  function substituer(texte, paires) {
    for (let i = 0; i < paires.length; i++) {
      if (texte.indexOf(paires[i][0]) !== -1) {
        texte = texte.split(paires[i][0]).join(paires[i][1]);
      }
    }
    return texte;
  }

  /* Parcourt un objet de figure et renvoie les chemins pointés dont la valeur
     de couleur a changé. Une figure fige ses couleurs : l'encre d'une
     annotation, le fond d'une piste, l'anneau de surface d'une marque. Un
     relayout du gabarit ne les atteint pas — ce parcours, si. */
  function chemins(obj, prefixe, paires, sortie) {
    for (const cle in obj) {
      if (!Object.prototype.hasOwnProperty.call(obj, cle)) continue;
      if (cle.charAt(0) === '_') continue;
      const v = obj[cle];
      const p = prefixe ? prefixe + '.' + cle : cle;
      if (typeof v === 'string') {
        const n = substituer(v, paires);
        if (n !== v) sortie[p] = n;
      } else if (Array.isArray(v)) {
        if (v.length && v.every(e => typeof e === 'string')) {
          const tab = v.map(e => substituer(e, paires));
          if (tab.some((e, i) => e !== v[i])) sortie[p] = tab;
        } else {
          v.forEach(function (e, i) {
            if (e && typeof e === 'object') chemins(e, p + '[' + i + ']', paires, sortie);
          });
        }
      } else if (v && typeof v === 'object') {
        chemins(v, p, paires, sortie);
      }
    }
  }

  function appliquerApparence(nom) {
    racine.setAttribute('data-theme', nom);
    document.querySelectorAll('.apparence button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.theme === nom));
    });
    try { localStorage.setItem('apparence', nom); } catch (e) {}
    const reglage = window.CHROMES && window.CHROMES[nom];
    if (!window.Plotly || !reglage) return;
    tousLesGraphiques().forEach(function (d) {
      try {
        const patch = Object.assign({}, reglage.chrome);
        if (d.layout) chemins(d.layout, '', reglage.paires, patch);
        window.Plotly.relayout(d, patch);
        (d.data || []).forEach(function (trace, i) {
          const t = {};
          chemins(trace, '', reglage.paires, t);
          const cles = Object.keys(t);
          if (!cles.length) return;
          const maj = {};
          cles.forEach(function (c) { maj[c] = [t[c]]; });
          window.Plotly.restyle(d, maj, [i]);
        });
      } catch (e) {}
    });
  }
  document.querySelectorAll('.apparence button').forEach(function (b) {
    b.addEventListener('click', function () { appliquerApparence(b.dataset.theme); });
  });
  let depart = 'sombre';
  try { depart = localStorage.getItem('apparence') || 'sombre'; } catch (e) {}
  appliquerApparence(depart);

  /* ---- Navigation ------------------------------------------------------- */
  function redimensionner(page) {
    if (!window.Plotly) return;
    page.querySelectorAll('.js-plotly-plot').forEach(function (d) {
      try { window.Plotly.Plots.resize(d); } catch (e) {}
    });
  }

  function reveler(page) {
    const cartes = [...page.querySelectorAll('.carte')];
    if (sobre || !('IntersectionObserver' in window)) {
      cartes.forEach(c => c.classList.add('vue'));
      return;
    }
    const obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (!e.isIntersecting) return;
        // Décalage en cascade : les cartes se posent, elles n'apparaissent pas
        // toutes au même instant.
        const rang = cartes.indexOf(e.target) % 4;
        e.target.style.transitionDelay = (rang * 60) + 'ms';
        e.target.classList.add('vue');
        obs.unobserve(e.target);
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.05 });
    cartes.forEach(c => obs.observe(c));
  }

  function afficher(i) {
    courante = Math.max(0, Math.min(pages.length - 1, i));
    pages.forEach((p, k) => p.classList.toggle('actif', k === courante));
    liens.forEach((l, k) => l.setAttribute('aria-current', k === courante ? 'page' : 'false'));
    const main = document.querySelector('main');
    if (main) main.scrollTop = 0;
    compteur.textContent = String(courante).padStart(2, '0') + ' / '
                         + String(pages.length - 1).padStart(2, '0');
    precedent.disabled = courante === 0;
    suivant.disabled = courante === pages.length - 1;
    if (progres) progres.style.width = (courante / (pages.length - 1) * 100) + '%';
    const page = pages[courante];
    reveler(page);
    // Plotly mesure à zéro dans un conteneur masqué : on redimensionne à
    // l'affichage, sinon les graphiques sortent écrasés.
    requestAnimationFrame(() => redimensionner(page));
    setTimeout(() => redimensionner(page), 300);
    if (history.replaceState) history.replaceState(null, '', '#page-' + courante);
  }

  liens.forEach((l, k) => l.addEventListener('click', () => afficher(k)));
  precedent.addEventListener('click', () => afficher(courante - 1));
  suivant.addEventListener('click', () => afficher(courante + 1));
  const entrer = document.getElementById('entrer');
  if (entrer) entrer.addEventListener('click', () => afficher(1));

  document.addEventListener('keydown', function (e) {
    if (e.target.matches('input,textarea')) return;
    if (e.key === 'ArrowRight' || e.key === 'PageDown') { afficher(courante + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { afficher(courante - 1); e.preventDefault(); }
    else if (e.key === 'Home') { afficher(0); e.preventDefault(); }
    else if (e.key === 'End') { afficher(pages.length - 1); e.preventDefault(); }
    else if (e.key === 't' || e.key === 'T') {
      appliquerApparence(racine.getAttribute('data-theme') === 'clair' ? 'sombre' : 'clair');
    }
    else if (/^[0-9]$/.test(e.key)) { afficher(parseInt(e.key, 10)); }
  });
  window.addEventListener('resize', () => redimensionner(pages[courante]));

  /* ---- Animations Lottie (lecteur et données embarqués) ---- */
  if (window.lottie && window.ANIMATIONS) {
    const monter = function (id, nom, boucle) {
      const hote = document.getElementById(id);
      if (!hote || !window.ANIMATIONS[nom]) return null;
      const a = window.lottie.loadAnimation({
        container: hote, renderer: 'svg', loop: boucle, autoplay: !sobre,
        animationData: window.ANIMATIONS[nom],
        rendererSettings: { progressiveLoad: true }
      });
      if (sobre) a.goToAndStop(a.totalFrames - 1, true);
      return a;
    };
    monter('lottie-flux', 'flux', false);
    const coche = monter('lottie-valide', 'valide', false);
    if (coche && !sobre) { coche.stop(); }
    const pageFin = document.querySelector('.page:last-of-type');
    if (coche && pageFin) {
      const jouer = new MutationObserver(function () {
        if (pageFin.classList.contains('actif') && !sobre) { coche.goToAndPlay(0, true); }
      });
      jouer.observe(pageFin, { attributes: true, attributeFilter: ['class'] });
    }
  }

  /* ---- Compteurs de couverture : la valeur finale reste la vérité ---- */
  document.querySelectorAll('[data-compteur]').forEach(function (el) {
    const cible = parseFloat(el.getAttribute('data-compteur'));
    const final = el.textContent;
    if (sobre || !isFinite(cible) || cible === 0) return;
    const duree = 1000, debutT = performance.now();
    el.textContent = final.replace(/[0-9]/g, '0');
    function pas(t) {
      const p = Math.min(1, (t - debutT) / duree);
      const doux = 1 - Math.pow(1 - p, 3);
      if (p < 1) {
        const v = cible * doux;
        el.textContent = final.replace(/[0-9][0-9 ,.]*/, function (m) {
          const dec = (m.split(',')[1] || '').length;
          return v.toLocaleString('fr-FR', { minimumFractionDigits: dec,
                                             maximumFractionDigits: dec });
        });
        requestAnimationFrame(pas);
      } else { el.textContent = final; }
    }
    requestAnimationFrame(pas);
  });

  /* ---- Le voile ne se lève qu'une fois la première page réellement peinte -- */
  const voile = document.getElementById('demarrage');
  function lever() {
    if (!voile) return;
    voile.hidden = true;
    setTimeout(function () { voile.style.display = 'none'; }, 460);
  }
  const versPage = (location.hash.match(/^#page-(\d+)$/) || [])[1];
  afficher(versPage ? parseInt(versPage, 10) : 0);
  requestAnimationFrame(function () { requestAnimationFrame(lever); });
  setTimeout(lever, 2500);
})();
"""


# =============================================================================
#  ASSEMBLAGE
# =============================================================================
def construire_rapport(analyse: core.Analysis, titre: str = TITRE_RAPPORT) -> str:
    """Retourne le document HTML complet sous forme de chaîne.

    Le rapport est le document DIFFUSÉ : il s'en tient aux deux familles du
    pilotage, RFP et due diligence. Les blocs et indicateurs marqués
    `hors_rapport` — le détail RFI / DDQ — restent à l'écran.

    Il est en deux parties, comme l'application : « Direction » se lit debout,
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
    logo = core.logo_svg()

    # ---- Page 0 : couverture --------------------------------------------
    flux = ('<div class="flux" id="lottie-flux"></div>' if core.animation("flux") else "")
    marque_couverture = f'<div class="couverture__marque">{logo}</div>' if logo else ""
    liens.append('<button class="lien" type="button"><span class="num">00</span>'
                 'Couverture</button>')
    # Le périmètre ne s'affiche que s'il restreint quelque chose : sur
    # l'historique complet, il répéterait la période déjà indiquée.
    portee = (f'<div class="portee">{_e(analyse.filtres.describe())}</div>'
              if analyse.filtres.actif else "")
    pages.append(
        '<section class="page couverture">'
        f'{flux}'
        f'{marque_couverture}'
        f'<div class="sur">{_e(core.MARQUE_NOM)} &middot; {_e(core.MARQUE_ACTIVITE)}</div>'
        '<h1>Activité <em>RFP &amp;&nbsp;Due&nbsp;Diligence</em></h1>'
        f'<p class="accroche">{core.fmt_int(len(analyse.df))} demandes analysées'
        f'&#8239;·&#8239;{core.pluriel(n_analyses, "analyse")}'
        f'&#8239;·&#8239;{_e(analyse.periode)}</p>'
        f'{portee}'
        f'{_heros_html(analyse)}'
        '<button class="entrer" id="entrer" type="button">Ouvrir le rapport →</button>'
        '</section>')

    # ---- Pages 1..n : une par section, groupées en deux parties ----------
    numero = 0
    for _, nom_partie, accroche_partie, groupe in parties:
        liens.append(f'<div class="rail__partie">{_e(nom_partie)}</div>')
        for cle, libelle in groupe:
            numero += 1
            blocs = analyse.section(cle, pour_rapport=True)
            n_blocs = len(blocs)
            ouverture = ""
            if cle == "synthese":
                # L'ARBRE D'ABORD : la décomposition de l'activité ouvre le
                # rapport, avant les indicateurs. C'est la question du comité.
                phares = []
                for phare in ("decomposition", "trimestre"):
                    bloc = next((b for b in blocs if b.cle == phare), None)
                    if bloc is None:
                        continue
                    phares.append(_carte_html(bloc, indice_figure, phare=True))
                    indice_figure += 1
                    blocs = [b for b in blocs if b is not bloc]
                comparaison = ""
                fenetre = analyse.stats.get("comparaison")
                if fenetre:
                    comparaison = (" Les variations sont mesurées face à la période "
                                   f"précédente de même durée ({core.fmt_date(fenetre[0])} → "
                                   f"{core.fmt_date(fenetre[1])}).")
                ouverture = (
                    f'<div class="grille">{"".join(phares)}</div>'
                    f'<div class="kpis" style="margin-top:var(--e6)">'
                    f'{"".join(_kpi_html(k) for k in analyse.kpis_rapport)}</div>'
                    f'<p class="avertissement">{_e(core.NOTE_CENSURE)}{_e(comparaison)}</p>'
                    f'{_synthese_html(analyse)}')
            cartes = []
            for bloc in blocs:
                cartes.append(_carte_html(bloc, indice_figure))
                indice_figure += 1
            entete = (f'<div class="tete"><span class="num">{numero:02d}</span>'
                      f'<h2><span class="partie-sur">{_e(nom_partie)} · '
                      f'{_e(accroche_partie)}</span>{_e(libelle)}</h2>'
                      f'<span class="compte">{core.pluriel(n_blocs, "analyse")}</span></div>')
            liens.append(f'<button class="lien" type="button">'
                         f'<span class="num">{numero:02d}</span>{_e(libelle)}</button>')
            pages.append(f'<section class="page">{entete}{ouverture}'
                         f'<div class="grille">{"".join(cartes)}</div></section>')

    # ---- Dernière page : méthodologie ------------------------------------
    numero += 1
    liens.append(f'<button class="lien" type="button"><span class="num">{numero:02d}</span>'
                 f'Méthodologie</button>')
    pages.append(
        f'<section class="page"><div class="tete"><span class="num">{numero:02d}</span>'
        f'<h2>Méthodologie &amp; qualité des données</h2></div>'
        f'{_annexe_html(analyse)}</section>')

    animations = {nom: core.animation(nom) for nom in ("flux", "valide")}
    animations = {k: v for k, v in animations.items() if v}
    lecteur = core.lecteur_lottie()
    bloc_lottie = (f'<script>{lecteur}</script>'
                   f'<script>window.ANIMATIONS={json.dumps(animations, separators=(",", ":"))};</script>'
                   if lecteur and animations else "")
    marque = f'<div class="rail__marque">{logo}</div>' if logo else ""
    genere = analyse.genere_le.strftime("%d/%m/%Y à %H:%M")
    voile = (f'<div class="demarrage" id="demarrage">'
             f'<div class="demarrage__marque">{logo}</div>'
             f'<div class="demarrage__texte">{_e(core.MARQUE_PRODUIT)}</div>'
             f'<div class="demarrage__jauge"><i></i></div></div>')

    return f"""<!doctype html>
<html lang="fr" data-theme="sombre">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titre)} — rapport du {analyse.genere_le:%d/%m/%Y}</title>
<style>{core.police_css()}{variables_css()}{CSS}</style>
<!-- Plotly doit précéder les graphiques : chaque figure s'initialise par un
     script en ligne posé dans la page. -->
<script>{bibliotheque_plotly()}</script>
<script>window.CHROMES={chromes_json()};</script>
</head>
<body>
{voile}
<div class="ambiance"></div>
<div class="progres"><i></i></div>

<aside class="rail">
  <div class="rail__tete">
    {marque}
    <div class="rail__titre">{_e(core.MARQUE_NOM)}<span>{_e(core.MARQUE_PRODUIT)}</span></div>
  </div>
  <nav>{"".join(liens)}</nav>
  <div class="barre">
    <button id="precedent" type="button" title="Page précédente (←)">‹</button>
    <span class="compteur" id="compteur">00 / 00</span>
    <button id="suivant" type="button" title="Page suivante (→)">›</button>
  </div>
  <div class="apparence" role="group" aria-label="Apparence">
    <button type="button" data-theme="sombre" aria-pressed="true">Sombre</button>
    <button type="button" data-theme="clair" aria-pressed="false">Clair</button>
  </div>
  <div class="rail__pied">
    <b>{core.fmt_int(len(analyse.df))}</b> demandes<br>
    {_e(analyse.periode)}<br>
    Édité le {genere}
  </div>
</aside>

<main>{"".join(pages)}</main>

{bloc_lottie}
<script>{SCRIPT}</script>
</body>
</html>"""


def ecrire_rapport(analyse: core.Analysis, chemin: str | Path = CHEMIN_RAPPORT,
                   titre: str = TITRE_RAPPORT) -> Path:
    """Écrit le rapport sur le disque et retourne son chemin."""
    chemin = Path(chemin)
    chemin.write_text(construire_rapport(analyse, titre), encoding="utf-8")
    return chemin


# =============================================================================
#  ÉTAT DU CARNET DANS LE README — la page d'accueil du dépôt
# -----------------------------------------------------------------------------
#  GitHub affiche le README comme page d'accueil du dépôt : autant qu'il dise
#  où en est l'activité, et pas seulement comment lancer l'application. Le bloc
#  est délimité par deux balises et réécrit par `python export.py --readme` ;
#  tout ce qui est en dehors n'est jamais touché.
# =============================================================================
CHEMIN_README = Path("README.md")
BALISE_DEBUT = "<!-- ÉTAT : début — généré par `python export.py --readme`, ne pas éditer -->"
BALISE_FIN = "<!-- ÉTAT : fin -->"


def _ligne_readme(ligne: pd.Series, valeur: str) -> str:
    contexte = " · ".join(
        str(ligne[c]) for c in ("pays", "classe_actifs")
        if c in ligne.index and pd.notna(ligne[c]) and str(ligne[c]) != core.VALEUR_INCONNUE)
    return f"| {ligne.get('client', '—')} | {contexte or '—'} | {valeur} |"


def etat_markdown(df: pd.DataFrame, rapport: core.LoadReport) -> str:
    """L'état du carnet en Markdown : les mêmes chiffres que la page d'accueil,
    produits par les mêmes fonctions. Aucun calcul n'est refait ici."""
    livre = core.carnet(df)
    taux, gagnes, tranches, _ = core.taux_succes_rfp(df)
    aujourdhui = core.fmt_date_longue(df["date_reception"].max())

    lignes = [BALISE_DEBUT, "", f"## État du carnet au {aujourdhui}", ""]

    # L'avertissement se déduit de la SOURCE réelle : il disparaît de lui-même
    # le jour où le vrai classeur est branché, et ne peut pas être oublié.
    if "synthétique" in rapport.source.lower():
        lignes += ["> **Jeu de démonstration.** Les chiffres de cette page sont produits "
                   "par le générateur livré avec le dépôt. Ils reproduisent la FORME d'une "
                   "activité réelle — saisonnalité, délais, concentration de la collecte — "
                   "mais aucun ne décrit une activité réelle, et aucun client nommé "
                   "n'existe. Voir « Brancher vos données ».", ""]

    lignes += [
        "| Appels d'offres vivants | Encours en jeu | Taux de succès | Encours remporté |",
        "|---:|---:|---:|---:|",
        f"| **{core.fmt_int(livre.vivants)}** "
        f"| **{core.fmt_dec(core.aum_en_jeu(df), 0, 'M€')}** "
        f"| **{core.fmt_pct(taux, 1)}** "
        f"| **{core.fmt_dec(core.aum_gagne(df), 0, 'M€')}** |", "",
        f"<sub>{core.fmt_int(gagnes)} mandats remportés sur "
        f"{core.fmt_int(tranches)} dossiers tranchés. Les dossiers en attente de décision "
        f"sont exclus du dénominateur.</sub>", "",
        "| Compartiment | Dossiers | Encours |", "|---|---:|---:|",
    ]
    for cle, libelle, sens in core.COMPARTIMENTS:
        lignes.append(f"| {libelle} <sub>{sens}</sub> | {core.fmt_int(livre.n(cle))} "
                      f"| {core.fmt_dec(livre.encours(cle), 0, 'M€')} |")
    lignes.append("")

    tableaux = [
        ("En attente de décision", livre.en_attente, "Attente",
         lambda l: (f"{core.fmt_int(l['jours_attente'])} j"
                    if pd.notna(l["jours_attente"]) else "—")),
        ("Gagnés", livre.gagnes, "Encours",
         lambda l: core.fmt_dec(l.get("montant_potentiel"), 0, "M€")),
        ("Perdus", livre.perdus, "Encours",
         lambda l: core.fmt_dec(l.get("montant_potentiel"), 0, "M€")),
    ]
    for titre, sous, colonne, valeur in tableaux:
        lignes.append(f"### {titre} — {core.fmt_int(len(sous))}")
        lignes.append("")
        if sous.empty:
            lignes += ["_Aucun dossier dans ce compartiment._", ""]
            continue
        lignes += [f"| Dossier | | {colonne} |", "|---|---|---:|"]
        lignes += [_ligne_readme(l, valeur(l)) for _, l in sous.head(5).iterrows()]
        if len(sous) > 5:
            lignes.append(f"| _… et {core.pluriel(len(sous) - 5, 'autre')}_ | | |")
        lignes.append("")

    types = core.repartition_type(df)
    detail = " · ".join(f"**{core.fmt_int(n)}** {t}" for t, n in types.items())
    lignes += [
        f"Mix des demandes : {detail}. Le rapport diffusé, lui, s'en tient aux deux "
        f"familles de pilotage — RFP et due diligence.", "",
        f"> Source : {rapport.source}. "
        f"{core.pluriel(rapport.n_lignes_retenues, 'ligne')} exploitable"
        f"{core.accord(rapport.n_lignes_retenues)} sur "
        f"{core.fmt_int(rapport.n_lignes_source)}. "
        f"Bloc régénéré par `python export.py --readme`.", "",
        BALISE_FIN,
    ]
    return "\n".join(lignes)


def ecrire_etat_readme(df: pd.DataFrame, rapport: core.LoadReport,
                       chemin: str | Path = CHEMIN_README) -> Path:
    """Remplace le bloc balisé du README. Le reste du fichier est intouché ;
    si les balises manquent, le bloc est inséré après le titre de premier niveau."""
    chemin = Path(chemin)
    texte = chemin.read_text(encoding="utf-8")
    bloc = etat_markdown(df, rapport)
    debut, fin = texte.find(BALISE_DEBUT), texte.find(BALISE_FIN)
    if debut != -1 and fin > debut:
        texte = texte[:debut] + bloc + texte[fin + len(BALISE_FIN):]
    else:
        lignes = texte.split("\n")
        i = next((n for n, l in enumerate(lignes) if l.startswith("# ")), -1) + 1
        texte = "\n".join(lignes[:i] + ["", bloc] + lignes[i:])
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def main() -> None:
    """Génération en ligne de commande, sur l'historique complet."""
    parseur = argparse.ArgumentParser(
        description="Rapport d'activité RFP & due diligence, autonome.")
    parseur.add_argument("--clair", action="store_true",
                         help="thème clair, adapté à l'impression papier")
    parseur.add_argument("--sortie", default=str(CHEMIN_RAPPORT),
                         help="chemin du fichier HTML produit")
    parseur.add_argument("--readme", action="store_true",
                         help="met à jour l'état du carnet dans README.md, sans "
                              "produire de rapport")
    options = parseur.parse_args()

    if options.readme:
        df, rapport = core.load_data()
        chemin = ecrire_etat_readme(df, rapport)
        livre = core.carnet(df)
        print(f"État écrit dans {chemin.resolve()} : {core.fmt_int(livre.vivants)} "
              f"appels d'offres vivants, {core.fmt_int(livre.n('gagnes'))} gagnés, "
              f"{core.fmt_int(livre.n('perdus'))} perdus.")
        return

    core.appliquer_theme("clair" if options.clair else core.THEME_DEFAUT)
    print(f"Thème : {core.THEME}")
    print("Chargement des données…")
    df, rapport = core.load_data()
    # Aucune borne : le rapport en ligne de commande couvre tout l'historique,
    # et la couverture n'a pas à répéter une période déjà affichée.
    filtres = core.Filters()
    print(f"Analyse de {core.fmt_int(len(df))} demandes…")
    analyse = core.build_analysis(df, filtres, rapport)
    if analyse.erreurs:
        print("Avertissements :", *analyse.erreurs, sep="\n  - ")
    chemin = ecrire_rapport(analyse, options.sortie)
    poids = chemin.stat().st_size / 1_048_576
    # Compter ce qui part vraiment : les blocs d'écran ne sont pas dans le fichier.
    blocs = [b for cle, _ in analyse.sections_rapport
             for b in analyse.section(cle, pour_rapport=True)]
    figures = sum(1 for b in blocs if b.figure is not None)
    tables = len(blocs) - figures
    ecran = len(analyse.blocs) - len(blocs)
    print(f"Rapport écrit : {chemin.resolve()}  ({poids:.1f} Mo, "
          f"{core.pluriel(figures, 'graphique')}, {core.pluriel(tables, 'tableau', 'tableaux')}, "
          f"{core.pluriel(len(analyse.kpis_rapport), 'indicateur')})")
    if ecran:
        print(f"{ecran} bloc{core.accord(ecran)} et "
              f"{len(analyse.kpis) - len(analyse.kpis_rapport)} indicateurs réservés à "
              f"l'écran (détail RFI / DDQ) n'y figurent pas.")
    print("Ouvrable d'un double-clic, sans Python ni connexion réseau.")


if __name__ == "__main__":
    main()
