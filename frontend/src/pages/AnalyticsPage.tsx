import { useQuery } from "@tanstack/react-query";
import { Filter } from "lucide-react";
import { useMemo, useState } from "react";

import {
  getAnalyticsSummary,
  getFeedbackAnalytics,
  getRetrievalAnalytics,
} from "../api/analytics";
import { getErrorMessage } from "../api/client";
import { listTraces } from "../api/traces";
import { LatencyChart } from "../components/charts/LatencyChart";
import { RatingDistributionChart } from "../components/charts/RatingDistributionChart";
import { RetrievalModeChart } from "../components/charts/RetrievalModeChart";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import { StatCard } from "../components/ui/StatCard";
import { formatMs, formatNumber, formatRate, formatRating, formatScore } from "../utils/format";
import { compactParams } from "../utils/params";

export function AnalyticsPage() {
  const [status, setStatus] = useState("");
  const [retrievalMode, setRetrievalMode] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [appliedVersion, setAppliedVersion] = useState(0);

  const params = useMemo(
    () =>
      compactParams({
        status: status || undefined,
        retrieval_mode: retrievalMode || undefined,
        created_from: createdFrom || undefined,
        created_to: createdTo || undefined,
      }),
    [appliedVersion, createdFrom, createdTo, retrievalMode, status],
  );

  const summaryQuery = useQuery({
    queryKey: ["analytics", "summary", params],
    queryFn: () => getAnalyticsSummary(params),
  });
  const feedbackQuery = useQuery({
    queryKey: ["analytics", "feedback", params],
    queryFn: () => getFeedbackAnalytics(params),
  });
  const retrievalQuery = useQuery({
    queryKey: ["analytics", "retrieval", params],
    queryFn: () => getRetrievalAnalytics({ ...params, top_failed_limit: 10 }),
  });
  const tracesQuery = useQuery({
    queryKey: ["traces", "latency", params],
    queryFn: () => listTraces({ ...params, limit: 20, offset: 0 }),
  });

  const error =
    summaryQuery.error || feedbackQuery.error || retrievalQuery.error || tracesQuery.error;
  const isLoading =
    summaryQuery.isLoading ||
    feedbackQuery.isLoading ||
    retrievalQuery.isLoading ||
    tracesQuery.isLoading;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics Dashboard"
        description="Analyze retrieval behavior, latency, feedback, and failed documents."
      />

      <Panel>
        <PanelHeader title="Filters" />
        <form
          className="grid gap-3 p-4 md:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            setAppliedVersion((value) => value + 1);
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
            type="datetime-local"
            value={createdFrom}
            onChange={(event) => setCreatedFrom(event.target.value)}
          />
          <input
            className="form-input"
            type="datetime-local"
            value={createdTo}
            onChange={(event) => setCreatedTo(event.target.value)}
          />
          <Button type="submit" icon={<Filter className="h-4 w-4" />}>Apply</Button>
        </form>
      </Panel>

      {isLoading ? <LoadingState label="Loading analytics" /> : null}
      {error ? (
        <ErrorState
          title="Analytics failed"
          detail={getErrorMessage(error, "Unable to load analytics.")}
        />
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Questions" value={formatNumber(summaryQuery.data?.total_questions)} />
        <StatCard label="Average Latency" value={formatMs(summaryQuery.data?.average_latency_ms)} />
        <StatCard label="Average Rating" value={formatRating(summaryQuery.data?.average_user_rating)} />
        <StatCard label="Bad Answer Rate" value={formatRate(summaryQuery.data?.bad_answer_rate)} />
        <StatCard label="Feedback Count" value={formatNumber(summaryQuery.data?.feedback_count)} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Panel>
          <PanelHeader title="Retrieval Mode Distribution" />
          <div className="p-4">
            <RetrievalModeChart data={retrievalQuery.data?.retrieval_mode_distribution ?? []} />
          </div>
        </Panel>
        <Panel>
          <PanelHeader title="Rating Distribution" />
          <div className="p-4">
            <RatingDistributionChart data={feedbackQuery.data?.rating_distribution ?? []} />
          </div>
        </Panel>
        <Panel>
          <PanelHeader title="Recent Latency" />
          <div className="p-4">
            <LatencyChart data={tracesQuery.data?.items ?? []} />
          </div>
        </Panel>
        <Panel>
          <PanelHeader title="Top Failed Documents" />
          {(retrievalQuery.data?.top_failed_documents.length ?? 0) > 0 ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Failures</th>
                    <th>Average Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {retrievalQuery.data?.top_failed_documents.map((document) => (
                    <tr key={`${document.filename}-${document.source_path ?? ""}`}>
                      <td className="max-w-72 truncate">{document.filename}</td>
                      <td>{formatNumber(document.failure_count)}</td>
                      <td>{formatScore(document.average_retrieval_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4">
              <EmptyState title="No failed document data yet" />
            </div>
          )}
        </Panel>
      </section>
    </div>
  );
}
