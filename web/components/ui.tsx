import { CAT, STATUS_LABEL } from "@/lib/categories";

export const timeAgo = (iso: string) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "ora";
  if (s < 3600) return `${Math.floor(s / 60)} min fa`;
  if (s < 86400) return `${Math.floor(s / 3600)} h fa`;
  return `${Math.floor(s / 86400)} g fa`;
};

export function StatusBadge({ status }: { status: string }) {
  const c = { open: "#fb7185", in_progress: "#fbbf24", resolved: "#a3e635", rejected: "#8b95b3" }[status] ?? "#8b95b3";
  return <span className="text-xs px-2.5 py-1 rounded-full" style={{ color: c, background: `${c}1f`, border: `1px solid ${c}44` }}>{STATUS_LABEL[status] ?? status}</span>;
}

export function CatDot({ slug }: { slug: string }) {
  const c = CAT[slug];
  return <span className="inline-flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c?.color, boxShadow: `0 0 10px ${c?.color}` }} />{c?.icon} {c?.name ?? slug}</span>;
}
