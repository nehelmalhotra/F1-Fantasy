"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type RacesResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";

export default function RacesPage() {
  const { user } = useAuth();
  const [data, setData] = useState<RacesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const lid = user.leagues?.[0]?.league_id;
    if (!lid) return;
    api.races(lid).then(setData).finally(() => setLoading(false));
  }, [user]);

  return (
    <PageShell title="Race Breakdown">
      {loading ? (
        <Spinner />
      ) : !data ? (
        <p className="text-[var(--text-secondary)]">No race data.</p>
      ) : (
        <RacesContent data={data} />
      )}
    </PageShell>
  );
}

function RacesContent({ data }: { data: RacesResponse }) {
  const { per_race, winners, race_names, final_race } = data;
  const users = Object.keys(per_race);

  // Heatmap grid
  const rounds = Array.from({ length: final_race }, (_, i) => i + 1);
  const sorted = [...users].sort((a, b) => {
    const cumA = Object.values(data.cumulative[a] || {}).pop() || 0;
    const cumB = Object.values(data.cumulative[b] || {}).pop() || 0;
    return cumB - cumA;
  });

  // Flatten all points for color scale
  const allPts: number[] = [];
  for (const u of users) {
    for (const pts of Object.values(per_race[u] || {})) {
      allPts.push(pts);
    }
  }
  const maxPts = Math.max(...allPts, 1);
  const minPts = Math.min(...allPts, 0);

  function heatColor(val: number): string {
    const ratio = (val - minPts) / (maxPts - minPts || 1);
    const r = Math.round(215 - ratio * 185);
    const g = Math.round(48 + ratio * 200);
    const b = Math.round(39 + ratio * 60);
    return `rgb(${r},${g},${b})`;
  }

  // Win counts
  const winCounts: Record<string, number> = {};
  for (const w of Object.values(winners)) {
    winCounts[w.user_name] = (winCounts[w.user_name] || 0) + 1;
  }
  const winCountData = Object.entries(winCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, wins]) => ({ name, wins }));

  return (
    <div className="space-y-6">
      {/* Heatmap */}
      <div className="rounded-xl bg-[var(--bg-card)] p-4 overflow-x-auto">
        <h3 className="mb-4 text-lg font-semibold">Points per Race Weekend</h3>
        <table className="text-xs min-w-full">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left text-[var(--text-secondary)]">Player</th>
              {rounds.map((r) => (
                <th key={r} className="px-2 py-1 text-center text-[var(--text-secondary)] whitespace-nowrap">
                  {race_names[String(r)]?.slice(0, 3) || `R${r}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((u) => (
              <tr key={u}>
                <td className="px-2 py-1.5 font-medium whitespace-nowrap">{u}</td>
                {rounds.map((r) => {
                  const pts = per_race[u]?.[String(r)];
                  return (
                    <td
                      key={r}
                      className="px-2 py-1.5 text-center font-mono"
                      style={{ backgroundColor: pts != null ? heatColor(pts) : "transparent", color: pts != null ? "#fff" : "var(--text-secondary)" }}
                    >
                      {pts != null ? Math.round(pts) : "-"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Race Winners */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl bg-[var(--bg-card)]">
          <h3 className="px-4 pt-4 text-lg font-semibold">Race Winners</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
                  <th className="px-4 py-3 text-left font-medium">Race</th>
                  <th className="px-4 py-3 text-left font-medium">GP</th>
                  <th className="px-4 py-3 text-left font-medium">Winner</th>
                  <th className="px-4 py-3 text-right font-medium">Points</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(winners)
                  .sort(([a], [b]) => parseInt(a) - parseInt(b))
                  .map(([rd, w]) => (
                    <tr key={rd} className="border-b border-[var(--border-subtle)]/50 hover:bg-[var(--bg-card-hover)]">
                      <td className="px-4 py-2 text-[var(--text-secondary)]">{rd}</td>
                      <td className="px-4 py-2">{race_names[rd] || `R${rd}`}</td>
                      <td className="px-4 py-2 font-medium">{w.user_name}</td>
                      <td className="px-4 py-2 text-right">{Math.round(w.points).toLocaleString()}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl bg-[var(--bg-card)] p-4">
          <h3 className="mb-4 text-lg font-semibold">Win Count</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={winCountData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis type="number" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} allowDecimals={false} />
              <YAxis dataKey="name" type="category" width={100} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "var(--bg-primary)", border: "1px solid var(--border-subtle)", borderRadius: 8 }} />
              <Bar dataKey="wins" name="Wins">
                {winCountData.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? "#e10600" : "#3e4989"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
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
