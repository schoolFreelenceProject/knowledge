import {
  Activity,
  BarChart3,
  BookOpen,
  Code2,
  Gauge,
  LogOut,
  MessageSquareWarning,
  Shield,
  Users,
  UserCog,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getReadiness } from "../api/health";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { useAuth } from "../hooks/useAuth";
import { cn } from "../utils/cn";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: Gauge },
  { to: "/documents", label: "Documents", icon: BookOpen },
  { to: "/code-repositories", label: "Code Repository", icon: Code2 },
  { to: "/users", label: "Users", icon: Users },
  { to: "/users-permissions", label: "Permissions", icon: UserCog },
  { to: "/traces", label: "Traces", icon: Activity },
  { to: "/feedback", label: "Feedback", icon: MessageSquareWarning },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];

export function AppLayout() {
  const { email, logout } = useAuth();
  const readinessQuery = useQuery({
    queryKey: ["health", "ready"],
    queryFn: getReadiness,
    refetchInterval: 30_000,
    retry: false,
  });

  const healthStatus = readinessQuery.data?.status ?? (readinessQuery.isError ? "degraded" : "checking");

  return (
    <div className="min-h-screen bg-surface text-ink">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-white lg:block">
        <div className="flex h-16 items-center gap-3 border-b border-border px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-ink text-white">
            <Shield className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">Knowledge Base</p>
            <p className="truncate text-xs text-muted">Admin Control Panel</p>
          </div>
        </div>
        <nav className="space-y-1 p-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted",
                    "hover:bg-slate-100 hover:text-ink",
                    isActive && "bg-blue-50 text-accent",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                <span className="truncate">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-border bg-white/95 px-4 backdrop-blur lg:px-6">
          <div className="flex items-center gap-2 overflow-x-auto lg:hidden">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      "flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted",
                      "hover:bg-slate-100 hover:text-ink",
                      isActive && "bg-blue-50 text-accent",
                    )
                  }
                  title={item.label}
                >
                  <Icon className="h-4 w-4" />
                </NavLink>
              );
            })}
          </div>
          <div className="ml-auto flex min-w-0 items-center gap-3">
            <Badge tone={healthStatus === "ok" ? "success" : healthStatus === "checking" ? "info" : "danger"}>
              {healthStatus}
            </Badge>
            <span className="hidden max-w-56 truncate text-sm text-muted sm:inline">{email}</span>
            <Button variant="ghost" icon={<LogOut className="h-4 w-4" />} onClick={logout}>
              Logout
            </Button>
          </div>
        </header>

        <main className="mx-auto max-w-7xl space-y-6 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
