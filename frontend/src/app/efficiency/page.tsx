"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type StandingsResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";

const VIRIDIS = ["#440154", "#482777", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"];
const RDYLGN = ["#d73027", "#f46d43", "#fdae61", "#fee08b", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850"];

function pickColor(palette: string[], value: number, max: number): string {
  const idx = Math.min(Math.floor((value / (max || 1)) * (palette.length - 1)), palette.length - 1);
  return palette[Math.max(0, idx)];
}

export default function EfficiencyPage() {
  const { user } = useAuth();
  const [data, setData] = useState<StandingsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const lid = user.leagues?.[0]?.league_id;
    if (!lid) return;
    api.standings(lid).then(setData).finally(() => setLoading(false));
  }, [user]);

  return (
    <PageShell title="Efficiency Analysis">
      {loading ? (
        <Spinner />
      ) : !data?.standings?.length ? (
        <p className="text-[var(--text-secondary)]">No data.</p>
      ) : (
        <EfficiencyContent standings={data.standings} />
      )}
    </PageShell>
  );
}

function EfficiencyContent({ standings }: { standings: StandingsResponse["standings"] }) {
  const ppmData = standings
    .filter((s) => s.points_per_million > 0)
    .sort((a, b) => a.points_per_million - b.points_per_million);
  const roiData = standings
    .filter((s) => s.roi_percent !== 0)
    .sort((a, b) => a.roi_percent - b.roi_percent);

  const maxPpm = Math.max(...ppmData.map((d) => d.points_per_million));
  const maxRoi = Math.max(...roiData.map((d) => Math.abs(d.roi_percent)));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl bg-[var(--bg-card)] p-4">
          <h3 className="mb-4 text-lg font-semibold">Points per $M Invested</h3>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={ppmData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis type="number" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
              <YAxis dataKey="user_name" type="category" width={120} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "var(--bg-primary)", border: "1px solid var(--border-subtle)", borderRadius: 8 }} />
              <Bar dataKey="points_per_million" name="Pts/$M">
                {ppmData.map((d, i) => (
                  <Cell key={i} fill={pickColor(VIRIDIS, d.points_per_million, maxPpm)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-xl bg-[var(--bg-card)] p-4">
          <h3 className="mb-4 text-lg font-semibold">ROI % (Team Value Growth)</h3>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={roiData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis type="number" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
              <YAxis dataKey="user_name" type="category" width={120} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "var(--bg-primary)", border: "1px solid var(--border-subtle)", borderRadius: 8 }} />
              <Bar dataKey="roi_percent" name="ROI %">
                {roiData.map((d, i) => (
                  <Cell key={i} fill={pickColor(RDYLGN, d.roi_percent + maxRoi, maxRoi * 2)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl bg-[var(--bg-card)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
              <th className="px-4 py-3 text-left font-medium">#</th>
              <th className="px-4 py-3 text-left font-medium">Player</th>
              <th className="px-4 py-3 text-right font-medium">Points</th>
              <th className="px-4 py-3 text-right font-medium">Team Value</th>
              <th className="px-4 py-3 text-right font-medium">Gain</th>
              <th className="px-4 py-3 text-right font-medium">Pts/$M</th>
              <th className="px-4 py-3 text-right font-medium">ROI</th>
            </tr>
          </thead>
          <tbody>
            {standings.map((s) => (
              <tr key={s.user_name} className="border-b border-[var(--border-subtle)]/50 hover:bg-[var(--bg-card-hover)]">
                <td className="px-4 py-3 text-[var(--text-secondary)]">{s.rank}</td>
                <td className="px-4 py-3 font-medium">{s.user_name}</td>
                <td className="px-4 py-3 text-right">{s.total_points.toLocaleString()}</td>
                <td className="px-4 py-3 text-right">{s.team_value > 0 ? `$${s.team_value.toFixed(1)}M` : "-"}</td>
                <td className={`px-4 py-3 text-right ${s.budget_gain >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {s.budget_gain >= 0 ? "+" : ""}${s.budget_gain.toFixed(1)}M
                </td>
                <td className="px-4 py-3 text-right">{s.points_per_million.toFixed(1)}</td>
                <td className={`px-4 py-3 text-right ${s.roi_percent >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {s.roi_percent >= 0 ? "+" : ""}{s.roi_percent.toFixed(1)}%
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
