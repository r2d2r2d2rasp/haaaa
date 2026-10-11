import { NextResponse } from "next/server";
import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";
import { parsePoint } from "@/lib/geo";

export const dynamic = "force-dynamic";
type Ctx = { params: Promise<{ id: string }> };

/** Dettaglio di un POD: chiavi, ultime richieste, misure, segnalazioni. */
export async function GET(req: Request, ctx: Ctx) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  const db = supabaseAdmin();
  const [dev, logs, readings, reports] = await Promise.all([
    db.from("devices").select("id, name, type, label, firmware, last_seen_at, last_geom, battery, active, created_at, api_keys(id, key_prefix, label, created_at, revoked_at, last_used_at)").eq("id", id).maybeSingle(),
    db.from("api_request_log").select("id, endpoint, status, ip, body, ts, key_prefix").eq("device_id", id).order("ts", { ascending: false }).limit(60),
    db.from("device_readings").select("ts, metrics").eq("device_id", id).order("ts", { ascending: false }).limit(300),
    db.from("reports").select("id, category, status, created_at, confidence, observations").eq("device_id", id).order("created_at", { ascending: false }).limit(20),
  ]);
  if (!dev.data) return NextResponse.json({ error: "not_found" }, { status: 404 });
  const { last_geom, ...d } = dev.data;
  return NextResponse.json({
    device: { ...d, position: parsePoint(last_geom as string | null), online: !!d.last_seen_at && Date.now() - new Date(d.last_seen_at).getTime() < 15 * 60_000 },
    logs: logs.data ?? [], readings: (readings.data ?? []).reverse(), reports: reports.data ?? [],
  });
}

const Patch = z.object({ name: z.string().min(1).max(80).optional(), label: z.string().max(120).nullable().optional(), active: z.boolean().optional() });

/** Modifica nome/etichetta o attiva/disattiva il POD (un POD disattivato riceve 401). */
export async function PATCH(req: Request, ctx: Ctx) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const parsed = Patch.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid_payload" }, { status: 422 });
  const { id } = await ctx.params;
  const { error } = await supabaseAdmin().from("devices").update(parsed.data).eq("id", id);
  return error ? NextResponse.json({ error: "server_error" }, { status: 500 }) : NextResponse.json({ ok: true });
}
