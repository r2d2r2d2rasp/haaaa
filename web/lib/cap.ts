import { haversine } from "./geo";

// ATTENZIONE: centroidi APPROSSIMATI dei CAP di Torino. Il CAP di una segnalazione è quello del
// centroide più vicino (diagramma di Voronoi). Da sostituire con i poligoni ufficiali (dati aperti
// Comune di Torino / geoportale) caricandoli in cap_zones.
export const CAP_CENTROIDS: Record<string, [number, number]> = {
  "10121": [7.6840, 45.0680], "10122": [7.6800, 45.0760], "10123": [7.6790, 45.0600],
  "10124": [7.7010, 45.0640], "10125": [7.6800, 45.0450], "10126": [7.6620, 45.0330],
  "10127": [7.6400, 45.0140], "10128": [7.6620, 45.0560], "10129": [7.6540, 45.0600],
  "10131": [7.7000, 45.0560], "10132": [7.7350, 45.0750], "10133": [7.6900, 45.0300],
  "10134": [7.6580, 45.0230], "10135": [7.6700, 45.0150], "10136": [7.6450, 45.0430],
  "10137": [7.6700, 45.0300], "10138": [7.6450, 45.0580], "10139": [7.6330, 45.0680],
  "10141": [7.6450, 45.0830], "10142": [7.6250, 45.0780], "10143": [7.6550, 45.0950],
  "10144": [7.6660, 45.0950], "10145": [7.6200, 45.0700], "10146": [7.6600, 45.0770],
  "10147": [7.6900, 45.0940], "10148": [7.7100, 45.1200], "10149": [7.6350, 45.0950],
  "10151": [7.6450, 45.0920], "10152": [7.6950, 45.0860], "10153": [7.7050, 45.0800],
  "10154": [7.7000, 45.1000], "10155": [7.7200, 45.1100], "10156": [7.7050, 45.1250],
};

export function capFor(lon: number, lat: number): string {
  let best = "N/D", d = Infinity;
  for (const [cap, c] of Object.entries(CAP_CENTROIDS)) {
    const x = haversine([lon, lat], c);
    if (x < d) { d = x; best = cap; }
  }
  return best;
}
