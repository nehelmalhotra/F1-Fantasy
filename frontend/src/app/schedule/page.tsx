"use client";

import { useEffect, useState } from "react";
import { api, type ScheduleResponse } from "@/lib/api";
import MetricCard from "@/components/MetricCard";

const TIMEZONES = [
  "America/Los_Angeles", "America/Denver", "America/Chicago",
  "America/New_York", "America/Toronto",
  "Europe/London", "Europe/Paris", "Europe/Berlin",
  "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo",
  "Australia/Sydney", "Pacific/Auckland",
];

export default function SchedulePage() {
  const [data, setData] = useState<ScheduleResponse | null>(null);
  const [tz, setTz] = useState("America/New_York");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.schedule(tz).then(setData).finally(() => setLoading(false));
  }, [tz]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <h1 className="text-2xl font-bold">2026 Race Calendar</h1>
        <select
          value={tz}
          onChange={(e) => setTz(e.target.value)}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm
            focus:border-[var(--f1-red)] focus:outline-none"
        >
          {TIMEZONES.map((t) => (
            <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <Spinner />
      ) : !data ? (
        <p className="text-[var(--text-secondary)]">Could not load schedule.</p>
      ) : (
        <>
          {data.next_race && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <MetricCard label="Next Race" value={data.next_race.name} accent />
              <MetricCard label="Date / Time" value={data.next_race.date_local} />
              <MetricCard label="Countdown" value={`${data.next_race.days}d ${data.next_race.hours}h`} />
            </div>
          )}

          <div className="overflow-x-auto rounded-xl bg-[var(--bg-card)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
                  <th className="px-4 py-3 text-left font-medium w-12">#</th>
                  <th className="px-4 py-3 text-left font-medium">Grand Prix</th>
                  <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Circuit</th>
                  <th className="px-4 py-3 text-left font-medium">Date</th>
                  <th className="px-4 py-3 text-left font-medium">Time</th>
                  <th className="px-4 py-3 text-center font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.schedule.map((race) => (
                  <tr
                    key={race.round}
                    className={`border-b border-[var(--border-subtle)]/50 transition-colors
                      ${race.status === "next" ? "bg-[var(--f1-red)]/10" : "hover:bg-[var(--bg-card-hover)]"}`}
                  >
                    <td className="px-4 py-3 text-[var(--text-secondary)]">{race.round}</td>
                    <td className="px-4 py-3 font-medium">
                      {race.name}
                      {race.sprint && (
                        <span className="ml-2 rounded bg-yellow-600/20 px-1.5 py-0.5 text-[10px] text-yellow-400 font-medium">
                          Sprint
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-secondary)] hidden sm:table-cell">{race.location}</td>
                    <td className="px-4 py-3">{race.date_local}</td>
                    <td className="px-4 py-3">{race.time_local}</td>
                    <td className="px-4 py-3 text-center">
                      {race.status === "completed" && (
                        <span className="rounded-full bg-green-600/20 px-2 py-0.5 text-xs text-green-400">Done</span>
                      )}
                      {race.status === "next" && (
                        <span className="rounded-full bg-[var(--f1-red)]/20 px-2 py-0.5 text-xs text-[var(--f1-red)] font-bold">NEXT</span>
                      )}
                      {race.status === "upcoming" && (
                        <span className="rounded-full bg-[var(--border-subtle)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">Upcoming</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
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
