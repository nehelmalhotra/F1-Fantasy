"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type ChipsResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";

const CHIP_COLORS: Record<string, string> = {
  Wildcard: "#e10600",
  Limitless: "#00d2be",
  "Final Fix": "#ff8700",
  Autopilot: "#0600ef",
  "No Negative": "#006f62",
  "Extra DRS": "#c92d4b",
};

export default function ChipsPage() {
  const { user } = useAuth();
  const [data, setData] = useState<ChipsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const lid = user.leagues?.[0]?.league_id;
    if (!lid) return;
    api.chips(lid).then(setData).finally(() => setLoading(false));
  }, [user]);

  return (
    <PageShell title="Chip Usage">
      {loading ? (
        <Spinner />
      ) : !data || !Object.keys(data.chips).length ? (
        <p className="text-[var(--text-secondary)]">No chip usage data yet.</p>
      ) : (
        <ChipsContent data={data} />
      )}
    </PageShell>
  );
}

function ChipsContent({ data }: { data: ChipsResponse }) {
  const { chips, race_names } = data;
  const users = Object.keys(chips).sort();

  // All race rounds used
  const allRounds = new Set<number>();
  for (const userChips of Object.values(chips)) {
    for (const c of userChips) allRounds.add(c.race);
  }
  const rounds = Array.from(allRounds).sort((a, b) => a - b);

  // Count by user
  const chipCounts: Record<string, Record<string, number>> = {};
  for (const [u, uChips] of Object.entries(chips)) {
    chipCounts[u] = {};
    for (const c of uChips) {
      chipCounts[u][c.chip] = (chipCounts[u][c.chip] || 0) + 1;
    }
  }
  const allChipTypes = [...new Set(Object.values(chips).flatMap((c) => c.map((x) => x.chip)))];

  return (
    <div className="space-y-6">
      {/* Grid */}
      <div className="rounded-xl bg-[var(--bg-card)] p-4 overflow-x-auto">
        <table className="text-sm min-w-full">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left text-[var(--text-secondary)] font-medium">Player</th>
              {rounds.map((r) => (
                <th key={r} className="px-3 py-2 text-center text-[var(--text-secondary)] font-medium whitespace-nowrap">
                  {race_names[String(r)] || `R${r}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u} className="border-b border-[var(--border-subtle)]/50">
                <td className="px-3 py-2 font-medium">{u}</td>
                {rounds.map((r) => {
                  const used = chips[u].filter((c) => c.race === r);
                  return (
                    <td key={r} className="px-3 py-2 text-center">
                      {used.length > 0 ? (
                        <div className="flex flex-wrap gap-1 justify-center">
                          {used.map((c, i) => (
                            <span
                              key={i}
                              className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium text-white"
                              style={{ backgroundColor: CHIP_COLORS[c.chip] || "#555" }}
                            >
                              {c.chip}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Chips per player summary */}
      <div className="rounded-xl bg-[var(--bg-card)]">
        <h3 className="px-4 pt-4 text-lg font-semibold">Chips Used Per Player</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
                <th className="px-4 py-3 text-left font-medium">Player</th>
                {allChipTypes.map((ct) => (
                  <th key={ct} className="px-4 py-3 text-center font-medium">{ct}</th>
                ))}
                <th className="px-4 py-3 text-center font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const total = Object.values(chipCounts[u] || {}).reduce((a, b) => a + b, 0);
                return (
                  <tr key={u} className="border-b border-[var(--border-subtle)]/50 hover:bg-[var(--bg-card-hover)]">
                    <td className="px-4 py-2 font-medium">{u}</td>
                    {allChipTypes.map((ct) => (
                      <td key={ct} className="px-4 py-2 text-center">
                        {chipCounts[u]?.[ct] || 0}
                      </td>
                    ))}
                    <td className="px-4 py-2 text-center font-bold">{total}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--f1-red)] border-t-transparent" />
    </div>
  );
}
