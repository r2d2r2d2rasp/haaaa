import { NextResponse } from "next/server";
import { authenticateDevice, bearer, type AuthedDevice } from "./apikeys";
import { supabaseAdmin } from "./supabase";

type Result = { status: number; json: unknown };

/** Toglie dal log i campi pesanti (foto) e limita la dimensione. */
function sanitize(body: unknown): unknown {
  if (!body || typeof body !== "object") return body ?? null;
  const copy: Record<string, unknown> = { ...(body as Record<string, unknown>) };
  if (typeof copy.photo_base64 === "string") copy.photo_base64 = `[foto ${Math.round((copy.photo_base64 as string).length * 0.75 / 1024)} KB]`;
  const s = JSON.stringify(copy);
  return s.length > 8000 ? { _truncated: true, preview: s.slice(0, 8000) } : copy;
}

/**
 * Gestisce una chiamata di un POD: autentica, esegue, e registra SEMPRE la richiesta in api_request_log
 * (anche se fallisce) così la console IT mostra cosa invia ogni dispositivo.
 */
export async function handlePod(req: Request, endpoint: string, fn: (device: AuthedDevice, body: unknown) => Promise<Result>) {
  const body = await req.json().catch(() => null);
  const device = await authenticateDevice(req);
  const res: Result = device ? await fn(device, body).catch(() => ({ status: 500, json: { error: "server_error" } })) : { status: 401, json: { error: "unauthorized" } };
  await supabaseAdmin().from("api_request_log").insert({
    device_id: device?.id ?? null,
    key_prefix: device?.keyPrefix ?? bearer(req)?.slice(0, 14) ?? null,
    endpoint, status: res.status,
    ip: req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? null,
    body: sanitize(body),
  });
  return NextResponse.json(res.json, { status: res.status });
}

export const point = (lat?: number | null, lon?: number | null) => (lat != null && lon != null ? `SRID=4326;POINT(${lon} ${lat})` : null);

/** Aggiorna "ultimo contatto" e posizione del dispositivo. */
export async function touchDevice(id: string, patch: { lat?: number; lon?: number; battery?: number; firmware?: string } = {}) {
  const p: Record<string, unknown> = { last_seen_at: new Date().toISOString() };
  const g = point(patch.lat, patch.lon); if (g) p.last_geom = g;
  if (patch.battery != null) p.battery = patch.battery;
  if (patch.firmware) p.firmware = patch.firmware;
  await supabaseAdmin().from("devices").update(p).eq("id", id);
}
