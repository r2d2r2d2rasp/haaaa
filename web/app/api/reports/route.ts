import { NextResponse } from "next/server";
import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { REPORT_COLS, shape, type ReportRow } from "@/lib/reports";

export const dynamic = "force-dynamic";

/** Elenco pubblico segnalazioni. Filtri: status, category, source, days, cap, limit */
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  let query = supabaseAdmin().from("reports").select(REPORT_COLS).order("created_at", { ascending: false }).limit(Math.min(Number(q.get("limit") ?? 1500), 3000));
  const status = q.get("status"); if (status) query = query.in("status", status.split(","));
  const category = q.get("category"); if (category) query = query.in("category", category.split(","));
  const source = q.get("source"); if (source) query = query.eq("source", source);
  const days = Number(q.get("days")); if (days > 0) query = query.gte("created_at", new Date(Date.now() - days * 864e5).toISOString());
  const { data, error } = await query;
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });
  let reports = (data as unknown as ReportRow[]).map(shape).filter((r): r is NonNullable<typeof r> => !!r);
  const cap = q.get("cap"); if (cap) reports = reports.filter((r) => r.cap === cap);
  return NextResponse.json({ reports });
}

const Body = z.object({
  category: z.string().min(1),
  lat: z.number().min(44.9).max(45.2),
  lon: z.number().min(7.45).max(7.9),
  description: z.string().max(500).optional(),
  photo_base64: z.string().max(7_000_000).optional(),
});

const hits = new Map<string, number[]>();
function limited(ip: string) {
  const now = Date.now(), win = (hits.get(ip) ?? []).filter((t) => now - t < 60_000);
  win.push(now); hits.set(ip, win);
  return win.length > 6;
}

/** Segnalazione di un cittadino dal form web (anonima, con rate limit per IP). */
export async function POST(req: Request) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (limited(ip)) return NextResponse.json({ error: "rate_limited" }, { status: 429 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid_payload", details: parsed.error.flatten() }, { status: 422 });
  const b = parsed.data;
  const db = supabaseAdmin();

  const { data: cat } = await db.from("report_categories").select("slug").eq("slug", b.category).maybeSingle();
  if (!cat) return NextResponse.json({ error: "unknown_category" }, { status: 422 });

  let photoUrl: string | null = null;
  if (b.photo_base64) {
    const path = `citizen/${Date.now()}-${Math.random().toString(36).slice(2, 8)}.jpg`;
    const up = await db.storage.from("report-photos").upload(path, Buffer.from(b.photo_base64, "base64"), { contentType: "image/jpeg" });
    if (!up.error) photoUrl = db.storage.from("report-photos").getPublicUrl(path).data.publicUrl;
  }
  const { data, error } = await db.rpc("ingest_report", {
    p_source: "citizen", p_device_id: null, p_category: b.category, p_lat: b.lat, p_lon: b.lon,
    p_description: b.description ?? null, p_photo_url: photoUrl, p_confidence: 1,
    p_captured_at: new Date().toISOString(), p_metadata: {},
  });
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });
  const row = Array.isArray(data) ? data[0] : data;
  return NextResponse.json({ id: row.id, deduped: row.deduped }, { status: 201 });
}
