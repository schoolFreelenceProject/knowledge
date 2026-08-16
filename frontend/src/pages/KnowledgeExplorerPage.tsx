import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, Code2, FileSearch, Search } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";

import { getErrorMessage } from "../api/client";
import { listCodeRepositories } from "../api/code";
import { listDocuments } from "../api/documents";
import { searchKnowledge } from "../api/knowledge";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import type {
  KnowledgeSearchMode,
  KnowledgeSearchResult,
} from "../types/api";
import { formatNumber, formatScore } from "../utils/format";

const LANGUAGE_OPTIONS = [
  "python",
  "javascript",
  "typescript",
  "tsx",
  "java",
  "go",
  "rust",
  "c",
  "cpp",
  "php",
];

export function KnowledgeExplorerPage() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<KnowledgeSearchMode>("all");
  const [topK, setTopK] = useState(8);
  const [documentId, setDocumentId] = useState("");
  const [repositoryId, setRepositoryId] = useState("");
  const [language, setLanguage] = useState("");
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });
  const repositoriesQuery = useQuery({
    queryKey: ["code-repositories"],
    queryFn: listCodeRepositories,
  });

  const searchMutation = useMutation({
    mutationFn: searchKnowledge,
    onSuccess: (response) => {
      setSelectedPointId(response.results[0]?.point_id ?? null);
    },
  });

  const response = searchMutation.data;
  const results = response?.results ?? [];
  const selectedResult = useMemo(
    () => results.find((result) => result.point_id === selectedPointId) ?? results[0],
    [results, selectedPointId],
  );

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      return;
    }

    searchMutation.mutate({
      query: trimmedQuery,
      mode,
      top_k: topK,
      document_ids: documentId && mode !== "code" ? [Number(documentId)] : [],
      repository_ids: repositoryId && mode !== "documents" ? [Number(repositoryId)] : [],
      languages: language && mode !== "documents" ? [language] : [],
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Explorer"
        description="Search indexed documents and code with source-level retrieval detail."
      />

      {searchMutation.error ? (
        <ErrorState
          title="Knowledge search failed"
          detail={getErrorMessage(searchMutation.error, "Unable to search knowledge.")}
        />
      ) : null}

      <Panel>
        <PanelHeader
          title="Search"
          actions={
            response ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="info">{response.retrieval_mode}</Badge>
                <Badge>{formatNumber(results.length)} results</Badge>
              </div>
            ) : null
          }
        />
        <form className="space-y-4 p-4" onSubmit={submitSearch}>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
              <input
                className="form-input w-full pl-9"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search knowledge"
                required
              />
            </label>
            <Button
              type="submit"
              icon={<FileSearch className="h-4 w-4" />}
              isLoading={searchMutation.isPending}
            >
              Search
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div className="flex rounded-md border border-border bg-white p-1">
              {(["all", "documents", "code"] as KnowledgeSearchMode[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`h-8 rounded px-3 text-sm font-medium ${
                    mode === item ? "bg-accent text-white" : "text-muted hover:bg-slate-100"
                  }`}
                  onClick={() => setMode(item)}
                >
                  {modeLabel(item)}
                </button>
              ))}
            </div>

            <label className="space-y-1">
              <span className="form-label">Top K</span>
              <input
                className="form-input w-24"
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </label>

            {mode !== "code" ? (
              <label className="min-w-56 space-y-1">
                <span className="form-label">Document Source</span>
                <select
                  className="form-input w-full"
                  value={documentId}
                  onChange={(event) => setDocumentId(event.target.value)}
                >
                  <option value="">All documents</option>
                  {(documentsQuery.data ?? []).map((document) => (
                    <option key={document.id} value={document.id}>
                      #{document.id} {document.filename}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {mode !== "documents" ? (
              <>
                <label className="min-w-56 space-y-1">
                  <span className="form-label">Code Source</span>
                  <select
                    className="form-input w-full"
                    value={repositoryId}
                    onChange={(event) => setRepositoryId(event.target.value)}
                  >
                    <option value="">All code sources</option>
                    {(repositoriesQuery.data ?? []).map((repository) => (
                      <option key={repository.id} value={repository.id}>
                        #{repository.id} {repository.repo_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="form-label">Language</span>
                  <select
                    className="form-input w-40"
                    value={language}
                    onChange={(event) => setLanguage(event.target.value)}
                  >
                    <option value="">All languages</option>
                    {LANGUAGE_OPTIONS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : null}
          </div>
        </form>
      </Panel>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(420px,0.9fr)]">
        <Panel>
          <PanelHeader title="Results" />
          <div className="space-y-3 p-4">
            {searchMutation.isPending ? <LoadingState label="Searching knowledge" /> : null}
            {!searchMutation.isPending && response && results.length === 0 ? (
              <EmptyState title="No matching knowledge" />
            ) : null}
            {!response && !searchMutation.isPending ? (
              <EmptyState title="No search results" />
            ) : null}
            {results.map((result) => (
              <SearchResultItem
                key={result.point_id}
                result={result}
                selected={result.point_id === selectedResult?.point_id}
                onSelect={() => setSelectedPointId(result.point_id)}
              />
            ))}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Source Inspection" />
          <div className="p-4">
            {selectedResult ? (
              <SourceInspection result={selectedResult} />
            ) : (
              <EmptyState title="Select a result" />
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}

function SearchResultItem({
  result,
  selected,
  onSelect,
}: {
  result: KnowledgeSearchResult;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`block w-full rounded-md border p-3 text-left transition ${
        selected ? "border-blue-300 bg-blue-50" : "border-border hover:bg-slate-50"
      }`}
      onClick={onSelect}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {result.content_type === "code" ? (
            <Code2 className="h-4 w-4 shrink-0 text-muted" />
          ) : (
            <BookOpen className="h-4 w-4 shrink-0 text-muted" />
          )}
          <span className="truncate text-sm font-semibold">{result.title}</span>
        </div>
        <Badge tone={result.content_type === "code" ? "info" : "success"}>
          {formatScore(result.score)}
        </Badge>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
        {result.content_type === "code" ? (
          <>
            <span>{result.language ?? "code"}</span>
            <span>{lineRange(result)}</span>
            {result.symbol_name ? <span>{result.symbol_name}</span> : null}
          </>
        ) : (
          <>
            <span>{result.filename}</span>
            <span>Chunk {result.chunk_index}</span>
            <span>{documentLocation(result)}</span>
          </>
        )}
      </div>
      <Preview result={result} className="mt-3" />
    </button>
  );
}

function SourceInspection({ result }: { result: KnowledgeSearchResult }) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={result.content_type === "code" ? "info" : "success"}>
            {result.content_type === "code" ? "Code" : "Document"}
          </Badge>
          <Badge>{formatScore(result.score)}</Badge>
          {result.reranker_score !== null ? (
            <Badge tone="warning">Rerank {formatScore(result.reranker_score)}</Badge>
          ) : null}
        </div>
        <h3 className="text-sm font-semibold text-ink">{result.title}</h3>
        <p className="text-xs text-muted">{sourceDetail(result)}</p>
      </div>

      <Preview result={result} />

      <div>
        <h4 className="mb-2 text-sm font-semibold">Context</h4>
        <pre className="max-h-[460px] overflow-auto rounded-md border border-border bg-slate-950 p-3 text-xs leading-5 text-slate-50">
          {result.inspection.text}
        </pre>
      </div>
    </div>
  );
}

function Preview({
  result,
  className = "",
}: {
  result: KnowledgeSearchResult;
  className?: string;
}) {
  if (result.content_type === "code") {
    return (
      <pre
        className={`max-h-40 overflow-auto rounded-md bg-slate-100 p-3 text-xs leading-5 text-slate-800 ${className}`}
      >
        {result.preview}
      </pre>
    );
  }

  return <p className={`text-sm leading-6 text-slate-700 ${className}`}>{result.preview}</p>;
}

function modeLabel(mode: KnowledgeSearchMode): string {
  if (mode === "documents") {
    return "Documents";
  }
  if (mode === "code") {
    return "Code";
  }
  return "All";
}

function lineRange(result: KnowledgeSearchResult): string {
  if (!result.start_line || !result.end_line) {
    return "Lines unknown";
  }

  return `Lines ${result.start_line}-${result.end_line}`;
}

function sourceDetail(result: KnowledgeSearchResult): string {
  if (result.content_type === "code") {
    const symbol = result.symbol_name
      ? `${result.symbol_kind ?? "symbol"} ${result.symbol_name}`
      : "file chunk";
    return `${result.repo_name ?? "Code source"} / ${result.file_path ?? ""} / ${symbol} / ${lineRange(result)}`;
  }

  return `${result.filename ?? "Document"} / Chunk ${result.chunk_index} / ${documentLocation(result)}`;
}

function documentLocation(result: KnowledgeSearchResult): string {
  if (result.page_number) {
    return `Page ${result.page_number}`;
  }
  if (result.sheet_name) {
    const range = result.cell_range ? ` ${result.cell_range}` : "";
    return `${result.sheet_name}${range}`;
  }
  if (result.slide_number) {
    const title = result.slide_title ? `: ${result.slide_title}` : "";
    return `Slide ${result.slide_number}${title}`;
  }
  if (result.heading_path || result.section_heading) {
    return result.heading_path ?? result.section_heading ?? "Document section";
  }
  return "Document section";
}
