import { z } from "zod";
import { supabaseAdmin } from "@/lib/supabase";
import { handlePod, touchDevice } from "@/lib/podApi";

// Bounding box larga attorno a Torino/area metropolitana: scarta coordinate palesemente errate (es. GPS a 0,0)
const Body = z.object({
  category: z.string().min(1),
  lat: z.number().min(44.9).max(45.2),
  lon: z.number().min(7.45).max(7.9),
  confidence: z.number().min(0).max(1).default(1),
  captured_at: z.string().datetime().optional(),
  description: z.string().max(500).optional(),
  photo_base64: z.string().max(7_000_000).optional(), // ~5 MB di immagine
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export function POST(req: Request) {
  return handlePod(req, "reports", async (device, raw) => {
    const parsed = Body.safeParse(raw);
    if (!parsed.success) return { status: 422, json: { error: "invalid_payload", details: parsed.error.flatten() } };
    const b = parsed.data;
    const db = supabaseAdmin();

    const { data: cat } = await db.from("report_categories").select("slug").eq("slug", b.category).maybeSingle();
    if (!cat) return { status: 422, json: { error: "unknown_category" } };

    let photoUrl: string | null = null;
    if (b.photo_base64) {
      const path = `${device.id}/${Date.now()}.jpg`;
      const up = await db.storage.from("report-photos").upload(path, Buffer.from(b.photo_base64, "base64"), { contentType: "image/jpeg" });
      if (!up.error) photoUrl = db.storage.from("report-photos").getPublicUrl(path).data.publicUrl;
    }

    const { data, error } = await db.rpc("ingest_report", {
      p_source: "device", p_device_id: device.id, p_category: b.category, p_lat: b.lat, p_lon: b.lon,
      p_description: b.description ?? null, p_photo_url: photoUrl, p_confidence: b.confidence,
      p_captured_at: b.captured_at ?? new Date().toISOString(), p_metadata: b.metadata ?? {},
    });
    if (error) return { status: 500, json: { error: "server_error" } };
    await touchDevice(device.id, device.type === "mobile" ? { lat: b.lat, lon: b.lon } : {});
    const row = Array.isArray(data) ? data[0] : data;
    return { status: 201, json: { id: row.id, deduped: row.deduped } };
  });
}
