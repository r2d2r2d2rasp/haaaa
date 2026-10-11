import { NextResponse } from "next/server";
import { z } from "zod";
import { generateKey } from "@/lib/apikeys";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";

export const dynamic = "force-dynamic";

const Body = z.object({
  name: z.string().min(1).max(80),
  type: z.enum(["fixed", "mobile"]),
  label: z.string().max(120).optional(),
  key_label: z.string().max(80).optional(),
});

/** Crea un POD + una chiave API. La chiave in chiaro è nella risposta e NON è più recuperabile. */
export async function POST(req: Request) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid_payload" }, { status: 422 });
  const { key_label, ...dev } = parsed.data;

  const db = supabaseAdmin();
  const { data: device, error } = await db.from("devices").insert(dev).select("id").single();
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });

  const { key, prefix, hash } = generateKey();
  const { error: kerr } = await db.from("api_keys").insert({ device_id: device.id, key_prefix: prefix, key_hash: hash, label: key_label ?? "Chiave iniziale" });
  if (kerr) return NextResponse.json({ error: "server_error" }, { status: 500 });

  return NextResponse.json({ device_id: device.id, api_key: key }, { status: 201 });
}

/** Elenco POD con indicatori per la console IT (richieste/errori nelle ultime 24 h). */
export async function GET(req: Request) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const db = supabaseAdmin();
  const since = new Date(Date.now() - 864e5).toISOString();
  const [{ data: devs }, { data: logs }] = await Promise.all([
    db.from("devices").select("id, name, type, label, firmware, last_seen_at, battery, active, created_at, api_keys(id, key_prefix, label, revoked_at, last_used_at)").order("created_at"),
    db.from("api_request_log").select("device_id, status").gte("ts", since).limit(20000),
  ]);
  const agg: Record<string, { req: number; err: number }> = {};
  for (const l of logs ?? []) {
    if (!l.device_id) continue;
    const a = (agg[l.device_id] ??= { req: 0, err: 0 });
    a.req++; if (l.status >= 400) a.err++;
  }
  const now = Date.now();
  const devices = (devs ?? []).map((d) => ({
    ...d,
    online: !!d.last_seen_at && now - new Date(d.last_seen_at).getTime() < 15 * 60_000,
    requests24h: agg[d.id]?.req ?? 0, errors24h: agg[d.id]?.err ?? 0,
  }));
  const unknown = (logs ?? []).filter((l) => !l.device_id).length; // tentativi con chiavi non valide
  return NextResponse.json({ devices, rejected24h: unknown });
}
