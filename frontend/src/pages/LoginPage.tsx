import { useMutation } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { getErrorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { ErrorState } from "../components/ui/StatusState";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { isAuthenticated, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [errorMessage, setErrorMessage] = useState("");

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;

  const authMutation = useMutation({
    mutationFn: async () => {
      const credentials = { email: email.trim().toLowerCase(), password };
      if (mode === "register") {
        await register(credentials);
        return;
      }

      await login(credentials);
    },
    onSuccess: () => {
      setErrorMessage("");
      navigate(from || "/dashboard", { replace: true });
    },
    onError: (error) => {
      setErrorMessage(getErrorMessage(error, "Authentication failed."));
    },
  });

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <section className="w-full max-w-md rounded-lg border border-border bg-white p-6 shadow-panel">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-ink text-white">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-ink">Knowledge Base Admin</h1>
            <p className="text-sm text-muted">Sign in with your account.</p>
          </div>
        </div>

        {errorMessage ? (
          <div className="mt-5">
            <ErrorState title="Authentication failed" detail={errorMessage} />
          </div>
        ) : null}

        <form
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            authMutation.mutate();
          }}
        >
          <label className="block space-y-1">
            <span className="form-label">Email</span>
            <input
              className="form-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="form-label">Password</span>
            <input
              className="form-input"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={mode === "register" ? 12 : 1}
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="submit"
              icon={<KeyRound className="h-4 w-4" />}
              isLoading={authMutation.isPending}
            >
              {mode === "login" ? "Login" : "Register"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setErrorMessage("");
              }}
            >
              {mode === "login" ? "Create Account" : "Use Login"}
            </Button>
          </div>
        </form>
      </section>
    </main>
  );
}
