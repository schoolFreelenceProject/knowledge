import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, UserPlus } from "lucide-react";
import { useState } from "react";

import { getErrorMessage } from "../api/client";
import {
  grantDocumentPermission,
  listDocumentPermissions,
  listDocuments,
  revokeDocumentPermission,
} from "../api/documents";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import { UnavailableState } from "../components/ui/UnavailableState";
import { formatDateTime } from "../utils/format";

export function UsersPermissionsPage() {
  const queryClient = useQueryClient();
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [userId, setUserId] = useState("");

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const permissionsQuery = useQuery({
    queryKey: ["documents", documentId, "permissions"],
    queryFn: () => listDocumentPermissions(documentId as number),
    enabled: documentId !== null,
  });

  const grantMutation = useMutation({
    mutationFn: (targetUserId: number) =>
      grantDocumentPermission(documentId as number, targetUserId),
    onSuccess: async () => {
      setUserId("");
      await queryClient.invalidateQueries({
        queryKey: ["documents", documentId, "permissions"],
      });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (targetUserId: number) =>
      revokeDocumentPermission(documentId as number, targetUserId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["documents", documentId, "permissions"],
      });
    },
  });

  const mutationError = grantMutation.error || revokeMutation.error;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Document Permissions"
        description="Manage user-document access with the current ACL model."
      />

      <section className="grid gap-4 lg:grid-cols-2">
        <UnavailableState
          title="Repository permissions unavailable"
          reason="The current API does not expose code repository permission management endpoints."
        />
        <UnavailableState
          title="Roles unavailable"
          reason="The current ACL scope is user-document access only."
        />
      </section>

      {mutationError ? (
        <ErrorState
          title="Permission update failed"
          detail={getErrorMessage(mutationError, "Unable to update permissions.")}
        />
      ) : null}

      <Panel>
        <PanelHeader
          title="Document Permissions"
          description="Use a known user ID to grant or revoke access."
        />
        <div className="grid gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-3">
            <label className="block space-y-1">
              <span className="form-label">Document</span>
              <select
                className="form-input"
                value={documentId ?? ""}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setDocumentId(Number.isInteger(value) && value > 0 ? value : null);
                }}
              >
                <option value="">Select document</option>
                {(documentsQuery.data ?? []).map((document) => (
                  <option key={document.id} value={document.id}>
                    #{document.id} {document.filename}
                  </option>
                ))}
              </select>
            </label>
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const targetUserId = Number(userId);
                if (documentId && Number.isInteger(targetUserId) && targetUserId > 0) {
                  grantMutation.mutate(targetUserId);
                }
              }}
            >
              <input
                className="form-input"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                placeholder="User ID"
                inputMode="numeric"
              />
              <Button
                type="submit"
                icon={<UserPlus className="h-4 w-4" />}
                isLoading={grantMutation.isPending}
                disabled={!documentId}
              >
                Grant
              </Button>
            </form>
          </div>

          <div>
            {documentsQuery.isLoading ? <LoadingState label="Loading documents" /> : null}
            {documentId === null && !documentsQuery.isLoading ? (
              <EmptyState title="Select a document to view permissions" />
            ) : null}
            {permissionsQuery.isLoading ? <LoadingState label="Loading permissions" /> : null}
            {permissionsQuery.error ? (
              <ErrorState
                title="Permission lookup failed"
                detail={getErrorMessage(
                  permissionsQuery.error,
                  "Unable to load document permissions.",
                )}
              />
            ) : null}
            {(permissionsQuery.data ?? []).length > 0 ? (
              <div className="table-shell">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>User ID</th>
                      <th>Granted</th>
                      <th>Updated</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {(permissionsQuery.data ?? []).map((permission) => (
                      <tr key={permission.id}>
                        <td className="font-medium">
                          <span className="inline-flex items-center gap-2">
                            <ShieldCheck className="h-4 w-4 text-muted" />
                            {permission.user_id}
                          </span>
                        </td>
                        <td>{formatDateTime(permission.created_at)}</td>
                        <td>{formatDateTime(permission.updated_at)}</td>
                        <td>
                          <Button
                            variant="ghost"
                            onClick={() => revokeMutation.mutate(permission.user_id)}
                            isLoading={revokeMutation.isPending}
                          >
                            Revoke
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : documentId !== null && !permissionsQuery.isLoading && !permissionsQuery.error ? (
              <EmptyState title="No permissions returned for this document" />
            ) : null}
          </div>
        </div>
      </Panel>
    </div>
  );
}
