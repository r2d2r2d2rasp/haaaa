import { NextResponse } from "next/server";
import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";
import { generateKey } from "@/lib/apikeys";

/** Genera una nuova chiave per un POD esistente (la chiave in chiaro è restituita una sola volta). */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const parsed = z.object({ label: z.string().max(80).optional() }).safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) return NextResponse.json({ error: "invalid_payload" }, { status: 422 });
  const { id } = await ctx.params;
  const { key, prefix, hash } = generateKey();
  const { error } = await supabaseAdmin().from("api_keys").insert({ device_id: id, key_prefix: prefix, key_hash: hash, label: parsed.data.label || null });
  return error ? NextResponse.json({ error: "server_error" }, { status: 500 }) : NextResponse.json({ api_key: key }, { status: 201 });
}
