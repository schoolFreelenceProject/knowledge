import { apiClient } from "./client";
import type { LoginRequest, TokenResponse, UserResponse } from "../types/api";

export async function login(credentials: LoginRequest): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>("/api/auth/login", credentials);
  return response.data;
}

export async function register(credentials: LoginRequest): Promise<UserResponse> {
  const response = await apiClient.post<UserResponse>("/api/auth/register", credentials);
  return response.data;
}
