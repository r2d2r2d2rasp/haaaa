import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";

export const dynamic = "force-dynamic";

/** Flusso delle richieste API dei POD (per la console IT). Filtri: device, errors=1, limit. */
export async function GET(req: Request) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const q = new URL(req.url).searchParams;
  let query = supabaseAdmin().from("api_request_log").select("id, device_id, key_prefix, endpoint, status, ip, body, ts, devices(name)")
    .order("ts", { ascending: false }).limit(Math.min(Number(q.get("limit") ?? 80), 300));
  if (q.get("device")) query = query.eq("device_id", q.get("device")!);
  if (q.get("errors") === "1") query = query.gte("status", 400);
  const { data, error } = await query;
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });
  return NextResponse.json({ logs: (data ?? []).map((l) => ({ ...l, device_name: (Array.isArray(l.devices) ? l.devices[0] : l.devices)?.name ?? null, devices: undefined })) });
}
