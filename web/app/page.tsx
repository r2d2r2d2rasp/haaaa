"use client";
import { useCallback, useEffect, useState } from "react";
import { X, MapPin } from "lucide-react";
import ReportMap from "@/components/ReportMap";
import { CatDot, StatusBadge, timeAgo } from "@/components/ui";
import { subscribeReports } from "@/lib/supabase";
import type { Report } from "@/lib/reports";
import { useEnvironment } from "@/components/useEnvironment";
import { aqiBand, WEATHER } from "@/lib/metrics";

/** Vista cittadino: solo la mappa delle segnalazioni aperte e il pulsante "Segnala". */
export default function Home() {
  const [reports, setReports] = useState<Report[]>([]);
  const [sel, setSel] = useState<Report | null>(null);
  const [flash, setFlash] = useState(false);
  const [showEnv, setShowEnv] = useState(false);
  const env = useEnvironment();
  const band = aqiBand(env?.city?.european_aqi);

  const load = useCallback(async () => {
    const r = await fetch("/api/reports?status=open,in_progress").then((x) => x.json());
    setReports(r.reports ?? []);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const poll = setInterval(load, 30000);
    const unsub = subscribeReports("reports-public", () => { load(); setFlash(true); setTimeout(() => setFlash(false), 2500); });
    return () => { clearInterval(poll); unsub(); };
  }, [load]);

  return (
    <div className="fixed inset-0">
      <ReportMap reports={reports} stations={showEnv ? env?.stations : []} onSelect={setSel} />

      {env?.city && (
        <button onClick={() => setShowEnv(!showEnv)} className="glass !rounded-2xl absolute left-3 sm:left-5 top-[76px] px-3.5 py-2 text-sm flex items-center gap-2.5 hover:!border-cyan/50 transition"
          title="Mostra i sensori di aria e meteo sulla mappa">
          <span className="text-base">{(WEATHER[env.city.weather_code ?? -1] ?? "🌡️").split(" ")[0]}</span>
          <b className="mono">{Math.round(env.city.temperature_c ?? 0)}°</b>
          <span className="w-px h-4 bg-white/15" />
          <span className="w-2 h-2 rounded-full" style={{ background: band.color }} />
          <span className="text-muted">Aria {band.label.toLowerCase()}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full transition ${showEnv ? "bg-cyan text-[#04121a]" : "bg-white/5 text-muted"}`}>{showEnv ? "sensori ✓" : "sensori"}</span>
        </button>
      )}

      <div className="glass !rounded-full absolute left-1/2 -translate-x-1/2 bottom-6 px-4 py-2 text-sm flex items-center gap-2 whitespace-nowrap">
        <span className={`w-2 h-2 rounded-full ${flash ? "bg-cyan shadow-[0_0_12px_var(--cyan)]" : "bg-lime-300"}`} />
        <b className="mono">{reports.length}</b> <span className="text-muted">{flash ? "nuova segnalazione!" : "problemi aperti in città"}</span>
      </div>

      {sel && (
        <div className="glass absolute left-3 right-3 bottom-20 sm:left-auto sm:right-5 sm:bottom-6 sm:w-[340px] p-5">
          <button onClick={() => setSel(null)} className="absolute right-4 top-4 text-muted hover:text-white" aria-label="Chiudi"><X size={18} /></button>
          <div className="text-lg font-semibold mb-2 pr-6"><CatDot slug={sel.category} /></div>
          {sel.photo_url && /* eslint-disable-next-line @next/next/no-img-element */ <img src={sel.photo_url} alt="" className="rounded-2xl mb-3 max-h-44 w-full object-cover" />}
          {sel.description && <p className="text-sm text-muted mb-3">{sel.description}</p>}
          <div className="flex items-center gap-3 text-xs text-muted">
            <StatusBadge status={sel.status} />
            <span>{timeAgo(sel.created_at)}</span>
            <span className="flex items-center gap-1"><MapPin size={12} />{sel.cap}</span>
          </div>
          {sel.observations > 1 && <div className="text-xs text-muted mt-2">Segnalato {sel.observations} volte</div>}
        </div>
      )}
    </div>
  );
}
