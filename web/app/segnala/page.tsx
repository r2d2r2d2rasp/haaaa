"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { Camera, LocateFixed, Send, CheckCircle2 } from "lucide-react";
import { CATEGORIES } from "@/lib/categories";
import LocationPicker from "@/components/LocationPicker";

/** Ridimensiona la foto lato client (max 1280px, JPEG) per tenerla leggera. */
async function shrink(file: File): Promise<string> {
  const img = await createImageBitmap(file);
  const k = Math.min(1, 1280 / Math.max(img.width, img.height));
  const c = document.createElement("canvas"); c.width = img.width * k; c.height = img.height * k;
  c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.78).split(",")[1];
}

export default function NewReport() {
  const [category, setCategory] = useState("rifiuti_abbandonati");
  const [description, setDescription] = useState("");
  const [loc, setLoc] = useState<{ lat: number; lon: number } | null>(null);
  const [photo, setPhoto] = useState<{ b64: string; preview: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState<{ deduped: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const locate = () => navigator.geolocation?.getCurrentPosition(
    (p) => setLoc({ lat: p.coords.latitude, lon: p.coords.longitude }),
    () => setErr("Posizione non disponibile: tocca la mappa per indicarla."),
  );

  async function submit() {
    if (!loc) return setErr("Indica dove si trova il problema (usa la tua posizione o tocca la mappa).");
    setBusy(true); setErr("");
    const r = await fetch("/api/reports", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, ...loc, description: description || undefined, photo_base64: photo?.b64 }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) setDone({ deduped: j.deduped });
    else setErr(r.status === 422 ? "Posizione fuori dall'area di Torino o dati non validi." : r.status === 429 ? "Troppe segnalazioni, riprova tra un minuto." : "Errore del server, riprova.");
  }

  if (done) return (
    <div className="grid place-items-center min-h-screen p-6">
      <div className="glass p-10 text-center max-w-md">
        <CheckCircle2 className="mx-auto text-lime-300 mb-4" size={56} />
        <h1 className="text-2xl font-semibold mb-2">Segnalazione inviata</h1>
        <p className="text-muted mb-6">{done.deduped ? "Esisteva già una segnalazione identica qui vicino: l'abbiamo rafforzata. Grazie!" : "Grazie! Comparirà subito sulla mappa."}</p>
        <div className="flex gap-3 justify-center"><Link href="/" className="btn">Vai alla mappa</Link>
          <button className="btn-ghost" onClick={() => { setDone(null); setDescription(""); setPhoto(null); }}>Nuova</button></div>
      </div>
    </div>
  );

  return (
    <div className="max-w-2xl w-full mx-auto p-4 sm:p-6 pt-24 sm:pt-24">
      <h1 className="text-3xl font-semibold tracking-tight mb-1">Nuova <span className="glow-text">segnalazione</span></h1>
      <p className="text-muted mb-6">20 secondi, nessuna registrazione.</p>
      <div className="glass p-5 sm:p-6 flex flex-col gap-6">
        <div>
          <div className="label mb-2">1 · Cosa hai visto?</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {CATEGORIES.map((c) => (
              <button key={c.slug} onClick={() => setCategory(c.slug)}
                className="rounded-2xl p-3 text-left border transition"
                style={category === c.slug ? { borderColor: c.color, background: `${c.color}1a`, boxShadow: `0 0 24px -8px ${c.color}` } : { borderColor: "var(--line)", background: "rgba(255,255,255,.03)" }}>
                <div className="text-2xl">{c.icon}</div><div className="text-sm mt-1">{c.name}</div>
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="label mb-2">2 · Dove?</div>
          <button className="btn-ghost mb-3" onClick={locate}><LocateFixed size={16} /> Usa la mia posizione</button>
          <LocationPicker value={loc} onChange={setLoc} />
          <div className="text-xs text-muted mt-2 mono">{loc ? `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}` : "Tocca la mappa per posizionare il pin"}</div>
        </div>
        <div>
          <div className="label mb-2">3 · Dettagli (facoltativo)</div>
          <textarea className="input min-h-24" maxLength={500} placeholder="Es. Divano e sacchi davanti al civico 12…" value={description} onChange={(e) => setDescription(e.target.value)} />
          <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden
            onChange={async (e) => { const f = e.target.files?.[0]; if (f) setPhoto({ b64: await shrink(f), preview: URL.createObjectURL(f) }); }} />
          <div className="flex items-center gap-3 mt-3">
            <button className="btn-ghost" onClick={() => fileRef.current?.click()}><Camera size={16} /> {photo ? "Cambia foto" : "Aggiungi foto"}</button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {photo && <img src={photo.preview} alt="" className="h-14 w-14 rounded-xl object-cover" />}
          </div>
        </div>
        {err && <div className="text-sm text-rose-300 bg-rose-500/10 border border-rose-400/20 rounded-2xl px-4 py-3">{err}</div>}
        <button className="btn w-full !py-3.5" disabled={busy} onClick={submit}><Send size={16} /> {busy ? "Invio…" : "Invia segnalazione"}</button>
      </div>
    </div>
  );
}
