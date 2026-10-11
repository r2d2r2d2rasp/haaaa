"use client";
import { useEffect, useRef, useState } from "react";
import { Route as RouteIcon, Truck, Sparkles, MapPinned, Download } from "lucide-react";
import { useMap, maplibregl } from "@/components/useMap";
import { CATEGORIES, CAT } from "@/lib/categories";
import { CAP_CENTROIDS } from "@/lib/cap";
import { adminFetch } from "@/lib/adminClient";

const COLORS = ["#22d3ee", "#a78bfa", "#a3e635", "#fbbf24", "#fb7185", "#38bdf8", "#f472b6", "#34d399", "#f97316", "#818cf8"];
type Stop = { id: string; lon: number; lat: number; severity: number; category: string; cap: string };
type Result = { totalCandidates: number; routes: { vehicle: number; stops: Stop[]; geometry: [number, number][]; km: number; minutes: number; savedPercent: number; roadRouted: boolean }[] };

export default function RoutesPage() {
  const { el, map, ready } = useMap();
  const [depot, setDepot] = useState<{ lat: number; lon: number }>({ lat: 45.0703, lon: 7.6869 });
  const [vehicles, setVehicles] = useState(2);
  const [cats, setCats] = useState<string[]>(["rifiuti_abbandonati"]);
  const [cap, setCap] = useState("");
  const [minSeverity, setMinSeverity] = useState(1);
  const [maxStops, setMaxStops] = useState(20);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState("");
  const overlays = useRef<maplibregl.Marker[]>([]);
  const depotMarker = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    m.on("click", (e) => setDepot({ lat: e.lngLat.lat, lon: e.lngLat.lng }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    if (!depotMarker.current) {
      const d = document.createElement("div");
      d.textContent = "🏭"; d.style.cssText = "font-size:26px;filter:drop-shadow(0 0 10px #22d3ee)";
      depotMarker.current = new maplibregl.Marker({ element: d });
    }
    depotMarker.current.setLngLat([depot.lon, depot.lat]).addTo(m);
  }, [depot, ready, map]);

  // disegna il risultato
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    overlays.current.forEach((x) => x.remove()); overlays.current = [];
    for (let i = 0; i < 10; i++) { if (m.getLayer(`r${i}`)) m.removeLayer(`r${i}`); if (m.getLayer(`r${i}g`)) m.removeLayer(`r${i}g`); if (m.getSource(`r${i}`)) m.removeSource(`r${i}`); }
    if (!res) return;
    const bounds = new maplibregl.LngLatBounds([depot.lon, depot.lat], [depot.lon, depot.lat]);
    res.routes.forEach((r, i) => {
      const color = COLORS[i % COLORS.length];
      m.addSource(`r${i}`, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r.geometry } } });
      m.addLayer({ id: `r${i}g`, type: "line", source: `r${i}`, paint: { "line-color": color, "line-width": 10, "line-opacity": 0.2, "line-blur": 6 } });
      m.addLayer({ id: `r${i}`, type: "line", source: `r${i}`, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": color, "line-width": 3.5 } });
      r.stops.forEach((s, k) => {
        const n = document.createElement("div");
        n.textContent = String(k + 1);
        n.style.cssText = `width:24px;height:24px;border-radius:50%;background:${color};color:#04121a;font:700 12px system-ui;display:grid;place-items:center;box-shadow:0 0 14px ${color};border:2px solid #0b0f1a`;
        overlays.current.push(new maplibregl.Marker({ element: n }).setLngLat([s.lon, s.lat]).addTo(m));
        bounds.extend([s.lon, s.lat]);
      });
    });
    m.fitBounds(bounds, { padding: { top: 80, bottom: 80, left: 380, right: 60 }, maxZoom: 15 });
  }, [res, ready, map, depot]);

  async function run() {
    setBusy(true); setErr(""); setRes(null);
    const r = await adminFetch("/api/routes/optimize", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ depot, vehicles, categories: cats.length ? cats : undefined, cap: cap || undefined, minSeverity, maxStops }) });
    const j = await r.json(); setBusy(false);
    if (!r.ok) return setErr("Errore nel calcolo, riprova.");
    if (!j.routes.length) return setErr("Nessuna segnalazione aperta con questi filtri.");
    setRes(j);
  }

  const gmaps = (r: Result["routes"][number]) => {
    const pts = [`${depot.lat},${depot.lon}`, ...r.stops.map((s) => `${s.lat},${s.lon}`), `${depot.lat},${depot.lon}`];
    return `https://www.google.com/maps/dir/${pts.join("/")}`;
  };
  const gpx = (r: Result["routes"][number]) => {
    const body = r.geometry.map(([lo, la]) => `<trkpt lat="${la}" lon="${lo}"/>`).join("");
    const url = URL.createObjectURL(new Blob([`<?xml version="1.0"?><gpx version="1.1" creator="TorinoSegnala"><trk><name>Mezzo ${r.vehicle}</name><trkseg>${body}</trkseg></trk></gpx>`], { type: "application/gpx+xml" }));
    const a = document.createElement("a"); a.href = url; a.download = `percorso-mezzo-${r.vehicle}.gpx`; a.click();
  };

  const totalKm = res?.routes.reduce((s, r) => s + r.km, 0) ?? 0;

  return (
    <div className="relative flex-1 min-h-screen">
      <div ref={el} className="map-fill" />
      <aside className="glass absolute left-3 sm:left-6 top-3 w-[min(92vw,350px)] p-4 flex flex-col gap-4 max-h-[calc(100%-1.5rem)] overflow-y-auto">
        <div>
          <div className="flex items-center gap-2 text-xl font-semibold"><RouteIcon className="text-cyan" size={20} /> Ottimizza <span className="glow-text">raccolta</span></div>
          <p className="text-xs text-muted mt-1">Pianifica il giro dei mezzi sulle segnalazioni aperte. Clicca sulla mappa per spostare il deposito 🏭.</p>
        </div>
        <div>
          <div className="label mb-2">Categorie</div>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((c) => <button key={c.slug} className="chip" data-on={cats.includes(c.slug)} onClick={() => setCats(cats.includes(c.slug) ? cats.filter((x) => x !== c.slug) : [...cats, c.slug])}>{c.icon} {c.name}</button>)}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label><div className="label mb-1.5 flex items-center gap-1"><Truck size={12} /> Mezzi: <b className="text-white mono">{vehicles}</b></div>
            <input type="range" min={1} max={8} value={vehicles} onChange={(e) => setVehicles(+e.target.value)} className="w-full accent-cyan-400" /></label>
          <label><div className="label mb-1.5">Max tappe: <b className="text-white mono">{maxStops}</b></div>
            <input type="range" min={5} max={60} step={5} value={maxStops} onChange={(e) => setMaxStops(+e.target.value)} className="w-full accent-cyan-400" /></label>
          <label><div className="label mb-1.5">Gravità min: <b className="text-white mono">{minSeverity}</b></div>
            <input type="range" min={1} max={5} value={minSeverity} onChange={(e) => setMinSeverity(+e.target.value)} className="w-full accent-cyan-400" /></label>
          <label><div className="label mb-1.5">CAP</div>
            <select className="input !py-2" value={cap} onChange={(e) => setCap(e.target.value)}>
              <option value="">Tutta Torino</option>{Object.keys(CAP_CENTROIDS).map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        </div>
        <button className="btn" disabled={busy} onClick={run}><Sparkles size={16} /> {busy ? "Calcolo…" : "Calcola percorsi"}</button>
        {err && <div className="text-sm text-rose-300 bg-rose-500/10 border border-rose-400/20 rounded-2xl px-4 py-3">{err}</div>}

        {res && (
          <div className="flex flex-col gap-3">
            <div className="rounded-2xl bg-white/5 p-3 text-sm flex justify-between">
              <span><b className="mono">{res.routes.reduce((s, r) => s + r.stops.length, 0)}</b> tappe / {res.totalCandidates}</span>
              <span><b className="mono">{totalKm.toFixed(1)}</b> km totali</span>
            </div>
            {res.routes.map((r, i) => (
              <div key={r.vehicle} className="rounded-2xl border p-3" style={{ borderColor: `${COLORS[i % 10]}66`, background: `${COLORS[i % 10]}0d` }}>
                <div className="flex justify-between items-center mb-1">
                  <div className="font-semibold flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{ background: COLORS[i % 10] }} />Mezzo {r.vehicle}</div>
                  <div className="text-xs mono text-muted">{r.stops.length} tappe · {r.km.toFixed(1)} km · {Math.round(r.minutes)} min</div>
                </div>
                <div className="text-xs text-muted mb-2">{r.savedPercent > 0 ? `−${r.savedPercent}% di strada rispetto all'ordine di arrivo · ` : ""}{r.roadRouted ? "percorso stradale" : "stima in linea d'aria"}</div>
                <ol className="text-xs flex flex-col gap-0.5 mb-2 max-h-28 overflow-y-auto">
                  {r.stops.map((s, k) => <li key={s.id} className="flex gap-2"><span className="mono text-muted w-5">{k + 1}.</span>{CAT[s.category]?.icon} {CAT[s.category]?.name} <span className="text-muted ml-auto">CAP {s.cap}</span></li>)}
                </ol>
                <div className="flex gap-2">
                  <a className="btn-ghost !py-1.5 !text-xs" href={gmaps(r)} target="_blank" rel="noreferrer"><MapPinned size={13} /> Google Maps</a>
                  <button className="btn-ghost !py-1.5 !text-xs" onClick={() => gpx(r)}><Download size={13} /> GPX</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
