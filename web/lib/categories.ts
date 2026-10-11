export const CATEGORIES = [
  { slug: "rifiuti_abbandonati", name: "Rifiuti abbandonati", icon: "🗑️", color: "#fb7185" },
  { slug: "cassonetto_pieno", name: "Cassonetto pieno", icon: "♻️", color: "#fbbf24" },
  { slug: "buca", name: "Buca stradale", icon: "🕳️", color: "#a78bfa" },
  { slug: "graffiti", name: "Graffiti / vandalismo", icon: "🎨", color: "#22d3ee" },
  { slug: "illuminazione", name: "Illuminazione guasta", icon: "💡", color: "#a3e635" },
  { slug: "altro", name: "Altro", icon: "📍", color: "#94a3b8" },
] as const;

export const CAT = Object.fromEntries(CATEGORIES.map((c) => [c.slug, c]));
export const STATUS_LABEL: Record<string, string> = {
  open: "Aperta", in_progress: "In lavorazione", resolved: "Risolta", rejected: "Respinta",
};
export const TORINO_CENTER: [number, number] = [7.6869, 45.0703]; // [lon, lat]
