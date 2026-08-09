import { apiClient } from "./client";
import type { HealthResponse } from "../types/api";

export async function getReadiness(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>("/health/ready");
  return response.data;
}
