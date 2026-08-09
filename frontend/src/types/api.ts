export type ApiError = {
  detail?: string | { status?: string; dependencies?: DependencyHealth[] };
};

export type UserResponse = {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ManagedUser = UserResponse;

export type CreateUserRequest = {
  email: string;
  password: string;
  is_active?: boolean;
};

export type UpdateUserActivationRequest = {
  is_active: boolean;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type DocumentSummary = {
  id: number;
  filename: string;
  file_type: string;
  storage_path: string;
  file_hash: string;
  status: string;
  created_at: string;
  updated_at: string;
  chunk_count: number;
};

export type DocumentChunkDetail = {
  id: number;
  qdrant_point_id: string;
  chunk_index: number;
  page_number: number | null;
  start_char: number;
  end_char: number;
  created_at: string;
};

export type DocumentDetail = DocumentSummary & {
  chunks: DocumentChunkDetail[];
};

export type IngestResponse = {
  document_id: number;
  filename: string;
  file_type: string;
  storage_path: string;
  file_hash: string;
  status: string;
  extracted_blocks: number;
  chunks: number;
  embeddings: number;
  collection_name: string;
  stored_vectors: number;
  saved_chunks: number;
  vector_size: number | null;
};

export type DeleteDocumentResponse = {
  document_id: number;
  deleted_vectors: number;
  deleted_metadata: boolean;
  deleted_file: boolean;
  cleanup_warning: string | null;
};

export type ReindexDocumentResponse = {
  document_id: number;
  status: string;
  chunks: number;
  stored_vectors: number;
  replaced_vectors: number;
  cleanup_warning: string | null;
};

export type DocumentPermissionResponse = {
  id: number;
  document_id: number;
  user_id: number;
  created_at: string;
  updated_at: string;
};

export type RevokeDocumentPermissionResponse = {
  document_id: number;
  user_id: number;
  revoked: boolean;
};

export type CodeIngestRequest = {
  repo_url: string;
  branch: string;
  include_globs?: string[];
  exclude_globs?: string[];
};

export type CodeIngestResponse = {
  repository_id: number;
  repo_name: string;
  repo_url: string;
  branch: string;
  commit_sha: string;
  storage_path: string;
  status: string;
  files: number;
  chunks: number;
  embeddings: number;
  collection_name: string;
  stored_vectors: number;
  saved_chunks: number;
  vector_size: number | null;
};

export type TraceSource = {
  filename?: string | null;
  source_path?: string | null;
  page_number?: number | null;
  chunk_index?: number | null;
  score?: number | null;
  vector_score?: number | null;
  bm25_score?: number | null;
  fusion_score?: number | null;
  reranker_score?: number | null;
  content_type?: "document" | "code";
  language?: string | null;
  symbol_name?: string | null;
  symbol_kind?: string | null;
  start_line?: number | null;
  end_line?: number | null;
};

export type TraceRecord = {
  id: number;
  request_id: string;
  user_id: number | null;
  question: string;
  retrieval_mode: string;
  retrieval_time_ms: number | null;
  reranker_time_ms: number | null;
  generation_time_ms: number | null;
  total_time_ms: number | null;
  model_name: string;
  retrieved_count: number;
  status: string;
  error_message: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  retrieved_sources: TraceSource[];
  created_at: string;
};

export type TraceListResponse = {
  items: TraceRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type FeedbackRecord = {
  id: number;
  trace_id: number;
  request_id: string;
  user_id: number;
  rating: number;
  comment: string | null;
  created_at: string;
};

export type FeedbackListResponse = {
  items: FeedbackRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type AnalyticsFilters = {
  user_id: number | null;
  status: string | null;
  retrieval_mode: string | null;
  created_from: string | null;
  created_to: string | null;
};

export type RatingDistributionItem = {
  rating: number;
  count: number;
  rate: number | null;
};

export type RetrievalModeDistributionItem = {
  retrieval_mode: string;
  count: number;
  rate: number | null;
  average_latency_ms: number | null;
};

export type TopFailedDocument = {
  filename: string;
  failure_count: number;
  average_retrieval_score: number | null;
  source_path: string | null;
};

export type AnalyticsSummaryResponse = {
  total_questions: number;
  average_latency_ms: number | null;
  feedback_count: number;
  average_user_rating: number | null;
  bad_answer_rate: number | null;
  good_answer_rate: number | null;
  filters: AnalyticsFilters;
};

export type AnalyticsFeedbackResponse = {
  feedback_count: number;
  average_user_rating: number | null;
  bad_answer_rate: number | null;
  good_answer_rate: number | null;
  rating_distribution: RatingDistributionItem[];
  filters: AnalyticsFilters;
};

export type AnalyticsRetrievalResponse = {
  total_questions: number;
  retrieval_mode_distribution: RetrievalModeDistributionItem[];
  top_failed_documents: TopFailedDocument[];
  filters: AnalyticsFilters;
};

export type DependencyHealth = {
  name: string;
  status: string;
  latency_ms: number | null;
  detail: string | null;
};

export type HealthResponse = {
  status: string;
  dependencies: DependencyHealth[];
};

export type AnalyticsQueryParams = {
  user_id?: number;
  status?: string;
  retrieval_mode?: string;
  created_from?: string;
  created_to?: string;
};

export type PaginationParams = {
  limit?: number;
  offset?: number;
};

export type UnavailableCapability = {
  title: string;
  reason: string;
};
