import { apiClient } from "./client";
import type { AxiosProgressEvent } from "axios";
import type {
  CodeIngestRequest,
  CodeIngestResponse,
  CodeRepositoryDetail,
  CodeRepositoryPermissionResponse,
  CodeRepositorySummary,
  DeleteCodeRepositoryResponse,
  ReindexCodeRepositoryResponse,
  RevokeCodeRepositoryPermissionResponse,
} from "../types/api";

export type CodeFolderUploadFile = {
  relativePath: string;
  file: File;
};

export async function ingestCodeRepository(
  request: CodeIngestRequest,
): Promise<CodeIngestResponse> {
  const response = await apiClient.post<CodeIngestResponse>("/api/code/ingest", request);
  return response.data;
}

export async function uploadCodeFolder(
  folderName: string,
  files: CodeFolderUploadFile[],
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<CodeIngestResponse> {
  const formData = new FormData();
  formData.append("folder_name", folderName);
  files.forEach((item) => {
    formData.append("relative_paths", item.relativePath);
    formData.append("files", item.file, item.relativePath);
  });

  const response = await apiClient.post<CodeIngestResponse>(
    "/api/code/ingest/folder",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress,
    },
  );
  return response.data;
}

export async function listCodeRepositories(): Promise<CodeRepositorySummary[]> {
  const response = await apiClient.get<CodeRepositorySummary[]>("/api/code/repositories");
  return response.data;
}

export async function getCodeRepository(
  repositoryId: number,
): Promise<CodeRepositoryDetail> {
  const response = await apiClient.get<CodeRepositoryDetail>(
    `/api/code/repositories/${repositoryId}`,
  );
  return response.data;
}

export async function deleteCodeRepository(
  repositoryId: number,
): Promise<DeleteCodeRepositoryResponse> {
  const response = await apiClient.delete<DeleteCodeRepositoryResponse>(
    `/api/code/repositories/${repositoryId}`,
  );
  return response.data;
}

export async function reindexCodeRepository(
  repositoryId: number,
): Promise<ReindexCodeRepositoryResponse> {
  const response = await apiClient.post<ReindexCodeRepositoryResponse>(
    `/api/code/repositories/${repositoryId}/reindex`,
  );
  return response.data;
}

export async function listCodeRepositoryPermissions(
  repositoryId: number,
): Promise<CodeRepositoryPermissionResponse[]> {
  const response = await apiClient.get<CodeRepositoryPermissionResponse[]>(
    `/api/admin/permissions/code-repositories/${repositoryId}/users`,
  );
  return response.data;
}

export async function grantCodeRepositoryPermission(
  repositoryId: number,
  userId: number,
): Promise<CodeRepositoryPermissionResponse> {
  const response = await apiClient.post<CodeRepositoryPermissionResponse>(
    `/api/admin/permissions/code-repositories/${repositoryId}/users`,
    { user_id: userId },
  );
  return response.data;
}

export async function revokeCodeRepositoryPermission(
  repositoryId: number,
  userId: number,
): Promise<RevokeCodeRepositoryPermissionResponse> {
  const response = await apiClient.delete<RevokeCodeRepositoryPermissionResponse>(
    `/api/admin/permissions/code-repositories/${repositoryId}/users/${userId}`,
  );
  return response.data;
}
