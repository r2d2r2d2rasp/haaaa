"use client";
import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { TORINO_CENTER } from "@/lib/categories";

// Turbopack non impacchetta il worker di MapLibre: lo serviamo da /public (copiato in postinstall).
if (typeof window !== "undefined") maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");

export const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

/** Crea una mappa MapLibre in un div. `ready` diventa true a stile caricato. */
export function useMap(opts: { zoom?: number; center?: [number, number]; pitch?: number } = {}) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!el.current) return;
    const map = new maplibregl.Map({
      container: el.current, style: MAP_STYLE,
      center: opts.center ?? TORINO_CENTER, zoom: opts.zoom ?? 11.6, pitch: opts.pitch ?? 0, attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => setReady(true));
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; setReady(false); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { el, map: mapRef, ready };
}

export { maplibregl };
