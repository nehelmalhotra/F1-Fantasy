"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type StandingsResponse } from "@/lib/api";
import PageShell from "@/components/PageShell";
import MetricCard from "@/components/MetricCard";
import Link from "next/link";

export default function StandingsPage() {
  const { user } = useAuth();
  const [data, setData] = useState<StandingsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const leagueId = user.leagues?.[0]?.league_id;
    if (!leagueId) return;
    api.standings(leagueId).then(setData).finally(() => setLoading(false));
  }, [user]);

  return (
    <PageShell title="League Standings">
      {loading ? (
        <LoadingState />
      ) : !data || !data.standings.length ? (
        <EmptyState />
      ) : (
        <StandingsContent data={data} username={user?.f1_username} />
      )}
    </PageShell>
  );
}

function StandingsContent({ data, username }: { data: StandingsResponse; username?: string }) {
  const { standings, final_race, total_players } = data;
  const leader = standings[0];
  const me = standings.find((s) => s.user_name.toLowerCase().includes(username?.toLowerCase() || "---"));

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <MetricCard label="Leader" value={leader.user_name} detail={`${leader.total_points.toLocaleString()} pts`} accent />
        <MetricCard label="Players" value={total_players} />
        <MetricCard label="Races Completed" value={final_race} />
        {me && (
          <MetricCard
            label="Your Position"
            value={`#${me.rank}`}
            detail={me.gap > 0 ? `-${me.gap.toLocaleString()} pts` : "Leading"}
            accent
          />
        )}
      </div>

      <div className="overflow-x-auto rounded-xl bg-[var(--bg-card)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
              <th className="px-4 py-3 text-left font-medium w-12">#</th>
              <th className="px-4 py-3 text-left font-medium">Player</th>
              <th className="px-4 py-3 text-right font-medium">Total</th>
              <th className="px-4 py-3 text-right font-medium hidden sm:table-cell">Last Race</th>
              <th className="px-4 py-3 text-right font-medium hidden md:table-cell">Avg/Race</th>
              <th className="px-4 py-3 text-right font-medium hidden lg:table-cell">Value</th>
              <th className="px-4 py-3 text-right font-medium hidden lg:table-cell">Pts/$M</th>
              <th className="px-4 py-3 text-right font-medium">Gap</th>
            </tr>
          </thead>
          <tbody>
            {standings.map((s) => (
              <tr
                key={s.user_name}
                className="border-b border-[var(--border-subtle)]/50 hover:bg-[var(--bg-card-hover)] transition-colors"
              >
                <td className="px-4 py-3 font-bold text-[var(--text-secondary)]">{s.rank}</td>
                <td className="px-4 py-3 font-medium">
                  <Link href={`/player/${encodeURIComponent(s.user_name)}`} className="hover:text-[var(--f1-red)] transition-colors">
                    {s.user_name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right font-bold">{s.total_points.toLocaleString()}</td>
                <td className="px-4 py-3 text-right hidden sm:table-cell">{s.last_race_points.toLocaleString()}</td>
                <td className="px-4 py-3 text-right hidden md:table-cell">{s.avg_per_race}</td>
                <td className="px-4 py-3 text-right hidden lg:table-cell">
                  {s.team_value > 0 ? `$${s.team_value.toFixed(1)}M` : "-"}
                </td>
                <td className="px-4 py-3 text-right hidden lg:table-cell">{s.points_per_million.toFixed(1)}</td>
                <td className="px-4 py-3 text-right">
                  {s.gap > 0 ? (
                    <span className="text-red-400">-{s.gap.toLocaleString()}</span>
                  ) : (
                    <span className="text-green-400">Leader</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--f1-red)] border-t-transparent" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] text-[var(--text-secondary)]">
      <p className="text-lg">No data yet</p>
      <p className="text-sm mt-1">Data is being collected. Refresh in a moment.</p>
    </div>
  );
}
