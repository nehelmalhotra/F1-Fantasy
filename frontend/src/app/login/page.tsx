"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [leagueId, setLeagueId] = useState("10328108");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) router.push("/");
  }, [user, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password, parseInt(leagueId) || undefined);
      router.push("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold">
            <span className="text-[var(--f1-red)]">F1</span> Fantasy Dashboard
          </h1>
          <p className="mt-2 text-[var(--text-secondary)]">
            Sign in with your F1 Fantasy account
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-[var(--bg-card)] p-6">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-sm font-medium text-[var(--text-secondary)]">
              F1 Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-2.5 text-sm
                focus:border-[var(--f1-red)] focus:outline-none focus:ring-1 focus:ring-[var(--f1-red)]"
              placeholder="your-email@example.com"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-[var(--text-secondary)]">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-2.5 text-sm
                focus:border-[var(--f1-red)] focus:outline-none focus:ring-1 focus:ring-[var(--f1-red)]"
              placeholder="Your F1 account password"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-[var(--text-secondary)]">
              League ID
            </label>
            <input
              type="text"
              value={leagueId}
              onChange={(e) => setLeagueId(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-2.5 text-sm
                focus:border-[var(--f1-red)] focus:outline-none focus:ring-1 focus:ring-[var(--f1-red)]"
              placeholder="Your private league ID"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-[var(--f1-red)] py-2.5 text-sm font-semibold text-white
              transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Signing in to F1 Fantasy...
              </span>
            ) : (
              "Sign in with F1"
            )}
          </button>

          {loading && (
            <div className="rounded-lg bg-blue-500/10 border border-blue-500/30 p-3 text-sm text-blue-300">
              Signing you in to F1 Fantasy. This can take up to a minute the
              first time while we securely fetch your session.
            </div>
          )}

          <p className="text-center text-xs text-[var(--text-secondary)] mt-3">
            Your credentials are used only to sign in to F1 Fantasy and are never stored.
          </p>
        </form>
      </div>
    </div>
  );
}
