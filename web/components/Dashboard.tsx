"use client";
// Dashboard condivisa: pubblica (/statistiche) e area Comune (admin = true, con dettaglio flotta POD).
import { useEffect, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, CheckCircle2, Clock, Cpu } from "lucide-react";
import { CAT } from "@/lib/categories";
import { CatDot, StatusBadge, timeAgo } from "@/components/ui";
import type { Report } from "@/lib/reports";
import { adminFetch } from "@/lib/adminClient";
import EnvCard from "@/components/EnvCard";

type Stats = {
  totals: { all: number; open: number; resolved: number; avgResolutionHours: number | null; fromDevices: number };
  byCategory: { slug: string; total: number }[];
  byDay: { day: string; total: number; device: number; citizen: number }[];
  byCap: { cap: string; total: number; open: number }[];
  fleet: { online: number; total: number };
  devices?: { id: string; name: string; type: string; label: string | null; battery: number | null; last_seen_at: string | null; online: boolean }[];
  latest: Report[];
};

const tip = { contentStyle: { background: "#101626", border: "1px solid rgba(148,163,255,.2)", borderRadius: 14, color: "#e8ecf8" }, cursor: { fill: "rgba(255,255,255,.04)" } };

function Kpi({ icon: Icon, label, value, sub, color }: { icon: typeof Clock; label: string; value: string | number; sub?: string; color: string }) {
  return (
    <div className="glass p-5 relative overflow-hidden">
      <div className="absolute -right-6 -top-6 w-24 h-24 rounded-full blur-2xl opacity-40" style={{ background: color }} />
      <Icon size={18} style={{ color }} />
      <div className="label mt-3">{label}</div>
      <div className="text-4xl font-semibold mono tracking-tight">{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
}

export default function Dashboard({ admin = false }: { admin?: boolean }) {
  const [s, setS] = useState<Stats | null>(null);
  useEffect(() => { const f = () => (admin ? adminFetch : fetch)("/api/stats").then((r) => r.json()).then(setS); f(); const t = setInterval(f, 30000); return () => clearInterval(t); }, [admin]);
  if (!s) return <div className="grid place-items-center flex-1 min-h-screen text-muted">Caricamento…</div>;

  const cats = s.byCategory.map((c) => ({ ...c, name: CAT[c.slug]?.name ?? c.slug, color: CAT[c.slug]?.color ?? "#94a3b8" })).sort((a, b) => b.total - a.total);
  const topCap = s.byCap.slice(0, 10);
  const maxCap = Math.max(1, ...s.byCap.map((c) => c.total));

  return (
    <div className={`max-w-7xl w-full mx-auto p-4 sm:p-8 flex flex-col gap-4 ${admin ? "" : "pt-24 sm:pt-24"}`}>
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{admin ? "Panoramica" : "Come sta"} <span className="glow-text">{admin ? "città" : "Torino"}</span></h1>
        <p className="text-muted">{admin ? "Statistiche in tempo reale su segnalazioni cittadine e POD." : "Segnalazioni, decoro urbano e qualità dell'aria, aggiornati in tempo reale."}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi icon={AlertTriangle} label="Aperte" value={s.totals.open} sub={`${s.totals.all} totali`} color="#fb7185" />
        <Kpi icon={CheckCircle2} label="Risolte" value={s.totals.resolved} sub={s.totals.all ? `${Math.round((s.totals.resolved / s.totals.all) * 100)}% del totale` : ""} color="#a3e635" />
        <Kpi icon={Clock} label="Tempo medio risoluzione" value={s.totals.avgResolutionHours != null ? `${s.totals.avgResolutionHours.toFixed(1)}h` : "—"} color="#fbbf24" />
        <Kpi icon={Cpu} label="Rilevate dai POD" value={s.totals.fromDevices} sub={`${s.fleet.online}/${s.fleet.total} POD online`} color="#22d3ee" />
      </div>

      <EnvCard />

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="glass p-5 lg:col-span-2">
          <div className="label mb-3">Segnalazioni · ultimi 30 giorni</div>
          <div className="h-64">
            <ResponsiveContainer>
              <AreaChart data={s.byDay}>
                <defs>
                  <linearGradient id="gd" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} /><stop offset="100%" stopColor="#22d3ee" stopOpacity={0} /></linearGradient>
                  <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity={0.5} /><stop offset="100%" stopColor="#a78bfa" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(148,163,255,.08)" vertical={false} />
                <XAxis dataKey="day" tickFormatter={(d) => d.slice(8) + "/" + d.slice(5, 7)} stroke="#8b95b3" fontSize={11} tickLine={false} interval={4} />
                <YAxis stroke="#8b95b3" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip {...tip} />
                <Area type="monotone" dataKey="device" name="POD" stackId="1" stroke="#22d3ee" fill="url(#gd)" strokeWidth={2} />
                <Area type="monotone" dataKey="citizen" name="Cittadini" stackId="1" stroke="#a78bfa" fill="url(#gc)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="glass p-5">
          <div className="label mb-3">Per categoria</div>
          <div className="h-44">
            <ResponsiveContainer>
              <PieChart><Pie data={cats} dataKey="total" nameKey="name" innerRadius={48} outerRadius={72} paddingAngle={3} stroke="none">
                {cats.map((c) => <Cell key={c.slug} fill={c.color} />)}</Pie><Tooltip {...tip} /></PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-col gap-1.5 mt-2">
            {cats.map((c) => <div key={c.slug} className="flex justify-between text-sm"><CatDot slug={c.slug} /><span className="mono text-muted">{c.total}</span></div>)}
          </div>
        </div>
      </div>

      <div className={`grid gap-4 ${admin ? "lg:grid-cols-2" : ""}`}>
        <div className="glass p-5">
          <div className="label mb-1">Zone più segnalate · per CAP</div>
          <div className="text-xs text-muted mb-3">CAP stimato dal centroide più vicino (approssimato)</div>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={topCap} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" hide /><YAxis type="category" dataKey="cap" stroke="#8b95b3" fontSize={12} tickLine={false} axisLine={false} width={52} />
                <Tooltip {...tip} />
                <Bar dataKey="total" name="Totali" radius={[0, 10, 10, 0]}>{topCap.map((c) => <Cell key={c.cap} fill={`rgba(34,211,238,${0.35 + 0.65 * (c.total / maxCap)})`} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        {admin && s.devices && <div className="glass p-5">
          <div className="label mb-3">Flotta POD</div>
          {s.devices.length === 0 && <div className="text-muted text-sm">Nessun POD registrato.</div>}
          <div className="flex flex-col gap-2 max-h-72 overflow-y-auto">
            {s.devices.map((d) => (
              <div key={d.id} className="flex items-center justify-between rounded-2xl bg-white/[.03] border border-line px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: d.online ? "#a3e635" : "#64748b", boxShadow: d.online ? "0 0 12px #a3e635" : "none" }} />
                  <div><div className="text-sm font-medium">{d.name} <span className="text-xs text-muted">· {d.type === "mobile" ? "mobile" : "fisso"}</span></div>
                    <div className="text-xs text-muted">{d.label ?? "—"}</div></div>
                </div>
                <div className="text-right text-xs text-muted mono">{d.battery != null ? `🔋 ${Math.round(d.battery)}%` : ""}<br />{d.last_seen_at ? timeAgo(d.last_seen_at) : "mai visto"}</div>
              </div>
            ))}
          </div>
        </div>}
      </div>

      <div className="glass p-5">
        <div className="label mb-3">Ultime segnalazioni</div>
        <div className="flex flex-col divide-y divide-white/5">
          {s.latest.map((r) => (
            <div key={r.id} className="flex items-center justify-between py-2.5 gap-3 flex-wrap">
              <div className="text-sm"><CatDot slug={r.category} /> <span className="text-muted ml-2">CAP {r.cap} · {r.source === "device" ? "POD" : "cittadino"}</span></div>
              <div className="flex items-center gap-3"><StatusBadge status={r.status} /><span className="text-xs text-muted w-16 text-right">{timeAgo(r.created_at)}</span></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
