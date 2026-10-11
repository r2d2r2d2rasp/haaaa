import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { handlePod, point, touchDevice } from "@/lib/podApi";
import { MetricsSchema } from "@/lib/metrics";

const Reading = z.object({
  lat: z.number().min(44.9).max(45.2).optional(),
  lon: z.number().min(7.45).max(7.9).optional(),
  captured_at: z.string().datetime().optional(),
  metrics: MetricsSchema,
});
// Una misura singola oppure un lotto { readings: [...] } (max 100, utile dopo un periodo offline)
const Batch = z.object({ readings: z.array(Reading).min(1).max(100) });

export function POST(req: Request) {
  return handlePod(req, "readings", async (device, raw) => {
    const isBatch = !!raw && typeof raw === "object" && "readings" in raw;
    const parsed = isBatch ? Batch.safeParse(raw) : Reading.safeParse(raw);
    if (!parsed.success) return { status: 422, json: { error: "invalid_payload", details: parsed.error.issues.map((i) => ({ field: i.path.join("."), message: i.message })) } };
    const list = "readings" in parsed.data ? parsed.data.readings : [parsed.data];
    const rows = list.map((r) => ({ device_id: device.id, geom: point(r.lat, r.lon), metrics: r.metrics, ts: r.captured_at ?? new Date().toISOString() }));
    const { error } = await supabaseAdmin().from("device_readings").insert(rows);
    if (error) return { status: 500, json: { error: "server_error" } };
    const last = list[list.length - 1];
    await touchDevice(device.id, { lat: last.lat, lon: last.lon });
    return { status: 201, json: { stored: rows.length } };
  });
}
