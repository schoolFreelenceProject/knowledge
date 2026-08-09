import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { getErrorMessage } from "../api/client";
import { getTrace, listTraces } from "../api/traces";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import type { TraceRecord, TraceSource } from "../types/api";
import { compactParams } from "../utils/params";
import { formatDateTime, formatMs, formatNumber, formatScore } from "../utils/format";

const PAGE_SIZE = 25;

export function TracesPage() {
  const [status, setStatus] = useState("");
  const [retrievalMode, setRetrievalMode] = useState("");
  const [userId, setUserId] = useState("");
  const [requestId, setRequestId] = useState("");
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [offset, setOffset] = useState(0);

  const params = useMemo(
    () =>
      compactParams({
        limit: PAGE_SIZE,
        offset,
        status: status || undefined,
        retrieval_mode: retrievalMode || undefined,
        user_id: userId ? Number(userId) : undefined,
      }),
    [offset, retrievalMode, status, userId],
  );

  const tracesQuery = useQuery({
    queryKey: ["traces", params],
    queryFn: () => listTraces(params),
  });

  const detailQuery = useQuery({
    queryKey: ["traces", "detail", selectedRequestId],
    queryFn: () => getTrace(selectedRequestId),
    enabled: Boolean(selectedRequestId),
  });

  const selectedTrace =
    detailQuery.data ||
    tracesQuery.data?.items.find((trace) => trace.request_id === selectedRequestId) ||
    null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Traces"
        description="Inspect RAG request history, timing, and retrieved source details."
      />

      <Panel>
        <PanelHeader title="Filters" />
        <form
          className="grid gap-3 p-4 md:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            setSelectedRequestId(requestId.trim());
          }}
        >
          <select className="form-input" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All status</option>
            <option value="SUCCESS">Success</option>
            <option value="ERROR">Error</option>
            <option value="PROCESSING">Processing</option>
          </select>
          <select
            className="form-input"
            value={retrievalMode}
            onChange={(event) => setRetrievalMode(event.target.value)}
          >
            <option value="">All modes</option>
            <option value="vector">Vector</option>
            <option value="bm25">BM25</option>
            <option value="hybrid">Hybrid</option>
          </select>
          <input
            className="form-input"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            placeholder="User ID"
            inputMode="numeric"
          />
          <input
            className="form-input"
            value={requestId}
            onChange={(event) => setRequestId(event.target.value)}
            placeholder="Request ID"
          />
          <Button type="submit" icon={<Search className="h-4 w-4" />}>
            Open
          </Button>
        </form>
      </Panel>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(420px,0.9fr)]">
        <Panel>
          <PanelHeader
            title="Request History"
            actions={
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  disabled={(tracesQuery.data?.items.length ?? 0) < PAGE_SIZE}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            }
          />
          {tracesQuery.isLoading ? <div className="p-4"><LoadingState /></div> : null}
          {tracesQuery.error ? (
            <div className="p-4">
              <ErrorState
                title="Trace lookup failed"
                detail={getErrorMessage(tracesQuery.error, "Unable to load traces.")}
              />
            </div>
          ) : null}
          {!tracesQuery.isLoading && !(tracesQuery.data?.items.length ?? 0) ? (
            <div className="p-4">
              <EmptyState title="No traces found" />
            </div>
          ) : null}
          {(tracesQuery.data?.items.length ?? 0) > 0 ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Request</th>
                    <th>Status</th>
                    <th>Mode</th>
                    <th>Latency</th>
                    <th>Sources</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {tracesQuery.data?.items.map((trace) => (
                    <tr
                      key={trace.id}
                      className="cursor-pointer hover:bg-slate-50"
                      onClick={() => setSelectedRequestId(trace.request_id)}
                    >
                      <td className="max-w-56 truncate font-mono text-xs">{trace.request_id}</td>
                      <td><TraceStatusBadge status={trace.status} /></td>
                      <td>{trace.retrieval_mode}</td>
                      <td>{formatMs(trace.total_time_ms)}</td>
                      <td>{formatNumber(trace.retrieved_count)}</td>
                      <td>{formatDateTime(trace.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Panel>

        <Panel>
          <PanelHeader title="Trace Detail" />
          <div className="space-y-4 p-4">
            {!selectedRequestId ? <EmptyState title="Select a trace" /> : null}
            {detailQuery.isLoading ? <LoadingState label="Loading trace detail" /> : null}
            {detailQuery.error ? (
              <ErrorState
                title="Trace detail failed"
                detail={getErrorMessage(detailQuery.error, "Unable to load trace detail.")}
              />
            ) : null}
            {selectedTrace ? <TraceDetail trace={selectedTrace} /> : null}
          </div>
        </Panel>
      </section>
    </div>
  );
}

function TraceDetail({ trace }: { trace: TraceRecord }) {
  return (
    <>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Detail label="Request ID" value={trace.request_id} />
        <Detail label="User ID" value={trace.user_id?.toString() ?? "-"} />
        <Detail label="Model" value={trace.model_name} />
        <Detail label="Mode" value={trace.retrieval_mode} />
        <Detail label="Retrieval" value={formatMs(trace.retrieval_time_ms)} />
        <Detail label="Reranker" value={formatMs(trace.reranker_time_ms)} />
        <Detail label="Generation" value={formatMs(trace.generation_time_ms)} />
        <Detail label="Total" value={formatMs(trace.total_time_ms)} />
      </dl>
      <section>
        <h3 className="mb-2 text-sm font-semibold">Question</h3>
        <p className="rounded-md border border-border bg-slate-50 p-3 text-sm">{trace.question}</p>
      </section>
      {trace.error_message ? (
        <ErrorState title="Trace error" detail={trace.error_message} />
      ) : null}
      <section>
        <h3 className="mb-2 text-sm font-semibold">Retrieved Sources</h3>
        <div className="space-y-2">
          {trace.retrieved_sources.length ? (
            trace.retrieved_sources.map((source, index) => (
              <SourceRow key={`${source.filename}-${index}`} source={source} index={index + 1} />
            ))
          ) : (
            <p className="text-sm text-muted">No retrieved sources recorded.</p>
          )}
        </div>
      </section>
    </>
  );
}

function SourceRow({ source, index }: { source: TraceSource; index: number }) {
  return (
    <div className="rounded-md border border-border p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate font-medium">
          {index}. {source.filename || source.source_path || "Unknown source"}
        </span>
        <span className="text-xs text-muted">{formatScore(source.score)}</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        chunk {source.chunk_index ?? "-"}
        {source.page_number ? ` / page ${source.page_number}` : ""}
        {source.content_type === "code" && source.symbol_name
          ? ` / ${source.symbol_name}`
          : ""}
      </p>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="form-label">{label}</dt>
      <dd className="mt-1 truncate text-ink">{value}</dd>
    </div>
  );
}

function TraceStatusBadge({ status }: { status: string }) {
  const tone = status === "SUCCESS" ? "success" : status === "ERROR" ? "danger" : "warning";
  return <Badge tone={tone}>{status}</Badge>;
}
