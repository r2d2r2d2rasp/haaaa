import { NextResponse } from "next/server";
import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";
import { REPORT_COLS, shape, type ReportRow } from "@/lib/reports";
import { solveTour, splitStops, tourStats, type Stop } from "@/lib/optimize";

export const dynamic = "force-dynamic";

const Body = z.object({
  depot: z.object({ lat: z.number(), lon: z.number() }),
  vehicles: z.number().int().min(1).max(10).default(1),
  categories: z.array(z.string()).optional(),
  cap: z.string().optional(),
  minSeverity: z.number().int().min(1).max(5).default(1),
  maxStops: z.number().int().min(1).max(60).default(30),
});

/** Geometria stradale reale via OSRM pubblico; se non disponibile si usa la linea retta tra le tappe. */
async function roadGeometry(coords: [number, number][]): Promise<{ line: [number, number][]; km: number | null; min: number | null }> {
  try {
    const path = coords.map((c) => c.join(",")).join(";");
    const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${path}?overview=full&geometries=geojson`, { signal: AbortSignal.timeout(6000) });
    const j = await r.json();
    if (j.code === "Ok") return { line: j.routes[0].geometry.coordinates, km: j.routes[0].distance / 1000, min: j.routes[0].duration / 60 };
  } catch { /* fallback */ }
  return { line: coords, km: null, min: null };
}

export async function POST(req: Request) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid_payload", details: parsed.error.flatten() }, { status: 422 });
  const b = parsed.data;

  let q = supabaseAdmin().from("reports").select(REPORT_COLS).in("status", ["open", "in_progress"]).gte("severity", b.minSeverity).limit(2000);
  if (b.categories?.length) q = q.in("category", b.categories);
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });

  let rows = (data as unknown as ReportRow[]).map(shape).filter((r): r is NonNullable<typeof r> => !!r);
  if (b.cap) rows = rows.filter((r) => r.cap === b.cap);
  // priorità: severità × confidenza × osservazioni
  rows.sort((a, c) => c.severity * c.confidence * (1 + Math.log(c.observations)) - a.severity * a.confidence * (1 + Math.log(a.observations)));
  const picked = rows.slice(0, b.maxStops);

  const depot: [number, number] = [b.depot.lon, b.depot.lat];
  const stops: Stop[] = picked.map((r) => ({ id: r.id, lon: r.lon, lat: r.lat, severity: r.severity, category: r.category, cap: r.cap }));
  const groups = splitStops(depot, stops, b.vehicles);

  const routes = await Promise.all(groups.map(async (g, i) => {
    const order = solveTour(depot, g);
    const naive = tourStats(depot, g);        // ordine di arrivo (senza ottimizzazione)
    const opt = tourStats(depot, order);
    const geo = await roadGeometry([depot, ...order.map((s): [number, number] => [s.lon, s.lat]), depot]);
    return {
      vehicle: i + 1,
      stops: order,
      geometry: geo.line,
      km: geo.km ?? opt.meters / 1000,
      minutes: (geo.min ?? opt.minutes - order.length * 4) + order.length * 4,
      savedPercent: naive.meters > 0 ? Math.max(0, Math.round((1 - opt.meters / naive.meters) * 100)) : 0,
      roadRouted: geo.km != null,
    };
  }));

  return NextResponse.json({ depot: b.depot, totalCandidates: rows.length, routes });
}
