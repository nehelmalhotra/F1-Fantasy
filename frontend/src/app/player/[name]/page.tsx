"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type StandingsResponse, type RacesResponse, type ChipsResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";
import MetricCard from "@/components/MetricCard";
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, BarChart, Bar, Cell,
} from "recharts";

export default function PlayerPage() {
  const params = useParams();
  const playerName = decodeURIComponent(params.name as string);
  const { user } = useAuth();
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [races, setRaces] = useState<RacesResponse | null>(null);
  const [chips, setChips] = useState<ChipsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const lid = user.leagues?.[0]?.league_id;
    if (!lid) return;
    Promise.all([
      api.standings(lid),
      api.races(lid),
      api.chips(lid),
    ]).then(([s, r, c]) => {
      setStandings(s);
      setRaces(r);
      setChips(c);
    }).finally(() => setLoading(false));
  }, [user]);

  const playerStanding = standings?.standings.find((s) => s.user_name === playerName);
  const playerPerRace = races?.per_race?.[playerName];
  const playerCumulative = races?.cumulative?.[playerName];
  const playerChips = chips?.chips?.[playerName];

  return (
    <PageShell title={playerName}>
      {loading ? (
        <Spinner />
      ) : !playerStanding ? (
        <p className="text-[var(--text-secondary)]">Player &quot;{playerName}&quot; not found.</p>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <MetricCard label="Rank" value={`#${playerStanding.rank}`} accent />
            <MetricCard label="Total Points" value={playerStanding.total_points.toLocaleString()} />
            <MetricCard label="Avg / Race" value={playerStanding.avg_per_race} />
            <MetricCard label="Team Value" value={playerStanding.team_value > 0 ? `$${playerStanding.team_value.toFixed(1)}M` : "-"} />
            <MetricCard
              label="ROI"
              value={`${playerStanding.roi_percent >= 0 ? "+" : ""}${playerStanding.roi_percent.toFixed(1)}%`}
              detail={`${playerStanding.budget_gain >= 0 ? "+" : ""}$${playerStanding.budget_gain.toFixed(1)}M`}
            />
          </div>

          {playerCumulative && races && (
            <div className="rounded-xl bg-[var(--bg-card)] p-4">
              <h3 className="mb-4 text-lg font-semibold">Cumulative Points</h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart
                  data={Object.entries(playerCumulative).map(([r, pts]) => ({
                    race: races.race_names[r] || `R${r}`,
                    points: pts,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                  <XAxis dataKey="race" angle={-45} textAnchor="end" height={70} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
                  <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
                  <Tooltip contentStyle={{ background: "var(--bg-primary)", border: "1px solid var(--border-subtle)", borderRadius: 8 }} />
                  <Line type="monotone" dataKey="points" stroke="#e10600" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {playerPerRace && races && (
            <div className="rounded-xl bg-[var(--bg-card)] p-4">
              <h3 className="mb-4 text-lg font-semibold">Points Per Race</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart
                  data={Object.entries(playerPerRace).map(([r, pts]) => ({
                    race: races.race_names[r] || `R${r}`,
                    points: pts,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                  <XAxis dataKey="race" angle={-45} textAnchor="end" height={70} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
                  <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
                  <Tooltip contentStyle={{ background: "var(--bg-primary)", border: "1px solid var(--border-subtle)", borderRadius: 8 }} />
                  <Bar dataKey="points">
                    {Object.values(playerPerRace).map((pts, i) => (
                      <Cell key={i} fill={pts >= 0 ? "#1f9e89" : "#d73027"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {playerChips && playerChips.length > 0 && (
            <div className="rounded-xl bg-[var(--bg-card)] p-4">
              <h3 className="mb-4 text-lg font-semibold">Chips Used</h3>
              <div className="flex flex-wrap gap-3">
                {playerChips.map((c, i) => (
                  <div key={i} className="rounded-lg bg-[var(--bg-primary)] px-4 py-3 text-center">
                    <p className="text-xs text-[var(--text-secondary)]">
                      {races?.race_names[String(c.race)] || `R${c.race}`}
                    </p>
                    <p className="font-semibold text-sm mt-1">{c.chip}</p>
                    <p className="text-xs text-[var(--text-secondary)] mt-0.5">{c.team}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </PageShell>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--f1-red)] border-t-transparent" />
    </div>
  );
}
