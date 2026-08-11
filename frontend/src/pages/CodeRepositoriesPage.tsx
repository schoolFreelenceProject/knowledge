import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Code2, FolderUp, GitBranch, RefreshCw, Search, Trash2, UploadCloud } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  deleteCodeRepository,
  getCodeRepository,
  grantCodeRepositoryPermission,
  ingestCodeRepository,
  listCodeRepositories,
  listCodeRepositoryPermissions,
  reindexCodeRepository,
  revokeCodeRepositoryPermission,
  uploadCodeFolder,
} from "../api/code";
import type { CodeFolderUploadFile } from "../api/code";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import { StatCard } from "../components/ui/StatCard";
import type { CodeIngestResponse, CodeRepositorySummary } from "../types/api";
import { compactHash, formatDateTime, formatNumber } from "../utils/format";

type CodeFolderSelection = {
  folderName: string;
  files: CodeFolderUploadFile[];
};

export function CodeRepositoriesPage() {
  const queryClient = useQueryClient();
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null);
  const [permissionUserId, setPermissionUserId] = useState("");
  const [folderSelection, setFolderSelection] = useState<CodeFolderSelection | null>(null);
  const [folderUploadProgress, setFolderUploadProgress] = useState(0);
  const [lastResult, setLastResult] = useState<CodeIngestResponse | null>(null);
  const [message, setMessage] = useState("");

  const repositoriesQuery = useQuery({
    queryKey: ["code-repositories"],
    queryFn: listCodeRepositories,
  });

  const detailQuery = useQuery({
    queryKey: ["code-repositories", selectedRepositoryId],
    queryFn: () => getCodeRepository(selectedRepositoryId as number),
    enabled: selectedRepositoryId !== null,
  });

  const permissionsQuery = useQuery({
    queryKey: ["code-repositories", selectedRepositoryId, "permissions"],
    queryFn: () => listCodeRepositoryPermissions(selectedRepositoryId as number),
    enabled: selectedRepositoryId !== null,
  });

  const ingestMutation = useMutation({
    mutationFn: ingestCodeRepository,
    onSuccess: async (response) => {
      setLastResult(response);
      setMessage(sourceResultMessage(response));
      setSelectedRepositoryId(response.repository_id);
      await queryClient.invalidateQueries({ queryKey: ["code-repositories"] });
      await queryClient.invalidateQueries({
        queryKey: ["code-repositories", response.repository_id],
      });
    },
  });

  const folderUploadMutation = useMutation({
    mutationFn: (selection: CodeFolderSelection) =>
      uploadCodeFolder(selection.folderName, selection.files, (event) => {
        if (event.total) {
          setFolderUploadProgress(Math.round((event.loaded / event.total) * 100));
        }
      }),
    onMutate: () => {
      setLastResult(null);
      setFolderUploadProgress(0);
    },
    onSuccess: async (response) => {
      setLastResult(response);
      setFolderUploadProgress(100);
      setMessage(sourceResultMessage(response));
      setSelectedRepositoryId(response.repository_id);
      await queryClient.invalidateQueries({ queryKey: ["code-repositories"] });
      await queryClient.invalidateQueries({
        queryKey: ["code-repositories", response.repository_id],
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCodeRepository,
    onSuccess: async () => {
      setMessage("Repository deleted");
      setSelectedRepositoryId(null);
      await queryClient.invalidateQueries({ queryKey: ["code-repositories"] });
    },
  });

  const reindexMutation = useMutation({
    mutationFn: reindexCodeRepository,
    onSuccess: async (response) => {
      setMessage(`Reindexed ${formatNumber(response.chunks)} code chunks`);
      await queryClient.invalidateQueries({ queryKey: ["code-repositories"] });
      await queryClient.invalidateQueries({
        queryKey: ["code-repositories", selectedRepositoryId],
      });
    },
  });

  const grantPermissionMutation = useMutation({
    mutationFn: (userId: number) =>
      grantCodeRepositoryPermission(selectedRepositoryId as number, userId),
    onSuccess: async () => {
      setPermissionUserId("");
      await queryClient.invalidateQueries({
        queryKey: ["code-repositories", selectedRepositoryId, "permissions"],
      });
    },
  });

  const revokePermissionMutation = useMutation({
    mutationFn: (userId: number) =>
      revokeCodeRepositoryPermission(selectedRepositoryId as number, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["code-repositories", selectedRepositoryId, "permissions"],
      });
    },
  });

  const repositories = repositoriesQuery.data ?? [];
  const filteredRepositories = useMemo(
    () => filterRepositories(repositories, search, status),
    [repositories, search, status],
  );
  const mutationError =
    ingestMutation.error ||
    folderUploadMutation.error ||
    deleteMutation.error ||
    reindexMutation.error ||
    grantPermissionMutation.error ||
    revokePermissionMutation.error;

  function handleFolderSelection(files: FileList | null) {
    const selection = buildCodeFolderSelection(files);
    if (!selection) {
      return;
    }

    setFolderSelection(selection);
    folderUploadMutation.mutate(selection);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Code Repositories"
        description="Manage indexed source code repositories and repository access."
      />

      {message ? <Badge tone="success">{message}</Badge> : null}
      {mutationError ? (
        <ErrorState
          title="Repository operation failed"
          detail={getErrorMessage(mutationError, "Unable to complete repository operation.")}
        />
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(420px,0.9fr)]">
        <Panel>
          <PanelHeader
            title="Repository Inventory"
            actions={
              <form
                className="flex flex-wrap items-center gap-2"
                onSubmit={(event) => event.preventDefault()}
              >
                <label className="relative">
                  <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted" />
                  <input
                    className="form-input w-64 pl-8"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search repository"
                  />
                </label>
                <select
                  className="form-input w-36"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="">All status</option>
                  <option value="PROCESSING">Processing</option>
                  <option value="INDEXED">Indexed</option>
                  <option value="FAILED">Failed</option>
                </select>
              </form>
            }
          />
          <div className="space-y-3 border-b border-border p-4">
            <form
              className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_160px_auto]"
              onSubmit={(event) => {
                event.preventDefault();
                ingestMutation.mutate({
                  repo_url: repoUrl.trim(),
                  branch: branch.trim() || "main",
                });
              }}
            >
              <input
                className="form-input"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/company/repository.git"
                required
              />
              <input
                className="form-input"
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                required
              />
              <Button
                type="submit"
                icon={<UploadCloud className="h-4 w-4" />}
                isLoading={ingestMutation.isPending}
              >
                Ingest
              </Button>
            </form>

            <div className="flex flex-wrap items-center gap-3 text-sm">
              <input
                ref={(node) => {
                  folderInputRef.current = node;
                  if (node) {
                    node.setAttribute("webkitdirectory", "");
                    node.setAttribute("directory", "");
                  }
                }}
                className="hidden"
                type="file"
                multiple
                onChange={(event) => {
                  handleFolderSelection(event.target.files);
                  event.target.value = "";
                }}
              />
              <Button
                type="button"
                variant="secondary"
                icon={<FolderUp className="h-4 w-4" />}
                isLoading={folderUploadMutation.isPending}
                onClick={() => folderInputRef.current?.click()}
              >
                Upload Code Folder
              </Button>
              {folderUploadMutation.isPending ? <Badge tone="info">Uploading</Badge> : null}
            </div>

            {folderSelection ? (
              <div className="space-y-2 rounded-md border border-border bg-slate-50 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">Folder: {folderSelection.folderName}</span>
                  <span className="text-muted">
                    Files discovered: {formatNumber(folderSelection.files.length)}
                  </span>
                </div>
                {folderUploadMutation.isPending ? (
                  <div className="space-y-1">
                    <div className="h-2 w-full overflow-hidden rounded-sm bg-white">
                      <div
                        className="h-full bg-accent transition-[width]"
                        style={{ width: `${folderUploadProgress}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted">
                      <span>
                        {folderUploadProgress >= 100 ? "Ingesting files" : "Uploading"}
                      </span>
                      <span>{folderUploadProgress}%</span>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {repositoriesQuery.isLoading ? <div className="p-4"><LoadingState /></div> : null}
          {repositoriesQuery.error ? (
            <div className="p-4">
              <ErrorState
                title="Repositories failed"
                detail={getErrorMessage(
                  repositoriesQuery.error,
                  "Unable to load code repositories.",
                )}
              />
            </div>
          ) : null}
          {!repositoriesQuery.isLoading && filteredRepositories.length === 0 ? (
            <div className="p-4">
              <EmptyState title="No matching repositories" />
            </div>
          ) : null}
          {filteredRepositories.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Repository</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Branch</th>
                    <th>Files</th>
                    <th>Chunks</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredRepositories.map((repository) => (
                    <tr
                      key={repository.id}
                      className="cursor-pointer hover:bg-slate-50"
                      onClick={() => setSelectedRepositoryId(repository.id)}
                    >
                      <td className="max-w-72 truncate font-medium">{repository.repo_name}</td>
                      <td>{sourceTypeLabel(repository.source_type)}</td>
                      <td><RepositoryStatusBadge status={repository.status} /></td>
                      <td>{repository.branch ?? "Not applicable"}</td>
                      <td>{formatNumber(repository.file_count)}</td>
                      <td>{formatNumber(repository.chunk_count)}</td>
                      <td>{formatDateTime(repository.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Panel>

        <Panel>
          <PanelHeader
            title="Repository Detail"
            description={selectedRepositoryId ? `Repository ID ${selectedRepositoryId}` : undefined}
            actions={
              selectedRepositoryId ? (
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    icon={<RefreshCw className="h-4 w-4" />}
                    isLoading={reindexMutation.isPending}
                    onClick={() => reindexMutation.mutate(selectedRepositoryId)}
                  >
                    Reindex
                  </Button>
                  <Button
                    variant="danger"
                    icon={<Trash2 className="h-4 w-4" />}
                    isLoading={deleteMutation.isPending}
                    onClick={() => {
                      if (window.confirm("Delete this repository index?")) {
                        deleteMutation.mutate(selectedRepositoryId);
                      }
                    }}
                  >
                    Delete
                  </Button>
                </div>
              ) : null
            }
          />
          <div className="space-y-5 p-4">
            {!selectedRepositoryId ? <EmptyState title="Select a repository" /> : null}
            {detailQuery.isLoading ? <LoadingState label="Loading repository detail" /> : null}
            {detailQuery.error ? (
              <ErrorState
                title="Repository detail failed"
                detail={getErrorMessage(
                  detailQuery.error,
                  "Unable to load repository detail.",
                )}
              />
            ) : null}
            {detailQuery.data ? (
              <>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <Detail label="Name" value={detailQuery.data.repo_name} />
                  <Detail label="Source" value={sourceTypeLabel(detailQuery.data.source_type)} />
                  <Detail label="Branch" value={detailQuery.data.branch ?? "Not applicable"} />
                  <Detail label="Status" value={detailQuery.data.status} />
                  <Detail
                    label="Revision"
                    value={
                      detailQuery.data.commit_sha
                        ? compactHash(detailQuery.data.commit_sha, 12)
                        : compactHash(detailQuery.data.source_fingerprint ?? "", 12) || "Not applicable"
                    }
                  />
                  <Detail label="Storage" value={detailQuery.data.storage_path} />
                  <Detail label="Updated" value={formatDateTime(detailQuery.data.updated_at)} />
                </dl>

                <section>
                  <h3 className="mb-2 text-sm font-semibold">Files</h3>
                  <div className="max-h-56 overflow-auto rounded-md border border-border">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Path</th>
                          <th>Language</th>
                          <th>Chunks</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {detailQuery.data.files.map((file) => (
                          <tr key={file.id}>
                            <td className="max-w-64 truncate">{file.file_path}</td>
                            <td>{file.language}</td>
                            <td>{formatNumber(file.chunk_count)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section>
                  <h3 className="mb-2 text-sm font-semibold">Permissions</h3>
                  <form
                    className="mb-3 flex gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const userId = Number(permissionUserId);
                      if (Number.isInteger(userId) && userId > 0) {
                        grantPermissionMutation.mutate(userId);
                      }
                    }}
                  >
                    <input
                      className="form-input"
                      value={permissionUserId}
                      onChange={(event) => setPermissionUserId(event.target.value)}
                      placeholder="User ID"
                      inputMode="numeric"
                    />
                    <Button type="submit" isLoading={grantPermissionMutation.isPending}>
                      Grant
                    </Button>
                  </form>
                  {permissionsQuery.isLoading ? <LoadingState label="Loading permissions" /> : null}
                  {(permissionsQuery.data ?? []).length ? (
                    <div className="space-y-2">
                      {(permissionsQuery.data ?? []).map((permission) => (
                        <div
                          key={permission.id}
                          className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
                        >
                          <span>User #{permission.user_id}</span>
                          <Button
                            variant="ghost"
                            onClick={() => revokePermissionMutation.mutate(permission.user_id)}
                          >
                            Revoke
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted">No permission rows returned.</p>
                  )}
                </section>
              </>
            ) : null}
          </div>
        </Panel>
      </section>

      {lastResult ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Latest Repository"
            value={lastResult.repo_name}
            hint={`ID ${lastResult.repository_id}`}
            icon={<Code2 className="h-5 w-5" />}
          />
          <StatCard
            label="Source"
            value={sourceTypeLabel(lastResult.source_type)}
            hint={
              lastResult.commit_sha
                ? compactHash(lastResult.commit_sha, 10)
                : compactHash(lastResult.source_fingerprint ?? "", 10) || "Uploaded folder"
            }
            icon={<GitBranch className="h-5 w-5" />}
          />
          <StatCard
            label="Files"
            value={formatNumber(lastResult.files)}
            hint={`${formatNumber(lastResult.chunks)} chunks`}
          />
          <StatCard
            label="Vectors"
            value={formatNumber(lastResult.stored_vectors)}
            hint={
              lastResult.skipped_files
                ? `${formatNumber(lastResult.skipped_files)} skipped`
                : lastResult.collection_name
            }
          />
        </section>
      ) : null}

      {lastResult?.skip_reasons && Object.keys(lastResult.skip_reasons).length > 0 ? (
        <Panel>
          <PanelHeader title="Latest Upload Skips" />
          <div className="grid gap-2 p-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(lastResult.skip_reasons).map(([reason, count]) => (
              <div
                key={reason}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              >
                <span>{skipReasonLabel(reason)}</span>
                <span className="font-medium">{formatNumber(count)}</span>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function filterRepositories(
  repositories: CodeRepositorySummary[],
  search: string,
  status: string,
): CodeRepositorySummary[] {
  const normalizedSearch = search.trim().toLowerCase();
  return repositories.filter((repository) => {
    const searchMatches =
      !normalizedSearch ||
      repository.repo_name.toLowerCase().includes(normalizedSearch) ||
      (repository.repo_url ?? "").toLowerCase().includes(normalizedSearch) ||
      repository.storage_path.toLowerCase().includes(normalizedSearch);
    const statusMatches = !status || repository.status === status;
    return searchMatches && statusMatches;
  });
}

function buildCodeFolderSelection(fileList: FileList | null): CodeFolderSelection | null {
  const browserFiles = Array.from(fileList ?? []);
  if (!browserFiles.length) {
    return null;
  }

  const folderName = inferFolderName(browserFiles[0]);
  const files = browserFiles
    .map((file) => ({
      file,
      relativePath: stripRootFolder(file.webkitRelativePath || file.name),
    }))
    .filter((item) => item.relativePath);

  if (!files.length) {
    return null;
  }

  return { folderName, files };
}

function inferFolderName(file: File): string {
  const path = (file.webkitRelativePath || file.name).replace(/\\/g, "/");
  const firstPart = path.split("/").find(Boolean);
  return firstPart || "UploadedCode";
}

function stripRootFolder(path: string): string {
  const parts = path
    .replace(/\\/g, "/")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean);

  if (parts.length > 1) {
    return parts.slice(1).join("/");
  }

  return parts.join("/");
}

function sourceTypeLabel(sourceType: string): string {
  return sourceType === "LOCAL_FOLDER" ? "Uploaded Folder" : "Git Repository";
}

function sourceResultMessage(response: CodeIngestResponse): string {
  if (response.message) {
    return response.message;
  }

  if (response.already_indexed) {
    return response.source_type === "LOCAL_FOLDER"
      ? "This code folder is already indexed."
      : "This revision is already indexed.";
  }
  if (response.recovered) {
    return response.source_type === "LOCAL_FOLDER"
      ? `Recovered and indexed ${response.repo_name}`
      : `Recovered and indexed ${response.repo_name}`;
  }

  return response.source_type === "LOCAL_FOLDER"
    ? `Indexed code folder ${response.repo_name}`
    : `Indexed ${response.repo_name}`;
}

function skipReasonLabel(reason: string): string {
  return reason
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="form-label">{label}</dt>
      <dd className="mt-1 truncate text-ink">{value}</dd>
    </div>
  );
}

function RepositoryStatusBadge({ status }: { status: string }) {
  const tone = status === "INDEXED" ? "success" : status === "FAILED" ? "danger" : "warning";
  return <Badge tone={tone}>{status}</Badge>;
}
