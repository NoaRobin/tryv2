// api.js — le seul endroit qui parle au serveur.

export class ErreurAPI extends Error {
  constructor(message, statut, detail) {
    super(message);
    this.statut = statut;
    this.detail = detail;
  }
}

async function lire(reponse) {
  const type = reponse.headers.get('content-type') || '';
  if (!reponse.ok) {
    let detail = reponse.statusText;
    try {
      const corps = type.includes('json') ? await reponse.json() : { detail: await reponse.text() };
      detail = corps.detail || detail;
    } catch (e) { /* corps illisible : on garde le statut */ }
    throw new ErreurAPI(typeof detail === 'string' ? detail : JSON.stringify(detail), reponse.status, detail);
  }
  return type.includes('json') ? reponse.json() : reponse.text();
}

export async function get(chemin, params) {
  const url = new URL(chemin, window.location.origin);
  if (params) {
    const p = params instanceof URLSearchParams ? params : new URLSearchParams(params);
    p.forEach((v, k) => url.searchParams.append(k, v));
  }
  return lire(await fetch(url, { headers: { Accept: 'application/json' } }));
}

export async function post(chemin, corps) {
  return lire(await fetch(chemin, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(corps || {}),
  }));
}

export async function deposer(chemin, fichier) {
  const forme = new FormData();
  forme.append('fichier', fichier, fichier.name);
  return lire(await fetch(chemin, { method: 'POST', body: forme }));
}

export function urlRapport(params) {
  const url = new URL('/api/rapport', window.location.origin);
  const p = params instanceof URLSearchParams ? params : new URLSearchParams(params || {});
  p.forEach((v, k) => url.searchParams.append(k, v));
  return url.toString();
}
