import { NextResponse } from "next/server";
import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";

export async function PATCH(req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const parsed = z.object({ status: z.enum(["open", "in_progress", "resolved", "rejected"]) }).safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid_payload" }, { status: 422 });
  const { id } = await ctx.params;
  const { error } = await supabaseAdmin().from("reports").update({ status: parsed.data.status }).eq("id", id);
  return error ? NextResponse.json({ error: "server_error" }, { status: 500 }) : NextResponse.json({ ok: true });
}
