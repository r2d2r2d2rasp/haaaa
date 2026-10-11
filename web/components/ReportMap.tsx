"use client";
import { useEffect, useRef } from "react";
import { useMap, maplibregl } from "./useMap";
import { CATEGORIES } from "@/lib/categories";
import type { Report } from "@/lib/reports";
import type { EnvStation } from "./useEnvironment";
import { METRICS, pm25Band } from "@/lib/metrics";

export type PodDevice = { id: string; name: string; type: "fixed" | "mobile"; label: string | null; lat: number | null; lon: number | null; battery: number | null; last_seen_at: string | null; online: boolean };

const colorExpr = [
  "match", ["get", "category"], ...CATEGORIES.flatMap((c) => [c.slug, c.color]), "#94a3b8",
] as unknown as maplibregl.ExpressionSpecification;

export default function ReportMap({ reports, devices = [], stations = [], heat = false, onSelect }: {
  reports: Report[]; devices?: PodDevice[]; stations?: EnvStation[]; heat?: boolean; onSelect: (r: Report) => void;
}) {
  const { el, map, ready } = useMap();
  const markers = useRef<maplibregl.Marker[]>([]);
  const envMarkers = useRef<maplibregl.Marker[]>([]);
  const byId = useRef<Record<string, Report>>({});

  // sorgenti e layer (una volta)
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    m.addSource("reports", { type: "geojson", data: { type: "FeatureCollection", features: [] }, cluster: true, clusterRadius: 38, clusterMaxZoom: 15 });
    m.addLayer({ id: "heat", type: "heatmap", source: "reports", maxzoom: 17, layout: { visibility: "none" }, paint: {
      "heatmap-weight": ["interpolate", ["linear"], ["get", "severity"], 1, 0.3, 5, 1],
      "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 10, 18, 15, 42],
      "heatmap-intensity": 1.3,
      "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "#3b2f8f", 0.45, "#a78bfa", 0.7, "#22d3ee", 1, "#fef08a"],
    } });
    m.addLayer({ id: "clusters", type: "circle", source: "reports", filter: ["has", "point_count"], paint: {
      "circle-color": "rgba(34,211,238,0.22)", "circle-stroke-color": "#22d3ee", "circle-stroke-width": 1.5,
      "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 30, 30],
    } });
    m.addLayer({ id: "cluster-count", type: "symbol", source: "reports", filter: ["has", "point_count"], layout: {
      "text-field": ["get", "point_count_abbreviated"], "text-size": 12, "text-font": ["Montserrat Medium", "Open Sans Semibold"],
    }, paint: { "text-color": "#e8ecf8" } });
    m.addLayer({ id: "glow", type: "circle", source: "reports", filter: ["!", ["has", "point_count"]], paint: {
      "circle-color": colorExpr, "circle-opacity": 0.22, "circle-blur": 0.8,
      "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 1, 10, 5, 22],
    } });
    m.addLayer({ id: "points", type: "circle", source: "reports", filter: ["!", ["has", "point_count"]], paint: {
      "circle-color": colorExpr, "circle-stroke-color": "#0b0f1a", "circle-stroke-width": 1.5,
      "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 1, 4.5, 5, 9],
    } });
    m.on("click", "clusters", (e) => {
      const f = m.queryRenderedFeatures(e.point, { layers: ["clusters"] })[0];
      const src = m.getSource("reports") as maplibregl.GeoJSONSource;
      src.getClusterExpansionZoom(Number(f.properties?.cluster_id)).then((z) => m.easeTo({ center: (f.geometry as GeoJSON.Point).coordinates as [number, number], zoom: z + 0.3 }));
    });
    m.on("click", "points", (e) => {
      const id = e.features?.[0]?.properties?.id as string;
      if (byId.current[id]) onSelect(byId.current[id]);
    });
    for (const l of ["clusters", "points"]) {
      m.on("mouseenter", l, () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", l, () => (m.getCanvas().style.cursor = ""));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  // dati
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    byId.current = Object.fromEntries(reports.map((r) => [r.id, r]));
    (m.getSource("reports") as maplibregl.GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: reports.map((r) => ({ type: "Feature", properties: { id: r.id, category: r.category, severity: r.severity }, geometry: { type: "Point", coordinates: [r.lon, r.lat] } })),
    });
  }, [reports, ready, map]);

  // modalità heatmap
  useEffect(() => {
    const m = map.current; if (!ready || !m || !m.getLayer("heat")) return;
    m.setLayoutProperty("heat", "visibility", heat ? "visible" : "none");
    for (const l of ["clusters", "cluster-count", "glow", "points"]) m.setLayoutProperty(l, "visibility", heat ? "none" : "visible");
  }, [heat, ready, map]);

  // POD come marker HTML pulsanti
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    markers.current.forEach((x) => x.remove());
    markers.current = devices.filter((d) => d.lat != null && d.lon != null).map((d) => {
      const dot = document.createElement("div");
      dot.className = `pod-marker ${d.online ? "live" : ""}`;
      dot.style.background = d.type === "mobile" ? "#a78bfa" : "#a3e635";
      dot.style.color = d.type === "mobile" ? "#a78bfa" : "#a3e635";
      dot.style.opacity = d.online ? "1" : "0.45";
      const popup = new maplibregl.Popup({ offset: 14, closeButton: false }).setHTML(
        `<div style="color:#0b0f1a;font:13px system-ui"><b>${d.name}</b><br/>${d.label ?? ""}<br/>${d.type === "mobile" ? "POD mobile" : "POD fisso"} · ${d.online ? "online" : "offline"}${d.battery != null ? ` · 🔋${Math.round(d.battery)}%` : ""}</div>`);
      return new maplibregl.Marker({ element: dot }).setLngLat([d.lon!, d.lat!]).setPopup(popup).addTo(m);
    });
  }, [devices, ready, map]);

  // stazioni ambientali: pastiglia col valore principale (PM2.5, altrimenti temperatura)
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    envMarkers.current.forEach((x) => x.remove());
    envMarkers.current = stations.map((st) => {
      const pm = st.values.pm25_ugm3, t = st.values.temperature_c;
      const color = pm != null ? pm25Band(pm).color : "#22d3ee";
      const pill = document.createElement("div");
      pill.style.cssText = `display:flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;background:rgba(11,15,26,.88);border:1px solid ${color}66;color:#e8ecf8;font:600 11px ui-monospace,monospace;box-shadow:0 0 14px -2px ${color}88;cursor:pointer;white-space:nowrap`;
      pill.innerHTML = `<span style="width:7px;height:7px;border-radius:50%;background:${color}"></span>${pm != null ? `${Math.round(pm)} <span style="opacity:.6">PM2.5</span>` : t != null ? `${t.toFixed(1)}°` : "•"}${st.source === "pod" ? ' <span style="color:#a78bfa">POD</span>' : ""}`;
      const rows = Object.entries(st.values).map(([k, v]) => `<tr><td style="padding:2px 10px 2px 0;color:#64748b">${METRICS[k]?.icon ?? ""} ${METRICS[k]?.label ?? k}</td><td style="text-align:right"><b>${v}</b> ${METRICS[k]?.unit ?? ""}</td></tr>`).join("");
      const popup = new maplibregl.Popup({ offset: 12, closeButton: false, maxWidth: "260px" }).setHTML(
        `<div style="color:#0b0f1a;font:13px system-ui"><b>${st.name}</b><div style="color:#64748b;font-size:11px;margin-bottom:6px">${st.source === "pod" ? "POD TorinoSegnala" : "Sensor.Community"} · ${new Date(st.ts.replace(" ", "T") + (st.ts.includes("Z") || st.source === "pod" ? "" : "Z")).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</div><table style="font-size:12px">${rows}</table></div>`);
      return new maplibregl.Marker({ element: pill }).setLngLat([st.lon, st.lat]).setPopup(popup).addTo(m);
    });
  }, [stations, ready, map]);

  return <div ref={el} className="map-fill" />;
}
