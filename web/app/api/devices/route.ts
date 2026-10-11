import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";

export const dynamic = "force-dynamic";

/** Elenco pubblico dei POD (senza chiavi): posizione, batteria, ultimo contatto. */
export async function GET(req: Request) {
  if (!isAdmin(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { data, error } = await supabaseAdmin().from("v_public_devices").select("*");
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });
  const now = Date.now();
  const devices = (data ?? []).map((d) => ({
    ...d,
    online: !!d.last_seen_at && now - new Date(d.last_seen_at).getTime() < 15 * 60_000,
  }));
  return NextResponse.json({ devices });
}
