import type { AxiosProgressEvent } from "axios";

import { apiClient } from "./client";
import type {
  DeleteDocumentResponse,
  DocumentDetail,
  DocumentPermissionResponse,
  DocumentSummary,
  FolderIngestResponse,
  IngestResponse,
  ReindexDocumentResponse,
  RevokeDocumentPermissionResponse,
} from "../types/api";

export type FolderUploadFile = {
  file: File;
  relativePath: string;
};

export async function listDocuments(): Promise<DocumentSummary[]> {
  const response = await apiClient.get<DocumentSummary[]>("/api/documents");
  return response.data;
}

export async function getDocument(documentId: number): Promise<DocumentDetail> {
  const response = await apiClient.get<DocumentDetail>(`/api/documents/${documentId}`);
  return response.data;
}

export async function uploadDocument(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<IngestResponse>("/api/ingest", formData);
  return response.data;
}

export async function uploadDocumentFolder(
  folderName: string,
  files: FolderUploadFile[],
  onUploadProgress?: (progressEvent: AxiosProgressEvent) => void,
): Promise<FolderIngestResponse> {
  const formData = new FormData();
  formData.append("folder_name", folderName);
  for (const item of files) {
    formData.append("relative_paths", item.relativePath);
    formData.append("files", item.file, item.relativePath.split("/").pop() || item.file.name);
  }

  const response = await apiClient.post<FolderIngestResponse>(
    "/api/ingest/folder",
    formData,
    { onUploadProgress },
  );
  return response.data;
}

export async function deleteDocument(documentId: number): Promise<DeleteDocumentResponse> {
  const response = await apiClient.delete<DeleteDocumentResponse>(
    `/api/documents/${documentId}`,
  );
  return response.data;
}

export async function reindexDocument(documentId: number): Promise<ReindexDocumentResponse> {
  const response = await apiClient.post<ReindexDocumentResponse>(
    `/api/documents/${documentId}/reindex`,
  );
  return response.data;
}

export async function listDocumentPermissions(
  documentId: number,
): Promise<DocumentPermissionResponse[]> {
  const response = await apiClient.get<DocumentPermissionResponse[]>(
    `/api/documents/${documentId}/permissions`,
  );
  return response.data;
}

export async function grantDocumentPermission(
  documentId: number,
  userId: number,
): Promise<DocumentPermissionResponse> {
  const response = await apiClient.post<DocumentPermissionResponse>(
    `/api/documents/${documentId}/permissions`,
    { user_id: userId },
  );
  return response.data;
}

export async function revokeDocumentPermission(
  documentId: number,
  userId: number,
): Promise<RevokeDocumentPermissionResponse> {
  const response = await apiClient.delete<RevokeDocumentPermissionResponse>(
    `/api/documents/${documentId}/permissions/${userId}`,
  );
  return response.data;
}
