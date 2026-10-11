import { createHash, randomBytes } from "node:crypto";
import { supabaseAdmin } from "./supabase";

const PREFIX = "ts_live_";

export const hashKey = (key: string) => createHash("sha256").update(key).digest("hex");

/** Genera una nuova chiave. La chiave in chiaro va mostrata UNA volta sola. */
export function generateKey() {
  const key = PREFIX + randomBytes(24).toString("base64url");
  return { key, prefix: key.slice(0, PREFIX.length + 6), hash: hashKey(key) };
}

export type AuthedDevice = { id: string; name: string; type: "fixed" | "mobile"; keyPrefix: string };

export const bearer = (req: Request) => /^Bearer\s+(\S+)$/i.exec(req.headers.get("authorization") ?? "")?.[1] ?? null;

/** Verifica l'header Authorization: Bearer <key>. Ritorna il device o null. */
export async function authenticateDevice(req: Request): Promise<AuthedDevice | null> {
  const token = bearer(req);
  if (!token) return null;
  const db = supabaseAdmin();
  const { data: k } = await db
    .from("api_keys")
    .select("id, key_prefix, revoked_at, devices(id, name, type, active)")
    .eq("key_hash", hashKey(token))
    .maybeSingle();
  const device = Array.isArray(k?.devices) ? k?.devices[0] : k?.devices;
  if (!k || k.revoked_at || !device || !device.active) return null;
  void db.from("api_keys").update({ last_used_at: new Date().toISOString() }).eq("id", k.id).then(() => {});
  return { id: device.id, name: device.name, type: device.type, keyPrefix: k.key_prefix };
}
