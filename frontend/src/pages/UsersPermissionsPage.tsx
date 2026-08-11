import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Code2, ShieldCheck, UserPlus } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import {
  grantCodeRepositoryPermission,
  listCodeRepositories,
  listCodeRepositoryPermissions,
  revokeCodeRepositoryPermission,
} from "../api/code";
import { getErrorMessage } from "../api/client";
import { listDocuments } from "../api/documents";
import {
  grantDocumentUserPermission,
  grantUserCodeRepositoryPermission,
  grantUserDocumentPermission,
  listDocumentUserPermissions,
  listUserCodeRepositoryPermissions,
  listUserDocumentPermissions,
  revokeDocumentUserPermission,
  revokeUserCodeRepositoryPermission,
  revokeUserDocumentPermission,
} from "../api/permissions";
import { listUsers } from "../api/users";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import type {
  CodeRepositoryPermissionResponse,
  DocumentPermissionResponse,
} from "../types/api";
import { compactHash, formatDateTime } from "../utils/format";

export function UsersPermissionsPage() {
  const queryClient = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [userDocumentGrantId, setUserDocumentGrantId] = useState("");
  const [userRepositoryGrantId, setUserRepositoryGrantId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null);
  const [documentUserGrantId, setDocumentUserGrantId] = useState("");
  const [repositoryUserGrantId, setRepositoryUserGrantId] = useState("");

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });
  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });
  const repositoriesQuery = useQuery({
    queryKey: ["code-repositories"],
    queryFn: listCodeRepositories,
  });

  const userDocumentPermissionsQuery = useQuery({
    queryKey: ["admin-permissions", "users", selectedUserId, "documents"],
    queryFn: () => listUserDocumentPermissions(selectedUserId as number),
    enabled: selectedUserId !== null,
  });
  const userRepositoryPermissionsQuery = useQuery({
    queryKey: ["admin-permissions", "users", selectedUserId, "code-repositories"],
    queryFn: () => listUserCodeRepositoryPermissions(selectedUserId as number),
    enabled: selectedUserId !== null,
  });
  const documentUsersQuery = useQuery({
    queryKey: ["documents", selectedDocumentId, "permissions"],
    queryFn: () => listDocumentUserPermissions(selectedDocumentId as number),
    enabled: selectedDocumentId !== null,
  });
  const repositoryUsersQuery = useQuery({
    queryKey: ["code-repositories", selectedRepositoryId, "permissions"],
    queryFn: () => listCodeRepositoryPermissions(selectedRepositoryId as number),
    enabled: selectedRepositoryId !== null,
  });

  const usersById = useMemo(
    () => new Map((usersQuery.data ?? []).map((user) => [user.id, user])),
    [usersQuery.data],
  );
  const documentsById = useMemo(
    () => new Map((documentsQuery.data ?? []).map((document) => [document.id, document])),
    [documentsQuery.data],
  );
  const repositoriesById = useMemo(
    () =>
      new Map(
        (repositoriesQuery.data ?? []).map((repository) => [repository.id, repository]),
      ),
    [repositoriesQuery.data],
  );

  const grantUserDocumentMutation = useMutation({
    mutationFn: (documentId: number) =>
      grantUserDocumentPermission(selectedUserId as number, documentId),
    onSuccess: async () => {
      setUserDocumentGrantId("");
      await invalidateUserPermissions(queryClient, selectedUserId);
    },
  });
  const revokeUserDocumentMutation = useMutation({
    mutationFn: (documentId: number) =>
      revokeUserDocumentPermission(selectedUserId as number, documentId),
    onSuccess: async () => invalidateUserPermissions(queryClient, selectedUserId),
  });
  const grantUserRepositoryMutation = useMutation({
    mutationFn: (repositoryId: number) =>
      grantUserCodeRepositoryPermission(selectedUserId as number, repositoryId),
    onSuccess: async () => {
      setUserRepositoryGrantId("");
      await invalidateUserPermissions(queryClient, selectedUserId);
    },
  });
  const revokeUserRepositoryMutation = useMutation({
    mutationFn: (repositoryId: number) =>
      revokeUserCodeRepositoryPermission(selectedUserId as number, repositoryId),
    onSuccess: async () => invalidateUserPermissions(queryClient, selectedUserId),
  });

  const grantDocumentUserMutation = useMutation({
    mutationFn: (userId: number) =>
      grantDocumentUserPermission(selectedDocumentId as number, userId),
    onSuccess: async () => {
      setDocumentUserGrantId("");
      await invalidateResourcePermissions(queryClient, selectedDocumentId, selectedRepositoryId);
    },
  });
  const revokeDocumentUserMutation = useMutation({
    mutationFn: (userId: number) =>
      revokeDocumentUserPermission(selectedDocumentId as number, userId),
    onSuccess: async () =>
      invalidateResourcePermissions(queryClient, selectedDocumentId, selectedRepositoryId),
  });
  const grantRepositoryUserMutation = useMutation({
    mutationFn: (userId: number) =>
      grantCodeRepositoryPermission(selectedRepositoryId as number, userId),
    onSuccess: async () => {
      setRepositoryUserGrantId("");
      await invalidateResourcePermissions(queryClient, selectedDocumentId, selectedRepositoryId);
    },
  });
  const revokeRepositoryUserMutation = useMutation({
    mutationFn: (userId: number) =>
      revokeCodeRepositoryPermission(selectedRepositoryId as number, userId),
    onSuccess: async () =>
      invalidateResourcePermissions(queryClient, selectedDocumentId, selectedRepositoryId),
  });

  const isLoading =
    usersQuery.isLoading || documentsQuery.isLoading || repositoriesQuery.isLoading;
  const error =
    usersQuery.error ||
    documentsQuery.error ||
    repositoriesQuery.error ||
    userDocumentPermissionsQuery.error ||
    userRepositoryPermissionsQuery.error ||
    documentUsersQuery.error ||
    repositoryUsersQuery.error ||
    grantUserDocumentMutation.error ||
    revokeUserDocumentMutation.error ||
    grantUserRepositoryMutation.error ||
    revokeUserRepositoryMutation.error ||
    grantDocumentUserMutation.error ||
    revokeDocumentUserMutation.error ||
    grantRepositoryUserMutation.error ||
    revokeRepositoryUserMutation.error;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Permissions"
        description="Manage user access to documents and code repositories."
      />

      {isLoading ? <LoadingState label="Loading permission controls" /> : null}
      {error ? (
        <ErrorState
          title="Permission operation failed"
          detail={getErrorMessage(error, "Unable to load or update permissions.")}
        />
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <Panel>
          <PanelHeader
            title="User Access"
            description="Select a user and manage their accessible resources."
          />
          <div className="space-y-5 p-4">
            <label className="block space-y-1">
              <span className="form-label">User</span>
              <select
                className="form-input"
                value={selectedUserId ?? ""}
                onChange={(event) => setSelectedUserId(parsePositiveId(event.target.value))}
              >
                <option value="">Select user</option>
                {(usersQuery.data ?? []).map((user) => (
                  <option key={user.id} value={user.id}>
                    #{user.id} {user.email}
                  </option>
                ))}
              </select>
            </label>

            {!selectedUserId ? <EmptyState title="Select a user" /> : null}
            {selectedUserId ? (
              <div className="grid gap-5 lg:grid-cols-2">
                <PermissionBlock
                  title="Documents"
                  icon={<BookOpen className="h-4 w-4" />}
                  grantValue={userDocumentGrantId}
                  onGrantValueChange={setUserDocumentGrantId}
                  grantOptions={(documentsQuery.data ?? []).map((document) => ({
                    id: document.id,
                    label: `#${document.id} ${document.filename}`,
                  }))}
                  onGrant={(id) => grantUserDocumentMutation.mutate(id)}
                  grantLoading={grantUserDocumentMutation.isPending}
                >
                  <DocumentPermissionTable
                    permissions={userDocumentPermissionsQuery.data ?? []}
                    documentsById={documentsById}
                    usersById={usersById}
                    showResource
                    onRevoke={(documentId) => revokeUserDocumentMutation.mutate(documentId)}
                    revokeLoading={revokeUserDocumentMutation.isPending}
                  />
                </PermissionBlock>

                <PermissionBlock
                  title="Code Repositories"
                  icon={<Code2 className="h-4 w-4" />}
                  grantValue={userRepositoryGrantId}
                  onGrantValueChange={setUserRepositoryGrantId}
                  grantOptions={(repositoriesQuery.data ?? []).map((repository) => ({
                    id: repository.id,
                    label: `#${repository.id} ${repository.repo_name}`,
                  }))}
                  onGrant={(id) => grantUserRepositoryMutation.mutate(id)}
                  grantLoading={grantUserRepositoryMutation.isPending}
                >
                  <RepositoryPermissionTable
                    permissions={userRepositoryPermissionsQuery.data ?? []}
                    repositoriesById={repositoriesById}
                    usersById={usersById}
                    showResource
                    onRevoke={(repositoryId) => revokeUserRepositoryMutation.mutate(repositoryId)}
                    revokeLoading={revokeUserRepositoryMutation.isPending}
                  />
                </PermissionBlock>
              </div>
            ) : null}
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Resource Access"
            description="Select a document or repository and view users with access."
          />
          <div className="space-y-6 p-4">
            <section className="space-y-3">
              <label className="block space-y-1">
                <span className="form-label">Document</span>
                <select
                  className="form-input"
                  value={selectedDocumentId ?? ""}
                  onChange={(event) => setSelectedDocumentId(parsePositiveId(event.target.value))}
                >
                  <option value="">Select document</option>
                  {(documentsQuery.data ?? []).map((document) => (
                    <option key={document.id} value={document.id}>
                      #{document.id} {document.filename}
                    </option>
                  ))}
                </select>
              </label>
              {selectedDocumentId ? (
                <PermissionBlock
                  title="Document Users"
                  icon={<BookOpen className="h-4 w-4" />}
                  grantValue={documentUserGrantId}
                  onGrantValueChange={setDocumentUserGrantId}
                  grantOptions={(usersQuery.data ?? []).map((user) => ({
                    id: user.id,
                    label: `#${user.id} ${user.email}`,
                  }))}
                  onGrant={(id) => grantDocumentUserMutation.mutate(id)}
                  grantLoading={grantDocumentUserMutation.isPending}
                >
                  <DocumentPermissionTable
                    permissions={documentUsersQuery.data ?? []}
                    documentsById={documentsById}
                    usersById={usersById}
                    onRevoke={(userId) => revokeDocumentUserMutation.mutate(userId)}
                    revokeLoading={revokeDocumentUserMutation.isPending}
                  />
                </PermissionBlock>
              ) : (
                <EmptyState title="Select a document" />
              )}
            </section>

            <section className="space-y-3">
              <label className="block space-y-1">
                <span className="form-label">Code Repository</span>
                <select
                  className="form-input"
                  value={selectedRepositoryId ?? ""}
                  onChange={(event) => setSelectedRepositoryId(parsePositiveId(event.target.value))}
                >
                  <option value="">Select repository</option>
                  {(repositoriesQuery.data ?? []).map((repository) => (
                    <option key={repository.id} value={repository.id}>
                      #{repository.id} {repository.repo_name}
                    </option>
                  ))}
                </select>
              </label>
              {selectedRepositoryId ? (
                <PermissionBlock
                  title="Repository Users"
                  icon={<Code2 className="h-4 w-4" />}
                  grantValue={repositoryUserGrantId}
                  onGrantValueChange={setRepositoryUserGrantId}
                  grantOptions={(usersQuery.data ?? []).map((user) => ({
                    id: user.id,
                    label: `#${user.id} ${user.email}`,
                  }))}
                  onGrant={(id) => grantRepositoryUserMutation.mutate(id)}
                  grantLoading={grantRepositoryUserMutation.isPending}
                >
                  <RepositoryPermissionTable
                    permissions={repositoryUsersQuery.data ?? []}
                    repositoriesById={repositoriesById}
                    usersById={usersById}
                    onRevoke={(userId) => revokeRepositoryUserMutation.mutate(userId)}
                    revokeLoading={revokeRepositoryUserMutation.isPending}
                  />
                </PermissionBlock>
              ) : (
                <EmptyState title="Select a repository" />
              )}
            </section>
          </div>
        </Panel>
      </section>
    </div>
  );
}

type GrantOption = {
  id: number;
  label: string;
};

function PermissionBlock({
  title,
  icon,
  grantValue,
  onGrantValueChange,
  grantOptions,
  onGrant,
  grantLoading,
  children,
}: {
  title: string;
  icon: ReactNode;
  grantValue: string;
  onGrantValueChange: (value: string) => void;
  grantOptions: GrantOption[];
  onGrant: (id: number) => void;
  grantLoading: boolean;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        <span>{title}</span>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const id = parsePositiveId(grantValue);
          if (id) {
            onGrant(id);
          }
        }}
      >
        <select
          className="form-input min-w-0"
          value={grantValue}
          onChange={(event) => onGrantValueChange(event.target.value)}
        >
          <option value="">Grant access</option>
          {grantOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        <Button
          type="submit"
          icon={<UserPlus className="h-4 w-4" />}
          isLoading={grantLoading}
        >
          Grant
        </Button>
      </form>
      {children}
    </section>
  );
}

function DocumentPermissionTable({
  permissions,
  documentsById,
  usersById,
  showResource = false,
  onRevoke,
  revokeLoading,
}: {
  permissions: DocumentPermissionResponse[];
  documentsById: Map<number, { filename: string }>;
  usersById: Map<number, { email: string }>;
  showResource?: boolean;
  onRevoke: (id: number) => void;
  revokeLoading: boolean;
}) {
  if (!permissions.length) {
    return <EmptyState title="No document permissions" />;
  }

  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            <th>{showResource ? "Document" : "User"}</th>
            <th>Granted</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {permissions.map((permission) => (
            <tr key={permission.id}>
              <td className="font-medium">
                <span className="inline-flex max-w-56 items-center gap-2 truncate">
                  <ShieldCheck className="h-4 w-4 shrink-0 text-muted" />
                  {showResource
                    ? documentsById.get(permission.document_id)?.filename ??
                      `Document #${permission.document_id}`
                    : usersById.get(permission.user_id)?.email ?? `User #${permission.user_id}`}
                </span>
              </td>
              <td>{formatDateTime(permission.created_at)}</td>
              <td>
                <Button
                  variant="ghost"
                  onClick={() => onRevoke(showResource ? permission.document_id : permission.user_id)}
                  isLoading={revokeLoading}
                >
                  Revoke
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RepositoryPermissionTable({
  permissions,
  repositoriesById,
  usersById,
  showResource = false,
  onRevoke,
  revokeLoading,
}: {
  permissions: CodeRepositoryPermissionResponse[];
  repositoriesById: Map<
    number,
    { repo_name: string; commit_sha: string | null; source_fingerprint: string | null }
  >;
  usersById: Map<number, { email: string }>;
  showResource?: boolean;
  onRevoke: (id: number) => void;
  revokeLoading: boolean;
}) {
  if (!permissions.length) {
    return <EmptyState title="No repository permissions" />;
  }

  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            <th>{showResource ? "Repository" : "User"}</th>
            <th>Granted</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {permissions.map((permission) => {
            const repository = repositoriesById.get(permission.repository_id);
            return (
              <tr key={permission.id}>
                <td className="font-medium">
                  <span className="inline-flex max-w-56 items-center gap-2 truncate">
                    <ShieldCheck className="h-4 w-4 shrink-0 text-muted" />
                    {showResource
                      ? repository
                        ? repositoryPermissionLabel(repository)
                        : `Repository #${permission.repository_id}`
                      : usersById.get(permission.user_id)?.email ?? `User #${permission.user_id}`}
                  </span>
                </td>
                <td>{formatDateTime(permission.created_at)}</td>
                <td>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      onRevoke(showResource ? permission.repository_id : permission.user_id)
                    }
                    isLoading={revokeLoading}
                  >
                    Revoke
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function repositoryPermissionLabel(repository: {
  repo_name: string;
  commit_sha: string | null;
  source_fingerprint: string | null;
}): string {
  const revision = repository.commit_sha ?? repository.source_fingerprint;
  if (!revision) {
    return repository.repo_name;
  }

  return `${repository.repo_name} ${compactHash(revision, 8)}`;
}

function parsePositiveId(value: string): number | null {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

async function invalidateUserPermissions(
  queryClient: ReturnType<typeof useQueryClient>,
  userId: number | null,
) {
  await queryClient.invalidateQueries({
    queryKey: ["admin-permissions", "users", userId],
  });
  await queryClient.invalidateQueries({ queryKey: ["documents"] });
  await queryClient.invalidateQueries({ queryKey: ["code-repositories"] });
}

async function invalidateResourcePermissions(
  queryClient: ReturnType<typeof useQueryClient>,
  documentId: number | null,
  repositoryId: number | null,
) {
  await queryClient.invalidateQueries({
    queryKey: ["documents", documentId, "permissions"],
  });
  await queryClient.invalidateQueries({
    queryKey: ["code-repositories", repositoryId, "permissions"],
  });
  await queryClient.invalidateQueries({ queryKey: ["admin-permissions"] });
}
