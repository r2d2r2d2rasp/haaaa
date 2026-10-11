"use client";
import { useEffect, useState } from "react";

export type EnvStation = { id: string; source: "sensor.community" | "pod"; name: string; lat: number; lon: number; ts: string; values: Record<string, number> };
export type EnvCity = { temperature_c?: number; humidity_pct?: number; wind_kmh?: number; weather_code?: number; precipitation_mm?: number; european_aqi?: number; pm25_ugm3?: number; pm10_ugm3?: number; no2_ugm3?: number; o3_ugm3?: number } | null;
export type EnvData = { city: EnvCity; stations: EnvStation[]; sources: { name: string; url: string; kind: string }[] };

/** Dati ambientali aggregati (Open-Meteo, Sensor.Community, POD), aggiornati ogni 5 minuti. */
export function useEnvironment() {
  const [env, setEnv] = useState<EnvData | null>(null);
  useEffect(() => {
    const f = () => fetch("/api/environment").then((r) => r.json()).then(setEnv).catch(() => {});
    f(); const t = setInterval(f, 300_000); return () => clearInterval(t);
  }, []);
  return env;
}
