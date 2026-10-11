import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";
import { isAdmin } from "@/lib/adminAuth";
import { REPORT_COLS, shape, type ReportRow } from "@/lib/reports";

export const dynamic = "force-dynamic";

/** Statistiche pubbliche. Il dettaglio della flotta POD è incluso solo per l'area Comune. */
export async function GET(req: Request) {
  const admin = isAdmin(req);
  const db = supabaseAdmin();
  const { data, error } = await db.from("reports").select(REPORT_COLS).order("created_at", { ascending: false }).limit(5000);
  if (error) return NextResponse.json({ error: "server_error" }, { status: 500 });
  const reports = (data as unknown as ReportRow[]).map(shape).filter((r): r is NonNullable<typeof r> => !!r);

  const count = <K extends string>(key: (r: (typeof reports)[number]) => K) => {
    const m: Record<string, number> = {};
    for (const r of reports) m[key(r)] = (m[key(r)] ?? 0) + 1;
    return m;
  };
  const open = reports.filter((r) => r.status === "open" || r.status === "in_progress").length;
  const resolved = reports.filter((r) => r.status === "resolved");
  const avgHours = resolved.length
    ? resolved.reduce((s, r) => s + (new Date(r.resolved_at ?? r.created_at).getTime() - new Date(r.created_at).getTime()), 0) / resolved.length / 36e5
    : null;

  // ultimi 30 giorni, giorno per giorno (anche quelli a zero)
  const byDay: { day: string; total: number; device: number; citizen: number }[] = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(Date.now() - i * 864e5).toISOString().slice(0, 10);
    byDay.push({ day: d, total: 0, device: 0, citizen: 0 });
  }
  for (const r of reports) {
    const row = byDay.find((x) => x.day === r.created_at.slice(0, 10));
    if (row) { row.total++; row[r.source]++; }
  }

  const byCap = Object.entries(count((r) => r.cap)).map(([cap, total]) => ({
    cap, total, open: reports.filter((r) => r.cap === cap && (r.status === "open" || r.status === "in_progress")).length,
  })).sort((a, b) => b.total - a.total);

  const { data: devs } = await db.from("v_public_devices").select("*");
  const now = Date.now();
  const devices = (devs ?? []).map((d) => ({ ...d, online: !!d.last_seen_at && now - new Date(d.last_seen_at).getTime() < 15 * 60_000 }));

  return NextResponse.json({
    totals: { all: reports.length, open, resolved: resolved.length, avgResolutionHours: avgHours, fromDevices: reports.filter((r) => r.source === "device").length },
    byCategory: Object.entries(count((r) => r.category)).map(([slug, total]) => ({ slug, total })),
    byStatus: count((r) => r.status as string),
    byDay, byCap,
    fleet: { online: devices.filter((d) => d.online).length, total: devices.length },
    devices: admin ? devices : undefined,
    latest: reports.slice(0, 8),
  });
}
