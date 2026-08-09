import { apiClient } from "./client";
import type { FeedbackListResponse, FeedbackRecord, PaginationParams } from "../types/api";

export type FeedbackQueryParams = PaginationParams & {
  user_id?: number;
  rating?: number;
  request_id?: string;
  created_from?: string;
  created_to?: string;
};

export async function listFeedback(
  params: FeedbackQueryParams = {},
): Promise<FeedbackListResponse> {
  const response = await apiClient.get<FeedbackListResponse>("/api/feedback", { params });
  return response.data;
}

export async function submitFeedback(
  requestId: string,
  rating: number,
  comment?: string,
): Promise<FeedbackRecord> {
  const response = await apiClient.post<FeedbackRecord>(
    `/api/traces/${encodeURIComponent(requestId)}/feedback`,
    { rating, comment },
  );
  return response.data;
}
