"use client";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, KeyRound, Plus, Power, Pencil, Check, Bus, TrafficCone } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { adminFetch } from "@/lib/adminClient";
import { CatDot, StatusBadge, timeAgo } from "@/components/ui";
import KeyReveal from "@/components/KeyReveal";
import LogList, { type LogEntry } from "@/components/LogList";
import { METRICS } from "@/lib/metrics";

type Key = { id: string; key_prefix: string; label: string | null; created_at: string; revoked_at: string | null; last_used_at: string | null };
type Detail = {
  device: { id: string; name: string; type: string; label: string | null; firmware: string | null; last_seen_at: string | null; battery: number | null; active: boolean; online: boolean; created_at: string; position: { lat: number; lon: number } | null; api_keys: Key[] };
  logs: LogEntry[]; readings: { ts: string; metrics: Record<string, number> }[];
  reports: { id: string; category: string; status: string; created_at: string; confidence: number; observations: number }[];
};

export default function PodDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [d, setD] = useState<Detail | null>(null);
  const [metric, setMetric] = useState<string | null>(null);
  const [keyLabel, setKeyLabel] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState("");

  const load = useCallback(async () => {
    const r = await adminFetch(`/api/admin/devices/${id}`);
    if (r.ok) setD(await r.json());
  }, [id]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const metricKeys = useMemo(() => [...new Set((d?.readings ?? []).flatMap((r) => Object.keys(r.metrics)))], [d]);
  const active = metric ?? metricKeys[0] ?? null;
  const series = useMemo(() => (d?.readings ?? []).filter((r) => active && r.metrics[active] != null).map((r) => ({ t: r.ts, v: r.metrics[active!] })), [d, active]);
  const latest = d?.readings.at(-1);

  if (!d) return <div className="grid place-items-center min-h-screen text-muted">Caricamento…</div>;
  const dev = d.device;

  const patch = async (body: object) => { await adminFetch(`/api/admin/devices/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); load(); };
  const createKey = async () => {
    const r = await adminFetch(`/api/admin/devices/${id}/keys`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: keyLabel || undefined }) });
    if (r.ok) { setNewKey((await r.json()).api_key); setKeyLabel(""); load(); }
  };
  const revoke = async (k: Key) => {
    if (!confirm(`Revocare la chiave ${k.key_prefix}…? Il POD che la usa smetterà subito di poter inviare dati.`)) return;
    await adminFetch(`/api/admin/keys/${k.id}`, { method: "DELETE" }); load();
  };

  return (
    <div className="max-w-7xl w-full mx-auto p-4 sm:p-8 flex flex-col gap-4">
      <Link href="/comune/pod" className="text-sm text-muted hover:text-white flex items-center gap-1 w-fit"><ArrowLeft size={15} /> Console IT</Link>

      <div className="glass p-5 flex flex-wrap items-center gap-4">
        <span className="grid place-items-center w-12 h-12 rounded-2xl bg-white/5 text-cyan">{dev.type === "mobile" ? <Bus size={22} /> : <TrafficCone size={22} />}</span>
        <div className="flex-1 min-w-48">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-semibold">{dev.name}</h1>
            <span className="text-xs px-2.5 py-1 rounded-full" style={!dev.active ? { color: "#8b95b3", background: "#8b95b31f" } : dev.online ? { color: "#a3e635", background: "#a3e6351f" } : { color: "#fb7185", background: "#fb71851f" }}>
              {!dev.active ? "Disattivato" : dev.online ? "Online" : "Offline"}
            </span>
          </div>
          {editing ? (
            <form className="flex gap-2 mt-1" onSubmit={(e) => { e.preventDefault(); patch({ label: label || null }); setEditing(false); }}>
              <input className="input !py-1.5 !text-sm" value={label} onChange={(e) => setLabel(e.target.value)} autoFocus />
              <button className="btn-ghost !py-1.5"><Check size={14} /></button>
            </form>
          ) : (
            <button className="text-sm text-muted hover:text-white flex items-center gap-1.5" onClick={() => { setLabel(dev.label ?? ""); setEditing(true); }}>{dev.label ?? "Aggiungi posizione/mezzo"} <Pencil size={12} /></button>
          )}
        </div>
        <button className="btn-ghost" onClick={() => patch({ active: !dev.active })} title="Un POD disattivato riceve 401 a ogni invio">
          <Power size={15} className={dev.active ? "text-lime-300" : "text-muted"} /> {dev.active ? "Disattiva" : "Riattiva"}
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ["Tipo", dev.type === "mobile" ? "Mobile (bus)" : "Fisso"],
          ["Ultimo contatto", dev.last_seen_at ? timeAgo(dev.last_seen_at) : "mai"],
          ["Batteria", dev.battery != null ? `${Math.round(dev.battery)}%` : "—"],
          ["Firmware", dev.firmware ?? "—"],
          ["Posizione", dev.position ? `${dev.position.lat.toFixed(4)}, ${dev.position.lon.toFixed(4)}` : "—"],
        ].map(([k, v]) => <div key={k} className="glass p-4"><div className="label">{k}</div><div className="mono text-sm mt-1">{v}</div></div>)}
      </div>

      {newKey && <KeyReveal deviceName={dev.name} apiKey={newKey} onClose={() => setNewKey(null)} />}

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="glass p-5 flex flex-col gap-3">
          <div className="label flex items-center gap-2"><KeyRound size={13} /> Chiavi API</div>
          {dev.api_keys.length === 0 && <div className="text-sm text-muted">Nessuna chiave: questo POD non può inviare dati finché non ne crei una.</div>}
          {dev.api_keys.map((k) => (
            <div key={k.id} className="flex items-center gap-3 rounded-2xl bg-white/[.03] border border-line px-4 py-3">
              <div className="flex-1 min-w-0">
                <div className="mono text-sm">{k.key_prefix}…{k.revoked_at && <span className="text-rose-300 text-xs ml-2">revocata</span>}</div>
                <div className="text-xs text-muted">{k.label ?? "senza nota"} · creata {timeAgo(k.created_at)} · {k.last_used_at ? `usata ${timeAgo(k.last_used_at)}` : "mai usata"}</div>
              </div>
              {!k.revoked_at && <button className="chip !py-1 !text-xs hover:!border-rose-400/60" onClick={() => revoke(k)}>Revoca</button>}
            </div>
          ))}
          <div className="flex gap-2">
            <input className="input !py-2" placeholder="Nota (es. Team hardware, demo)" value={keyLabel} onChange={(e) => setKeyLabel(e.target.value)} />
            <button className="btn !py-2 shrink-0" onClick={createKey}><Plus size={15} /> Nuova chiave</button>
          </div>
        </div>

        <div className="glass p-5">
          <div className="label mb-3">Ultime misure dei sensori</div>
          {!latest ? <div className="text-sm text-muted">Nessuna misura ricevuta. Il POD può inviarle su <span className="mono">/api/v1/readings</span>.</div> : (
            <>
              <div className="flex flex-wrap gap-2 mb-3">
                {Object.entries(latest.metrics).map(([k, v]) => (
                  <button key={k} onClick={() => setMetric(k)} className="rounded-2xl px-3 py-2 text-left border transition" style={active === k ? { borderColor: "var(--cyan)", background: "rgba(34,211,238,.08)" } : { borderColor: "var(--line)" }}>
                    <div className="text-[11px] text-muted">{METRICS[k]?.icon} {METRICS[k]?.label ?? k}</div>
                    <div className="mono">{v} <span className="text-xs text-muted">{METRICS[k]?.unit ?? ""}</span></div>
                  </button>
                ))}
              </div>
              <div className="h-40">
                <ResponsiveContainer>
                  <LineChart data={series}>
                    <CartesianGrid stroke="rgba(148,163,255,.08)" vertical={false} />
                    <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })} stroke="#8b95b3" fontSize={10} tickLine={false} minTickGap={40} />
                    <YAxis stroke="#8b95b3" fontSize={10} tickLine={false} axisLine={false} width={36} domain={["auto", "auto"]} />
                    <Tooltip contentStyle={{ background: "#101626", border: "1px solid rgba(148,163,255,.2)", borderRadius: 12 }} labelFormatter={(t) => new Date(String(t)).toLocaleString("it-IT")} formatter={(v) => [`${v} ${METRICS[active ?? ""]?.unit ?? ""}`, METRICS[active ?? ""]?.label ?? active]} />
                    <Line type="monotone" dataKey="v" stroke="#22d3ee" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <div className="glass p-3 lg:col-span-3">
          <div className="label px-2 py-2">Cosa ha inviato (ultime {d.logs.length} richieste) · clic per il contenuto</div>
          <div className="max-h-96 overflow-y-auto"><LogList logs={d.logs} showDevice={false} /></div>
        </div>
        <div className="glass p-5 lg:col-span-2">
          <div className="label mb-3">Segnalazioni generate</div>
          {d.reports.length === 0 && <div className="text-sm text-muted">Nessuna.</div>}
          <div className="flex flex-col divide-y divide-white/5">
            {d.reports.map((r) => (
              <div key={r.id} className="flex items-center justify-between py-2 gap-2 text-sm">
                <CatDot slug={r.category} />
                <div className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="text-xs text-muted w-14 text-right">{timeAgo(r.created_at)}</span></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
