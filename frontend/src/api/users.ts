import { apiClient } from "./client";
import type {
  CreateUserRequest,
  ManagedUser,
  UpdateUserActivationRequest,
} from "../types/api";


export async function listUsers(): Promise<ManagedUser[]> {
  const response = await apiClient.get<ManagedUser[]>("/api/admin/users");
  return response.data;
}


export async function createUser(
  request: CreateUserRequest,
): Promise<ManagedUser> {
  const response = await apiClient.post<ManagedUser>(
    "/api/admin/users",
    request,
  );
  return response.data;
}


export async function updateUserActivation(
  userId: number,
  request: UpdateUserActivationRequest,
): Promise<ManagedUser> {
  const response = await apiClient.patch<ManagedUser>(
    `/api/admin/users/${userId}/activation`,
    request,
  );
  return response.data;
}
