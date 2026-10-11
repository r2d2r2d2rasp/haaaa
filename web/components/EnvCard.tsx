"use client";
import { Wind, Droplets, Radio } from "lucide-react";
import { useEnvironment } from "./useEnvironment";
import { aqiBand, METRICS, pm25Band, WEATHER } from "@/lib/metrics";

/** Scheda "Aria e clima ora": meteo e qualità dell'aria della città + media dei sensori a terra. */
export default function EnvCard() {
  const env = useEnvironment();
  if (!env) return <div className="glass p-5 h-40 animate-pulse" />;
  const c = env.city, band = aqiBand(c?.european_aqi);
  const pods = env.stations.filter((s) => s.source === "pod");
  const avg = (k: string, list = env.stations) => {
    const v = list.map((s) => s.values[k]).filter((x) => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const groundPm = avg("pm25_ugm3"), co2 = avg("co2_ppm", pods), noise = avg("noise_db", pods);
  const tiles = [
    groundPm != null && { k: "PM2.5 sensori a terra", v: `${groundPm.toFixed(1)}`, u: "µg/m³", color: pm25Band(groundPm).color },
    co2 != null && { k: "CO₂ media POD", v: `${Math.round(co2)}`, u: "ppm", color: co2 > 800 ? "#fb923c" : "#a3e635" },
    noise != null && { k: "Rumore medio POD", v: `${Math.round(noise)}`, u: "dB", color: noise > 65 ? "#fb923c" : "#22d3ee" },
    c?.no2_ugm3 != null && { k: METRICS.no2_ugm3.label + " città", v: `${Math.round(c.no2_ugm3)}`, u: "µg/m³", color: "#a78bfa" },
  ].filter(Boolean) as { k: string; v: string; u: string; color: string }[];

  return (
    <div className="glass p-5 grid md:grid-cols-[auto_1fr] gap-6 items-center">
      <div className="flex items-center gap-5">
        <div>
          <div className="label">Aria e clima ora</div>
          <div className="text-5xl font-semibold mono tracking-tight">{c?.temperature_c != null ? `${Math.round(c.temperature_c)}°` : "—"}</div>
          <div className="text-sm text-muted">{WEATHER[c?.weather_code ?? -1] ?? ""}</div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-sm px-3 py-1.5 rounded-full w-fit" style={{ color: band.color, background: `${band.color}1f`, border: `1px solid ${band.color}55` }}>Aria {band.label.toLowerCase()}</span>
          <span className="text-xs text-muted flex items-center gap-1.5"><Droplets size={13} />{c?.humidity_pct ?? "—"}% <Wind size={13} className="ml-2" />{c?.wind_kmh != null ? Math.round(c.wind_kmh) : "—"} km/h</span>
          <span className="text-xs text-muted flex items-center gap-1.5"><Radio size={13} />{env.stations.length} stazioni · {pods.length} POD</span>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {tiles.map((t) => (
          <div key={t.k} className="rounded-2xl bg-white/[.04] border border-line p-3">
            <div className="text-[11px] text-muted">{t.k}</div>
            <div className="mono text-xl" style={{ color: t.color }}>{t.v} <span className="text-xs text-muted">{t.u}</span></div>
          </div>
        ))}
      </div>
      <div className="md:col-span-2 text-[11px] text-muted">
        Fonti: {env.sources.map((s, i) => <span key={s.name}>{i > 0 && " · "}{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="underline decoration-dotted hover:text-white">{s.name}</a> : s.name}</span>)}
      </div>
    </div>
  );
}
