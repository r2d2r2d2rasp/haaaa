import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { handlePod, point, touchDevice } from "@/lib/podApi";
import { MetricsSchema } from "@/lib/metrics";

const Body = z.object({
  lat: z.number().min(-90).max(90).optional(),
  lon: z.number().min(-180).max(180).optional(),
  battery: z.number().min(0).max(100).optional(),
  firmware: z.string().max(64).optional(),
  metrics: MetricsSchema.optional(), // facoltativo: misure dei sensori insieme al battito
});

export function POST(req: Request) {
  return handlePod(req, "heartbeat", async (device, raw) => {
    const parsed = Body.safeParse(raw ?? {});
    if (!parsed.success) return { status: 422, json: { error: "invalid_payload", details: parsed.error.flatten() } };
    const { lat, lon, battery, firmware, metrics } = parsed.data;
    const db = supabaseAdmin();
    await touchDevice(device.id, { lat, lon, battery, firmware });
    const g = point(lat, lon);
    if (g) await db.from("device_heartbeats").insert({ device_id: device.id, geom: g, battery });
    if (metrics) await db.from("device_readings").insert({ device_id: device.id, geom: g, metrics });
    return { status: 200, json: { ok: true } };
  });
}
