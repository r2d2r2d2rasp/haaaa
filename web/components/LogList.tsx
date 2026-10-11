"use client";
import { useState } from "react";

export type LogEntry = { id: number; ts: string; endpoint: string; status: number; key_prefix: string | null; ip: string | null; body: unknown; device_name?: string | null };

const statusColor = (s: number) => (s < 300 ? "#a3e635" : s === 401 ? "#fb7185" : s < 500 ? "#fbbf24" : "#c026d3");
const statusText: Record<number, string> = { 200: "OK", 201: "Creato", 401: "Chiave non valida", 422: "Dati non validi", 429: "Troppe richieste", 500: "Errore server" };

/** Elenco delle richieste API: un clic su una riga mostra il contenuto inviato dal POD. */
export default function LogList({ logs, showDevice = true }: { logs: LogEntry[]; showDevice?: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!logs.length) return <div className="text-sm text-muted p-3">Nessuna richiesta registrata.</div>;
  return (
    <div className="flex flex-col">
      {logs.map((l) => {
        const c = statusColor(l.status);
        return (
          <div key={l.id} className="border-b border-white/5 last:border-0">
            <button onClick={() => setOpen(open === l.id ? null : l.id)} className="w-full flex items-center gap-3 px-2 py-2 text-left text-xs hover:bg-white/[.03] rounded-lg">
              <span className="mono text-muted w-16 shrink-0">{new Date(l.ts).toLocaleTimeString("it-IT")}</span>
              <span className="mono px-2 py-0.5 rounded-md shrink-0" style={{ color: c, background: `${c}1a` }}>{l.status}</span>
              <span className="mono text-cyan w-20 shrink-0">/{l.endpoint}</span>
              {showDevice && <span className="truncate">{l.device_name ?? <span className="text-rose-300">sconosciuto · {l.key_prefix ?? "senza chiave"}</span>}</span>}
              <span className="text-muted ml-auto hidden sm:inline shrink-0">{statusText[l.status] ?? ""}</span>
            </button>
            {open === l.id && (
              <pre className="mono text-[11px] bg-black/40 rounded-xl p-3 mx-2 mb-2 overflow-x-auto">{JSON.stringify(l.body, null, 2)}{`\n\n// chiave ${l.key_prefix ?? "—"} · IP ${l.ip ?? "—"}`}</pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
