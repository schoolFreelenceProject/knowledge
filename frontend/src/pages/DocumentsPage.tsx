import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderUp, RefreshCw, Search, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { getErrorMessage } from "../api/client";
import {
  deleteDocument,
  getDocument,
  grantDocumentPermission,
  listDocumentPermissions,
  listDocuments,
  reindexDocument,
  revokeDocumentPermission,
  uploadDocument,
  uploadDocumentFolder,
} from "../api/documents";
import type { FolderUploadFile } from "../api/documents";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type {
  DocumentChunkDetail,
  DocumentSummary,
  FolderIngestResponse,
} from "../types/api";
import { compactHash, formatDateTime, formatNumber } from "../utils/format";

type FolderSelection = {
  folderName: string;
  files: FolderUploadFile[];
};

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [permissionUserId, setPermissionUserId] = useState("");
  const [folderSelection, setFolderSelection] = useState<FolderSelection | null>(null);
  const [folderUploadProgress, setFolderUploadProgress] = useState(0);
  const [folderResult, setFolderResult] = useState<FolderIngestResponse | null>(null);
  const [message, setMessage] = useState("");
  const debouncedSearch = useDebouncedValue(search);

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const detailQuery = useQuery({
    queryKey: ["documents", selectedDocumentId],
    queryFn: () => getDocument(selectedDocumentId as number),
    enabled: selectedDocumentId !== null,
  });

  const permissionsQuery = useQuery({
    queryKey: ["documents", selectedDocumentId, "permissions"],
    queryFn: () => listDocumentPermissions(selectedDocumentId as number),
    enabled: selectedDocumentId !== null,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: async (response) => {
      setMessage(`Uploaded ${response.filename}`);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      setSelectedDocumentId(response.document_id);
    },
  });

  const folderUploadMutation = useMutation({
    mutationFn: (selection: FolderSelection) =>
      uploadDocumentFolder(selection.folderName, selection.files, (event) => {
        if (event.total) {
          setFolderUploadProgress(Math.round((event.loaded / event.total) * 100));
        }
      }),
    onMutate: () => {
      setFolderResult(null);
      setFolderUploadProgress(0);
    },
    onSuccess: async (response) => {
      setFolderResult(response);
      setFolderUploadProgress(100);
      setMessage(
        `Folder ingestion complete: ${formatNumber(response.indexed)} indexed, ${formatNumber(
          response.skipped,
        )} skipped, ${formatNumber(response.failed)} failed`,
      );
      const firstSelectableResult = response.results.find((result) => result.document_id);
      if (firstSelectableResult?.document_id) {
        setSelectedDocumentId(firstSelectableResult.document_id);
      }
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      setMessage("Document deleted");
      setSelectedDocumentId(null);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const reindexMutation = useMutation({
    mutationFn: reindexDocument,
    onSuccess: async (response) => {
      setMessage(`Reindexed ${response.chunks} chunks`);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queryClient.invalidateQueries({ queryKey: ["documents", selectedDocumentId] });
    },
  });

  const grantPermissionMutation = useMutation({
    mutationFn: (userId: number) => grantDocumentPermission(selectedDocumentId as number, userId),
    onSuccess: async () => {
      setPermissionUserId("");
      await queryClient.invalidateQueries({
        queryKey: ["documents", selectedDocumentId, "permissions"],
      });
    },
  });

  const revokePermissionMutation = useMutation({
    mutationFn: (userId: number) =>
      revokeDocumentPermission(selectedDocumentId as number, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["documents", selectedDocumentId, "permissions"],
      });
    },
  });

  const documents = documentsQuery.data ?? [];
  const filteredDocuments = useMemo(
    () => filterDocuments(documents, debouncedSearch, status),
    [debouncedSearch, documents, status],
  );

  const mutationError =
    uploadMutation.error ||
    folderUploadMutation.error ||
    deleteMutation.error ||
    reindexMutation.error ||
    grantPermissionMutation.error ||
    revokePermissionMutation.error;

  function handleFolderSelection(files: FileList | null) {
    const selection = buildFolderSelection(files);
    if (!selection) {
      return;
    }

    setFolderSelection(selection);
    folderUploadMutation.mutate(selection);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="Manage uploaded knowledge documents and document access."
      />

      {message ? <Badge tone="success">{message}</Badge> : null}
      {mutationError ? (
        <ErrorState
          title="Document operation failed"
          detail={getErrorMessage(mutationError, "The document operation failed.")}
        />
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(420px,0.9fr)]">
        <Panel>
          <PanelHeader
            title="Document Inventory"
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
                    placeholder="Search filename"
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
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label className="flex flex-wrap items-center gap-3">
                <input
                  className="block text-sm"
                  type="file"
                  accept=".pdf,.md,.markdown,.docx,.xlsx,.pptx"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      uploadMutation.mutate(file);
                      event.target.value = "";
                    }
                  }}
                />
                {uploadMutation.isPending ? <Badge tone="info">Uploading</Badge> : null}
              </label>
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
                Upload Folder
              </Button>
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

            {folderResult ? <FolderIngestSummary result={folderResult} /> : null}
          </div>

          {documentsQuery.isLoading ? <div className="p-4"><LoadingState /></div> : null}
          {documentsQuery.error ? (
            <div className="p-4">
              <ErrorState
                title="Documents failed"
                detail={getErrorMessage(documentsQuery.error, "Unable to load documents.")}
              />
            </div>
          ) : null}
          {!documentsQuery.isLoading && filteredDocuments.length === 0 ? (
            <div className="p-4">
              <EmptyState title="No matching documents" />
            </div>
          ) : null}
          {filteredDocuments.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Status</th>
                    <th>Chunks</th>
                    <th>Updated</th>
                    <th>Hash</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredDocuments.map((document) => (
                    <tr
                      key={document.id}
                      className="cursor-pointer hover:bg-slate-50"
                      onClick={() => setSelectedDocumentId(document.id)}
                    >
                      <td className="max-w-72 truncate font-medium">{document.filename}</td>
                      <td><DocumentStatusBadge status={document.status} /></td>
                      <td>{formatNumber(document.chunk_count)}</td>
                      <td>{formatDateTime(document.updated_at)}</td>
                      <td className="font-mono text-xs text-muted">{compactHash(document.file_hash)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Panel>

        <Panel>
          <PanelHeader
            title="Document Detail"
            description={selectedDocumentId ? `Document ID ${selectedDocumentId}` : undefined}
            actions={
              selectedDocumentId ? (
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    icon={<RefreshCw className="h-4 w-4" />}
                    isLoading={reindexMutation.isPending}
                    onClick={() => reindexMutation.mutate(selectedDocumentId)}
                  >
                    Reindex
                  </Button>
                  <Button
                    variant="danger"
                    icon={<Trash2 className="h-4 w-4" />}
                    isLoading={deleteMutation.isPending}
                    onClick={() => {
                      if (window.confirm("Delete this document?")) {
                        deleteMutation.mutate(selectedDocumentId);
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
            {!selectedDocumentId ? <EmptyState title="Select a document" /> : null}
            {detailQuery.isLoading ? <LoadingState label="Loading document detail" /> : null}
            {detailQuery.error ? (
              <ErrorState
                title="Document detail failed"
                detail={getErrorMessage(detailQuery.error, "Unable to load document detail.")}
              />
            ) : null}
            {detailQuery.data ? (
              <>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <Detail label="Filename" value={detailQuery.data.filename} />
                  <Detail label="Type" value={detailQuery.data.file_type} />
                  <Detail label="Status" value={detailQuery.data.status} />
                  <Detail label="Storage" value={detailQuery.data.storage_path} />
                  <Detail label="Created" value={formatDateTime(detailQuery.data.created_at)} />
                  <Detail label="Updated" value={formatDateTime(detailQuery.data.updated_at)} />
                </dl>

                <section>
                  <h3 className="mb-2 text-sm font-semibold">Chunks</h3>
                  <div className="max-h-56 overflow-auto rounded-md border border-border">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Index</th>
                          <th>Location</th>
                          <th>Chars</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {detailQuery.data.chunks.map((chunk) => (
                          <tr key={chunk.id}>
                            <td>{chunk.chunk_index}</td>
                            <td>{documentChunkLocation(chunk)}</td>
                            <td>{chunk.start_char}-{chunk.end_char}</td>
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
    </div>
  );
}

function filterDocuments(
  documents: DocumentSummary[],
  search: string,
  status: string,
): DocumentSummary[] {
  const normalizedSearch = search.trim().toLowerCase();
  return documents.filter((document) => {
    const searchMatches =
      !normalizedSearch ||
      document.filename.toLowerCase().includes(normalizedSearch) ||
      document.storage_path.toLowerCase().includes(normalizedSearch);
    const statusMatches = !status || document.status === status;
    return searchMatches && statusMatches;
  });
}

function FolderIngestSummary({ result }: { result: FolderIngestResponse }) {
  const skippedOrFailed = result.results.filter((item) => item.status !== "indexed");

  return (
    <div className="space-y-3 rounded-md border border-border bg-white px-3 py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold">Folder: {result.folder_name}</span>
        <span className="text-muted">
          Files discovered: {formatNumber(result.files_discovered)}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <FolderSummaryCount label="Indexed" value={result.indexed} tone="success" />
        <FolderSummaryCount label="Skipped" value={result.skipped} tone="warning" />
        <FolderSummaryCount label="Failed" value={result.failed} tone="danger" />
      </div>
      {skippedOrFailed.length ? (
        <details className="rounded-md border border-border">
          <summary className="cursor-pointer px-3 py-2 font-medium">
            Skipped and failed files
          </summary>
          <div className="max-h-56 overflow-auto border-t border-border">
            <table className="data-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {skippedOrFailed.map((item) => (
                  <tr key={`${item.status}-${item.relative_path}`}>
                    <td className="max-w-72 truncate font-medium">{item.relative_path}</td>
                    <td>
                      <FolderResultBadge status={item.status} />
                    </td>
                    <td>{formatFolderReason(item.reason, item.message)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function FolderSummaryCount({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "warning" | "danger";
}) {
  return (
    <div className="min-w-0 rounded-md border border-border px-3 py-2">
      <div className="form-label">{label}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-base font-semibold">{formatNumber(value)}</span>
        <Badge tone={tone}>{label}</Badge>
      </div>
    </div>
  );
}

function FolderResultBadge({ status }: { status: "indexed" | "skipped" | "failed" }) {
  const tone = status === "indexed" ? "success" : status === "failed" ? "danger" : "warning";
  return <Badge tone={tone}>{status}</Badge>;
}

function formatFolderReason(reason: string | null, message: string | null): string {
  if (message) {
    return message;
  }
  if (!reason) {
    return "-";
  }

  return reason.replaceAll("_", " ");
}

function documentChunkLocation(chunk: DocumentChunkDetail): string {
  if (chunk.page_number) {
    return `Page ${chunk.page_number}`;
  }
  if (chunk.sheet_name) {
    const range = chunk.cell_range ? ` ${chunk.cell_range}` : "";
    return `${chunk.sheet_name}${range}`;
  }
  if (chunk.slide_number) {
    const title = chunk.slide_title ? `: ${chunk.slide_title}` : "";
    return `Slide ${chunk.slide_number}${title}`;
  }
  if (chunk.heading_path || chunk.section_heading) {
    return chunk.heading_path ?? chunk.section_heading ?? "-";
  }

  return chunk.block_kind ?? "-";
}

function buildFolderSelection(fileList: FileList | null): FolderSelection | null {
  const files = Array.from(fileList ?? []);
  if (!files.length) {
    return null;
  }

  const firstParts = splitBrowserPath(getBrowserRelativePath(files[0]));
  const folderName = firstParts.length > 1 ? firstParts[0] : "Selected folder";
  return {
    folderName,
    files: files.map((file) => ({
      file,
      relativePath: folderRelativePath(file),
    })),
  };
}

function folderRelativePath(file: File): string {
  const parts = splitBrowserPath(getBrowserRelativePath(file));
  if (parts.length <= 1) {
    return file.name;
  }

  return parts.slice(1).join("/") || file.name;
}

function getBrowserRelativePath(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

function splitBrowserPath(path: string): string[] {
  return path.replaceAll("\\", "/").split("/").filter(Boolean);
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="form-label">{label}</dt>
      <dd className="mt-1 truncate text-ink">{value}</dd>
    </div>
  );
}

function DocumentStatusBadge({ status }: { status: string }) {
  const tone = status === "INDEXED" ? "success" : status === "FAILED" ? "danger" : "warning";
  return <Badge tone={tone}>{status}</Badge>;
}
