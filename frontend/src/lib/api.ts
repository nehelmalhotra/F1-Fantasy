const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    let message = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(body);
      message = parsed.detail || parsed.message || body;
    } catch {
      if (body) message = body;
    }
    throw new Error(message);
  }
  return res.json();
}

export interface User {
  user_id: number;
  f1_username: string;
  f1_guid: string;
  leagues: { league_id: number; league_name: string }[];
  token_valid: boolean;
}

export interface Standing {
  rank: number;
  user_name: string;
  total_points: number;
  last_race_points: number;
  avg_per_race: number;
  team_value: number;
  budget_gain: number;
  points_per_million: number;
  roi_percent: number;
  gap: number;
}

export interface StandingsResponse {
  standings: Standing[];
  final_race: number;
  race_names: Record<string, string>;
  total_players: number;
}

export interface RacesResponse {
  cumulative: Record<string, Record<string, number>>;
  per_race: Record<string, Record<string, number>>;
  winners: Record<string, { user_name: string; points: number }>;
  race_names: Record<string, string>;
  final_race: number;
}

export interface BudgetResponse {
  budget: Record<string, Record<string, { team_val: number; team_bal: number; max_team_bal: number }>>;
  race_names: Record<string, string>;
}

export interface ChipsResponse {
  chips: Record<string, { race: number; team: string; chip: string }[]>;
  race_names: Record<string, string>;
}

export interface ScheduleRace {
  round: number;
  name: string;
  location: string;
  sprint: boolean;
  date_local: string;
  time_local: string;
  date_utc: string;
  time_utc: string;
  status: "completed" | "next" | "upcoming";
}

export interface ScheduleResponse {
  schedule: ScheduleRace[];
  next_race: {
    name: string;
    days: number;
    hours: number;
    date_local: string;
  } | null;
}

export const api = {
  login(email: string, password: string, league_id?: number) {
    return apiFetch<{ user_id: number; f1_username: string; league_id: number }>(
      "/api/auth/f1-login",
      { method: "POST", body: JSON.stringify({ email, password, league_id }) }
    );
  },

  me() {
    return apiFetch<User>("/api/auth/me");
  },

  logout() {
    return apiFetch<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
  },

  standings(leagueId: number) {
    return apiFetch<StandingsResponse>(`/api/league/${leagueId}/standings`);
  },

  races(leagueId: number) {
    return apiFetch<RacesResponse>(`/api/league/${leagueId}/races`);
  },

  budget(leagueId: number) {
    return apiFetch<BudgetResponse>(`/api/league/${leagueId}/budget`);
  },

  chips(leagueId: number) {
    return apiFetch<ChipsResponse>(`/api/league/${leagueId}/chips`);
  },

  schedule(tz?: string) {
    const q = tz ? `?tz=${encodeURIComponent(tz)}` : "";
    return apiFetch<ScheduleResponse>(`/api/schedule${q}`);
  },
};
