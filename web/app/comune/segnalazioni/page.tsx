"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Cpu, Camera } from "lucide-react";
import { CATEGORIES } from "@/lib/categories";
import { CatDot, StatusBadge, timeAgo } from "@/components/ui";
import { adminFetch } from "@/lib/adminClient";
import type { Report } from "@/lib/reports";

const TABS = [["open", "Aperte"], ["in_progress", "In lavorazione"], ["resolved", "Risolte"], ["rejected", "Respinte"]] as const;

export default function Segnalazioni() {
  const [tab, setTab] = useState<string>("open");
  const [cat, setCat] = useState("");
  const [reports, setReports] = useState<Report[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`/api/reports?status=${tab}${cat ? `&category=${cat}` : ""}&limit=300`).then((x) => x.json());
    setReports(r.reports ?? []);
  }, [tab, cat]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  // priorità: gravità × affidabilità × osservazioni
  const sorted = useMemo(() => [...reports].sort((a, b) =>
    b.severity * b.confidence * (1 + Math.log(b.observations)) - a.severity * a.confidence * (1 + Math.log(a.observations))), [reports]);

  async function setStatus(id: string, status: string) {
    setBusy(id);
    await adminFetch(`/api/reports/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    setBusy(null); load();
  }

  return (
    <div className="max-w-6xl w-full mx-auto p-4 sm:p-8 flex flex-col gap-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Gestione <span className="glow-text">segnalazioni</span></h1>
        <p className="text-muted">Ordinate per priorità: gravità × affidabilità × numero di osservazioni.</p>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        {TABS.map(([s, l]) => <button key={s} className="chip" data-on={tab === s} onClick={() => setTab(s)}>{l}</button>)}
        <select className="input !w-auto !py-2 ml-auto" value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">Tutte le categorie</option>{CATEGORIES.map((c) => <option key={c.slug} value={c.slug}>{c.icon} {c.name}</option>)}
        </select>
      </div>
      <div className="glass p-2 sm:p-3">
        {sorted.length === 0 && <div className="text-muted text-sm p-4">Nessuna segnalazione.</div>}
        <div className="flex flex-col divide-y divide-white/5">
          {sorted.map((r) => (
            <div key={r.id} className={`flex items-center justify-between gap-3 flex-wrap px-3 py-3 ${busy === r.id ? "opacity-50" : ""}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium"><CatDot slug={r.category} /></div>
                <div className="text-xs text-muted mt-1 flex items-center gap-2 flex-wrap">
                  <span>CAP {r.cap}</span>·<span>{timeAgo(r.created_at)}</span>·
                  <span className="flex items-center gap-1">{r.source === "device" ? <><Cpu size={11} />POD</> : <><Camera size={11} />cittadino</>}</span>·
                  <span>gravità {r.severity}/5</span>·<span>{Math.round(r.confidence * 100)}%</span>
                  {r.observations > 1 && <>·<span className="text-cyan">×{r.observations}</span></>}
                </div>
                {r.description && <div className="text-xs text-muted mt-1 truncate max-w-xl">“{r.description}”</div>}
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={r.status} />
                {r.status !== "in_progress" && r.status !== "resolved" && <button className="chip" onClick={() => setStatus(r.id, "in_progress")}>Prendi in carico</button>}
                {r.status !== "resolved" && <button className="chip" onClick={() => setStatus(r.id, "resolved")}>Risolta</button>}
                {r.status === "open" && <button className="chip" onClick={() => setStatus(r.id, "rejected")}>Respingi</button>}
                {(r.status === "resolved" || r.status === "rejected") && <button className="chip" onClick={() => setStatus(r.id, "open")}>Riapri</button>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
