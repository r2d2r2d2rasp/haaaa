"use client";
import { useState } from "react";
import { Check, Copy, KeyRound, X } from "lucide-react";

function CopyBtn({ text, label = "Copia" }: { text: string; label?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button className="btn-ghost !py-1.5 !px-3 !text-xs shrink-0" onClick={() => { navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1800); }}>
      {ok ? <Check size={13} className="text-lime-300" /> : <Copy size={13} />} {ok ? "Copiato" : label}
    </button>
  );
}

/** Mostra una chiave appena creata (una sola volta) con gli snippet pronti da mandare al team POD. */
export default function KeyReveal({ deviceName, apiKey, onClose }: { deviceName: string; apiKey: string; onClose: () => void }) {
  const base = typeof window !== "undefined" ? window.location.origin : "";
  const [tab, setTab] = useState<"env" | "curl" | "python">("env");
  const snippets = {
    env: `TS_BASE_URL=${base}\nTS_API_KEY=${apiKey}`,
    curl: `curl -X POST ${base}/api/v1/reports \\\n  -H "Authorization: Bearer ${apiKey}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"category":"rifiuti_abbandonati","lat":45.0703,"lon":7.6869,"confidence":0.9}'`,
    python: `import requests\nBASE = "${base}"\nH = {"Authorization": "Bearer ${apiKey}"}\n\n# segnalazione\nrequests.post(f"{BASE}/api/v1/reports", headers=H, json={"category": "rifiuti_abbandonati", "lat": 45.0703, "lon": 7.6869, "confidence": 0.9})\n# misure ambientali\nrequests.post(f"{BASE}/api/v1/readings", headers=H, json={"lat": 45.0703, "lon": 7.6869, "metrics": {"temperature_c": 21.5, "co2_ppm": 480}})`,
  };
  const message = `Chiave API TorinoSegnala per ${deviceName}\n\n${snippets.env}\n\nDocumentazione: docs/POD_API.md`;

  return (
    <div className="glass p-5 !border-lime-300/40 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 font-semibold"><KeyRound size={16} className="text-lime-300" /> Nuova chiave per {deviceName}</div>
        <button onClick={onClose} className="text-muted hover:text-white" aria-label="Chiudi"><X size={18} /></button>
      </div>
      <div className="text-xs text-amber-300/90">Copiala ora: per sicurezza non sarà più visibile (nel database ne salviamo solo l&apos;impronta).</div>
      <div className="flex gap-2 items-center">
        <code className="mono text-sm bg-black/40 rounded-xl px-3 py-2 flex-1 overflow-x-auto whitespace-nowrap">{apiKey}</code>
        <CopyBtn text={apiKey} label="Copia chiave" />
      </div>
      <div className="flex gap-1.5 items-center flex-wrap">
        {([["env", "Config POD (.env)"], ["curl", "Test con curl"], ["python", "Python"]] as const).map(([k, l]) => (
          <button key={k} className="chip !py-1 !text-xs" data-on={tab === k} onClick={() => setTab(k)}>{l}</button>
        ))}
        <span className="ml-auto"><CopyBtn text={message} label="Copia messaggio per il team" /></span>
      </div>
      <div className="relative">
        <pre className="mono text-xs bg-black/40 rounded-xl p-3 overflow-x-auto">{snippets[tab]}</pre>
        <span className="absolute right-2 top-2"><CopyBtn text={snippets[tab]} /></span>
      </div>
    </div>
  );
}
