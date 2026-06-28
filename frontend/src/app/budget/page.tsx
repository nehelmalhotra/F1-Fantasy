"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type BudgetResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";

const COLORS = [
  "#e10600", "#00d2be", "#0600ef", "#ff8700", "#006f62",
  "#2b4562", "#b6babd", "#c92d4b", "#5e8faa", "#f596c8",
];

export default function BudgetPage() {
  const { user } = useAuth();
  const [data, setData] = useState<BudgetResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const lid = user.leagues?.[0]?.league_id;
    if (!lid) return;
    api.budget(lid).then(setData).finally(() => setLoading(false));
  }, [user]);

  return (
    <PageShell title="Team Value Evolution">
      {loading ? (
        <Spinner />
      ) : !data || !Object.keys(data.budget).length ? (
        <p className="text-[var(--text-secondary)]">No budget data available.</p>
      ) : (
        <BudgetChart data={data} />
      )}
    </PageShell>
  );
}

function BudgetChart({ data }: { data: BudgetResponse }) {
  const { budget, race_names } = data;
  const users = Object.keys(budget);

  const allRounds = new Set<number>();
  for (const hist of Object.values(budget)) {
    for (const r of Object.keys(hist)) allRounds.add(parseInt(r));
  }
  const rounds = Array.from(allRounds).sort((a, b) => a - b);

  const chartData = rounds.map((r) => {
    const row: Record<string, string | number> = { race: race_names[String(r)] || `R${r}` };
    for (const u of users) {
      const val = budget[u]?.[String(r)]?.max_team_bal ?? 0;
      if (val > 0) row[u] = val;
    }
    return row;
  });

  return (
    <div className="space-y-6">
      <div className="rounded-xl bg-[var(--bg-card)] p-4">
        <ResponsiveContainer width="100%" height={500}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
            <XAxis
              dataKey="race" angle={-45} textAnchor="end" height={80}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            />
            <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
            <Tooltip
              contentStyle={{ background: "var(--bg-primary)", border: "1px solid var(--border-subtle)", borderRadius: 8 }}
              formatter={(val: number) => `$${val.toFixed(1)}M`}
            />
            <Legend wrapperStyle={{ paddingTop: 12 }} />
            <ReferenceLine y={200} stroke="rgba(255,255,255,0.2)" strokeDasharray="6 4" label={{ value: "Starting ($200M)", fill: "var(--text-secondary)", fontSize: 11, position: "insideTopLeft" }} />
            {users.map((u, i) => (
              <Line key={u} type="monotone" dataKey={u} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 3 }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-x-auto rounded-xl bg-[var(--bg-card)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
              <th className="px-4 py-3 text-left font-medium">Player</th>
              <th className="px-4 py-3 text-right font-medium">Final Value</th>
              <th className="px-4 py-3 text-right font-medium">Gain</th>
              <th className="px-4 py-3 text-right font-medium">ROI</th>
            </tr>
          </thead>
          <tbody>
            {users
              .map((u) => {
                const hist = budget[u];
                const vals = Object.values(hist).map((v) => v.max_team_bal).filter((v) => v > 0);
                const final_val = vals.length ? vals[vals.length - 1] : 0;
                const gain = final_val - 200;
                const roi = (gain / 200) * 100;
                return { user: u, final_val, gain, roi };
              })
              .sort((a, b) => b.final_val - a.final_val)
              .map((row) => (
                <tr key={row.user} className="border-b border-[var(--border-subtle)]/50 hover:bg-[var(--bg-card-hover)]">
                  <td className="px-4 py-3 font-medium">{row.user}</td>
                  <td className="px-4 py-3 text-right">${row.final_val.toFixed(1)}M</td>
                  <td className={`px-4 py-3 text-right ${row.gain >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {row.gain >= 0 ? "+" : ""}${row.gain.toFixed(1)}M
                  </td>
                  <td className={`px-4 py-3 text-right ${row.roi >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {row.roi >= 0 ? "+" : ""}{row.roi.toFixed(1)}%
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
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
