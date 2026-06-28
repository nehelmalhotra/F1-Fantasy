"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type RacesResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";

const COLORS = [
  "#e10600", "#00d2be", "#0600ef", "#ff8700", "#006f62",
  "#2b4562", "#b6babd", "#c92d4b", "#5e8faa", "#f596c8",
];

export default function PointsPage() {
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
    <PageShell title="Cumulative Points">
      {loading ? (
        <Spinner />
      ) : !data ? (
        <p className="text-[var(--text-secondary)]">No race data available.</p>
      ) : (
        <PointsChart data={data} />
      )}
    </PageShell>
  );
}

function PointsChart({ data }: { data: RacesResponse }) {
  const { cumulative, race_names, final_race } = data;
  const users = Object.keys(cumulative);

  const chartData = [];
  for (let r = 1; r <= final_race; r++) {
    const key = String(r);
    const row: Record<string, string | number> = {
      race: race_names[key] || `R${r}`,
    };
    for (const u of users) {
      row[u] = cumulative[u]?.[key] ?? 0;
    }
    chartData.push(row);
  }

  return (
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
            labelStyle={{ color: "var(--text-primary)" }}
          />
          <Legend wrapperStyle={{ paddingTop: 12 }} />
          {users.map((u, i) => (
            <Line
              key={u} type="monotone" dataKey={u}
              stroke={COLORS[i % COLORS.length]} strokeWidth={2}
              dot={{ r: 3 }} activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
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
