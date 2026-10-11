import { parsePoint } from "./geo";
import { capFor } from "./cap";

export type ReportRow = {
  id: string; source: "citizen" | "device"; device_id: string | null; category: string;
  description: string | null; geom: string; photo_url: string | null; confidence: number;
  severity: number; status: string; observations: number; created_at: string; resolved_at: string | null;
};
export const REPORT_COLS =
  "id, source, device_id, category, description, geom, photo_url, confidence, severity, status, observations, created_at, resolved_at";

export function shape(r: ReportRow) {
  const p = parsePoint(r.geom);
  if (!p) return null;
  const { geom: _g, ...rest } = r;
  void _g;
  return { ...rest, lat: p.lat, lon: p.lon, cap: capFor(p.lon, p.lat) };
}
export type Report = NonNullable<ReturnType<typeof shape>>;
