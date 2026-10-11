import { z } from "zod";

/** Nomi consigliati per le metriche dei sensori (altri nomi sono accettati: snake_case, numerici). */
export const METRICS: Record<string, { label: string; unit: string; icon: string }> = {
  temperature_c: { label: "Temperatura", unit: "°C", icon: "🌡️" },
  humidity_pct: { label: "Umidità", unit: "%", icon: "💧" },
  co2_ppm: { label: "CO₂", unit: "ppm", icon: "🫧" },
  pm25_ugm3: { label: "PM2.5", unit: "µg/m³", icon: "🌫️" },
  pm10_ugm3: { label: "PM10", unit: "µg/m³", icon: "🌫️" },
  no2_ugm3: { label: "NO₂", unit: "µg/m³", icon: "🏭" },
  noise_db: { label: "Rumore", unit: "dB", icon: "🔊" },
  pressure_hpa: { label: "Pressione", unit: "hPa", icon: "🧭" },
  voc_index: { label: "VOC", unit: "idx", icon: "🧪" },
};

export const MetricsSchema = z.record(z.string().regex(/^[a-z0-9_]{1,32}$/), z.number().finite()).refine((m) => Object.keys(m).length > 0 && Object.keys(m).length <= 30, "da 1 a 30 metriche");

/** Fascia di qualità dell'aria (indice europeo, PM2.5 in µg/m³). */
export function pm25Band(v: number | null | undefined) {
  if (v == null) return { label: "n/d", color: "#8b95b3" };
  if (v <= 10) return { label: "Buona", color: "#a3e635" };
  if (v <= 20) return { label: "Discreta", color: "#d9f99d" };
  if (v <= 25) return { label: "Moderata", color: "#fbbf24" };
  if (v <= 50) return { label: "Scadente", color: "#fb923c" };
  if (v <= 75) return { label: "Pessima", color: "#fb7185" };
  return { label: "Molto pessima", color: "#c026d3" };
}

export function aqiBand(eaqi: number | null | undefined) {
  if (eaqi == null) return { label: "n/d", color: "#8b95b3" };
  if (eaqi <= 20) return { label: "Buona", color: "#a3e635" };
  if (eaqi <= 40) return { label: "Discreta", color: "#d9f99d" };
  if (eaqi <= 60) return { label: "Moderata", color: "#fbbf24" };
  if (eaqi <= 80) return { label: "Scadente", color: "#fb923c" };
  if (eaqi <= 100) return { label: "Pessima", color: "#fb7185" };
  return { label: "Molto pessima", color: "#c026d3" };
}

export const WEATHER: Record<number, string> = {
  0: "☀️ Sereno", 1: "🌤️ Poco nuvoloso", 2: "⛅ Parz. nuvoloso", 3: "☁️ Coperto", 45: "🌫️ Nebbia", 48: "🌫️ Nebbia",
  51: "🌦️ Pioviggine", 53: "🌦️ Pioviggine", 55: "🌦️ Pioviggine", 61: "🌧️ Pioggia", 63: "🌧️ Pioggia", 65: "🌧️ Pioggia forte",
  71: "🌨️ Neve", 73: "🌨️ Neve", 75: "🌨️ Neve forte", 80: "🌦️ Rovesci", 81: "🌦️ Rovesci", 82: "⛈️ Rovesci forti", 95: "⛈️ Temporale", 96: "⛈️ Temporale", 99: "⛈️ Temporale",
};
