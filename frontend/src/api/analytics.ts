import { apiClient } from "./client";
import type {
  AnalyticsFeedbackResponse,
  AnalyticsQueryParams,
  AnalyticsRetrievalResponse,
  AnalyticsSummaryResponse,
} from "../types/api";

export async function getAnalyticsSummary(
  params: AnalyticsQueryParams = {},
): Promise<AnalyticsSummaryResponse> {
  const response = await apiClient.get<AnalyticsSummaryResponse>(
    "/api/analytics/summary",
    { params },
  );
  return response.data;
}

export async function getFeedbackAnalytics(
  params: AnalyticsQueryParams = {},
): Promise<AnalyticsFeedbackResponse> {
  const response = await apiClient.get<AnalyticsFeedbackResponse>(
    "/api/analytics/feedback",
    { params },
  );
  return response.data;
}

export async function getRetrievalAnalytics(
  params: AnalyticsQueryParams & { top_failed_limit?: number } = {},
): Promise<AnalyticsRetrievalResponse> {
  const response = await apiClient.get<AnalyticsRetrievalResponse>(
    "/api/analytics/retrieval",
    { params },
  );
  return response.data;
}
