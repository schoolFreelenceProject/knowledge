import { apiClient } from "./client";
import type { CodeIngestRequest, CodeIngestResponse } from "../types/api";

export async function ingestCodeRepository(
  request: CodeIngestRequest,
): Promise<CodeIngestResponse> {
  const response = await apiClient.post<CodeIngestResponse>("/api/code/ingest", request);
  return response.data;
}
