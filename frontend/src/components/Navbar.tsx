"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV_LINKS = [
  { href: "/", label: "Standings" },
  { href: "/points", label: "Points" },
  { href: "/budget", label: "Budget" },
  { href: "/efficiency", label: "Efficiency" },
  { href: "/races", label: "Races" },
  { href: "/chips", label: "Chips" },
  { href: "/schedule", label: "Schedule" },
];

export default function Navbar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <nav className="sticky top-0 z-50 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/95 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg tracking-tight">
          <span className="text-[var(--f1-red)]">F1</span>
          <span>Fantasy</span>
        </Link>

        {user && (
          <div className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors
                    ${active
                      ? "bg-[var(--bg-card)] text-white border-b-2 border-[var(--f1-red)]"
                      : "text-[var(--text-secondary)] hover:text-white hover:bg-[var(--bg-card)]"
                    }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
        )}

        <div className="flex items-center gap-3">
          {user && (
            <>
              <span className="hidden sm:inline text-sm text-[var(--text-secondary)]">
                {user.f1_username}
              </span>
              {!user.token_valid && (
                <span className="rounded bg-yellow-600/20 px-2 py-0.5 text-xs text-yellow-400">
                  Token expired
                </span>
              )}
              <button
                onClick={() => logout()}
                className="rounded-md bg-[var(--bg-card)] px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:text-white transition-colors"
              >
                Sign out
              </button>
            </>
          )}
        </div>
      </div>

      {/* Mobile nav */}
      {user && (
        <div className="flex md:hidden overflow-x-auto gap-1 px-4 pb-2">
          {NAV_LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors
                  ${active
                    ? "bg-[var(--bg-card)] text-white"
                    : "text-[var(--text-secondary)]"
                  }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
}
