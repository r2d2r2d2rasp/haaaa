// Dati DEMO per Torino. Tutte le righe hanno metadata.demo = true.
//   node --env-file=.env.local scripts/seed.mjs          → inserisce
//   node --env-file=.env.local scripts/seed.mjs --clear  → rimuove solo i dati demo
import { createClient } from "@supabase/supabase-js";
const db = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, { auth: { persistSession: false } });

if (process.argv.includes("--clear")) {
  await db.from("reports").delete().eq("metadata->>demo", "true");
  await db.from("api_request_log").delete().eq("key_prefix", "ts_live_demo00");
  await db.from("devices").delete().like("name", "DEMO-%");
  console.log("dati demo rimossi"); process.exit(0);
}

// hotspot: [lon, lat, peso, raggio gradi]
const HOT = [
  [7.6800, 45.0760, 5, 0.004], // Porta Palazzo
  [7.6950, 45.0860, 4, 0.006], // Barriera di Milano
  [7.6790, 45.0440, 3, 0.005], // San Salvario
  [7.6450, 45.0580, 3, 0.006], // San Paolo
  [7.6660, 45.0950, 3, 0.006], // Borgo Vittoria
  [7.6700, 45.0160, 2, 0.007], // Lingotto / Mirafiori
  [7.6840, 45.0680, 2, 0.004], // Centro
  [7.7050, 45.0640, 1, 0.005], // Vanchiglia
];
const CATS = [["rifiuti_abbandonati", 38], ["cassonetto_pieno", 24], ["buca", 14], ["graffiti", 9], ["illuminazione", 10], ["altro", 5]];
const SEV = { rifiuti_abbandonati: 4, cassonetto_pieno: 3, buca: 4, graffiti: 1, illuminazione: 3, altro: 2 };
const pick = (items) => { const t = items.reduce((s, x) => s + x[items[0].length - 1 === 1 ? 1 : 2], 0); let r = Math.random() * t; for (const x of items) { r -= x[items[0].length - 1 === 1 ? 1 : 2]; if (r <= 0) return x; } return items[0]; };
const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;

const { data: pods } = await db.from("devices").insert([
  { name: "DEMO-SEM-01", type: "fixed", label: "Semaforo Corso Regina/Via Cigna", last_geom: "SRID=4326;POINT(7.6930 45.0850)", battery: 88, last_seen_at: new Date().toISOString() },
  { name: "DEMO-SEM-02", type: "fixed", label: "Semaforo Via Nizza/Corso Marconi", last_geom: "SRID=4326;POINT(7.6795 45.0440)", battery: 74, last_seen_at: new Date().toISOString() },
  { name: "DEMO-SEM-03", type: "fixed", label: "Semaforo Piazza Statuto", last_geom: "SRID=4326;POINT(7.6700 45.0770)", battery: 95, last_seen_at: new Date(Date.now() - 3600e3).toISOString() },
  { name: "DEMO-BUS-15", type: "mobile", label: "Bus linea 15", last_geom: "SRID=4326;POINT(7.6800 45.0600)", battery: 81, last_seen_at: new Date().toISOString() },
  { name: "DEMO-BUS-4", type: "mobile", label: "Bus linea 4", last_geom: "SRID=4326;POINT(7.6700 45.0950)", battery: 67, last_seen_at: new Date().toISOString() },
]).select("id");

const rows = [];
for (let i = 0; i < 140; i++) {
  const h = pick(HOT.map((x) => [x, x[2]]).map(([x, w]) => [x, w]));
  const c = h[0];
  const [cat] = pick(CATS);
  const ageH = Math.random() ** 1.6 * 24 * 29;
  const created = new Date(Date.now() - ageH * 3600e3);
  const r = Math.random();
  const status = ageH < 24 ? "open" : r < 0.45 ? "resolved" : r < 0.6 ? "in_progress" : r < 0.65 ? "rejected" : "open";
  const device = Math.random() < 0.45;
  rows.push({
    source: device ? "device" : "citizen",
    device_id: device ? pods[Math.floor(Math.random() * pods.length)].id : null,
    category: cat, severity: SEV[cat], status,
    geom: `SRID=4326;POINT(${(c[0] + gauss() * c[3] * 1.3).toFixed(6)} ${(c[1] + gauss() * c[3]).toFixed(6)})`,
    confidence: device ? +(0.6 + Math.random() * 0.39).toFixed(2) : 1,
    observations: 1 + (Math.random() < 0.25 ? Math.floor(Math.random() * 4) : 0),
    created_at: created.toISOString(), captured_at: created.toISOString(),
    resolved_at: status === "resolved" ? new Date(created.getTime() + (3 + Math.random() * 60) * 3600e3).toISOString() : null,
    metadata: { demo: true },
  });
}
const { error } = await db.from("reports").insert(rows);
console.log(error ? error : `inseriti ${rows.length} report demo e ${pods.length} POD demo`);
