"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Map, ListChecks, Route, Cpu, LogOut, Landmark, ShieldCheck } from "lucide-react";
import { getAdminPw, setAdminPw } from "@/lib/adminClient";

const NAV = [
  { href: "/comune", label: "Panoramica", icon: BarChart3 },
  { href: "/comune/mappa", label: "Mappa operativa", icon: Map },
  { href: "/comune/segnalazioni", label: "Segnalazioni", icon: ListChecks },
  { href: "/comune/percorsi", label: "Percorsi raccolta", icon: Route },
  { href: "/comune/pod", label: "Console IT · POD", icon: Cpu },
];

export default function ComuneLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [state, setState] = useState<"checking" | "out" | "in">("checking");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");

  async function check(p: string) {
    const r = await fetch("/api/stats", { headers: { "x-admin-password": p } });
    if (r.ok) { setAdminPw(p); setState("in"); setErr(""); }
    else { setAdminPw(null); setState("out"); if (p) setErr("Password errata"); }
  }
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { const p = getAdminPw(); if (p) check(p); else setState("out"); }, []);

  if (state === "checking") return <div className="grid place-items-center min-h-screen text-muted">…</div>;
  if (state === "out") return (
    <div className="grid place-items-center min-h-screen p-6">
      <form className="glass p-8 w-full max-w-sm flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); check(pw); }}>
        <span className="grid place-items-center w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan to-violet text-[#04121a]"><Landmark size={22} /></span>
        <div><h1 className="text-xl font-semibold">Area Comune</h1><p className="text-sm text-muted">Accesso riservato agli operatori.</p></div>
        <input className="input" type="password" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        {err && <div className="text-sm text-rose-300">{err}</div>}
        <button className="btn" type="submit"><ShieldCheck size={16} /> Entra</button>
        <Link href="/" className="text-xs text-muted text-center hover:text-white">← Torna alla mappa pubblica</Link>
      </form>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="hidden md:flex flex-col gap-1 w-60 shrink-0 p-4 border-r border-line bg-black/20 sticky top-0 h-screen">
        <div className="flex items-center gap-2 px-2 py-3 mb-3">
          <span className="grid place-items-center w-9 h-9 rounded-xl bg-gradient-to-br from-cyan to-violet text-[#04121a]"><Landmark size={18} /></span>
          <div className="leading-tight"><div className="font-semibold">Comune di Torino</div><div className="text-xs text-muted">Centrale segnalazioni</div></div>
        </div>
        {NAV.map(({ href, label, icon: Icon }) => {
          const on = href === "/comune" ? path === href : path.startsWith(href);
          return (
            <Link key={href} href={href} className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition ${on ? "bg-white/10 text-white shadow-[inset_2px_0_0_var(--cyan)]" : "text-muted hover:text-white hover:bg-white/5"}`}>
              <Icon size={17} className={on ? "text-cyan" : ""} /> {label}
            </Link>
          );
        })}
        <button onClick={() => { setAdminPw(null); setState("out"); setPw(""); }} className="mt-auto flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-muted hover:text-white hover:bg-white/5">
          <LogOut size={17} /> Esci
        </button>
      </aside>
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-50 glass !rounded-none !rounded-t-2xl flex justify-around py-2">
        {NAV.map(({ href, icon: Icon }) => {
          const on = href === "/comune" ? path === href : path.startsWith(href);
          return <Link key={href} href={href} className={`p-2.5 rounded-xl ${on ? "bg-white/10 text-cyan" : "text-muted"}`}><Icon size={20} /></Link>;
        })}
      </nav>
      <div className="flex-1 min-w-0 flex flex-col pb-16 md:pb-0">{children}</div>
    </div>
  );
}
