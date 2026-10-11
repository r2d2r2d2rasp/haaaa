import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";

/** Revoca una chiave: da subito le richieste con quella chiave ricevono 401. */
export async function DELETE(req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  const { error } = await supabaseAdmin().from("api_keys").update({ revoked_at: new Date().toISOString() }).eq("id", id).is("revoked_at", null);
  return error ? NextResponse.json({ error: "server_error" }, { status: 500 }) : NextResponse.json({ ok: true });
}
