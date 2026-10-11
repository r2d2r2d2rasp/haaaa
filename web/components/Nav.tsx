"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Map, Plus, Radar } from "lucide-react";

/** Barra del cittadino: logo, statistiche/mappa e "Segnala". L'area Comune ha la sua navigazione. */
export default function Nav() {
  const path = usePathname();
  if (path.startsWith("/comune")) return null;
  const onStats = path === "/statistiche";
  return (
    <header className="fixed top-0 inset-x-0 z-50 px-3 sm:px-5 pt-3 pointer-events-none">
      <nav className="flex items-center justify-between gap-2">
        <Link href="/" className="glass !rounded-2xl pointer-events-auto flex items-center gap-2 pl-2 pr-4 py-2 font-semibold tracking-tight">
          <span className="grid place-items-center w-8 h-8 rounded-xl bg-gradient-to-br from-cyan to-violet text-[#04121a]"><Radar size={18} /></span>
          <span>Torino<span className="glow-text">Segnala</span></span>
        </Link>
        <div className="flex items-center gap-2">
          <Link href={onStats ? "/" : "/statistiche"} className="glass !rounded-2xl pointer-events-auto flex items-center gap-2 px-3.5 py-2.5 text-sm hover:!border-cyan/50" title={onStats ? "Mappa" : "Statistiche"}>
            {onStats ? <Map size={17} /> : <BarChart3 size={17} />}<span className="hidden sm:inline">{onStats ? "Mappa" : "Statistiche"}</span>
          </Link>
          {path !== "/segnala" && <Link href="/segnala" className="btn pointer-events-auto"><Plus size={18} /> <span className="hidden min-[380px]:inline">Segnala</span></Link>}
        </div>
      </nav>
    </header>
  );
}
