import { apiClient } from "./client";
import type {
  CodeRepositoryPermissionResponse,
  DocumentPermissionResponse,
  RevokeCodeRepositoryPermissionResponse,
  RevokeDocumentPermissionResponse,
} from "../types/api";

export async function listUserDocumentPermissions(
  userId: number,
): Promise<DocumentPermissionResponse[]> {
  const response = await apiClient.get<DocumentPermissionResponse[]>(
    `/api/admin/permissions/users/${userId}/documents`,
  );
  return response.data;
}

export async function grantUserDocumentPermission(
  userId: number,
  documentId: number,
): Promise<DocumentPermissionResponse> {
  const response = await apiClient.post<DocumentPermissionResponse>(
    `/api/admin/permissions/users/${userId}/documents`,
    { document_id: documentId },
  );
  return response.data;
}

export async function revokeUserDocumentPermission(
  userId: number,
  documentId: number,
): Promise<RevokeDocumentPermissionResponse> {
  const response = await apiClient.delete<RevokeDocumentPermissionResponse>(
    `/api/admin/permissions/users/${userId}/documents/${documentId}`,
  );
  return response.data;
}

export async function listDocumentUserPermissions(
  documentId: number,
): Promise<DocumentPermissionResponse[]> {
  const response = await apiClient.get<DocumentPermissionResponse[]>(
    `/api/admin/permissions/documents/${documentId}/users`,
  );
  return response.data;
}

export async function grantDocumentUserPermission(
  documentId: number,
  userId: number,
): Promise<DocumentPermissionResponse> {
  const response = await apiClient.post<DocumentPermissionResponse>(
    `/api/admin/permissions/documents/${documentId}/users`,
    { user_id: userId },
  );
  return response.data;
}

export async function revokeDocumentUserPermission(
  documentId: number,
  userId: number,
): Promise<RevokeDocumentPermissionResponse> {
  const response = await apiClient.delete<RevokeDocumentPermissionResponse>(
    `/api/admin/permissions/documents/${documentId}/users/${userId}`,
  );
  return response.data;
}

export async function listUserCodeRepositoryPermissions(
  userId: number,
): Promise<CodeRepositoryPermissionResponse[]> {
  const response = await apiClient.get<CodeRepositoryPermissionResponse[]>(
    `/api/admin/permissions/users/${userId}/code-repositories`,
  );
  return response.data;
}

export async function grantUserCodeRepositoryPermission(
  userId: number,
  repositoryId: number,
): Promise<CodeRepositoryPermissionResponse> {
  const response = await apiClient.post<CodeRepositoryPermissionResponse>(
    `/api/admin/permissions/users/${userId}/code-repositories`,
    { repository_id: repositoryId },
  );
  return response.data;
}

export async function revokeUserCodeRepositoryPermission(
  userId: number,
  repositoryId: number,
): Promise<RevokeCodeRepositoryPermissionResponse> {
  const response = await apiClient.delete<RevokeCodeRepositoryPermissionResponse>(
    `/api/admin/permissions/users/${userId}/code-repositories/${repositoryId}`,
  );
  return response.data;
}
