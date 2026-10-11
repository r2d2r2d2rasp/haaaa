// Telemetria DEMO per i POD "DEMO-*": 24 h di misure ogni 20 min + battiti e log API.
//   node --env-file=.env.local scripts/seed-telemetry.mjs
// Si rimuove insieme ai POD demo con: node --env-file=.env.local scripts/seed.mjs --clear
import { createClient } from "@supabase/supabase-js";
const db = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, { auth: { persistSession: false } });

// percorso approssimato della linea 15 e 4 (per i POD sui bus)
const ROUTES = {
  "DEMO-BUS-15": [[7.6560, 45.0700], [7.6700, 45.0690], [7.6840, 45.0680], [7.6950, 45.0650], [7.7050, 45.0640]],
  "DEMO-BUS-4": [[7.6650, 45.1100], [7.6700, 45.0950], [7.6780, 45.0800], [7.6800, 45.0650], [7.6750, 45.0450], [7.6600, 45.0300]],
};
const { data: devs } = await db.from("devices").select("id, name, type, last_geom").like("name", "DEMO-%");
const now = Date.now(), readings = [], logs = [];
for (const d of devs) {
  const base = { temp: 16 + Math.random() * 3, co2: 420 + Math.random() * 60, pm: 10 + Math.random() * 12 };
  for (let i = 72; i >= 0; i--) {
    const t = now - i * 20 * 60e3, h = new Date(t).getHours();
    const traffic = Math.max(0, Math.sin(((h - 6) / 24) * Math.PI * 2)) + (h >= 7 && h <= 9 ? 0.8 : 0) + (h >= 17 && h <= 19 ? 0.9 : 0);
    let lon = null, lat = null;
    if (ROUTES[d.name]) { const r = ROUTES[d.name], k = (i % (r.length * 2 - 2)); const p = r[k < r.length ? k : r.length * 2 - 2 - k]; [lon, lat] = [p[0] + (Math.random() - .5) * .002, p[1] + (Math.random() - .5) * .002]; }
    const metrics = {
      temperature_c: +(base.temp + 5 * Math.sin(((h - 9) / 24) * Math.PI * 2) + Math.random() * .6).toFixed(1),
      humidity_pct: Math.round(55 + 15 * Math.cos(((h - 4) / 24) * Math.PI * 2) + Math.random() * 4),
      co2_ppm: Math.round(base.co2 + traffic * 140 + Math.random() * 25),
      pm25_ugm3: +(base.pm + traffic * 9 + Math.random() * 3).toFixed(1),
      noise_db: Math.round(48 + traffic * 16 + Math.random() * 4),
    };
    const ts = new Date(t).toISOString();
    readings.push({ device_id: d.id, ts, metrics, geom: lon ? `SRID=4326;POINT(${lon} ${lat})` : null });
    logs.push({ device_id: d.id, key_prefix: "ts_live_demo00", endpoint: "readings", status: 201, ip: "10.0.0." + (10 + devs.indexOf(d)), body: { ...(lon ? { lat, lon } : {}), metrics }, ts });
    if (i % 6 === 0) logs.push({ device_id: d.id, key_prefix: "ts_live_demo00", endpoint: "heartbeat", status: Math.random() < 0.06 ? 422 : 200, ip: "10.0.0." + (10 + devs.indexOf(d)), body: { battery: 60 + Math.round(Math.random() * 35), firmware: "1.0.3" }, ts });
  }
  const last = readings[readings.length - 1];
  await db.from("devices").update({ last_seen_at: new Date().toISOString(), firmware: "1.0.3", ...(last.geom ? { last_geom: last.geom } : {}) }).eq("id", d.id);
}
for (let i = 0; i < readings.length; i += 500) await db.from("device_readings").insert(readings.slice(i, i + 500));
for (let i = 0; i < logs.length; i += 500) await db.from("api_request_log").insert(logs.slice(i, i + 500));
console.log(`${readings.length} misure e ${logs.length} log per ${devs.length} POD demo`);
