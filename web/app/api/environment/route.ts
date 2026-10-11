import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";
import { parsePoint } from "@/lib/geo";

export const dynamic = "force-dynamic";

const LAT = 45.0703, LON = 7.6869;
export type Station = {
  id: string; source: "sensor.community" | "pod"; name: string; lat: number; lon: number; ts: string;
  values: Record<string, number>;
};

type SCEntry = { timestamp: string; location: { id: number; latitude: string; longitude: string }; sensordatavalues: { value_type: string; value: string }[] };
const SC_MAP: Record<string, string> = { P2: "pm25_ugm3", P1: "pm10_ugm3", temperature: "temperature_c", humidity: "humidity_pct", pressure_at_sealevel: "pressure_hpa" };

/** Sensori civici Sensor.Community (ex Luftdaten) entro 12 km da Torino: PM, temperatura, umidità. */
async function sensorCommunity(): Promise<Station[]> {
  try {
    const r = await fetch(`https://data.sensor.community/airrohr/v1/filter/area=${LAT},${LON},12`, { next: { revalidate: 300 }, signal: AbortSignal.timeout(8000) });
    const data = (await r.json()) as SCEntry[];
    const byLoc = new Map<number, Station>();
    for (const e of data) {
      const id = e.location.id;
      const st = byLoc.get(id) ?? { id: `sc-${id}`, source: "sensor.community" as const, name: `Sensore civico #${id}`, lat: +e.location.latitude, lon: +e.location.longitude, ts: e.timestamp, values: {} };
      for (const v of e.sensordatavalues) {
        const k = SC_MAP[v.value_type]; const n = Number(v.value);
        if (k && Number.isFinite(n)) st.values[k] = k === "pressure_hpa" ? Math.round(n / 100) : Math.round(n * 10) / 10;
      }
      if (e.timestamp > st.ts) st.ts = e.timestamp;
      byLoc.set(id, st);
    }
    return [...byLoc.values()].filter((s) => Object.keys(s.values).length);
  } catch { return []; }
}

/** Meteo e qualità dell'aria cittadina (modelli Open-Meteo / Copernicus CAMS). */
async function openMeteo() {
  try {
    const [w, a] = await Promise.all([
      fetch(`https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,precipitation&timezone=Europe%2FRome`, { next: { revalidate: 600 }, signal: AbortSignal.timeout(8000) }).then((r) => r.json()),
      fetch(`https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${LAT}&longitude=${LON}&current=european_aqi,pm10,pm2_5,nitrogen_dioxide,ozone&timezone=Europe%2FRome`, { next: { revalidate: 600 }, signal: AbortSignal.timeout(8000) }).then((r) => r.json()),
    ]);
    return {
      time: w.current?.time, temperature_c: w.current?.temperature_2m, humidity_pct: w.current?.relative_humidity_2m,
      wind_kmh: w.current?.wind_speed_10m, weather_code: w.current?.weather_code, precipitation_mm: w.current?.precipitation,
      european_aqi: a.current?.european_aqi, pm25_ugm3: a.current?.pm2_5, pm10_ugm3: a.current?.pm10,
      no2_ugm3: a.current?.nitrogen_dioxide, o3_ugm3: a.current?.ozone,
    };
  } catch { return null; }
}

/** Ultima misura di ogni POD nelle ultime 3 ore. */
async function pods(): Promise<Station[]> {
  const db = supabaseAdmin();
  const { data } = await db.from("device_readings").select("device_id, ts, geom, metrics, devices(name, label, last_geom)")
    .gte("ts", new Date(Date.now() - 3 * 3600e3).toISOString()).order("ts", { ascending: false }).limit(1000);
  const seen = new Map<string, Station>();
  for (const r of data ?? []) {
    if (seen.has(r.device_id)) continue;
    const dev = (Array.isArray(r.devices) ? r.devices[0] : r.devices) as { name: string; label: string | null; last_geom: string | null } | null;
    const p = parsePoint(r.geom as string) ?? parsePoint(dev?.last_geom);
    if (!p) continue;
    seen.set(r.device_id, { id: `pod-${r.device_id}`, source: "pod", name: dev?.label || dev?.name || "POD", lat: p.lat, lon: p.lon, ts: r.ts, values: r.metrics as Record<string, number> });
  }
  return [...seen.values()];
}

export async function GET() {
  const [city, sc, pd] = await Promise.all([openMeteo(), sensorCommunity(), pods()]);
  return NextResponse.json({
    city, stations: [...pd, ...sc],
    sources: [
      { name: "Open-Meteo / Copernicus CAMS", url: "https://open-meteo.com", kind: "modello meteo e aria (città)" },
      { name: "Sensor.Community", url: "https://sensor.community", kind: "sensori civici PM e meteo" },
      { name: "POD TorinoSegnala", url: "", kind: "sensori sui POD (CO₂, temperatura, …)" },
    ],
  });
}
