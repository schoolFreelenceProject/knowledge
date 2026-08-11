import { apiClient } from "./client";
import type {
  KnowledgeSearchRequest,
  KnowledgeSearchResponse,
} from "../types/api";

export async function searchKnowledge(
  request: KnowledgeSearchRequest,
): Promise<KnowledgeSearchResponse> {
  const response = await apiClient.post<KnowledgeSearchResponse>(
    "/api/knowledge/search",
    request,
  );
  return response.data;
}
