// relief.js — le relief du prix : une surface de sensibilité, pas un décor.
//
// Pour UN client (un encours donné), chaque point de la nappe est une variante
// de la grille simulée :
//   · de gauche à droite, une remise uniforme sur tous les taux ;
//   · d'avant en arrière, les seuils des tranches abaissés ou relevés ;
//   · la hauteur, le taux moyen que ce client paierait.
// La couleur dit où ce prix tombe parmi les offres déjà faites à cette taille :
// claire sous la plus basse, foncée au-dessus de la plus haute, et c'est dans
// la fourchette qu'elle change. Les lignes relient les variantes de même prix.
// Un graphique plat montre la courbe d'une grille ; il ne montre jamais toutes
// ses voisines à la fois, ni quel levier pèse le plus pour ce client.

import * as THREE from '/static/vendor/three.module.min.js';
import * as T from './tarif.js';
import { fmtTaux, plafondJoli } from './graphes-tarif.js';
import { entier, decimal, NBSP } from './format.js';

const REMISE = [-0.4, 0.2];          // −40 % à +20 % sur tous les taux
const FACTEUR = [0.5, 2];            // seuils divisés par deux ou doublés
const NX = 72; const NZ = 72;        // finesse de la nappe
const LARG = 2.6; const PROF = 2.0; const HAUT = 1.15;
const TONS = ['#eef1f4', '#c9d1da', '#95a3b3', '#61748b', '#34496a', '#0b2545'];   // les tons de la teinte
const MOINS = '−';

const reduit = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function webglDisponible() {
  try {
    const c = document.createElement('canvas');
    return Boolean(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
  } catch (e) { return false; }
}

/* ------------------------------------------------------------ axes ----- */
const remiseEn = (i) => REMISE[0] + (i / (NX - 1)) * (REMISE[1] - REMISE[0]);
const facteurEn = (j) => Math.exp(Math.log(FACTEUR[0]) + (j / (NZ - 1)) * (Math.log(FACTEUR[1]) - Math.log(FACTEUR[0])));
const xDe = (remise) => -LARG / 2 + ((remise - REMISE[0]) / (REMISE[1] - REMISE[0])) * LARG;
const zDe = (facteur) => PROF / 2 - ((Math.log(facteur) - Math.log(FACTEUR[0])) / (Math.log(FACTEUR[1]) - Math.log(FACTEUR[0]))) * PROF;
const remiseDe = (x) => REMISE[0] + ((x + LARG / 2) / LARG) * (REMISE[1] - REMISE[0]);
const facteurDe = (z) => Math.exp(Math.log(FACTEUR[0]) + ((PROF / 2 - z) / PROF) * (Math.log(FACTEUR[1]) - Math.log(FACTEUR[0])));

function fmtRemise(r) {
  const p = Math.round(r * 100);
  if (p === 0) return 'aucune remise';
  return p < 0 ? `remise de ${Math.abs(p)}${NBSP}%` : `majoration de ${p}${NBSP}%`;
}
function fmtFacteur(f) {
  if (Math.abs(f - 1) < 0.005) return 'seuils inchangés';
  return `seuils ×${decimal(f, 2).replace(/,?0+$/, '')}`;
}

/* ------------------------------------------------------------ couleur --- */
const tonsRVB = TONS.map(t => new THREE.Color(t));
function couleurRampe(t, cible) {
  const u = Math.min(1, Math.max(0, t)) * (tonsRVB.length - 1);
  const i = Math.min(tonsRVB.length - 2, Math.floor(u));
  cible.copy(tonsRVB[i]).lerp(tonsRVB[i + 1], u - i);
  return cible;
}

/* ------------------------------------------------ carrés qui marchent --- */
// Les lignes d'iso-prix : à hauteur donnée, les segments de la nappe qui la
// traversent. Cas ambigus tranchés par la moyenne des quatre coins.
function isoLignes(hauteurs, niveau) {
  const segs = [];
  const interp = (a, b, va, vb) => a + ((niveau - va) / (vb - va || 1e-12)) * (b - a);
  for (let j = 0; j < NZ - 1; j++) {
    for (let i = 0; i < NX - 1; i++) {
      const a = hauteurs[j * NX + i]; const b = hauteurs[j * NX + i + 1];
      const c = hauteurs[(j + 1) * NX + i + 1]; const d = hauteurs[(j + 1) * NX + i];
      const cas = (a > niveau ? 1 : 0) | (b > niveau ? 2 : 0) | (c > niveau ? 4 : 0) | (d > niveau ? 8 : 0);
      if (cas === 0 || cas === 15) continue;
      const e = [
        [interp(i, i + 1, a, b), j], [i + 1, interp(j, j + 1, b, c)],
        [interp(i, i + 1, d, c), j + 1], [i, interp(j, j + 1, a, d)],
      ];
      const centre = (a + b + c + d) / 4 > niveau;
      const table = {
        1: [[3, 0]], 2: [[0, 1]], 3: [[3, 1]], 4: [[1, 2]], 5: centre ? [[3, 2], [0, 1]] : [[3, 0], [1, 2]],
        6: [[0, 2]], 7: [[3, 2]], 8: [[2, 3]], 9: [[0, 2]], 10: centre ? [[0, 3], [1, 2]] : [[0, 1], [2, 3]],
        11: [[1, 2]], 12: [[1, 3]], 13: [[0, 1]], 14: [[0, 3]],
      };
      for (const [p, q] of table[cas]) segs.push(e[p], e[q]);
    }
  }
  return segs;
}

/* ====================================================================== */
export function creerRelief(hote, { surAppliquer, surApercu } = {}) {
  hote.classList.add('relief');
  if (!webglDisponible()) {
    const p = document.createElement('p');
    p.className = 'note';
    p.textContent = 'Ce navigateur n’affiche pas la 3D (WebGL indisponible). La lecture chiffrée ci-dessous reste exacte.';
    hote.append(p);
    return { maj() {}, detruire() {} };
  }

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 2, 0.1, 50);
  const rendu = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  rendu.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  rendu.setClearColor(0xffffff, 0);
  const toile = rendu.domElement;
  toile.className = 'relief__toile';
  toile.setAttribute('role', 'img');
  toile.setAttribute('aria-label', 'Relief du prix : taux moyen selon la remise et les seuils des tranches');
  hote.append(toile);
  const calque = document.createElement('div');
  calque.className = 'relief__calque';
  hote.append(calque);

  scene.add(new THREE.HemisphereLight(0xffffff, 0xdfe4ea, 2.1));
  const soleil = new THREE.DirectionalLight(0xffffff, 1.05);
  soleil.position.set(-2.2, 4, 3.2);
  scene.add(soleil);

  // --- la nappe ---------------------------------------------------------
  const geo = new THREE.PlaneGeometry(LARG, PROF, NX - 1, NZ - 1);
  geo.rotateX(-Math.PI / 2);                                 // plan horizontal (x, z)
  const nV = NX * NZ;
  const couleurs = new Float32Array(nV * 3);
  geo.setAttribute('color', new THREE.BufferAttribute(couleurs, 3));
  const matiere = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0,
    side: THREE.DoubleSide, flatShading: false, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  const nappe = new THREE.Mesh(geo, matiere);
  scene.add(nappe);
  // PlaneGeometry range ses sommets ligne par ligne, du fond (z négatif) vers
  // l'avant : on retrouve (i, j) de nos axes à partir de la position.
  const pos = geo.attributes.position;
  const indexSommet = new Int32Array(nV);
  for (let k = 0; k < nV; k++) {
    const i = Math.round(((pos.getX(k) + LARG / 2) / LARG) * (NX - 1));
    const j = Math.round(((PROF / 2 - pos.getZ(k)) / PROF) * (NZ - 1));
    indexSommet[k] = j * NX + i;
  }

  // Les parois : du sol au bord de la nappe, pour que la hauteur se lise comme
  // un volume et non comme un plan qui flotte.
  const matParoi = new THREE.MeshBasicMaterial({ color: 0x0b2545, transparent: true, opacity: 0.07,
    side: THREE.DoubleSide, depthWrite: false });
  const bords = [
    { n: NX, ij: (k) => [k, 0] }, { n: NX, ij: (k) => [k, NZ - 1] },
    { n: NZ, ij: (k) => [0, k] }, { n: NZ, ij: (k) => [NX - 1, k] },
  ].map((b) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(b.n * 2 * 3), 3));
    const idx = [];
    for (let k = 0; k < b.n - 1; k++) { const a = 2 * k; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    g.setIndex(idx);
    const m = new THREE.Mesh(g, matParoi);
    m.renderOrder = 2;
    scene.add(m);
    const arete = new THREE.Line(new THREE.BufferGeometry().setAttribute('position',
      new THREE.BufferAttribute(new Float32Array(b.n * 3), 3)), new THREE.LineBasicMaterial({ color: 0x4f6279 }));
    scene.add(arete);
    return { ...b, g, arete };
  });

  // Maillage fin du paramétrage : une ligne sur huit, pour lire la forme.
  const grilleLignes = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0x0b2545, transparent: true, opacity: 0.07 }));
  scene.add(grilleLignes);

  // Sol, cadre et graduations.
  const sol = new THREE.Group();
  scene.add(sol);
  const matSol = new THREE.LineBasicMaterial({ color: 0xc9cfd6 });
  const matSolFin = new THREE.LineBasicMaterial({ color: 0xe2e5e9 });
  const segmentsSol = [];
  const segmentsSolFin = [];
  const cadre = [[-LARG / 2, -PROF / 2], [LARG / 2, -PROF / 2], [LARG / 2, PROF / 2], [-LARG / 2, PROF / 2]];
  for (let k = 0; k < 4; k++) segmentsSol.push(new THREE.Vector3(cadre[k][0], 0, cadre[k][1]), new THREE.Vector3(cadre[(k + 1) % 4][0], 0, cadre[(k + 1) % 4][1]));
  for (const r of [-0.4, -0.3, -0.2, -0.1, 0, 0.1, 0.2]) segmentsSolFin.push(new THREE.Vector3(xDe(r), 0, -PROF / 2), new THREE.Vector3(xDe(r), 0, PROF / 2));
  for (const f of [0.5, 0.75, 1, 1.5, 2]) segmentsSolFin.push(new THREE.Vector3(-LARG / 2, 0, zDe(f)), new THREE.Vector3(LARG / 2, 0, zDe(f)));
  sol.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(segmentsSolFin), matSolFin));
  sol.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(segmentsSol), matSol));
  const poteau = new THREE.LineSegments(new THREE.BufferGeometry(), matSol);   // axe des taux, coin arrière gauche
  scene.add(poteau);

  // Lignes d'iso-prix et limites de la fourchette pratiquée.
  // Un gris moyen se lit sur la nappe claire comme sur la foncée.
  const iso = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0x808e9e, transparent: true, opacity: 0.7 }));
  const limites = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0x0b2545 }));
  const limitesClair = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0xffffff }));
  const ombreIso = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0xa7b1bc, transparent: true, opacity: 0.55 }));
  scene.add(iso, limitesClair, limites, ombreIso);

  // L'offre actuelle (plein) et la variante qu'on explore (anneau).
  const matEncre = new THREE.MeshStandardMaterial({ color: 0x0b2545, roughness: 0.4 });
  const actuelle = new THREE.Mesh(new THREE.SphereGeometry(0.045, 32, 16), matEncre);
  const poignee = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 8), new THREE.MeshBasicMaterial({ visible: false }));
  actuelle.add(poignee);
  const tige = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x0b2545 }));
  const anneauSol = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.065, 40), new THREE.MeshBasicMaterial({ color: 0x0b2545, side: THREE.DoubleSide }));
  anneauSol.rotation.x = -Math.PI / 2;
  const variante = new THREE.Mesh(new THREE.TorusGeometry(0.055, 0.014, 12, 40), matEncre);
  variante.visible = false;
  const tigeVariante = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x4f6279 }));
  tigeVariante.visible = false;
  scene.add(actuelle, tige, anneauSol, variante, tigeVariante);

  // --- étiquettes HTML, projetées à chaque image ------------------------
  const etiquettes = [];
  function etiquette(classe, ancre) {
    const el = document.createElement('div');
    el.className = `relief__etiquette ${classe}`;
    calque.append(el);
    const e = { el, ancre: ancre.clone(), visible: true };
    etiquettes.push(e);
    return e;
  }
  const etqRemise = [-0.4, -0.2, 0, 0.2].map(r => {
    // −40 % part du coin vers la droite : le coin porte déjà « seuils ×0,5 ».
    const e = etiquette(r === -0.4 ? 'relief__graduation relief__graduation--gauche' : 'relief__graduation',
      new THREE.Vector3(xDe(r), 0, PROF / 2 + 0.16));
    const t = `${r < 0 ? MOINS : '+'}${Math.abs(Math.round(r * 100))}${NBSP}%`;
    e.el.textContent = r === 0 ? 'taux actuels' : r === -0.4 ? `remise ${t}` : r === 0.2 ? `majoration ${t}` : t;
    return e;
  });
  const etqFacteur = [[0.5, `seuils ×0,5`], [1, 'seuils actuels'], [2, 'seuils ×2']].map(([f, texte]) => {
    const e = etiquette('relief__graduation relief__graduation--droite', new THREE.Vector3(-LARG / 2 - 0.12, 0, zDe(f)));
    e.el.textContent = texte;
    return e;
  });
  const titreHauteur = etiquette('relief__titre-axe relief__titre-axe--haut', new THREE.Vector3(-LARG / 2, HAUT + 0.12, -PROF / 2));
  titreHauteur.el.textContent = 'taux moyen payé';
  const etqHauteur = [];
  const etqActuelle = etiquette('relief__offre', new THREE.Vector3());
  const etqVariante = etiquette('relief__offre relief__offre--variante', new THREE.Vector3());
  etqVariante.visible = false;
  const etqLimites = [etiquette('relief__limite', new THREE.Vector3()), etiquette('relief__limite', new THREE.Vector3()),
    etiquette('relief__limite', new THREE.Vector3())];

  // --- état ------------------------------------------------------------
  const E = {
    grille: null, encours: 100, eligibles: [], libelle: '',
    hauteurs: new Float32Array(nV), cibles: new Float32Array(nV), taux: new Float32Array(nV),
    yMax: 0.3, yMaxCible: 0.3, yMin: 0, yMinCible: 0, departYMin: 0, fourchette: { n: 0 }, choisi: null, balayage: null,
    encoursAffiche: 100, debutTransition: 0, depart: new Float32Array(nV), departYMax: 0.3,
  };

  // --- la caméra : orbite amortie, balancement lent au repos -----------
  const orbite = { az: -0.68, el: 0.44, dist: 5.2, azC: -0.68, elC: 0.44, distC: 5.2 };
  const cible = new THREE.Vector3(0, 0.26, 0.08);
  let repos = performance.now();
  function placerCamera(t) {
    // Au repos, un lent balancement révèle le relief ; il s'amorce en douceur
    // et s'efface par le même amortissement dès qu'on reprend la main.
    const repose = t - repos;
    const montee = Math.min(1, Math.max(0, (repose - 2500) / 3000));
    const sway = reduit() || E.balayage || geste ? 0 : Math.sin(repose / 5200) * 0.14 * montee;
    orbite.az += (orbite.azC + sway - orbite.az) * 0.12;
    orbite.el += (orbite.elC - orbite.el) * 0.12;
    orbite.dist += (orbite.distC - orbite.dist) * 0.12;
    const az = orbite.az;
    camera.position.set(cible.x + orbite.dist * Math.cos(orbite.el) * Math.sin(az),
      cible.y + orbite.dist * Math.sin(orbite.el), cible.z + orbite.dist * Math.cos(orbite.el) * Math.cos(az));
    camera.lookAt(cible);
    const hauteurLisible = orbite.el < 1.15;
    poteau.visible = hauteurLisible; titreHauteur.visible = hauteurLisible;
    for (const e of etqHauteur) e.visible = hauteurLisible;
  }

  // --- calcul de la nappe -------------------------------------------------
  function hauteurEn(remise, facteur, encours = E.encoursAffiche) {
    return E.grille ? T.tauxMoyen(T.ajuster(E.grille, remise, facteur), encours) : 0;
  }

  function calculerCibles(encours) {
    let haut = 0; let bas = Infinity;
    for (let j = 0; j < NZ; j++) {
      const f = facteurEn(j);
      const base = T.tauxMoyen(E.grille, encours / f);        // (1 + r) × Taux(A / f)
      for (let i = 0; i < NX; i++) {
        const v = (1 + remiseEn(i)) * base;
        E.taux[j * NX + i] = v;
        if (v > haut) haut = v;
        if (v < bas) bas = v;
      }
    }
    E.fourchette = T.fourchetteTaille(E.eligibles, encours);
    E.valsTriees = E.fourchette.valeurs.map(x => x.v).filter(Number.isFinite).sort((a, b) => a - b);
    if (E.fourchette.n) { haut = Math.max(haut, E.fourchette.max); bas = Math.min(bas, E.fourchette.min); }
    E.yMaxCible = plafondJoli(haut * 1.04, 5);
    // La base de l'axe est posée un pas sous le prix le plus bas : la pente se lit,
    // et la base est écrite à côté du titre de l'axe pour ne tromper personne.
    const pasBase = pasJoli(E.yMaxCible / 9);
    E.yMinCible = Number.isFinite(bas) ? Math.max(0, Math.floor(bas / pasBase) * pasBase - pasBase) : 0;
    E.cibles.set(E.taux);
  }

  function couleurDe(v, c) {
    const vals = E.valsTriees;
    if (!vals || !vals.length) return couleurRampe((v - E.yMin) / (E.yMax - E.yMin), c);
    // Position parmi les offres passées : la couleur change DANS la fourchette.
    // Rang interpolé entre offres voisines : continu, donc sans marches d'escalier
    // sur la nappe ; les lignes blanches et encre marquent les bornes exactes.
    const n = vals.length; const bas = vals[0]; const haut = vals[n - 1];
    let rang;
    if (v <= bas) rang = 0.14 * Math.max(0, (v - E.yMin) / ((bas - E.yMin) || 1));
    else if (v >= haut) rang = 0.86 + 0.14 * Math.min(1, (v - haut) / ((E.yMax - haut) || 1));
    else if (n < 2) rang = 0.5;
    else {
      let k = 0;
      while (k < n - 2 && vals[k + 1] <= v) k++;
      const u = vals[k + 1] > vals[k] ? (v - vals[k]) / (vals[k + 1] - vals[k]) : 0;
      rang = 0.14 + 0.72 * ((k + u) / (n - 1));
    }
    return couleurRampe(rang, c);
  }

  const couleurTemp = new THREE.Color();
  function appliquerGeometrie(progression) {
    const ease = 1 - (1 - progression) ** 3;
    E.yMax = E.departYMax + (E.yMaxCible - E.departYMax) * ease;
    E.yMin = E.departYMin + (E.yMinCible - E.departYMin) * ease;
    for (let k = 0; k < nV; k++) E.hauteurs[k] = E.depart[k] + (E.cibles[k] - E.depart[k]) * ease;
    for (let k = 0; k < nV; k++) {
      const idx = indexSommet[k];
      const v = E.hauteurs[idx];
      pos.setY(k, Yv(v));
      couleurDe(v, couleurTemp);
      couleurs[k * 3] = couleurTemp.r; couleurs[k * 3 + 1] = couleurTemp.g; couleurs[k * 3 + 2] = couleurTemp.b;
    }
    pos.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
    geo.computeVertexNormals();
    geo.computeBoundingSphere();
    for (const b of bords) {
      const p = b.g.attributes.position; const a = b.arete.geometry.attributes.position;
      for (let k = 0; k < b.n; k++) {
        const [i, j] = b.ij(k);
        const x = X(i); const z = Z(j); const y = Yv(E.hauteurs[j * NX + i]);
        p.setXYZ(2 * k, x, 0, z); p.setXYZ(2 * k + 1, x, y, z);
        a.setXYZ(k, x, y + 0.003, z);
      }
      p.needsUpdate = true; a.needsUpdate = true;
      b.g.computeBoundingSphere(); b.arete.geometry.computeBoundingSphere();
    }
    tracerLignes();
    placerOffres();
  }

  const X = (i) => -LARG / 2 + (i / (NX - 1)) * LARG;
  const Z = (j) => PROF / 2 - (j / (NZ - 1)) * PROF;
  const Yv = (v) => Math.max(0, (v - E.yMin) / (E.yMax - E.yMin)) * HAUT;

  function tracerLignes() {
    // Maillage (une ligne sur huit).
    const g = [];
    for (let j = 0; j < NZ; j += 8) for (let i = 0; i < NX - 1; i++) {
      g.push(X(i), Yv(E.hauteurs[j * NX + i]) + 0.002, Z(j), X(i + 1), Yv(E.hauteurs[j * NX + i + 1]) + 0.002, Z(j));
    }
    for (let i = 0; i < NX; i += 8) for (let j = 0; j < NZ - 1; j++) {
      g.push(X(i), Yv(E.hauteurs[j * NX + i]) + 0.002, Z(j), X(i), Yv(E.hauteurs[(j + 1) * NX + i]) + 0.002, Z(j + 1));
    }
    grilleLignes.geometry.dispose();
    grilleLignes.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(g, 3));

    // Iso-prix au pas « joli », et leur ombre au sol : la carte plate.
    const pasJ = pasJoli((E.yMax - E.yMin) / 9);
    const lignesIso = []; const lignesOmbre = [];
    for (let niv = Math.floor(E.yMin / pasJ + 1 + 1e-9) * pasJ; niv < E.yMax - 1e-9; niv += pasJ) {
      const segs = isoLignes(E.hauteurs, niv);
      for (let k = 0; k < segs.length; k += 2) {
        const a = segs[k]; const b = segs[k + 1];
        lignesIso.push(X(a[0]), Yv(niv) + 0.004, Z(a[1]), X(b[0]), Yv(niv) + 0.004, Z(b[1]));
        lignesOmbre.push(X(a[0]), 0.001, Z(a[1]), X(b[0]), 0.001, Z(b[1]));
      }
    }
    iso.geometry.dispose();
    iso.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(lignesIso, 3));
    ombreIso.geometry.dispose();
    ombreIso.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(lignesOmbre, 3));

    // Les bornes de ce qui a déjà été fait : plus bas, médiane, plus haut.
    // Un trait blanc doublé d'encre : lisible sur la nappe claire comme foncée.
    const f = E.fourchette;
    const lim = []; const limClair = [];
    const noms = f.n ? [['plus bas déjà proposé', f.min], ['médiane', f.mediane], ['plus haut déjà proposé', f.max]] : [];
    etqLimites.forEach(e => { e.visible = false; });
    noms.forEach(([nom, niv], k) => {
      if (!(niv > E.yMin) || niv >= E.yMax) return;
      const segs = isoLignes(E.hauteurs, niv);
      let ancre = null;
      for (let s2 = 0; s2 < segs.length; s2 += 2) {
        const a = segs[s2]; const b = segs[s2 + 1];
        limClair.push(X(a[0]), Yv(niv) + 0.006, Z(a[1]), X(b[0]), Yv(niv) + 0.006, Z(b[1]));
        lim.push(X(a[0]), Yv(niv) + 0.011, Z(a[1]), X(b[0]), Yv(niv) + 0.011, Z(b[1]));
        if (!ancre || a[0] > ancre[0]) ancre = a;
      }
      if (ancre) {
        const e = etqLimites[k];
        e.ancre.set(X(ancre[0]), Yv(niv), Z(ancre[1]));
        e.el.textContent = `${nom} · ${fmtTaux(niv)}`;
        e.visible = true;
      }
    });
    limites.geometry.dispose();
    limites.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(lim, 3));
    limitesClair.geometry.dispose();
    limitesClair.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(limClair, 3));

    // Axe vertical des taux, au coin arrière gauche. Pas de graduation au sol :
    // le coin porte déjà « seuils ×2 », et la base est écrite dans le titre.
    const p = [];
    const graduations = [];
    const pasG = pasJ * ((E.yMax - E.yMin) / pasJ > 6 ? 2 : 1);
    for (let v = Math.floor(E.yMin / pasG + 1 + 1e-9) * pasG; v <= E.yMax + 1e-9; v += pasG) graduations.push(v);
    p.push(-LARG / 2, 0, -PROF / 2, -LARG / 2, HAUT, -PROF / 2);
    for (const v of graduations) p.push(-LARG / 2, Yv(v), -PROF / 2, -LARG / 2 - 0.05, Yv(v), -PROF / 2);
    titreHauteur.el.textContent = E.yMin > 1e-9 ? `taux moyen payé · base ${fmtTaux(E.yMin)}` : 'taux moyen payé';
    poteau.geometry.dispose();
    poteau.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
    while (etqHauteur.length > graduations.length) { const e = etqHauteur.pop(); e.el.remove(); etiquettes.splice(etiquettes.indexOf(e), 1); }
    graduations.forEach((v, k) => {
      if (!etqHauteur[k]) etqHauteur[k] = etiquette('relief__graduation relief__graduation--droite', new THREE.Vector3());
      etqHauteur[k].ancre.set(-LARG / 2 - 0.08, Yv(v), -PROF / 2);
      etqHauteur[k].el.textContent = fmtTaux(v);
    });
  }

  function placerOffres() {
    const v0 = hauteurEn(0, 1);
    const y0 = Yv(v0);
    actuelle.position.set(xDe(0), y0, zDe(1));
    anneauSol.position.set(xDe(0), 0.002, zDe(1));
    tige.geometry.dispose();
    tige.geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(xDe(0), 0, zDe(1)), new THREE.Vector3(xDe(0), y0, zDe(1))]);
    etqActuelle.ancre.set(xDe(0), y0 + 0.1, zDe(1));
    etqActuelle.el.replaceChildren(
      Object.assign(document.createElement('b'), { textContent: `Votre grille · ${fmtTaux(v0)}` }),
      Object.assign(document.createElement('span'), { textContent: E.balayage ? ` à ${entier(E.encoursAffiche)} M€` : '' }));
    if (E.choisi) {
      const v = hauteurEn(E.choisi.remise, E.choisi.facteur);
      const y = Yv(v);
      const x = xDe(E.choisi.remise); const z = zDe(E.choisi.facteur);
      variante.position.set(x, y + 0.012, z);
      variante.rotation.x = Math.PI / 2;
      tigeVariante.geometry.dispose();
      tigeVariante.geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x, 0, z), new THREE.Vector3(x, y, z)]);
      variante.visible = true; tigeVariante.visible = true;
      etqVariante.ancre.set(x, y + 0.12, z);
      etqVariante.el.textContent = `${fmtRemise(E.choisi.remise)}, ${fmtFacteur(E.choisi.facteur)} · ${fmtTaux(v)}`;
      etqVariante.visible = true;
    } else {
      variante.visible = false; tigeVariante.visible = false; etqVariante.visible = false;
    }
  }

  function transition(encours, duree = 420) {
    E.depart.set(E.hauteurs);
    E.departYMax = E.yMax; E.departYMin = E.yMin;
    E.encoursAffiche = encours;
    calculerCibles(encours);
    E.debutTransition = performance.now();
    E.dureeTransition = reduit() ? 0 : duree;
  }

  // --- interaction : orbite, choix d'une variante ------------------------
  const lanceur = new THREE.Raycaster();
  const pointeur = new THREE.Vector2();
  let geste = null;
  function viser(e) {
    const r = toile.getBoundingClientRect();
    pointeur.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    lanceur.setFromCamera(pointeur, camera);
  }
  function choisirSur(e) {
    viser(e);
    const touche = lanceur.intersectObject(nappe, false)[0];
    if (!touche) return false;
    const remise = Math.min(REMISE[1], Math.max(REMISE[0], remiseDe(touche.point.x)));
    const facteur = Math.min(FACTEUR[1], Math.max(FACTEUR[0], facteurDe(touche.point.z)));
    // Aimant doux : 0 % et ×1 se retrouvent sans viser au pixel.
    E.choisi = { remise: Math.abs(remise) < 0.012 ? 0 : Math.round(remise * 100) / 100,
      facteur: Math.abs(Math.log(facteur)) < 0.025 ? 1 : Math.round(facteur * 100) / 100 };
    if (E.choisi.remise === 0 && E.choisi.facteur === 1) E.choisi = null;
    placerOffres();
    if (surApercu) surApercu(E.choisi ? { ...E.choisi, taux: hauteurEn(E.choisi.remise, E.choisi.facteur, E.encours) } : null);
    return true;
  }
  toile.addEventListener('pointerdown', (e) => {
    viser(e);
    const surPoignee = lanceur.intersectObject(poignee, false).length > 0
      || (E.choisi && lanceur.intersectObject(variante, false).length > 0);
    geste = { x: e.clientX, y: e.clientY, az: orbite.azC, el: orbite.elC, mode: surPoignee ? 'variante' : 'orbite', bouge: false };
    toile.setPointerCapture(e.pointerId);
    repos = performance.now();
  });
  toile.addEventListener('pointermove', (e) => {
    if (!geste) {
      viser(e);
      toile.style.cursor = lanceur.intersectObject(poignee, false).length ? 'grab'
        : (lanceur.intersectObject(nappe, false).length ? 'crosshair' : 'default');
      return;
    }
    const dx = e.clientX - geste.x; const dy = e.clientY - geste.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) geste.bouge = true;
    if (geste.mode === 'variante') { choisirSur(e); toile.style.cursor = 'grabbing'; } else {
      orbite.azC = geste.az - dx * 0.006;
      orbite.elC = Math.min(1.45, Math.max(0.12, geste.el + dy * 0.005));
    }
    repos = performance.now();
  });
  toile.addEventListener('pointerup', (e) => {
    if (geste && !geste.bouge) choisirSur(e);
    geste = null;
    repos = performance.now();
  });
  toile.addEventListener('wheel', (e) => {
    e.preventDefault();
    orbite.distC = Math.min(8, Math.max(3.2, orbite.distC * (1 + Math.sign(e.deltaY) * 0.08)));
    repos = performance.now();
  }, { passive: false });

  // --- boucle de rendu : seulement visible, et libérée quand l'écran part --
  let visible = true;
  const observateur = new IntersectionObserver((entrees) => { visible = entrees[0].isIntersecting; });
  observateur.observe(hote);
  const v3 = new THREE.Vector3();
  function redimensionner() {
    const l = hote.clientWidth; const hh = hote.clientHeight;
    if (!l || !hh) return;
    if (toile.width !== Math.round(l * rendu.getPixelRatio()) || toile.height !== Math.round(hh * rendu.getPixelRatio())) {
      rendu.setSize(l, hh, false);
      camera.aspect = l / hh;
      camera.updateProjectionMatrix();
    }
  }
  let detruit = false;
  function image(t) {
    if (detruit) return;
    if (!hote.isConnected) { detruire(); return; }
    requestAnimationFrame(image);
    if (!visible || document.hidden) return;
    redimensionner();
    if (E.balayage) {
      const b = E.balayage;
      const u = Math.min(1, (t - b.debut) / b.duree);
      const aller = u < 0.5 ? u * 2 : (1 - u) * 2;
      const lisse = 0.5 - 0.5 * Math.cos(Math.PI * aller);
      const a = b.de * (b.a / b.de) ** lisse;
      E.encoursAffiche = a;
      calculerCibles(a);
      E.yMaxCible = b.yMax; E.yMinCible = b.yMin;
      E.hauteurs.set(E.cibles); E.yMax = b.yMax; E.yMin = b.yMin;
      E.depart.set(E.cibles); E.departYMax = E.yMax; E.departYMin = E.yMin;
      appliquerGeometrie(1);
      if (b.surPas) b.surPas(a, u);
      if (u >= 1) { E.balayage = null; E.encoursAffiche = E.encours; transition(E.encours, 300); if (b.fin) b.fin(); }
    } else if (E.debutTransition) {
      const u = E.dureeTransition ? Math.min(1, (t - E.debutTransition) / E.dureeTransition) : 1;
      appliquerGeometrie(u);
      if (u >= 1) E.debutTransition = 0;
    }
    placerCamera(t);
    rendu.render(scene, camera);
    const l = hote.clientWidth; const hh = hote.clientHeight;
    for (const e of etiquettes) {
      if (!e.visible) { e.el.style.display = 'none'; continue; }
      v3.copy(e.ancre).project(camera);
      if (v3.z > 1) { e.el.style.display = 'none'; continue; }
      e.el.style.display = '';
      e.el.style.transform = `translate(${((v3.x + 1) / 2) * l}px, ${((1 - v3.y) / 2) * hh}px) translate(var(--dx), var(--dy))`;
    }
  }
  requestAnimationFrame(image);

  function detruire() {
    if (detruit) return;
    detruit = true;
    observateur.disconnect();
    scene.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    rendu.dispose();
  }

  return {
    /** Nouvelle grille, nouvel encours, nouvelles offres de comparaison. */
    maj({ grille, encours, eligibles, libelle }) {
      const premier = !E.grille;
      E.grille = grille; E.encours = encours; E.eligibles = eligibles || []; E.libelle = libelle || '';
      E.choisi = null;
      if (surApercu) surApercu(null);
      if (E.balayage) return;
      if (premier) {
        E.encoursAffiche = encours;
        calculerCibles(encours);
        E.yMax = E.yMaxCible; E.departYMax = E.yMax; E.yMin = E.yMinCible; E.departYMin = E.yMin;
        E.hauteurs.set(E.cibles); E.depart.set(E.cibles);
        appliquerGeometrie(1);
      } else transition(encours);
    },
    /** Le mandat grossit : la nappe suit l'encours, puis revient. */
    balayer({ jusqua, duree = 7000, surPas, fin } = {}) {
      if (!E.grille) return;
      E.choisi = null; placerOffres();
      if (surApercu) surApercu(null);
      const de = Math.max(1, E.encours); const jusque = Math.max(E.encours * 1.01, jusqua || E.encours * 4);
      // Échelle figée pendant tout le balayage : la nappe doit DESCENDRE à l'œil,
      // pas être recadrée à chaque image.
      calculerCibles(jusque); const bornesA = [E.yMinCible, E.yMaxCible];
      calculerCibles(de);
      E.balayage = { de, a: jusque, yMin: Math.min(bornesA[0], E.yMinCible), yMax: Math.max(bornesA[1], E.yMaxCible),
        debut: performance.now(), duree: reduit() ? 1 : duree, surPas, fin };
    },
    arreterBalayage() { if (E.balayage) E.balayage.debut = performance.now() - E.balayage.duree; },
    vue(nom) {
      const vues = { perspective: [-0.68, 0.44, 5.2], face: [0, 0.16, 5.6], dessus: [0, 1.45, 5.4], cote: [-1.5708, 0.2, 5.6] };
      [orbite.azC, orbite.elC, orbite.distC] = vues[nom] || vues.perspective;
      repos = performance.now();
    },
    choisi: () => (E.choisi ? { ...E.choisi } : null),
    appliquer() {
      if (!E.choisi) return;
      const c = E.choisi;
      E.choisi = null;
      if (surAppliquer) surAppliquer(c.remise, c.facteur);
    },
    oublier() { E.choisi = null; placerOffres(); if (surApercu) surApercu(null); },
    detruire,
  };
}

/** La lecture chiffrée du relief : quel levier pèse le plus pour ce client. */
export function sensibilite(grille, encours) {
  const base = T.tauxMoyen(grille, encours);
  const remise10 = T.tauxMoyen(T.ajuster(grille, -0.1, 1), encours) - base;
  const seuilsHaut = T.tauxMoyen(T.ajuster(grille, 0, 1.5), encours) - base;
  const seuilsBas = T.tauxMoyen(T.ajuster(grille, 0, 1 / 1.5), encours) - base;
  // La remise qui rend ce qu'on concède en abaissant les seuils d'un tiers.
  const equivalente = base > 0 ? -seuilsBas / base : NaN;
  return { base, remise10, seuilsHaut, seuilsBas, equivalente, fraisBase: T.frais(grille, encours) };
}

function pasJoli(brut) {
  if (!(brut > 0)) return 0.02;
  const e = 10 ** Math.floor(Math.log10(brut));
  for (const m of [1, 2, 2.5, 5, 10]) if (brut <= m * e) return m * e;
  return 10 * e;
}
