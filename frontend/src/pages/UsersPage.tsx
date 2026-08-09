import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, UserCheck, UserPlus, UserX } from "lucide-react";
import { useMemo, useState } from "react";

import { getErrorMessage } from "../api/client";
import { createUser, listUsers, updateUserActivation } from "../api/users";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { ErrorState, LoadingState } from "../components/ui/StatusState";
import { useAuth } from "../hooks/useAuth";
import type { ManagedUser } from "../types/api";
import { formatDateTime } from "../utils/format";


export function UsersPage() {
  const queryClient = useQueryClient();
  const { email: currentEmail } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: async (user) => {
      setEmail("");
      setPassword("");
      setIsActive(true);
      setMessage(`Created ${user.email}`);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const activationMutation = useMutation({
    mutationFn: ({
      userId,
      nextIsActive,
    }: {
      userId: number;
      nextIsActive: boolean;
    }) => updateUserActivation(userId, { is_active: nextIsActive }),
    onSuccess: async (user) => {
      setMessage(`${user.email} ${user.is_active ? "activated" : "deactivated"}`);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const users = usersQuery.data ?? [];
  const filteredUsers = useMemo(
    () => filterUsers(users, search),
    [search, users],
  );
  const operationError = createMutation.error || activationMutation.error;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users"
        description="Create and activate Knowledge Base users."
      />

      {message ? <Badge tone="success">{message}</Badge> : null}
      {operationError ? (
        <ErrorState
          title="User operation failed"
          detail={getErrorMessage(operationError, "Unable to update users.")}
        />
      ) : null}
      {usersQuery.error ? (
        <ErrorState
          title="User list failed"
          detail={getErrorMessage(usersQuery.error, "Unable to load users.")}
        />
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Panel>
          <PanelHeader title="Create User" />
          <form
            className="space-y-4 p-4"
            onSubmit={(event) => {
              event.preventDefault();
              createMutation.mutate({
                email: email.trim(),
                password,
                is_active: isActive,
              });
            }}
          >
            <label className="block space-y-1">
              <span className="form-label">Email</span>
              <input
                className="form-input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="analyst@example.com"
                required
              />
            </label>
            <label className="block space-y-1">
              <span className="form-label">Temporary Password</span>
              <input
                className="form-input"
                type="password"
                value={password}
                minLength={12}
                maxLength={256}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="h-4 w-4 rounded border-border text-accent"
                type="checkbox"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
              />
              <span>Active</span>
            </label>
            <Button
              type="submit"
              icon={<UserPlus className="h-4 w-4" />}
              isLoading={createMutation.isPending}
            >
              Create User
            </Button>
          </form>
        </Panel>

        <Panel>
          <PanelHeader
            title="User Directory"
            actions={
              <label className="relative">
                <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted" />
                <input
                  className="form-input w-64 pl-8"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search users"
                />
              </label>
            }
          />

          {usersQuery.isLoading ? (
            <div className="p-4">
              <LoadingState label="Loading users" />
            </div>
          ) : null}

          {!usersQuery.isLoading && !usersQuery.error && filteredUsers.length === 0 ? (
            <div className="p-4 text-sm text-muted">No users found.</div>
          ) : null}

          {filteredUsers.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Updated</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredUsers.map((user) => {
                    const nextIsActive = !user.is_active;
                    const isCurrentSessionUser = user.email === currentEmail;
                    return (
                      <tr key={user.id}>
                        <td className="font-mono text-xs text-muted">#{user.id}</td>
                        <td className="max-w-80 truncate font-medium">{user.email}</td>
                        <td><UserStatusBadge isActive={user.is_active} /></td>
                        <td>{formatDateTime(user.created_at)}</td>
                        <td>{formatDateTime(user.updated_at)}</td>
                        <td>
                          <Button
                            variant="secondary"
                            icon={
                              nextIsActive ? (
                                <UserCheck className="h-4 w-4" />
                              ) : (
                                <UserX className="h-4 w-4" />
                              )
                            }
                            disabled={user.is_active && isCurrentSessionUser}
                            isLoading={activationMutation.isPending}
                            onClick={() => {
                              if (
                                !nextIsActive &&
                                !window.confirm(`Deactivate ${user.email}?`)
                              ) {
                                return;
                              }

                              activationMutation.mutate({
                                userId: user.id,
                                nextIsActive,
                              });
                            }}
                          >
                            {nextIsActive ? "Activate" : "Deactivate"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </Panel>
      </section>
    </div>
  );
}


function UserStatusBadge({ isActive }: { isActive: boolean }) {
  return (
    <Badge tone={isActive ? "success" : "neutral"}>
      {isActive ? "Active" : "Inactive"}
    </Badge>
  );
}


function filterUsers(users: ManagedUser[], search: string): ManagedUser[] {
  const normalizedSearch = search.trim().toLowerCase();
  if (!normalizedSearch) {
    return users;
  }

  return users.filter((user) => (
    user.email.toLowerCase().includes(normalizedSearch) ||
    String(user.id).includes(normalizedSearch)
  ));
}
