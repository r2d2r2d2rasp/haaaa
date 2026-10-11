import { haversine } from "./geo";

export type Stop = { id: string; lon: number; lat: number; severity: number; category: string; cap: string };
type P = [number, number];

const pt = (s: Stop): P => [s.lon, s.lat];
// Le strade sono più lunghe della linea d'aria: fattore empirico urbano.
const D = (a: P, b: P) => haversine(a, b) * 1.3;

function tourLength(depot: P, order: Stop[]) {
  let t = 0, cur = depot;
  for (const s of order) { t += D(cur, pt(s)); cur = pt(s); }
  return t + D(cur, depot);
}

/** Nearest neighbour con leggera preferenza per severità alta, poi 2-opt. */
export function solveTour(depot: P, stops: Stop[]): Stop[] {
  const left = [...stops], order: Stop[] = [];
  let cur = depot;
  while (left.length) {
    let bi = 0, bs = Infinity;
    left.forEach((s, i) => {
      const score = D(cur, pt(s)) / (1 + 0.12 * (s.severity - 1));
      if (score < bs) { bs = score; bi = i; }
    });
    const [n] = left.splice(bi, 1);
    order.push(n); cur = pt(n);
  }
  let improved = true, guard = 0;
  while (improved && guard++ < 60) {
    improved = false;
    for (let i = 0; i < order.length - 1; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const cand = [...order.slice(0, i), ...order.slice(i, j + 1).reverse(), ...order.slice(j + 1)];
        if (tourLength(depot, cand) < tourLength(depot, order) - 1) { order.splice(0, order.length, ...cand); improved = true; }
      }
    }
  }
  return order;
}

/** Divide le tappe in k gruppi compatti (k-means sulle coordinate, inizializzato a settori angolari). */
export function splitStops(depot: P, stops: Stop[], k: number): Stop[][] {
  if (k <= 1 || stops.length <= k) return k <= 1 ? [stops] : stops.map((s) => [s]);
  const ang = (s: Stop) => Math.atan2(s.lat - depot[1], s.lon - depot[0]);
  const sorted = [...stops].sort((a, b) => ang(a) - ang(b));
  let centers: P[] = Array.from({ length: k }, (_, i) => pt(sorted[Math.floor(((i + 0.5) * sorted.length) / k)]));
  let groups: Stop[][] = [];
  for (let it = 0; it < 15; it++) {
    groups = Array.from({ length: k }, () => []);
    for (const s of stops) {
      let bi = 0, bd = Infinity;
      centers.forEach((c, i) => { const d = haversine(pt(s), c); if (d < bd) { bd = d; bi = i; } });
      groups[bi].push(s);
    }
    centers = groups.map((g, i) => g.length
      ? [g.reduce((a, s) => a + s.lon, 0) / g.length, g.reduce((a, s) => a + s.lat, 0) / g.length] as P
      : centers[i]);
  }
  return groups.filter((g) => g.length);
}

export const tourStats = (depot: P, order: Stop[]) => {
  const meters = tourLength(depot, order);
  // ~22 km/h medi urbani + 4 minuti per tappa di raccolta
  return { meters, minutes: (meters / 1000 / 22) * 60 + order.length * 4 };
};
