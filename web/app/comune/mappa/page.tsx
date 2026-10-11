"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Flame, MapPin, X, Cpu, Radio, Camera, Thermometer } from "lucide-react";
import ReportMap, { type PodDevice } from "@/components/ReportMap";
import { CATEGORIES } from "@/lib/categories";
import { CatDot, StatusBadge, timeAgo } from "@/components/ui";
import { subscribeReports } from "@/lib/supabase";
import type { Report } from "@/lib/reports";
import { adminFetch } from "@/lib/adminClient";
import { useEnvironment } from "@/components/useEnvironment";

const STATUSES = [["open", "Aperte"], ["in_progress", "In corso"], ["resolved", "Risolte"]] as const;

export default function MappaOperativa() {
  const [reports, setReports] = useState<Report[]>([]);
  const [devices, setDevices] = useState<PodDevice[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>(["open", "in_progress"]);
  const [source, setSource] = useState<"all" | "citizen" | "device">("all");
  const [heat, setHeat] = useState(false);
  const [showEnv, setShowEnv] = useState(false);
  const env = useEnvironment();
  const [sel, setSel] = useState<Report | null>(null);
  const [live, setLive] = useState(false);
  const [flash, setFlash] = useState(false);

  const load = useCallback(async () => {
    const [r, d] = await Promise.all([fetch("/api/reports").then((x) => x.json()), adminFetch("/api/devices").then((x) => x.json())]);
    setReports(r.reports ?? []); setDevices(d.devices ?? []);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const poll = setInterval(load, 20000);
    const unsub = subscribeReports("reports-ops", () => { load(); setFlash(true); setTimeout(() => setFlash(false), 2500); }, setLive);
    return () => { clearInterval(poll); unsub(); };
  }, [load]);

  const toggle = (arr: string[], v: string, set: (a: string[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const filtered = useMemo(() => reports.filter((r) =>
    (!cats.length || cats.includes(r.category)) && statuses.includes(r.status) && (source === "all" || r.source === source)), [reports, cats, statuses, source]);

  return (
    <div className="relative flex-1 min-h-screen">
      <ReportMap reports={filtered} devices={devices} stations={showEnv ? env?.stations : []} heat={heat} onSelect={setSel} />

      <aside className="glass absolute left-3 sm:left-6 top-3 w-[min(92vw,330px)] p-4 flex flex-col gap-4 max-h-[calc(100%-1.5rem)] overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <div className="label">Torino · in tempo reale</div>
            <div className="text-3xl font-semibold tracking-tight mono">{filtered.length}<span className="text-sm text-muted ml-2">segnalazioni</span></div>
          </div>
          <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition ${flash ? "text-[#04121a] bg-cyan border-transparent" : live ? "text-lime-300 border-lime-300/30" : "text-muted border-line"}`}>
            <Radio size={12} /> {flash ? "nuova!" : live ? "live" : "…"}
          </span>
        </div>

        <div>
          <div className="label mb-2">Categoria</div>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((c) => (
              <button key={c.slug} className="chip" data-on={cats.includes(c.slug)} onClick={() => toggle(cats, c.slug, setCats)}>{c.icon} {c.name}</button>
            ))}
          </div>
        </div>
        <div>
          <div className="label mb-2">Stato</div>
          <div className="flex flex-wrap gap-1.5">
            {STATUSES.map(([s, l]) => <button key={s} className="chip" data-on={statuses.includes(s)} onClick={() => toggle(statuses, s, setStatuses)}>{l}</button>)}
          </div>
        </div>
        <div>
          <div className="label mb-2">Fonte</div>
          <div className="flex gap-1.5">
            {([["all", "Tutte"], ["citizen", "Cittadini"], ["device", "POD"]] as const).map(([s, l]) => <button key={s} className="chip" data-on={source === s} onClick={() => setSource(s)}>{l}</button>)}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="chip" data-on={heat} onClick={() => setHeat(!heat)}><Flame size={14} /> Heatmap</button>
          <button className="chip" data-on={showEnv} onClick={() => setShowEnv(!showEnv)}><Thermometer size={14} /> Ambiente</button>
          <span className="chip cursor-default"><Cpu size={14} /> {devices.filter((d) => d.online).length}/{devices.length} POD online</span>
        </div>
        <div className="flex gap-3 text-xs text-muted">
          <span><i className="inline-block w-2.5 h-2.5 rounded-full bg-lime-300 mr-1.5" />POD fisso</span>
          <span><i className="inline-block w-2.5 h-2.5 rounded-full bg-violet mr-1.5" />POD mobile (bus)</span>
        </div>
      </aside>

      {sel && (
        <div className="glass absolute left-3 right-3 sm:left-auto sm:right-6 bottom-6 sm:w-[360px] p-5">
          <button onClick={() => setSel(null)} className="absolute right-4 top-4 text-muted hover:text-white"><X size={18} /></button>
          <div className="flex items-center gap-2 mb-3"><StatusBadge status={sel.status} /><span className="text-xs text-muted">{timeAgo(sel.created_at)}</span></div>
          <div className="text-lg font-semibold mb-1"><CatDot slug={sel.category} /></div>
          {sel.description && <p className="text-sm text-muted mb-3">{sel.description}</p>}
          {sel.photo_url && /* eslint-disable-next-line @next/next/no-img-element */ <img src={sel.photo_url} alt="" className="rounded-2xl mb-3 max-h-44 w-full object-cover" />}
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["Gravità", `${sel.severity}/5`], ["Affidab.", `${Math.round(sel.confidence * 100)}%`], ["Osserv.", sel.observations]].map(([k, v]) => (
              <div key={k as string} className="rounded-2xl bg-white/5 py-2"><div className="label">{k}</div><div className="mono text-base">{v}</div></div>
            ))}
          </div>
          <div className="flex items-center gap-3 mt-3 text-xs text-muted">
            <span className="flex items-center gap-1"><MapPin size={13} />CAP {sel.cap}</span>
            <span className="flex items-center gap-1">{sel.source === "device" ? <><Cpu size={13} />POD</> : <><Camera size={13} />Cittadino</>}</span>
          </div>
        </div>
      )}

    </div>
  );
}
