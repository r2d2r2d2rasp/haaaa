"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, AlertTriangle, ChevronRight, Cpu, Plus, ShieldX, Bus, TrafficCone, Pause, Play } from "lucide-react";
import { timeAgo } from "@/components/ui";
import { adminFetch } from "@/lib/adminClient";
import KeyReveal from "@/components/KeyReveal";
import LogList, { type LogEntry } from "@/components/LogList";

type Dev = {
  id: string; name: string; type: string; label: string | null; firmware: string | null; last_seen_at: string | null; battery: number | null;
  active: boolean; online: boolean; requests24h: number; errors24h: number; api_keys: { id: string; revoked_at: string | null }[];
};

function Tile({ icon: Icon, label, value, color }: { icon: typeof Cpu; label: string; value: string | number; color: string }) {
  return (
    <div className="glass p-4 flex items-center gap-3">
      <span className="grid place-items-center w-10 h-10 rounded-xl" style={{ background: `${color}1a`, color }}><Icon size={18} /></span>
      <div><div className="label">{label}</div><div className="mono text-2xl">{value}</div></div>
    </div>
  );
}

export default function ConsoleIT() {
  const [devs, setDevs] = useState<Dev[]>([]);
  const [rejected, setRejected] = useState(0);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [live, setLive] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", type: "fixed", label: "", key_label: "" });
  const [newKey, setNewKey] = useState<{ name: string; key: string } | null>(null);
  const [err, setErr] = useState("");

  const loadDevs = useCallback(async () => {
    const r = await adminFetch("/api/admin/devices");
    if (r.ok) { const j = await r.json(); setDevs(j.devices); setRejected(j.rejected24h); }
  }, []);
  const loadLogs = useCallback(async () => {
    const r = await adminFetch(`/api/admin/logs?limit=60${onlyErrors ? "&errors=1" : ""}`);
    if (r.ok) setLogs((await r.json()).logs);
  }, [onlyErrors]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadDevs(); const t = setInterval(loadDevs, 15000); return () => clearInterval(t); }, [loadDevs]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadLogs();
    if (!live) return;
    const t = setInterval(loadLogs, 4000); return () => clearInterval(t);
  }, [loadLogs, live]);

  async function create() {
    if (!form.name.trim()) return setErr("Dai un nome al POD");
    const r = await adminFetch("/api/admin/devices", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: form.name.trim(), type: form.type, label: form.label || undefined, key_label: form.key_label || undefined }) });
    const j = await r.json();
    if (!r.ok) return setErr("Creazione non riuscita");
    setNewKey({ name: form.name, key: j.api_key }); setForm({ name: "", type: "fixed", label: "", key_label: "" }); setShowForm(false); setErr(""); loadDevs();
  }

  const online = devs.filter((d) => d.online).length;
  const req = devs.reduce((s, d) => s + d.requests24h, 0), errs = devs.reduce((s, d) => s + d.errors24h, 0);

  return (
    <div className="max-w-7xl w-full mx-auto p-4 sm:p-8 flex flex-col gap-4">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Console <span className="glow-text">IT</span></h1>
          <p className="text-muted">POD collegati, chiavi API e traffico in tempo reale.</p>
        </div>
        <button className="btn" onClick={() => setShowForm(!showForm)}><Plus size={16} /> Nuovo POD</button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile icon={Cpu} label="POD online" value={`${online}/${devs.length}`} color="#a3e635" />
        <Tile icon={Activity} label="Richieste 24h" value={req} color="#22d3ee" />
        <Tile icon={AlertTriangle} label="Errori 24h" value={errs} color={errs ? "#fbbf24" : "#8b95b3"} />
        <Tile icon={ShieldX} label="Chiavi rifiutate 24h" value={rejected} color={rejected ? "#fb7185" : "#8b95b3"} />
      </div>

      {showForm && (
        <div className="glass p-5 grid sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <label className="lg:col-span-1"><div className="label mb-1.5">Nome</div><input className="input" placeholder="POD-BUS15" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus /></label>
          <label><div className="label mb-1.5">Tipo</div>
            <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}><option value="fixed">Fisso (semaforo / palo)</option><option value="mobile">Mobile (bus)</option></select></label>
          <label><div className="label mb-1.5">Posizione / mezzo</div><input className="input" placeholder="Semaforo Via Po / Bus 15" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></label>
          <label><div className="label mb-1.5">Nota sulla chiave</div><input className="input" placeholder="es. Team hardware" value={form.key_label} onChange={(e) => setForm({ ...form, key_label: e.target.value })} /></label>
          <button className="btn" onClick={create}>Crea e genera chiave</button>
          {err && <div className="text-sm text-rose-300 sm:col-span-2 lg:col-span-5">{err}</div>}
        </div>
      )}

      {newKey && <KeyReveal deviceName={newKey.name} apiKey={newKey.key} onClose={() => setNewKey(null)} />}

      <div className="grid xl:grid-cols-5 gap-4">
        <div className="glass p-3 xl:col-span-3">
          <div className="label px-2 py-2">Dispositivi ({devs.length})</div>
          <div className="flex flex-col gap-1.5">
            {devs.map((d) => (
              <Link key={d.id} href={`/comune/pod/${d.id}`} className="flex items-center gap-3 rounded-2xl px-3 py-3 hover:bg-white/[.04] border border-transparent hover:border-line transition">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: !d.active ? "#64748b" : d.online ? "#a3e635" : "#fb7185", boxShadow: d.active && d.online ? "0 0 10px #a3e635" : "none" }} />
                <span className="grid place-items-center w-8 h-8 rounded-xl bg-white/5 text-muted shrink-0">{d.type === "mobile" ? <Bus size={15} /> : <TrafficCone size={15} />}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{d.name} {!d.active && <span className="text-xs text-muted">(disattivato)</span>}</div>
                  <div className="text-xs text-muted truncate">{d.label ?? "—"}</div>
                </div>
                <div className="hidden md:block text-xs text-muted text-right mono w-28">
                  {d.last_seen_at ? timeAgo(d.last_seen_at) : "mai visto"}<br />{d.battery != null ? `🔋 ${Math.round(d.battery)}%` : ""} {d.firmware ? `· v${d.firmware}` : ""}
                </div>
                <div className="text-xs mono text-right w-16">
                  <div>{d.requests24h} req</div>
                  <div className={d.errors24h ? "text-amber-300" : "text-muted"}>{d.errors24h} err</div>
                </div>
                <ChevronRight size={16} className="text-muted" />
              </Link>
            ))}
          </div>
        </div>

        <div className="glass p-3 xl:col-span-2 flex flex-col min-h-0">
          <div className="flex items-center gap-2 px-2 py-2">
            <div className="label flex items-center gap-2">
              {live && <span className="w-2 h-2 rounded-full bg-lime-300 animate-pulse" />}Traffico API
            </div>
            <button className="chip !py-1 !text-xs ml-auto" data-on={onlyErrors} onClick={() => setOnlyErrors(!onlyErrors)}>Solo errori</button>
            <button className="chip !py-1 !text-xs" onClick={() => setLive(!live)} title={live ? "Metti in pausa" : "Riprendi"}>{live ? <Pause size={12} /> : <Play size={12} />}</button>
          </div>
          <div className="overflow-y-auto max-h-[560px]"><LogList logs={logs} /></div>
        </div>
      </div>
    </div>
  );
}
