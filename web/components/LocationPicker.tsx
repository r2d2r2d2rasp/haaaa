"use client";
import { useEffect, useRef } from "react";
import { useMap, maplibregl } from "./useMap";

export default function LocationPicker({ value, onChange }: { value: { lat: number; lon: number } | null; onChange: (v: { lat: number; lon: number }) => void }) {
  const { el, map, ready } = useMap({ zoom: 13 });
  const marker = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    m.on("click", (e) => onChange({ lat: e.lngLat.lat, lon: e.lngLat.lng }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  useEffect(() => {
    const m = map.current; if (!ready || !m || !value) return;
    if (!marker.current) {
      const dot = document.createElement("div");
      dot.className = "pod-marker live"; dot.style.background = "#22d3ee"; dot.style.color = "#22d3ee";
      marker.current = new maplibregl.Marker({ element: dot });
    }
    marker.current.setLngLat([value.lon, value.lat]).addTo(m);
    m.easeTo({ center: [value.lon, value.lat], zoom: Math.max(m.getZoom(), 15) });
  }, [value, ready, map]);

  return <div className="relative h-64 rounded-2xl overflow-hidden border border-line"><div ref={el} className="map-fill" /></div>;
}
