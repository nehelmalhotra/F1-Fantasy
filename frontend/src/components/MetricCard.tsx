"use client";

interface MetricCardProps {
  label: string;
  value: string | number;
  detail?: string;
  accent?: boolean;
}

export default function MetricCard({ label, value, detail, accent }: MetricCardProps) {
  return (
    <div
      className={`rounded-lg bg-gradient-to-br from-[#1a1a2e] to-[var(--bg-card)] p-4
        border-l-[3px] ${accent ? "border-[var(--f1-red)]" : "border-[var(--border-subtle)]"}`}
    >
      <p className="text-xs uppercase tracking-wider text-[var(--text-secondary)] mb-1">{label}</p>
      <p className="text-xl font-bold">{value}</p>
      {detail && <p className="text-sm text-[var(--text-secondary)] mt-0.5">{detail}</p>}
    </div>
  );
}
