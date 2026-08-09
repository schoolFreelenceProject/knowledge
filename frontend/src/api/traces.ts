import { apiClient } from "./client";
import type { AnalyticsQueryParams, PaginationParams, TraceListResponse, TraceRecord } from "../types/api";

export async function listTraces(
  params: AnalyticsQueryParams & PaginationParams = {},
): Promise<TraceListResponse> {
  const response = await apiClient.get<TraceListResponse>("/api/traces", { params });
  return response.data;
}

export async function getTrace(requestId: string): Promise<TraceRecord> {
  const response = await apiClient.get<TraceRecord>(
    `/api/traces/${encodeURIComponent(requestId)}`,
  );
  return response.data;
}
